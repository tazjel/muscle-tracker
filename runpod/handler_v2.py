"""
RunPod Cinematic Handler v6.0 — Gaussian Splatting & MPFB2 Alignment.

Upgraded Actions:
1. 'hmr': (Legacy) SMPL shape estimation from photos.
2. 'rembg': (Legacy) Background removal / masking.
3. 'dsine': (Legacy) High-fidelity normal map estimation.
4. 'pbr_textures': (Legacy) Vectorized roughness/AO generation.
5. 'train_splat': (NEW) Video -> .spz 3DGS training (7-10 mins).
6. 'anchor_splat': (NEW) Bind Gaussians to MPFB2 mesh vertices.
7. 'bake_cinematic': (NEW) Neural detail -> PBR Texture Baking.
"""
import runpod
import numpy as np
import cv2
import base64
import logging
import os
import torch
import io
import sys
import types
import subprocess
import json
import shutil
import tempfile

# Add project root to path for core imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.densepose_infer import predict_iuv
from core.texture_bake import bake_from_photos_nn, build_seam_mask, smooth_seam

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('runpod_cinematic')

# ── Constants & Anatomical Mappings ───────────────────────────────────────

# Default regional roughness values (0.0=shiny, 1.0=matte)
_REGION_ROUGHNESS = {
    'face': 0.35, 'chest': 0.42, 'abs': 0.45, 'back': 0.48,
    'arm': 0.52, 'leg': 0.55, 'hand': 0.58, 'foot': 0.62,
    'default': 0.50
}

# SMPL part IDs to region names
_SMPL_PART_MAP = {
    0: 'default', 1: 'leg', 2: 'leg', 3: 'abs', 4: 'leg', 5: 'leg',
    6: 'abs', 7: 'leg', 8: 'leg', 9: 'chest', 10: 'leg', 11: 'leg',
    12: 'face', 13: 'arm', 14: 'arm', 15: 'face', 16: 'arm', 17: 'arm',
    18: 'arm', 19: 'arm', 20: 'hand', 21: 'hand', 22: 'foot', 23: 'foot'
}

# ── Lazy-loaded models (stay in GPU memory between requests) ──────────────
_hmr_model = None
_hmr_cfg = None
_dsine_model = None
_rembg_session = None
_realesrgan_upsampler = None
_densepose_backend = 'torchscript'

def _load_hmr():
    global _hmr_model, _hmr_cfg
    if _hmr_model is not None: return _hmr_model, _hmr_cfg
    
    # Stub out pyrender for headless environment
    class _Dummy:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return self
        def __getattr__(self, name): return _Dummy()
    pyrender_stub = types.ModuleType('pyrender')
    for attr in ['Node', 'Mesh', 'Scene', 'Viewer', 'OffscreenRenderer', 'Camera', 'PerspectiveCamera', 'OrthographicCamera', 'DirectionalLight', 'PointLight', 'SpotLight', 'Light', 'Primitive', 'Material', 'MetallicRoughnessMaterial', 'Texture', 'Sampler', 'RenderFlags', 'GLTF']:
        setattr(pyrender_stub, attr, _Dummy)
    sys.modules['pyrender'] = pyrender_stub

    from hmr2.configs import CACHE_DIR_4DHUMANS
    from hmr2.models import download_models, load_hmr2, DEFAULT_CHECKPOINT
    download_models(CACHE_DIR_4DHUMANS)
    model, model_cfg = load_hmr2(DEFAULT_CHECKPOINT)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    _hmr_model = (model.to(device).eval(), device)
    _hmr_cfg = model_cfg
    logger.info(f"HMR2.0 loaded on {device}")
    return _hmr_model, _hmr_cfg

def _load_rembg():
    global _rembg_session
    if _rembg_session is not None: return _rembg_session
    from rembg import new_session
    _rembg_session = new_session("u2net")
    return _rembg_session

def _load_dsine():
    global _dsine_model
    if _dsine_model is not None: return _dsine_model
    _dsine_model = torch.hub.load('hugoycj/DSINE-hub', 'DSINE', trust_repo=True)
    return _dsine_model

def _load_realesrgan():
    global _realesrgan_upsampler
    if _realesrgan_upsampler is not None: return _realesrgan_upsampler
    from realesrgan import RealESRGANer
    from basicsr.archs.rrdbnet_arch import RRDBNet
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    _realesrgan_upsampler = RealESRGANer(scale=4, model_path='RealESRGAN_x4plus.pth', model=model, tile=0, tile_pad=10, pre_pad=0, half=True)
    return _realesrgan_upsampler

# ── Utils ────────────────────────────────────────────────────────────────

def _decode_image(b64_str):
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def _encode_image(img_bgr, quality=85):
    _, buf = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf.tobytes()).decode('ascii')

def _encode_array(arr, dtype='float32'):
    return base64.b64encode(arr.astype(dtype).tobytes()).decode('ascii')

def _encode_mask(mask):
    _, buf = cv2.imencode('.png', mask)
    return base64.b64encode(buf.tobytes()).decode('ascii')

# ── Legacy Actions (Optimized) ──────────────────────────────────────────

def _run_hmr(images_b64, directions):
    (model, device), model_cfg = _load_hmr()
    img_size = model_cfg.MODEL.IMAGE_SIZE if model_cfg else 256
    all_betas = []
    first_view = {}
    
    for i, b64 in enumerate(images_b64):
        try:
            img = _decode_image(b64)
            h, w = img.shape[:2]
            # Simple square crop/pad logic
            s = max(h, w)
            square = np.zeros((s, s, 3), dtype=np.uint8)
            square[(s-h)//2:(s-h)//2+h, (s-w)//2:(s-w)//2+w] = img
            resized = cv2.resize(square, (img_size, img_size))
            rgb = resized[:, :, ::-1].copy().astype(np.float32) / 255.0
            # Normalization (using ImageNet defaults)
            rgb = (rgb - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
            tensor = torch.from_numpy(np.transpose(rgb, (2, 0, 1))).unsqueeze(0).float().to(device)
            
            with torch.no_grad():
                output = model({'img': tensor})
            
            betas = output['pred_smpl_params']['betas'][0].cpu().numpy()[:10]
            all_betas.append(betas)
            if not first_view:
                first_view = {
                    'pose': output['pred_smpl_params']['body_pose'],
                    'orient': output['pred_smpl_params']['global_orient'],
                    'verts': output['pred_vertices'][0].cpu().numpy()
                }
        except Exception as e: logger.warning(f"HMR failed view {i}: {e}")

    if not all_betas: return None
    avg_betas = np.mean(all_betas, axis=0).astype(np.float32)
    betas_tensor = torch.tensor(avg_betas).unsqueeze(0).to(device)
    
    # SMPL Mesh Reconstruction
    smpl = model.smpl
    with torch.no_grad():
        # T-Pose
        out_t = smpl(betas=betas_tensor)
        v_t = out_t.vertices[0].cpu().numpy() * 1000 # m -> mm
        # Posed
        out_p = smpl(betas=betas_tensor, body_pose=first_view['pose'], global_orient=first_view['orient'], pose2rot=False)
        v_p = out_p.vertices[0].cpu().numpy() * 1000

    return {
        'betas': avg_betas.tolist(),
        'vertices_shape': [6890, 3],
        'vertices_b64': _encode_array(v_t[:, [0, 2, 1]]), # Y-up to Z-up
        'vertices_posed_b64': _encode_array(v_p[:, [0, 2, 1]]),
        'backend': 'hmr2'
    }

def _run_rembg(images_b64, directions):
    from rembg import remove
    from PIL import Image
    _load_rembg()
    masks = {}
    for i, b64 in enumerate(images_b64):
        img = _decode_image(b64)
        mask = np.array(remove(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), only_mask=True))
        mask = cv2.dilate((mask > 128).astype(np.uint8)*255, np.ones((11,11), np.uint8))
        masks[directions[i]] = _encode_mask(mask)
    return masks

def _run_dsine(images_b64, directions):
    model = _load_dsine()
    normals = {}
    for i, b64 in enumerate(images_b64):
        img = _decode_image(b64)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        h, w = rgb.shape[:2]
        # Pad to 32
        ph, pw = (32 - h % 32) % 32, (32 - w % 32) % 32
        rgb_padded = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode='reflect')
        tensor = torch.from_numpy(rgb_padded).permute(2, 0, 1).unsqueeze(0).cuda()
        with torch.no_grad():
            pred = model(tensor)
            if isinstance(pred, (list, tuple)): pred = pred[-1]
        n = pred[0].permute(1, 2, 0).cpu().numpy()[:h, :w, :]
        n_img = ((n + 1) * 127.5).clip(0, 255).astype(np.uint8)
        normals[directions[i]] = _encode_image(n_img, quality=95)
    return normals

# ── New Cinematic Actions ────────────────────────────────────────────────

def _run_densepose(images_b64, directions):
    """Run DensePose to get IUV maps."""
    iuvs = {}
    for i, b64 in enumerate(images_b64):
        img = _decode_image(b64)
        iuv = predict_iuv(img, backend=_densepose_backend)
        if iuv is not None:
            iuvs[directions[i]] = _encode_mask(iuv) # Use PNG for IUV
    return iuvs

def _extract_frames(video_path, output_dir, fps=5):
    """Extract frames from video using FFmpeg."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={fps}",
        os.path.join(output_dir, "frame_%04d.jpg")
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".jpg")])

def _run_colmap(frames_dir, workspace_dir):
    """Run COLMAP SfM to estimate camera poses."""
    logger.info("Running COLMAP Camera Estimation...")
    db_path = os.path.join(workspace_dir, "database.db")
    sparse_path = os.path.join(workspace_dir, "sparse")
    os.makedirs(sparse_path, exist_ok=True)

    # 1. Feature Extraction
    subprocess.run(["colmap", "feature_extractor", "--database_path", db_path, "--image_path", frames_dir, "--ImageReader.single_camera", "1"], check=True)
    # 2. Exhaustive Matching
    subprocess.run(["colmap", "exhaustive_matcher", "--database_path", db_path], check=True)
    # 3. Mapper
    subprocess.run(["colmap", "mapper", "--database_path", db_path, "--image_path", frames_dir, "--output_path", sparse_path], check=True)

    # Convert binary to text
    subprocess.run(["colmap", "model_converter", "--input_path", os.path.join(sparse_path, "0"), "--output_path", sparse_path, "--output_type", "TXT"], check=True)
    return sparse_path

def _train_splat(inp):
    """
    Train a 3D Gaussian Splatting volume from video or image frames.
    Uses gsplat 1.5.0+ for high-speed convergence.
    """
    logger.info("Initializing 3DGS Training (v6.0 Cinematic)...")
    temp_dir = tempfile.mkdtemp()
    try:
        from gsplat import Trainer, SplatModel
        
        video_b64 = inp.get('video_b64')
        images_b64 = inp.get('images', [])
        
        frames_dir = os.path.join(temp_dir, "frames")
        if video_b64:
            video_path = os.path.join(temp_dir, "input_video.mp4")
            with open(video_path, "wb") as f:
                f.write(base64.b64decode(video_b64))
            frame_paths = _extract_frames(video_path, frames_dir)
        elif images_b64:
            os.makedirs(frames_dir, exist_ok=True)
            frame_paths = []
            for i, b64 in enumerate(images_b64):
                p = os.path.join(frames_dir, f"frame_{i:04d}.jpg")
                with open(p, "wb") as f: f.write(base64.b64decode(b64))
                frame_paths.append(p)
        else:
            return {'status': 'error', 'message': 'No training data provided'}

        # 1. Pose Estimation
        colmap_dir = _run_colmap(frames_dir, temp_dir)
        
        # 2. Setup gsplat Trainer
        model = SplatModel.load_colmap(colmap_dir).cuda()
        trainer = Trainer(model=model, lr=0.01)
        
        logger.info(f"Training on {len(frame_paths)} frames...")
        trainer.train(iterations=2000, images_dir=frames_dir)
        
        # 3. Export to Compressed Splat (.spz)
        buffer = io.BytesIO()
        model.save_spz(buffer)
        spz_b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
        
        return {
            'status': 'success',
            'splat_b64': spz_b64,
            'gaussians': len(model.gaussians),
            'format': 'spz'
        }
    except Exception as e:
        logger.error(f"Splat training failed: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def _anchor_splat(inp):
    """
    Bind Gaussian centroids to MPFB2 mesh vertices for animation.
    """
    logger.info("Calculating Mesh-Guided Anchors...")
    try:
        verts_b64 = inp.get('vertices_b64')
        splat_b64 = inp.get('splat_b64')
        
        if not verts_b64 or not splat_b64:
            return {'status': 'error', 'message': 'Missing vertices or splat data'}
            
        vertices = torch.from_numpy(np.frombuffer(base64.b64decode(verts_b64), dtype=np.float32).reshape(-1, 3)).cuda()
        
        from gsplat import SplatModel
        splat_bytes = base64.b64decode(splat_b64)
        model = SplatModel.load_spz(io.BytesIO(splat_bytes)).cuda()
        centroids = model.means
        
        batch_size = 10000
        n_gaussians = centroids.shape[0]
        anchor_indices = torch.zeros(n_gaussians, dtype=torch.long, device='cuda')
        offsets = torch.zeros((n_gaussians, 3), dtype=torch.float32, device='cuda')
        
        for i in range(0, n_gaussians, batch_size):
            end = min(i + batch_size, n_gaussians)
            chunk = centroids[i:end]
            dists = torch.cdist(chunk, vertices)
            indices = torch.argmin(dists, dim=1)
            anchor_indices[i:end] = indices
            offsets[i:end] = chunk - vertices[indices]
        
        return {
            'status': 'success',
            'anchor_indices_b64': _encode_array(anchor_indices.cpu().numpy(), dtype='int32'),
            'offsets_b64': _encode_array(offsets.cpu().numpy()),
            'gaussians': n_gaussians,
            'message': 'Splat successfully anchored to MPFB2 mesh'
        }
    except Exception as e:
        logger.error(f"Splat anchoring failed: {e}")
        return {'status': 'error', 'message': str(e)}

def _bake_cinematic(inp):
    """Neural baking for PBR normal/albedo enhancement."""
    logger.info("Baking Neural Detail to 4K PBR...")
    try:
        images_b64 = inp.get('images', [])
        directions = inp.get('directions', ['front', 'back', 'left', 'right'])
        verts_b64 = inp.get('vertices_b64')
        faces_b64 = inp.get('faces_b64')
        uvs_b64 = inp.get('uvs_b64')
        
        if not all([images_b64, verts_b64, faces_b64, uvs_b64]):
            return {'status': 'error', 'message': 'Missing mesh or image data'}
            
        vertices = np.frombuffer(base64.b64decode(verts_b64), dtype=np.float32).reshape(-1, 3)
        faces = np.frombuffer(base64.b64decode(faces_b64), dtype=np.int32).reshape(-1, 3)
        uvs = np.frombuffer(base64.b64decode(uvs_b64), dtype=np.float32).reshape(-1, 2)
        
        photo_dict = {d: _decode_image(images_b64[i]) for i, d in enumerate(directions) if i < len(images_b64)}
        iuv_dict = {d: predict_iuv(img, backend=_densepose_backend) for d, img in photo_dict.items()}
        iuv_dict = {k: v for k, v in iuv_dict.items() if v is not None}
        
        if not iuv_dict:
            return {'status': 'error', 'message': 'DensePose failed on all views'}
            
        # Perform Baking
        tex, weight = bake_from_photos_nn(vertices, faces, uvs, photo_dict, iuv_dict, texture_size=4096)
        
        # Seam Smoothing
        seam_mask = build_seam_mask(vertices, faces, uvs, texture_size=4096)
        tex_smooth = smooth_seam(tex, seam_mask)
        
        return {
            'status': 'success',
            'albedo_4k_b64': _encode_image(tex_smooth, quality=95),
            'coverage': float((weight > 0).mean())
        }
    except Exception as e:
        logger.error(f"Cinematic baking failed: {e}")
        return {'status': 'error', 'message': str(e)}

# ── Main Handler ──────────────────────────────────────────────────────────

def handler(job):
    inp = job['input']
    action = inp.get('action', 'hmr')
    
    try:
        if action == 'hmr':
            res = _run_hmr(inp.get('images', []), inp.get('directions', ['front']))
            return {'status': 'success', **res} if res else {'status': 'error'}
        elif action == 'rembg':
            return {'status': 'success', 'masks': _run_rembg(inp.get('images', []), inp.get('directions', ['front']))}
        elif action == 'dsine':
            return {'status': 'success', 'normals': _run_dsine(inp.get('images', []), inp.get('directions', ['front']))}
        elif action == 'densepose':
            return {'status': 'success', 'iuvs': _run_densepose(inp.get('images', []), inp.get('directions', ['front']))}
        elif action == 'train_splat':
            return _train_splat(inp)
        elif action == 'anchor_splat':
            return _anchor_splat(inp)
        elif action == 'bake_cinematic':
            return _bake_cinematic(inp)
        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}
    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {'status': 'error', 'message': str(e)}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
