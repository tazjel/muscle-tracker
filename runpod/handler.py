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

    logger.info("Done — returning results")
    return result


runpod.serverless.start({"handler": handler})
