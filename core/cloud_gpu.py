"""
cloud_gpu.py — RunPod serverless client for GPU-heavy inference.

Sends body photos to RunPod cloud GPU, receives SMPL params + masks + normals.
Photos are sent as base64 over HTTPS, processed in-memory on RunPod, never saved to disk.

Usage:
    from core.cloud_gpu import cloud_inference
    result = cloud_inference(images_dict, tasks=['hmr', 'rembg', 'dsine'])

Environment variables:
    RUNPOD_API_KEY    — your RunPod API key
    RUNPOD_ENDPOINT   — your serverless endpoint ID (e.g., "abc123xyz")
"""
import os
import base64
import json
import time
import logging
import numpy as np
import cv2

logger = logging.getLogger('cloud_gpu')

def _load_env():
    """Manual .env loader to avoid new dependencies."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base, '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"\'')
_load_env()

RUNPOD_API_KEY = os.environ.get('RUNPOD_API_KEY', '')
RUNPOD_ENDPOINT = os.environ.get('RUNPOD_ENDPOINT', '')
RUNPOD_BASE_URL = 'https://api.runpod.ai/v2'

# Timeout for polling results (seconds)
POLL_TIMEOUT = 180  # 3 minutes — PBR + upscale can take 2 minutes
POLL_INTERVAL = 2


def _encode_image(img_bgr, max_dim=1024, quality=85):
    """BGR image → base64 JPEG string. Resize if too large."""
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf.tobytes()).decode('ascii')


def _decode_mask(b64_str):
    """Base64 PNG → uint8 mask array."""
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)


def _decode_normal_image(b64_str):
    """Base64 JPEG normal image → float32 [-1, 1] array."""
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    # [0,255] → [-1,1]
    return (img.astype(np.float32) / 127.5) - 1.0


def _decode_vertices(b64_str, shape):
    """Base64 float32 buffer → numpy array."""
    buf = base64.b64decode(b64_str)
    return np.frombuffer(buf, dtype=np.float32).reshape(shape)


def cloud_inference(images_dict, tasks=None):
    """
    Send body photos to RunPod for GPU inference.

    Args:
        images_dict: dict {direction: BGR ndarray} — body photos
        tasks: list of str — ['hmr', 'rembg', 'dsine']. Default: ['hmr', 'rembg']

    Returns:
        dict with:
            'hmr': {betas, vertices, confidence, backend} — if 'hmr' in tasks
            'masks': {direction: uint8 mask} — if 'rembg' in tasks
            'normals': {direction: float32 normal map} — if 'dsine' in tasks
        or None on failure
    """
    if tasks is None:
        tasks = ['hmr', 'rembg']

    if not RUNPOD_API_KEY or not RUNPOD_ENDPOINT:
        logger.error("RUNPOD_API_KEY and RUNPOD_ENDPOINT must be set. "
                      "Get these from console.runpod.io")
        return None

    # Encode images as base64
    images_b64 = {}
    for direction, img in images_dict.items():
        images_b64[direction] = _encode_image(img)
        logger.info(f"Encoded {direction}: {img.shape} → base64")

    # Build request payload
    payload = {
        'input': {
            'images': images_b64,
            'tasks': tasks,
        }
    }

    # Send to RunPod
    import urllib.request
    import urllib.error
    import socket

    headers = {
        'Authorization': f'Bearer {RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }

    data = json.dumps(payload).encode('utf-8')
    logger.info(f"Sending {len(data) / 1024:.0f}KB to RunPod ({len(images_dict)} images, "
                f"tasks={tasks})")

    # Multi-task requests (HMR+rembg+DSINE) take 50-70s — use async directly
    if len(tasks) > 1:
        logger.info("Multi-task request → using async endpoint")
        return _run_async(payload, headers)

    url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/runsync"
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        # Use runsync for fast single-task requests (< 60s)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 408 or 'timeout' in str(e).lower():
                logger.info("Sync timed out, switching to async...")
                return _run_async(payload, headers)
            raise
        except (socket.timeout, urllib.error.URLError) as e:
            if 'timed out' in str(e).lower():
                logger.info("Sync timed out, switching to async...")
                return _run_async(payload, headers)
            logger.error(f"RunPod request failed: {e}")
            return None

    except Exception as e:
        logger.error(f"RunPod request failed: {e}")
        return None

    # Check response
    status = result.get('status')
    if status == 'COMPLETED':
        return _parse_output(result.get('output', {}))
    elif status in ('IN_QUEUE', 'IN_PROGRESS'):
        # Poll for result
        job_id = result.get('id')
        return _poll_result(job_id, headers)
    else:
        logger.error(f"RunPod returned status={status}: {result}")
        return None


def _run_async(payload, headers):
    """Submit async job and poll for result."""
    import urllib.request

    url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/run"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())

    job_id = result.get('id')
    if not job_id:
        logger.error(f"No job ID in async response: {result}")
        return None

    return _poll_result(job_id, headers)


def _poll_result(job_id, headers):
    """Poll RunPod for job completion."""
    import urllib.request

    url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/status/{job_id}"
    start = time.time()

    while time.time() - start < POLL_TIMEOUT:
        req = urllib.request.Request(url, headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        status = result.get('status')
        if status == 'COMPLETED':
            return _parse_output(result.get('output', {}))
        elif status in ('FAILED', 'CANCELLED'):
            logger.error(f"RunPod job {status}: {result}")
            return None

        logger.info(f"Job {job_id}: {status}, waiting...")
        time.sleep(POLL_INTERVAL)

    logger.error(f"RunPod job {job_id} timed out after {POLL_TIMEOUT}s")
    return None


def _run_async_raw(payload, headers):
    """Submit async job and poll, returning raw RunPod response."""
    import urllib.request
    url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/run"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    job_id = result.get('id')
    if not job_id:
        return None
    return _poll_result_raw(job_id, headers)


def _poll_result_raw(job_id, headers):
    """Poll RunPod for job completion, returning raw output dict."""
    import urllib.request
    url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/status/{job_id}"
    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        req = urllib.request.Request(url, headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        status = result.get('status')
        if status == 'COMPLETED':
            return result.get('output', {})
        elif status in ('FAILED', 'CANCELLED'):
            logger.error("RunPod job %s: %s", job_id, status)
            return None
        time.sleep(POLL_INTERVAL)
    logger.error("RunPod job %s timed out", job_id)
    return None


def _parse_output(output):
    """Convert RunPod response back to numpy arrays."""
    if output.get('status') != 'success':
        logger.error(f"RunPod worker error: {output.get('message')}")
        return None

    result = {}

    # Parse HMR results
    if 'hmr' in output:
        hmr = output['hmr']
        verts = None
        if hmr.get('vertices_b64') and hmr.get('vertices_shape'):
            verts = _decode_vertices(hmr['vertices_b64'], hmr['vertices_shape'])
        
        posed_verts = None
        if hmr.get('vertices_posed_b64') and hmr.get('vertices_shape'):
            posed_verts = _decode_vertices(hmr['vertices_posed_b64'], hmr['vertices_shape'])

        result['hmr'] = {
            'betas': np.array(hmr['betas'], dtype=np.float32),
            'vertices': verts,
            'vertices_posed': posed_verts,
            'pose': np.zeros(72, dtype=np.float32),
            'joints_3d': None,
            'confidence': hmr.get('confidence', 0.85),
            'backend': hmr.get('backend', 'hmr2_cloud'),
        }

    # ... (rest of parsing) ...

    # Parse body masks
    if 'masks' in output:
        result['masks'] = {}
        for direction, mask_b64 in output['masks'].items():
            result['masks'][direction] = _decode_mask(mask_b64)

    # Parse normal maps
    if 'normals' in output:
        result['normals'] = {}
        for direction, normal_b64 in output['normals'].items():
            result['normals'][direction] = _decode_normal_image(normal_b64)

    # Parse texture upscale result
    if 'texture_upscale' in output:
        result['texture_upscale'] = output['texture_upscale']

    # Parse normal_from_depth result (same format as normals)
    if 'normal_from_depth' in output:
        result['normals'] = {}
        for direction, normal_b64 in output['normal_from_depth'].items():
            result['normals'][direction] = _decode_normal_image(normal_b64)

    # Parse PBR texture generation result
    if 'pbr_textures' in output:
        result['pbr_textures'] = output['pbr_textures']

    return result


def cloud_texture_upscale(texture_bgr, target_size=4096):
    """
    Upscale a texture atlas using Real-ESRGAN on RunPod GPU.

    Args:
        texture_bgr: BGR numpy array (the texture to upscale)
        target_size: max dimension after upscaling (default 4096)

    Returns:
        Upscaled BGR numpy array, or None on failure.
    """
    if not is_configured():
        logger.warning("RunPod not configured, cannot cloud upscale")
        return None

    import urllib.request
    import urllib.error

    # Encode texture at full resolution (no downscale — we want max quality)
    _, buf = cv2.imencode('.png', texture_bgr)
    texture_b64 = base64.b64encode(buf.tobytes()).decode('ascii')

    payload = {
        'input': {
            'images': {},
            'tasks': ['texture_upscale'],
            'texture_b64': texture_b64,
            'target_size': target_size,
        }
    }

    headers = {
        'Authorization': f'Bearer {RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }
    data = json.dumps(payload).encode('utf-8')
    logger.info("Sending %.0fKB texture to RunPod for upscaling", len(data) / 1024)

    try:
        url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/runsync"
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 408 or 'timeout' in str(e).lower():
                logger.info("Sync timed out, switching to async for upscale...")
                result = _run_async_raw(payload, headers)
            else:
                raise

        if result is None:
            return None

        status = result.get('status')
        if status == 'COMPLETED':
            output = result.get('output', {})
        elif status in ('IN_QUEUE', 'IN_PROGRESS'):
            job_id = result.get('id')
            output = _poll_result_raw(job_id, headers)
        else:
            logger.error("RunPod upscale returned status=%s", status)
            return None

        if output is None:
            return None

        upscale_data = output.get('texture_upscale', {})
        if upscale_data.get('status') != 'success':
            logger.error("Upscale failed: %s", upscale_data.get('message'))
            return None

        # Decode the upscaled texture
        img_bytes = base64.b64decode(upscale_data['texture_b64'])
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        upscaled = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        logger.info("Cloud upscale: %s → %s", texture_bgr.shape[:2], upscaled.shape[:2])
        return upscaled

    except Exception as e:
        logger.error("Cloud texture upscale failed: %s", e)
        return None


def cloud_pbr_textures(albedo_bgr, uvs, vertices, faces,
                        normal_map_bgr=None, atlas_size=2048, upscale=True, target_size=4096):
    """
    Generate full PBR texture set on RunPod GPU.

    Args:
        albedo_bgr: BGR numpy array (photo-projected albedo texture)
        uvs: float32 (N, 2) UV coordinates
        vertices: float32 (N, 3) mesh vertices
        faces: int32 (F, 3) face indices
        normal_map_bgr: optional pre-computed normal map (e.g. from DSINE)
        atlas_size: base atlas resolution
        upscale: whether to Real-ESRGAN upscale (default True)
        target_size: max dimension after upscale

    Returns:
        Dict with keys 'albedo', 'normal', 'roughness', 'ao' -> BGR numpy arrays.
        Or None on failure.
    """
    if not is_configured():
        logger.warning("RunPod not configured, cannot generate cloud PBR")
        return None

    import urllib.request

    # Encode all arrays as base64
    _, albedo_buf = cv2.imencode('.png', albedo_bgr)
    albedo_b64 = base64.b64encode(albedo_buf.tobytes()).decode('ascii')

    normal_b64 = None
    if normal_map_bgr is not None:
        _, normal_buf = cv2.imencode('.png', normal_map_bgr)
        normal_b64 = base64.b64encode(normal_buf.tobytes()).decode('ascii')

    uvs_b64 = base64.b64encode(uvs.astype(np.float32).tobytes()).decode('ascii')
    verts_b64 = base64.b64encode(vertices.astype(np.float32).tobytes()).decode('ascii')
    faces_b64 = base64.b64encode(faces.astype(np.int32).tobytes()).decode('ascii')

    payload = {
        'input': {
            'images': {},
            'tasks': ['pbr_textures'],
            'albedo_b64': albedo_b64,
            'normal_map_b64': normal_b64,
            'uvs_b64': uvs_b64,
            'uvs_shape': list(uvs.shape),
            'vertices_b64': verts_b64,
            'vertices_shape': list(vertices.shape),
            'faces_b64': faces_b64,
            'faces_shape': list(faces.shape),
            'atlas_size': atlas_size,
            'upscale': upscale,
            'target_size': target_size,
        }
    }

    headers = {
        'Authorization': f'Bearer {RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }
    data = json.dumps(payload).encode('utf-8')
    logger.info("Sending %.0fKB to RunPod for PBR generation", len(data) / 1024)

    try:
        url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/run"  # Use async — PBR takes 30-120s
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        job_id = result.get('id')
        if not job_id:
            logger.error("No job ID in response: %s", result)
            return None

        # Poll with extended timeout (PBR + upscale takes time)
        output = _poll_result_raw(job_id, headers)
        if output is None:
            return None

        pbr_data = output.get('pbr_textures', {})
        if pbr_data.get('status') != 'success':
            logger.error("Cloud PBR failed: %s", pbr_data.get('message'))
            return None

        # Decode texture maps
        textures = {}
        for name, tex_info in pbr_data.get('textures', {}).items():
            img_bytes = base64.b64decode(tex_info['texture_b64'])
            arr = np.frombuffer(img_bytes, dtype=np.uint8)
            textures[name] = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        logger.info("Cloud PBR complete: %s", {k: v.shape for k, v in textures.items()})
        return textures

    except Exception as e:
        logger.error("Cloud PBR generation failed: %s", e)
        return None


def is_configured():
    """Check if RunPod cloud GPU is configured."""
    return bool(RUNPOD_API_KEY and RUNPOD_ENDPOINT)
