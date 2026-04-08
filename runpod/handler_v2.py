"""
RunPod Handler v8.0 — LHM++ Gaussian Splatting Live Scan.

Actions:
1. 'live_scan_bake': (PRIMARY) LHM++ Gaussian Splat inference -> GLB export.
2. 'hmr':            (Legacy) SMPL shape estimation from photos.
3. 'rembg':          (Legacy) Background removal / masking.
4. 'dsine':          (Legacy) High-fidelity normal map estimation.
5. 'pbr_textures':   (Legacy) Vectorized roughness/AO generation.
6. 'health_check':   Liveness probe.

LHM++ model path: /app/lhm/pretrained_models/LHMPP-700M
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('runpod_handler_v8')

# ── Constants ────────────────────────────────────────────────────────────────

LHM_ROOT = '/app/lhm'
LHM_MODEL_PATH = os.path.join(LHM_ROOT, 'pretrained_models', 'LHMPP-700M')
LHM_SCRIPT = os.path.join(LHM_ROOT, 'scripts', 'test', 'test_app_case.py')

# Max frames fed into LHM++ (keep the sharpest ones)
_MAX_LHM_FRAMES = 16

# ── Lazy-loaded models (stay in GPU memory between requests) ─────────────────
_lhm_model = None       # LHM++ model (loaded once at startup)
_hmr_model = None
_hmr_cfg = None
_dsine_model = None
_rembg_session = None
_realesrgan_upsampler = None

# ── LHM++ model loading ──────────────────────────────────────────────────────

def _load_lhm():
    """
    Load LHM++ model once at worker startup.
    Tries programmatic import first; falls back gracefully to subprocess mode
    if the import interface is unavailable.
    Returns True if loaded, False if subprocess mode will be used.
    """
    global _lhm_model
    if _lhm_model is not None:
        return True
    try:
        sys.path.insert(0, LHM_ROOT)
        # LHM++ exposes a high-level inference class; adjust if API differs
        from lhm.runner.infer import LHMInferencer  # type: ignore
        _lhm_model = LHMInferencer(model_path=LHM_MODEL_PATH, device='cuda')
        logger.info('LHM++ model loaded (programmatic mode)')
        return True
    except Exception as exc:
        logger.warning(f'LHM++ programmatic import failed ({exc}); will use subprocess mode')
        _lhm_model = 'subprocess'
        return False


# ── Legacy model loaders ─────────────────────────────────────────────────────

def _load_hmr():
    global _hmr_model, _hmr_cfg
    if _hmr_model is not None:
        return _hmr_model, _hmr_cfg

    class _Dummy:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return self
        def __getattr__(self, name): return _Dummy()

    pyrender_stub = types.ModuleType('pyrender')
    for attr in ['Node', 'Mesh', 'Scene', 'Viewer', 'OffscreenRenderer',
                 'Camera', 'PerspectiveCamera', 'OrthographicCamera',
                 'DirectionalLight', 'PointLight', 'SpotLight', 'Light',
                 'Primitive', 'Material', 'MetallicRoughnessMaterial',
                 'Texture', 'Sampler', 'RenderFlags', 'GLTF']:
        setattr(pyrender_stub, attr, _Dummy)
    sys.modules['pyrender'] = pyrender_stub

    from hmr2.configs import CACHE_DIR_4DHUMANS
    from hmr2.models import download_models, load_hmr2, DEFAULT_CHECKPOINT
    download_models(CACHE_DIR_4DHUMANS)
    model, model_cfg = load_hmr2(DEFAULT_CHECKPOINT)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    _hmr_model = (model.to(device).eval(), device)
    _hmr_cfg = model_cfg
    logger.info(f'HMR2.0 loaded on {device}')
    return _hmr_model, _hmr_cfg


def _load_rembg():
    global _rembg_session
    if _rembg_session is not None:
        return _rembg_session
    from rembg import new_session
    _rembg_session = new_session('u2net')
    return _rembg_session


def _load_dsine():
    global _dsine_model
    if _dsine_model is not None:
        return _dsine_model
    _dsine_model = torch.hub.load('hugoycj/DSINE-hub', 'DSINE', trust_repo=True)
    return _dsine_model


def _load_realesrgan():
    global _realesrgan_upsampler
    if _realesrgan_upsampler is not None:
        return _realesrgan_upsampler
    from realesrgan import RealESRGANer
    from basicsr.archs.rrdbnet_arch import RRDBNet
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                    num_block=23, num_grow_ch=32, scale=4)
    _realesrgan_upsampler = RealESRGANer(
        scale=4, model_path='RealESRGAN_x4plus.pth', model=model,
        tile=0, tile_pad=10, pre_pad=0, half=True,
    )
    return _realesrgan_upsampler


# ── Image utils ──────────────────────────────────────────────────────────────

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


def _remove_background(img_bgr):
    """
    Remove background from a BGR image using rembg.
    Returns RGBA numpy array (uint8) with white background filled in for PNG
    export, and also the alpha mask.
    """
    from rembg import remove
    from PIL import Image
    _load_rembg()
    pil_in = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    pil_out = remove(pil_in)  # RGBA PIL image
    rgba = np.array(pil_out, dtype=np.uint8)
    # Composite onto white background for PNG files LHM++ will read
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    white_bg = np.ones_like(rgb) * 255.0
    composited = (rgb * alpha + white_bg * (1.0 - alpha)).astype(np.uint8)
    return composited, rgba[:, :, 3]


# ── Gaussian → GLB conversion ────────────────────────────────────────────────

def _gaussians_to_glb(positions: np.ndarray, colors: np.ndarray,
                       output_path: str) -> str:
    """
    Convert a 160K Gaussian splat (positions + colors) to a GLB point-cloud.

    Strategy: export as a mesh with one degenerate triangle per Gaussian
    (triangle fans around each point) so that standard GLB viewers show
    the colored point cloud without requiring extensions.  We use pygltflib
    directly to stay consistent with the rest of the codebase.

    Args:
        positions: (N, 3) float32 — Gaussian centre positions
        colors:    (N, 3) float32 — RGB in [0, 1] or [0, 255]
        output_path: where to write the .glb file
    Returns:
        output_path
    """
    import pygltflib

    N = positions.shape[0]
    pos = positions.astype(np.float32)
    col = colors.astype(np.float32)
    if col.max() > 1.5:
        col = col / 255.0
    col = np.clip(col, 0.0, 1.0)

    # Build degenerate triangles: each Gaussian → triangle [i, i, i]
    indices = np.repeat(np.arange(N, dtype=np.uint32), 3)  # (3N,)

    # Interleaved vertex buffer: position(xyz) + color(rgb) as VEC3 FLOAT
    # We pack them separately for clarity.
    pos_bytes = pos.tobytes()
    col_bytes = col.astype(np.float32).tobytes()
    idx_bytes = indices.tobytes()

    # Pad idx_bytes to 4-byte boundary
    pad = (4 - len(idx_bytes) % 4) % 4
    idx_bytes_padded = idx_bytes + b'\x00' * pad

    blob = idx_bytes_padded + pos_bytes + col_bytes
    offset = 0

    bv_idx = pygltflib.BufferView(
        buffer=0, byteOffset=offset,
        byteLength=len(idx_bytes_padded),
        target=pygltflib.ELEMENT_ARRAY_BUFFER,
    )
    acc_idx = pygltflib.Accessor(
        bufferView=0, componentType=pygltflib.UNSIGNED_INT,
        count=int(len(indices)), type=pygltflib.SCALAR,
        max=[int(N - 1)], min=[0],
    )
    offset += len(idx_bytes_padded)

    bv_pos = pygltflib.BufferView(
        buffer=0, byteOffset=offset,
        byteLength=len(pos_bytes),
        target=pygltflib.ARRAY_BUFFER,
    )
    acc_pos = pygltflib.Accessor(
        bufferView=1, componentType=pygltflib.FLOAT,
        count=int(N), type=pygltflib.VEC3,
        max=pos.max(axis=0).tolist(),
        min=pos.min(axis=0).tolist(),
    )
    offset += len(pos_bytes)

    bv_col = pygltflib.BufferView(
        buffer=0, byteOffset=offset,
        byteLength=len(col_bytes),
        target=pygltflib.ARRAY_BUFFER,
    )
    acc_col = pygltflib.Accessor(
        bufferView=2, componentType=pygltflib.FLOAT,
        count=int(N), type=pygltflib.VEC3,
    )

    attributes = pygltflib.Attributes(POSITION=1, COLOR_0=2)

    mat = pygltflib.Material(
        pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
            baseColorFactor=[1.0, 1.0, 1.0, 1.0],
            metallicFactor=0.0,
            roughnessFactor=1.0,
        ),
        doubleSided=True,
    )

    gltf = pygltflib.GLTF2(
        scene=0,
        scenes=[pygltflib.Scene(nodes=[0])],
        nodes=[pygltflib.Node(mesh=0)],
        meshes=[pygltflib.Mesh(primitives=[
            pygltflib.Primitive(
                attributes=attributes,
                indices=0,
                material=0,
                mode=pygltflib.TRIANGLES,
            )
        ])],
        materials=[mat],
        accessors=[acc_idx, acc_pos, acc_col],
        bufferViews=[bv_idx, bv_pos, bv_col],
        buffers=[pygltflib.Buffer(byteLength=len(blob))],
    )
    gltf.set_binary_blob(blob)
    gltf.save(output_path)
    return output_path


# ── LHM++ inference helpers ──────────────────────────────────────────────────

def _run_lhm_programmatic(frame_paths: list, ref_view: int):
    """
    Call LHM++ via the Python API (fast, no subprocess overhead).
    Returns dict with keys: positions (N,3) float32, colors (N,3) float32.
    """
    result = _lhm_model.infer(
        image_paths=frame_paths,
        ref_view=ref_view,
    )
    # LHMInferencer is expected to return an object with .gaussians attribute
    # (positions: Tensor (N,3), colors: Tensor (N,3))
    gaussians = result.gaussians
    positions = gaussians.means.detach().cpu().numpy().astype(np.float32)
    # Colors may be SH coefficients — take DC term (first 3 values) and
    # convert from SH to RGB: rgb = 0.5 + 0.5 * dc / C0  (C0 = 0.2821)
    if hasattr(gaussians, 'features_dc'):
        C0 = 0.28209479177387814
        dc = gaussians.features_dc.detach().cpu().numpy()  # (N, 1, 3)
        dc = dc[:, 0, :] if dc.ndim == 3 else dc
        colors = np.clip(0.5 + C0 * dc, 0.0, 1.0).astype(np.float32)
    elif hasattr(gaussians, 'colors'):
        colors = gaussians.colors.detach().cpu().numpy().astype(np.float32)
        if colors.max() > 1.5:
            colors = colors / 255.0
    else:
        colors = np.ones((positions.shape[0], 3), dtype=np.float32) * 0.7
    return {'positions': positions, 'colors': colors}


def _run_lhm_subprocess(frame_paths: list, ref_view: int, work_dir: str):
    """
    Call LHM++ via subprocess (fallback when programmatic import is unavailable).
    Parses the output directory for Gaussian data saved as .npz.
    Returns dict with keys: positions (N,3) float32, colors (N,3) float32.
    """
    out_dir = os.path.join(work_dir, 'lhm_output')
    os.makedirs(out_dir, exist_ok=True)

    # Write frame list as a glob-friendly directory — LHM++ expects --image_glob
    frames_list_dir = os.path.join(work_dir, 'frames')
    os.makedirs(frames_list_dir, exist_ok=True)
    for i, p in enumerate(frame_paths):
        dst = os.path.join(frames_list_dir, f'frame_{i:04d}.png')
        if not os.path.exists(dst):
            shutil.copy(p, dst)

    cmd = [
        sys.executable, LHM_SCRIPT,
        '--image_glob', os.path.join(frames_list_dir, '*.png'),
        '--ref_view', str(ref_view),
        '--output_dir', out_dir,
        '--model_path', LHM_MODEL_PATH,
        '--save_gaussians',  # flag to save .npz output
    ]
    logger.info(f'LHM++ subprocess: {" ".join(cmd)}')
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f'LHM++ subprocess failed (rc={proc.returncode}):\n'
            f'STDOUT: {proc.stdout[-2000:]}\nSTDERR: {proc.stderr[-2000:]}'
        )

    # Find saved Gaussian .npz
    npz_files = sorted(
        [f for f in os.listdir(out_dir) if f.endswith('.npz')]
    )
    if not npz_files:
        # Try .ply fallback
        ply_files = sorted(
            [f for f in os.listdir(out_dir) if f.endswith('.ply')]
        )
        if ply_files:
            return _load_ply_gaussians(os.path.join(out_dir, ply_files[-1]))
        raise FileNotFoundError(
            f'LHM++ did not produce output in {out_dir}. '
            f'Files: {os.listdir(out_dir)}'
        )

    data = np.load(os.path.join(out_dir, npz_files[-1]))
    positions = data['positions'].astype(np.float32)
    colors = data.get('colors', np.ones((positions.shape[0], 3), dtype=np.float32) * 0.7)
    colors = colors.astype(np.float32)
    if colors.max() > 1.5:
        colors = colors / 255.0
    return {'positions': positions, 'colors': np.clip(colors, 0.0, 1.0)}


def _load_ply_gaussians(ply_path: str):
    """Parse a PLY file to extract Gaussian positions and colors."""
    try:
        import open3d as o3d
        pcd = o3d.io.read_point_cloud(ply_path)
        positions = np.asarray(pcd.points, dtype=np.float32)
        if pcd.has_colors():
            colors = np.asarray(pcd.colors, dtype=np.float32)
        else:
            colors = np.ones((positions.shape[0], 3), dtype=np.float32) * 0.7
        return {'positions': positions, 'colors': colors}
    except ImportError:
        pass

    # Pure-Python minimal PLY reader for float xyz + uchar rgb
    positions, colors = [], []
    with open(ply_path, 'rb') as f:
        header_lines = []
        while True:
            line = f.readline().decode('ascii', errors='replace').strip()
            header_lines.append(line)
            if line == 'end_header':
                break
        n_verts = 0
        prop_names = []
        for ln in header_lines:
            if ln.startswith('element vertex'):
                n_verts = int(ln.split()[-1])
            elif ln.startswith('property'):
                prop_names.append(ln.split()[-1])
        # Assume float x,y,z + uchar red,green,blue if present
        has_color = 'red' in prop_names
        struct_fmt = '<' + 'f' * 3
        struct_sz = 12
        if has_color:
            struct_fmt += 'BBB'
            struct_sz += 3
        import struct
        for _ in range(n_verts):
            row = struct.unpack_from(struct_fmt, f.read(struct_sz))
            positions.append(row[:3])
            if has_color:
                colors.append([row[3] / 255.0, row[4] / 255.0, row[5] / 255.0])
            else:
                colors.append([0.7, 0.7, 0.7])
    return {
        'positions': np.array(positions, dtype=np.float32),
        'colors': np.array(colors, dtype=np.float32),
    }


# ── PRIMARY ACTION: live_scan_bake ───────────────────────────────────────────

def _live_scan_bake(inp):
    """
    LHM++ live-scan pipeline.

    Input:
        frames:  [{image_b64, iuv_b64 (ignored), region, sharpness}]
        profile: {height_cm, weight_kg, gender}

    Returns:
        {status, glb_b64, vertex_count, face_count, texture_coverage, lhm_used}
    """
    logger.info('=== LIVE SCAN BAKE (LHM++) START ===')
    temp_dir = tempfile.mkdtemp(prefix='lhm_scan_')
    try:
        frames_data = inp.get('frames', [])
        profile = inp.get('profile', {})

        if not frames_data:
            return {'status': 'error', 'message': 'No frames provided'}

        # ── Step 1: decode + background removal ─────────────────────────────
        decoded_frames = []  # list of (sharpness, bgr_nobg, region)
        for i, fd in enumerate(frames_data):
            try:
                img_bgr = _decode_image(fd['image_b64'])
                sharpness = float(fd.get('sharpness', 1.0))
                region = fd.get('region', f'view_{i}')
                # iuv_b64 is ignored — LHM++ doesn't use DensePose
                composited, _alpha = _remove_background(img_bgr)
                decoded_frames.append((sharpness, composited, region))
            except Exception as exc:
                logger.warning(f'Frame {i} decode/rembg failed: {exc}')

        if not decoded_frames:
            return {'status': 'error', 'message': 'All frames failed to decode'}

        logger.info(f'Decoded {len(decoded_frames)} frames after background removal')

        # ── Step 2: select up to _MAX_LHM_FRAMES best frames by sharpness ───
        decoded_frames.sort(key=lambda x: x[0], reverse=True)
        selected = decoded_frames[:_MAX_LHM_FRAMES]
        ref_view = min(len(selected), 16) - 1

        # Save selected frames as PNG files
        frame_paths = []
        for idx, (sharp, img_rgb, region) in enumerate(selected):
            p = os.path.join(temp_dir, f'frame_{idx:04d}.png')
            # img_rgb is BGR from OpenCV; LHM++ expects RGB PNG
            cv2.imwrite(p, img_rgb)
            frame_paths.append(p)
        logger.info(f'Selected {len(frame_paths)} frames (ref_view={ref_view})')

        # ── Step 3: LHM++ inference ──────────────────────────────────────────
        loaded = _load_lhm()
        if loaded and _lhm_model != 'subprocess':
            logger.info('Running LHM++ (programmatic)')
            gauss = _run_lhm_programmatic(frame_paths, ref_view)
        else:
            logger.info('Running LHM++ (subprocess)')
            gauss = _run_lhm_subprocess(frame_paths, ref_view, temp_dir)

        positions = gauss['positions']   # (N, 3) float32
        colors    = gauss['colors']      # (N, 3) float32, [0,1]
        N = positions.shape[0]
        logger.info(f'LHM++ produced {N} Gaussians')

        if N == 0:
            return {'status': 'error', 'message': 'LHM++ returned 0 Gaussians'}

        # ── Step 4: convert Gaussians → GLB ─────────────────────────────────
        glb_path = os.path.join(temp_dir, 'body_scan.glb')
        _gaussians_to_glb(positions, colors, glb_path)

        with open(glb_path, 'rb') as f:
            glb_b64 = base64.b64encode(f.read()).decode('ascii')

        logger.info(f'=== LIVE SCAN BAKE DONE: {N} Gaussians, GLB {os.path.getsize(glb_path)//1024} KB ===')

        return {
            'status': 'success',
            'glb_b64': glb_b64,
            'vertex_count': N,
            'face_count': 0,           # point cloud — no faces
            'texture_coverage': 1.0,   # Gaussians cover full body
            'lhm_used': True,
            'profile_metadata': {      # passed through for py4web
                'height_cm': profile.get('height_cm'),
                'weight_kg': profile.get('weight_kg'),
                'gender':    profile.get('gender'),
            },
        }

    except Exception as exc:
        logger.error(f'LHM++ live scan failed: {exc}', exc_info=True)
        return {'status': 'error', 'message': str(exc)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── Legacy actions ────────────────────────────────────────────────────────────

def _run_hmr(images_b64, directions):
    (model, device), model_cfg = _load_hmr()
    img_size = model_cfg.MODEL.IMAGE_SIZE if model_cfg else 256
    all_betas = []
    first_view = {}

    for i, b64 in enumerate(images_b64):
        try:
            img = _decode_image(b64)
            h, w = img.shape[:2]
            s = max(h, w)
            square = np.zeros((s, s, 3), dtype=np.uint8)
            square[(s-h)//2:(s-h)//2+h, (s-w)//2:(s-w)//2+w] = img
            resized = cv2.resize(square, (img_size, img_size))
            rgb = resized[:, :, ::-1].copy().astype(np.float32) / 255.0
            rgb = (rgb - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
            tensor = torch.from_numpy(
                np.transpose(rgb, (2, 0, 1))
            ).unsqueeze(0).float().to(device)
            with torch.no_grad():
                output = model({'img': tensor})
            betas = output['pred_smpl_params']['betas'][0].cpu().numpy()[:10]
            all_betas.append(betas)
            if not first_view:
                first_view = {
                    'pose':   output['pred_smpl_params']['body_pose'],
                    'orient': output['pred_smpl_params']['global_orient'],
                    'verts':  output['pred_vertices'][0].cpu().numpy(),
                }
        except Exception as e:
            logger.warning(f'HMR failed view {i}: {e}')

    if not all_betas:
        return None
    avg_betas = np.mean(all_betas, axis=0).astype(np.float32)
    betas_tensor = torch.tensor(avg_betas).unsqueeze(0).to(device)
    smpl = model.smpl
    with torch.no_grad():
        out_t = smpl(betas=betas_tensor)
        v_t = out_t.vertices[0].cpu().numpy() * 1000
        out_p = smpl(betas=betas_tensor,
                     body_pose=first_view['pose'],
                     global_orient=first_view['orient'],
                     pose2rot=False)
        v_p = out_p.vertices[0].cpu().numpy() * 1000
    return {
        'betas': avg_betas.tolist(),
        'vertices_shape': [6890, 3],
        'vertices_b64':       _encode_array(v_t[:, [0, 2, 1]]),
        'vertices_posed_b64': _encode_array(v_p[:, [0, 2, 1]]),
        'backend': 'hmr2',
    }


def _run_rembg(images_b64, directions):
    from rembg import remove
    from PIL import Image
    _load_rembg()
    masks = {}
    for i, b64 in enumerate(images_b64):
        img = _decode_image(b64)
        mask = np.array(remove(
            Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)),
            only_mask=True,
        ))
        mask = cv2.dilate(
            (mask > 128).astype(np.uint8) * 255,
            np.ones((11, 11), np.uint8),
        )
        masks[directions[i]] = _encode_mask(mask)
    return masks


def _run_dsine(images_b64, directions):
    model = _load_dsine()
    normals = {}
    for i, b64 in enumerate(images_b64):
        img = _decode_image(b64)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        h, w = rgb.shape[:2]
        ph = (32 - h % 32) % 32
        pw = (32 - w % 32) % 32
        rgb_padded = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode='reflect')
        tensor = torch.from_numpy(rgb_padded).permute(2, 0, 1).unsqueeze(0).cuda()
        with torch.no_grad():
            pred = model(tensor)
            if isinstance(pred, (list, tuple)):
                pred = pred[-1]
        n = pred[0].permute(1, 2, 0).cpu().numpy()[:h, :w, :]
        n_img = ((n + 1) * 127.5).clip(0, 255).astype(np.uint8)
        normals[directions[i]] = _encode_image(n_img, quality=95)
    return normals


def _extract_frames(video_path, output_dir, fps=5):
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', f'fps={fps}',
        os.path.join(output_dir, 'frame_%04d.jpg'),
    ]
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir) if f.endswith('.jpg')
    ])


def _run_colmap(frames_dir, workspace_dir):
    logger.info('Running COLMAP Camera Estimation...')
    db_path = os.path.join(workspace_dir, 'database.db')
    sparse_path = os.path.join(workspace_dir, 'sparse')
    os.makedirs(sparse_path, exist_ok=True)
    subprocess.run(['colmap', 'feature_extractor',
                    '--database_path', db_path,
                    '--image_path', frames_dir,
                    '--ImageReader.single_camera', '1'], check=True)
    subprocess.run(['colmap', 'exhaustive_matcher',
                    '--database_path', db_path], check=True)
    subprocess.run(['colmap', 'mapper',
                    '--database_path', db_path,
                    '--image_path', frames_dir,
                    '--output_path', sparse_path], check=True)
    subprocess.run(['colmap', 'model_converter',
                    '--input_path', os.path.join(sparse_path, '0'),
                    '--output_path', sparse_path,
                    '--output_type', 'TXT'], check=True)
    return sparse_path


def _health_check():
    """Liveness probe — reports model loading status."""
    return {
        'status': 'ok',
        'lhm_loaded': _lhm_model is not None and _lhm_model != 'subprocess',
        'lhm_mode':   'programmatic' if (_lhm_model not in (None, 'subprocess'))
                      else ('subprocess' if _lhm_model == 'subprocess' else 'not_loaded'),
        'cuda':        torch.cuda.is_available(),
        'gpu':         torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


# ── Startup: pre-load LHM++ so first request is fast ─────────────────────────

try:
    _load_lhm()
except Exception as _exc:
    logger.warning(f'LHM++ pre-load skipped: {_exc}')


# ── Main handler ──────────────────────────────────────────────────────────────

def handler(job):
    inp    = job['input']
    action = inp.get('action', 'live_scan_bake')

    try:
        if action == 'live_scan_bake':
            return _live_scan_bake(inp)
        elif action == 'health_check':
            return _health_check()
        elif action == 'hmr':
            res = _run_hmr(inp.get('images', []),
                           inp.get('directions', ['front']))
            return {'status': 'success', **res} if res else {'status': 'error', 'message': 'HMR failed'}
        elif action == 'rembg':
            return {
                'status': 'success',
                'masks': _run_rembg(inp.get('images', []),
                                    inp.get('directions', ['front'])),
            }
        elif action == 'dsine':
            return {
                'status': 'success',
                'normals': _run_dsine(inp.get('images', []),
                                      inp.get('directions', ['front'])),
            }
        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}
    except Exception as exc:
        logger.error(f'Handler error: {exc}', exc_info=True)
        return {'status': 'error', 'message': str(exc)}


if __name__ == '__main__':
    runpod.serverless.start({'handler': handler})
