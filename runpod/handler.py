"""
RunPod Serverless Handler — GPU-heavy body mesh inference.

Runs on RunPod cloud GPUs. Receives base64-encoded body photos,
returns SMPL shape params + body mask + optional normal map.

Photos are processed IN MEMORY ONLY — never written to disk.
"""
import runpod
import numpy as np
import cv2
import base64
import logging
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('runpod_body')

# ── Lazy-loaded models (stay in GPU memory between requests) ──────────────
_hmr_model = None
_hmr_cfg = None
_dsine_model = None
_rembg_session = None


def _load_hmr():
    """Load HMR2.0 model once, keep in GPU memory."""
    global _hmr_model, _hmr_cfg
    if _hmr_model is not None:
        return _hmr_model, _hmr_cfg

    import torch

    # Stub out pyrender before importing hmr2 — we don't need rendering,
    # only the SMPL model weights. pyrender requires OpenGL/EGL which
    # isn't available on headless GPU servers.
    import sys
    import types

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
    model = model.to(device).eval()
    _hmr_model = (model, device)
    _hmr_cfg = model_cfg
    logger.info(f"HMR2.0 loaded on {device}")
    return _hmr_model, _hmr_cfg


def _load_rembg():
    """Load rembg session once."""
    global _rembg_session
    if _rembg_session is not None:
        return _rembg_session
    from rembg import new_session
    _rembg_session = new_session("u2net")
    logger.info("rembg U2-Net loaded")
    return _rembg_session


def _load_dsine():
    """Load DSINE normal estimation model once."""
    global _dsine_model
    if _dsine_model is not None:
        return _dsine_model
    import torch
    _dsine_model = torch.hub.load('hugoycj/DSINE-hub', 'DSINE', trust_repo=True)
    logger.info("DSINE loaded (CUDA=%s)", torch.cuda.is_available())
    return _dsine_model


def _decode_image(b64_str):
    """Base64 string → BGR numpy array. Never touches disk."""
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _encode_array(arr, dtype='float32'):
    """Numpy array → base64 string for transport."""
    buf = arr.astype(dtype).tobytes()
    return base64.b64encode(buf).decode('ascii')


def _encode_image(img_bgr, quality=85):
    """BGR image → base64 JPEG. Never touches disk."""
    _, buf = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf.tobytes()).decode('ascii')


def _encode_mask(mask):
    """Binary mask → base64 PNG."""
    _, buf = cv2.imencode('.png', mask)
    return base64.b64encode(buf.tobytes()).decode('ascii')


# ── HMR2.0 inference ─────────────────────────────────────────────────────

def _run_hmr(images_b64, directions):
    """Run HMR2.0 on images, return SMPL params."""
    import torch

    (model, device), model_cfg = _load_hmr()
    img_size = model_cfg.MODEL.IMAGE_SIZE if model_cfg else 256
    img_mean = 255.0 * np.array(
        model_cfg.MODEL.IMAGE_MEAN if model_cfg else [0.485, 0.456, 0.406])
    img_std = 255.0 * np.array(
        model_cfg.MODEL.IMAGE_STD if model_cfg else [0.229, 0.224, 0.225])

    all_betas = []
    best_verts = None

    for i, b64 in enumerate(images_b64):
        try:
            img = _decode_image(b64)
            h, w = img.shape[:2]

            # Center crop to square
            if h > w:
                pad = (h - w) // 2
                square = img[pad:pad + w, :, :]
            elif w > h:
                pad = (w - h) // 2
                square = img[:, pad:pad + h, :]
            else:
                square = img

            resized = cv2.resize(square, (img_size, img_size),
                                 interpolation=cv2.INTER_LINEAR)

            # BGR → RGB, normalize
            rgb = resized[:, :, ::-1].copy().astype(np.float32)
            tensor = np.transpose(rgb, (2, 0, 1))
            for c in range(3):
                tensor[c] = (tensor[c] - img_mean[c]) / img_std[c]

            tensor = torch.from_numpy(tensor).unsqueeze(0).float().to(device)

            with torch.no_grad():
                output = model({'img': tensor})

            betas = output['pred_smpl_params']['betas'][0].cpu().numpy()
            all_betas.append(betas[:10])

            if best_verts is None:
                best_verts = output['pred_vertices'][0].cpu().numpy()

            logger.info(f"HMR2 view {i} ({directions[i]}): betas[:3]="
                        f"{betas[:3].round(2)}")
        except Exception as e:
            logger.warning(f"HMR prediction failed for image {i}: {e}")

    if not all_betas:
        return None

    avg_betas = np.mean(all_betas, axis=0).astype(np.float32)

    # Reconstruct SMPL mesh with averaged betas (T-pose)
    verts = None
    try:
        betas_tensor = torch.tensor(avg_betas).unsqueeze(0).float().to(device)
        smpl_layer = model.smpl
        body_pose = torch.eye(3, device=device).unsqueeze(0).expand(1, 23, -1, -1)
        global_orient = torch.eye(3, device=device).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            smpl_out = smpl_layer(
                betas=betas_tensor, body_pose=body_pose,
                global_orient=global_orient, pose2rot=False)
            verts = smpl_out.vertices[0].cpu().numpy() * 1000  # m → mm
        # SMPL Y-up → Z-up
        verts = verts[:, [0, 2, 1]]
    except Exception as e:
        logger.warning(f"SMPL reconstruction failed: {e}")
        if best_verts is not None:
            verts = best_verts * 1000
            verts = verts[:, [0, 2, 1]]

    return {
        'betas': avg_betas.tolist(),
        'vertices_shape': list(verts.shape) if verts is not None else None,
        'vertices_b64': _encode_array(verts) if verts is not None else None,
        'backend': 'hmr2',
        'confidence': 0.85,
    }


# ── rembg body segmentation ──────────────────────────────────────────────

def _run_rembg(images_b64, directions):
    """Segment bodies from images. Returns base64 masks."""
    from rembg import remove
    from PIL import Image

    _load_rembg()
    masks = {}

    for i, b64 in enumerate(images_b64):
        img = _decode_image(b64)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        result = remove(pil_img, only_mask=True)
        mask = np.array(result)
        mask = (mask > 128).astype(np.uint8) * 255
        kernel = np.ones((21, 21), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)
        masks[directions[i]] = _encode_mask(mask)
        coverage = (mask > 0).sum() / mask.size * 100
        logger.info(f"rembg {directions[i]}: {coverage:.1f}% body")

    return masks


# ── DSINE normal estimation ──────────────────────────────────────────────

def _run_dsine(images_b64, directions):
    """Estimate surface normals from images."""
    import torch

    model = _load_dsine()
    if model is None:
        return {}

    normals = {}
    for i, b64 in enumerate(images_b64):
        try:
            img = _decode_image(b64)
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

            h, w = rgb.shape[:2]
            # Pad to multiple of 32
            ph = (32 - h % 32) % 32
            pw = (32 - w % 32) % 32
            if ph > 0 or pw > 0:
                rgb = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode='reflect')

            tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).cuda()

            with torch.no_grad():
                pred = model(tensor)
                if isinstance(pred, (list, tuple)):
                    pred = pred[-1]

            normal = pred[0].permute(1, 2, 0).cpu().numpy()
            # Crop back to original size
            normal = normal[:h, :w, :]

            # Encode as 8-bit image for transport ([-1,1] → [0,255])
            normal_img = ((normal + 1) * 127.5).clip(0, 255).astype(np.uint8)
            normals[directions[i]] = _encode_image(normal_img, quality=95)
            logger.info(f"DSINE {directions[i]}: {h}x{w}")
        except Exception as e:
            logger.warning(f"DSINE failed for {directions[i]}: {e}")

    return normals


# ── Main handler ──────────────────────────────────────────────────────────

def handler(job):
    """
    RunPod serverless handler.

    Input (job['input']):
        images: dict {direction: base64_jpeg} — body photos
        tasks: list of str — ['hmr', 'rembg', 'dsine'] — which models to run

    Output:
        dict with results for each requested task
    """
    inp = job['input']
    images_dict = inp.get('images', {})
    tasks = inp.get('tasks', ['hmr', 'rembg'])

    directions = list(images_dict.keys())
    images_b64 = [images_dict[d] for d in directions]

    logger.info(f"Processing {len(images_b64)} images, tasks={tasks}")

    result = {'status': 'success'}

    if 'hmr' in tasks:
        hmr_result = _run_hmr(images_b64, directions)
        if hmr_result is None:
            return {'status': 'error', 'message': 'HMR2.0 prediction failed'}
        result['hmr'] = hmr_result

    if 'rembg' in tasks:
        result['masks'] = _run_rembg(images_b64, directions)

    if 'dsine' in tasks:
        result['normals'] = _run_dsine(images_b64, directions)

    # ── GPU texture tasks ────────────────────────────────────────────────
    if 'texture_upscale' in tasks:
        result['texture_upscale'] = _run_texture_upscale(inp)

    if 'normal_from_depth' in tasks:
        result['normal_from_depth'] = _run_normal_from_depth(images_b64, directions)

    if 'pbr_textures' in tasks:
        result['pbr_textures'] = _run_pbr_textures(inp)

    logger.info("Done — returning results")
    return result


# ── GPU texture processing ───────────────────────────────────────────────

_realesrgan_model = None


def _load_realesrgan():
    """Lazy-load Real-ESRGAN model (stays in GPU memory)."""
    global _realesrgan_model
    if _realesrgan_model is not None:
        return _realesrgan_model

    import os
    from realesrgan import RealESRGANer
    from basicsr.archs.rrdbnet_arch import RRDBNet

    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                    num_block=23, num_grow_ch=32, scale=4)

    model_path = os.path.join('/root/.cache', 'realesrgan', 'RealESRGAN_x4plus.pth')
    os.makedirs(os.path.dirname(model_path), exist_ok=True)

    if not os.path.exists(model_path):
        from basicsr.utils.download_util import load_file_from_url
        load_file_from_url(
            'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
            model_dir=os.path.dirname(model_path))

    _realesrgan_model = RealESRGANer(
        scale=4, model_path=model_path, model=model,
        tile=512, tile_pad=10, pre_pad=0,
        half=True, device='cuda',
    )
    logger.info("Real-ESRGAN loaded on GPU")
    return _realesrgan_model


def _run_texture_upscale(inp):
    """4x upscale a texture atlas using Real-ESRGAN on GPU."""
    try:
        texture_b64 = inp.get('texture_b64')
        if not texture_b64:
            return {'status': 'error', 'message': 'No texture_b64 provided'}

        img = _decode_image(texture_b64)
        target_size = inp.get('target_size', 4096)

        upsampler = _load_realesrgan()
        output, _ = upsampler.enhance(img, outscale=4)

        h, w = output.shape[:2]
        if max(h, w) > target_size:
            scale = target_size / max(h, w)
            output = cv2.resize(output, (int(w * scale), int(h * scale)),
                                interpolation=cv2.INTER_LANCZOS4)

        logger.info(f"Texture upscaled: {img.shape[:2]} -> {output.shape[:2]}")
        return {
            'status': 'success',
            'texture_b64': _encode_image(output, quality=95),
            'shape': list(output.shape),
        }
    except Exception as e:
        logger.error(f"Texture upscale failed: {e}")
        return {'status': 'error', 'message': str(e)}


def _run_normal_from_depth(images_b64, directions):
    """Generate detailed normal maps from photos using DSINE (reuses _run_dsine)."""
    return _run_dsine(images_b64, directions)


# ── SMPL data for PBR generation ─────────────────────────────────────────

_smpl_data = None


def _load_smpl_data():
    """Load SMPL model data (weights, faces) for texture generation."""
    import os
    import pickle
    global _smpl_data
    if _smpl_data is not None:
        return _smpl_data

    smpl_path = '/root/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl'
    with open(smpl_path, 'rb') as f:
        data = pickle.load(f, encoding='latin1')

    _smpl_data = {
        'weights': np.array(data['weights']),  # (6890, 24)
        'faces': np.array(data['f'], dtype=np.int32),  # (13776, 3)
    }
    logger.info("SMPL data loaded: weights %s, faces %s",
                _smpl_data['weights'].shape, _smpl_data['faces'].shape)
    return _smpl_data


def _get_smpl_part_ids(vertices):
    """Assign SMPL body-part IDs (0-23) from blend weights."""
    smpl = _load_smpl_data()
    weights = smpl['weights']
    if len(weights) != len(vertices):
        logger.warning("Vertex count mismatch: %d vs %d", len(vertices), len(weights))
        return None
    return np.argmax(weights, axis=1)


# SMPL part-to-region mapping (same as texture_factory.py)
_SMPL_PART_MAP = {
    0: 'torso', 1: 'torso', 2: 'torso', 3: 'torso',
    4: 'legs', 5: 'legs', 6: 'torso',
    7: 'legs', 8: 'legs', 9: 'torso',
    10: 'legs', 11: 'legs',
    12: 'torso', 13: 'arms', 14: 'arms', 15: 'torso',
    16: 'arms', 17: 'arms',
    18: 'arms', 19: 'arms',
    20: 'hands', 21: 'hands',
    22: 'hands', 23: 'hands',
}

_REGION_ROUGHNESS = {
    'torso': 0.55, 'arms': 0.50, 'legs': 0.60,
    'hands': 0.45, 'head': 0.30,
}


def _generate_roughness_map(vertices, faces, uvs, atlas_size):
    """Generate anatomical roughness map from SMPL body-part assignments."""
    roughness_map = np.full((atlas_size, atlas_size), 0.55, dtype=np.float32)

    part_ids = _get_smpl_part_ids(vertices)
    if part_ids is None:
        return (roughness_map * 255).astype(np.uint8)

    vert_roughness = np.full(len(uvs), 0.55, dtype=np.float32)
    for part_id, region_name in _SMPL_PART_MAP.items():
        mask = part_ids == part_id
        vert_roughness[mask] = _REGION_ROUGHNESS.get(region_name, 0.55)

    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

    for i in range(len(uvs)):
        roughness_map[v_px[i], u_px[i]] = vert_roughness[i]

    kernel_size = atlas_size // 128 | 1
    if kernel_size >= 3:
        roughness_map = cv2.GaussianBlur(roughness_map, (kernel_size, kernel_size), 0)

    return (roughness_map * 255).astype(np.uint8)


def _generate_ao_map(vertices, faces, uvs, atlas_size):
    """Generate ambient occlusion map by computing per-vertex concavity."""
    normals = np.zeros_like(vertices, dtype=np.float32)
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    fn_lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
    fn_lens[fn_lens < 1e-10] = 1.0
    face_normals /= fn_lens

    for i in range(3):
        np.add.at(normals, faces[:, i], face_normals)
    n_lens = np.linalg.norm(normals, axis=1, keepdims=True)
    n_lens[n_lens < 1e-10] = 1.0
    normals /= n_lens

    n_verts = len(vertices)
    ao_values = np.ones(n_verts, dtype=np.float32)

    adj = [[] for _ in range(n_verts)]
    for f in faces:
        for i in range(3):
            for j in range(3):
                if i != j:
                    adj[f[i]].append(f[j])

    for vi in range(n_verts):
        if not adj[vi]:
            continue
        neighbors = np.array(list(set(adj[vi])))
        deltas = vertices[neighbors] - vertices[vi]
        dots = (deltas * normals[vi]).sum(axis=1)
        concavity = np.clip(dots.mean() / (np.linalg.norm(deltas, axis=1).mean() + 1e-6), -1, 1)
        ao_values[vi] = np.clip(0.5 + concavity * 0.5, 0.2, 1.0)

    ao_map = np.full((atlas_size, atlas_size), 255, dtype=np.uint8)
    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

    for i in range(n_verts):
        ao_map[v_px[i], u_px[i]] = int(ao_values[i] * 255)

    kernel_size = atlas_size // 64 | 1
    ao_map = cv2.GaussianBlur(ao_map, (kernel_size, kernel_size), 0)
    return ao_map


def _generate_normal_map(vertices, faces, uvs, atlas_size):
    """Generate tangent-space normal map from mesh geometry."""
    normal_map = np.full((atlas_size, atlas_size, 3), 128, dtype=np.uint8)
    normal_map[:, :, 2] = 255

    # Compute smooth normals
    norms = np.zeros_like(vertices, dtype=np.float32)
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    fn_lens = np.linalg.norm(fn, axis=1, keepdims=True)
    fn_lens[fn_lens < 1e-10] = 1.0
    fn /= fn_lens
    for i in range(3):
        np.add.at(norms, faces[:, i], fn)
    n_lens = np.linalg.norm(norms, axis=1, keepdims=True)
    n_lens[n_lens < 1e-10] = 1.0
    norms /= n_lens

    for fi in range(len(faces)):
        f = faces[fi]
        for vi in f:
            uv = uvs[vi]
            tx = int(np.clip(uv[0] * (atlas_size - 1), 0, atlas_size - 1))
            ty = int(np.clip((1 - uv[1]) * (atlas_size - 1), 0, atlas_size - 1))
            n = norms[vi]
            normal_map[ty, tx, 0] = int(np.clip((n[0] * 0.5 + 0.5) * 255, 0, 255))
            normal_map[ty, tx, 1] = int(np.clip((n[1] * 0.5 + 0.5) * 255, 0, 255))
            normal_map[ty, tx, 2] = int(np.clip((n[2] * 0.5 + 0.5) * 255, 0, 255))

    return normal_map


def _run_pbr_textures(inp):
    """Generate complete PBR texture set (albedo, normal, roughness, AO) on GPU."""
    try:
        albedo_b64 = inp.get('albedo_b64')
        uvs_b64 = inp.get('uvs_b64')
        uvs_shape = inp.get('uvs_shape')
        verts_b64 = inp.get('vertices_b64')
        verts_shape = inp.get('vertices_shape')
        faces_b64 = inp.get('faces_b64')
        faces_shape = inp.get('faces_shape')

        if not all([albedo_b64, uvs_b64, verts_b64, faces_b64]):
            return {'status': 'error', 'message': 'Missing required inputs (albedo, uvs, vertices, faces)'}

        albedo = _decode_image(albedo_b64)
        uvs = np.frombuffer(base64.b64decode(uvs_b64), dtype=np.float32).reshape(uvs_shape)
        vertices = np.frombuffer(base64.b64decode(verts_b64), dtype=np.float32).reshape(verts_shape)
        faces = np.frombuffer(base64.b64decode(faces_b64), dtype=np.int32).reshape(faces_shape)

        atlas_size = inp.get('atlas_size', 2048)
        upscale = inp.get('upscale', True)
        target_size = inp.get('target_size', 4096)

        roughness_map = _generate_roughness_map(vertices, faces, uvs, atlas_size)
        ao_map = _generate_ao_map(vertices, faces, uvs, atlas_size)
        normal_map = _generate_normal_map(vertices, faces, uvs, atlas_size)

        result_maps = {
            'albedo': albedo,
            'normal': normal_map,
            'roughness': roughness_map,
            'ao': ao_map,
        }

        if upscale:
            upsampler = _load_realesrgan()
            for name, img in result_maps.items():
                if img is None:
                    continue
                if len(img.shape) == 2:
                    img_3ch = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                else:
                    img_3ch = img
                upscaled, _ = upsampler.enhance(img_3ch, outscale=4)
                h, w = upscaled.shape[:2]
                if max(h, w) > target_size:
                    scale = target_size / max(h, w)
                    upscaled = cv2.resize(upscaled, (int(w * scale), int(h * scale)),
                                          interpolation=cv2.INTER_LANCZOS4)
                if name in ('roughness', 'ao') and len(upscaled.shape) == 3:
                    upscaled = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
                result_maps[name] = upscaled
                logger.info(f"Upscaled {name}: {img.shape[:2]} -> {upscaled.shape[:2]}")

        encoded = {}
        for name, img in result_maps.items():
            if img is not None:
                encoded[name] = {
                    'texture_b64': _encode_image(img, quality=95),
                    'shape': list(img.shape),
                }

        return {'status': 'success', 'textures': encoded}

    except Exception as e:
        logger.error(f"PBR texture generation failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}


runpod.serverless.start({"handler": handler})
