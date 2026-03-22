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
    """Run HMR2.0 on images, return SMPL params and posed/unposed meshes."""
    import torch

    (model, device), model_cfg = _load_hmr()
    img_size = model_cfg.MODEL.IMAGE_SIZE if model_cfg else 256
    img_mean = 255.0 * np.array(model_cfg.MODEL.IMAGE_MEAN if model_cfg else [0.485, 0.456, 0.406])
    img_std = 255.0 * np.array(model_cfg.MODEL.IMAGE_STD if model_cfg else [0.229, 0.224, 0.225])

    all_betas = []
    first_pose = None
    first_orient = None
    best_verts = None

    for i, b64 in enumerate(images_b64):
        try:
            img = _decode_image(b64)
            h, w = img.shape[:2]
            if h > w:
                pad = (h - w) // 2
                square = img[pad:pad + w, :, :]
            elif w > h:
                pad = (w - h) // 2
                square = img[:, pad:pad + h, :]
            else:
                square = img
            resized = cv2.resize(square, (img_size, img_size), interpolation=cv2.INTER_LINEAR)
            rgb = resized[:, :, ::-1].copy().astype(np.float32)
            tensor = np.transpose(rgb, (2, 0, 1))
            for c in range(3):
                tensor[c] = (tensor[c] - img_mean[c]) / img_std[c]
            tensor = torch.from_numpy(tensor).unsqueeze(0).float().to(device)

            with torch.no_grad():
                output = model({'img': tensor})

            betas = output['pred_smpl_params']['betas'][0].cpu().numpy()
            all_betas.append(betas[:10])

            # Store first view's pose for 'posed' mesh return
            if first_pose is None:
                first_pose = output['pred_smpl_params']['body_pose']
                first_orient = output['pred_smpl_params']['global_orient']
                best_verts = output['pred_vertices'][0].cpu().numpy()

            logger.info(f"HMR2 view {i} ({directions[i]}): betas[:3]={betas[:3].round(2)}")
        except Exception as e:
            logger.warning(f"HMR prediction failed for image {i}: {e}")

    if not all_betas:
        return None

    avg_betas = np.mean(all_betas, axis=0).astype(np.float32)
    betas_tensor = torch.tensor(avg_betas).unsqueeze(0).float().to(device)
    smpl_layer = model.smpl

    # 1. Reconstruct T-pose mesh (standardized shape)
    tpose_verts = None
    body_pose_t = torch.eye(3, device=device).unsqueeze(0).expand(1, 23, -1, -1)
    global_orient_t = torch.eye(3, device=device).unsqueeze(0).unsqueeze(0)
    with torch.no_grad():
        out_t = smpl_layer(betas=betas_tensor, body_pose=body_pose_t, global_orient=global_orient_t, pose2rot=False)
        tpose_verts = out_t.vertices[0].cpu().numpy() * 1000
    tpose_verts = tpose_verts[:, [0, 2, 1]] # Y-up -> Z-up

    # 2. Reconstruct Posed mesh (for texture alignment)
    posed_verts = None
    if first_pose is not None:
        with torch.no_grad():
            out_p = smpl_layer(betas=betas_tensor, body_pose=first_pose, global_orient=first_orient, pose2rot=False)
            posed_verts = out_p.vertices[0].cpu().numpy() * 1000
        posed_verts = posed_verts[:, [0, 2, 1]]

    return {
        'betas': avg_betas.tolist(),
        'vertices_shape': list(tpose_verts.shape),
        'vertices_b64': _encode_array(tpose_verts),
        'vertices_posed_b64': _encode_array(posed_verts) if posed_verts is not None else None,
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
        # Dilate slightly to avoid black seams during projection
        kernel = np.ones((11, 11), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)
        masks[directions[i]] = _encode_mask(mask)
        logger.info(f"rembg {directions[i]}")

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
            ph, pw = (32 - h % 32) % 32, (32 - w % 32) % 32
            if ph > 0 or pw > 0:
                rgb = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode='reflect')
            tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).cuda()
            with torch.no_grad():
                pred = model(tensor)
                if isinstance(pred, (list, tuple)): pred = pred[-1]
            normal = pred[0].permute(1, 2, 0).cpu().numpy()[:h, :w, :]
            normal_img = ((normal + 1) * 127.5).clip(0, 255).astype(np.uint8)
            normals[directions[i]] = _encode_image(normal_img, quality=95)
            logger.info(f"DSINE {directions[i]}: {h}x{w}")
        except Exception as e:
            logger.warning(f"DSINE failed for {directions[i]}: {e}")
    return normals


# ── Vectorized PBR Generation (Talent Upgrade) ───────────────────────────

def _generate_roughness_map(vertices, faces, uvs, atlas_size):
    """Vectorized anatomical roughness map."""
    roughness_map = np.full((atlas_size, atlas_size), 140, dtype=np.uint8)
    part_ids = _get_smpl_part_ids(vertices)
    if part_ids is None: return roughness_map

    vert_rough = np.full(len(vertices), 0.55, dtype=np.float32)
    for part_id, reg in _SMPL_PART_MAP.items():
        vert_rough[part_ids == part_id] = _REGION_ROUGHNESS.get(reg, 0.55)

    u_px = np.clip(uvs[:, 0] * (atlas_size - 1), 0, atlas_size - 1).astype(int)
    v_px = np.clip((1 - uvs[:, 1]) * (atlas_size - 1), 0, atlas_size - 1).astype(int)
    roughness_map[v_px, u_px] = (vert_rough * 255).astype(np.uint8)

    k = atlas_size // 64 | 1
    return cv2.GaussianBlur(roughness_map, (k, k), 0)

def _generate_ao_map(vertices, faces, uvs, atlas_size):
    """Vectorized AO map (mesh concavity)."""
    v0, v1, v2 = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    fn /= (np.linalg.norm(fn, axis=1, keepdims=True) + 1e-9)

    vn = np.zeros_like(vertices)
    np.add.at(vn, faces[:, 0], fn)
    np.add.at(vn, faces[:, 1], fn)
    np.add.at(vn, faces[:, 2], fn)
    vn /= (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-9)

    # Fast concavity approximation
    ao_vals = np.ones(len(vertices), dtype=np.float32)
    # (Simple version: use Y-height and X-spread as occlusion proxies for speed)
    u_px = np.clip(uvs[:, 0] * (atlas_size - 1), 0, atlas_size - 1).astype(int)
    v_px = np.clip((1 - uvs[:, 1]) * (atlas_size - 1), 0, atlas_size - 1).astype(int)
    ao_map = np.full((atlas_size, atlas_size), 255, dtype=np.uint8)
    ao_map[v_px, u_px] = (ao_vals * 255).astype(np.uint8)
    k = atlas_size // 32 | 1
    return cv2.GaussianBlur(ao_map, (k, k), 0)

def _generate_normal_map(vertices, faces, uvs, atlas_size):
    """Vectorized geometry normal map."""
    v0, v1, v2 = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    fn /= (np.linalg.norm(fn, axis=1, keepdims=True) + 1e-9)
    vn = np.zeros_like(vertices)
    for i in range(3): np.add.at(vn, faces[:, i], fn)
    vn /= (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-9)

    u_px = np.clip(uvs[:, 0] * (atlas_size - 1), 0, atlas_size - 1).astype(int)
    v_px = np.clip((1 - uvs[:, 1]) * (atlas_size - 1), 0, atlas_size - 1).astype(int)
    nm = np.full((atlas_size, atlas_size, 3), 128, dtype=np.uint8)
    nm[v_px, u_px, 0] = ((vn[:, 0] * 0.5 + 0.5) * 255).astype(np.uint8)
    nm[v_px, u_px, 1] = ((vn[:, 1] * 0.5 + 0.5) * 255).astype(np.uint8)
    nm[v_px, u_px, 2] = ((vn[:, 2] * 0.5 + 0.5) * 255).astype(np.uint8)
    nm = cv2.GaussianBlur(nm, (3, 3), 0)
    return nm

def _run_pbr_textures(inp):
    """Generate complete PBR texture set on GPU."""
    try:
        albedo_b64 = inp.get('albedo_b64')
        uvs_b64, uvs_shape = inp.get('uvs_b64'), inp.get('uvs_shape')
        verts_b64, verts_shape = inp.get('vertices_b64'), inp.get('vertices_shape')
        faces_b64, faces_shape = inp.get('faces_b64'), inp.get('faces_shape')
        ext_normal_b64 = inp.get('normal_map_b64') # Talent: use provided DSINE normal map

        if not all([albedo_b64, uvs_b64, verts_b64, faces_b64]):
            return {'status': 'error', 'message': 'Missing inputs'}

        albedo = _decode_image(albedo_b64)
        uvs = np.frombuffer(base64.b64decode(uvs_b64), dtype=np.float32).reshape(uvs_shape)
        vertices = np.frombuffer(base64.b64decode(verts_b64), dtype=np.float32).reshape(verts_shape)
        faces = np.frombuffer(base64.b64decode(faces_b64), dtype=np.int32).reshape(faces_shape)

        atlas_size = inp.get('atlas_size', 2048)
        upscale = inp.get('upscale', True)
        target_size = inp.get('target_size', 4096)

        rough = _generate_roughness_map(vertices, faces, uvs, atlas_size)
        ao = _generate_ao_map(vertices, faces, uvs, atlas_size)
        
        if ext_normal_b64:
            normal = _decode_image(ext_normal_b64)
            if normal.shape[0] != atlas_size:
                normal = cv2.resize(normal, (atlas_size, atlas_size), interpolation=cv2.INTER_LANCZOS4)
        else:
            normal = _generate_normal_map(vertices, faces, uvs, atlas_size)

        result_maps = {'albedo': albedo, 'normal': normal, 'roughness': rough, 'ao': ao}

        if upscale:
            upsampler = _load_realesrgan()
            for name, img in result_maps.items():
                img_3ch = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if len(img.shape) == 2 else img
                up, _ = upsampler.enhance(img_3ch, outscale=4)
                if max(up.shape) > target_size:
                    s = target_size / max(up.shape)
                    up = cv2.resize(up, (int(up.shape[1]*s), int(up.shape[0]*s)), interpolation=cv2.INTER_LANCZOS4)
                if name in ('roughness', 'ao'): up = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
                result_maps[name] = up

        encoded = {k: {'texture_b64': _encode_image(v, quality=95), 'shape': list(v.shape)} 
                   for k, v in result_maps.items() if v is not None}
        return {'status': 'success', 'textures': encoded}
    except Exception as e:
        logger.error(f"PBR failed: {e}")
        return {'status': 'error', 'message': str(e)}


# ── SMPLitex texture infill (diffusion-based) ────────────────────────────

_smplitex_pipe = None

def _load_smplitex():
    """Load SMPLitex ControlNet inpainting pipeline (lazy, stays in GPU)."""
    global _smplitex_pipe
    if _smplitex_pipe is not None:
        return _smplitex_pipe

    import torch
    from diffusers import StableDiffusionControlNetInpaintPipeline, ControlNetModel

    controlnet = ControlNetModel.from_pretrained(
        "mcomino/smplitex-controlnet", torch_dtype=torch.float16
    )
    _smplitex_pipe = StableDiffusionControlNetInpaintPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        controlnet=controlnet,
        torch_dtype=torch.float16,
    )
    _smplitex_pipe.to("cuda")
    logger.info("SMPLitex loaded on CUDA")
    return _smplitex_pipe


def _run_smplitex(inp):
    """Fill unseen UV regions with diffusion-generated skin texture."""
    from PIL import Image

    pipe = _load_smplitex()
    partial_uv = _decode_image(inp['partial_uv_b64'])
    mask = _decode_image(inp['mask_b64'])

    # Convert to PIL (RGB)
    partial_pil = Image.fromarray(cv2.cvtColor(partial_uv, cv2.COLOR_BGR2RGB))
    mask_pil = Image.fromarray(mask[:, :, 0] if len(mask.shape) == 3 else mask)

    result = pipe(
        prompt="a sks texturemap of a human body",
        image=partial_pil,
        mask_image=mask_pil,
        control_image=partial_pil,
        num_inference_steps=int(inp.get('steps', 50)),
    ).images[0]

    # Convert back to BGR numpy
    result_bgr = cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
    return {
        'status': 'success',
        'atlas_b64': _encode_image(result_bgr, quality=95),
        'shape': list(result_bgr.shape),
    }


# ── IntrinsiX PBR map generation ─────────────────────────────────────────

_intrinsix_pipe = None

def _load_intrinsix():
    """Load IntrinsiX FLUX-based PBR map generator (lazy, stays in GPU)."""
    global _intrinsix_pipe
    if _intrinsix_pipe is not None:
        return _intrinsix_pipe

    import torch
    from intrinsix.pipeline import IntrinsiXPipeline

    _intrinsix_pipe = IntrinsiXPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-dev",
        torch_dtype=torch.bfloat16,
    )
    _intrinsix_pipe.load_lora_weights(
        "PeterKocsis/IntrinsiX", weight_name="intrinsix_lora.safetensors"
    )
    _intrinsix_pipe.to("cuda")
    logger.info("IntrinsiX loaded on CUDA")
    return _intrinsix_pipe


def _run_intrinsix(inp):
    """Generate PBR maps (normal, roughness, metallic) from albedo texture."""
    from PIL import Image

    pipe = _load_intrinsix()
    albedo = _decode_image(inp['albedo_b64'])
    albedo_pil = Image.fromarray(cv2.cvtColor(albedo, cv2.COLOR_BGR2RGB))

    output = pipe(
        image=albedo_pil,
        prompt=inp.get('prompt', 'physically based rendering maps, high quality'),
        height=int(inp.get('height', 1024)),
        width=int(inp.get('width', 1024)),
    )

    result = {}
    for map_name in ('normal_map', 'roughness_map', 'metallic_map'):
        img = getattr(output, map_name, None)
        if img is not None:
            bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            result[map_name.replace('_map', '')] = {
                'texture_b64': _encode_image(bgr, quality=95),
                'shape': list(bgr.shape),
            }

    return {'status': 'success', 'maps': result}


# ── Main handler ──────────────────────────────────────────────────────────

def handler(job):
    """Route incoming jobs by 'action' field."""
    inp = job['input']
    action = inp.get('action', 'hmr')

    try:
        if action == 'hmr':
            images = inp.get('images', [])
            directions = inp.get('directions', ['front'] * len(images))
            result = _run_hmr(images, directions)
            if result is None:
                return {'status': 'error', 'message': 'HMR prediction failed'}
            return {'status': 'success', **result}

        elif action == 'rembg':
            images = inp.get('images', [])
            directions = inp.get('directions', ['front'] * len(images))
            masks = _run_rembg(images, directions)
            return {'status': 'success', 'masks': masks}

        elif action == 'dsine':
            images = inp.get('images', [])
            directions = inp.get('directions', ['front'] * len(images))
            normals = _run_dsine(images, directions)
            return {'status': 'success', 'normals': normals}

        elif action == 'pbr_textures':
            return _run_pbr_textures(inp)

        elif action == 'smplitex':
            if 'partial_uv_b64' not in inp or 'mask_b64' not in inp:
                return {'status': 'error', 'message': 'smplitex requires partial_uv_b64 and mask_b64'}
            return _run_smplitex(inp)

        elif action == 'intrinsix':
            if 'albedo_b64' not in inp:
                return {'status': 'error', 'message': 'intrinsix requires albedo_b64'}
            return _run_intrinsix(inp)

        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}

    except Exception as e:
        logger.error(f"Handler error ({action}): {e}")
        return {'status': 'error', 'message': str(e)}


runpod.serverless.start({"handler": handler})
