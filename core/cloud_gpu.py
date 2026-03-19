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

RUNPOD_API_KEY = os.environ.get('RUNPOD_API_KEY', '')
RUNPOD_ENDPOINT = os.environ.get('RUNPOD_ENDPOINT', '')
RUNPOD_BASE_URL = 'https://api.runpod.ai/v2'

# Timeout for polling results (seconds)
POLL_TIMEOUT = 120
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

    url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/runsync"
    headers = {
        'Authorization': f'Bearer {RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }

    data = json.dumps(payload).encode('utf-8')
    logger.info(f"Sending {len(data) / 1024:.0f}KB to RunPod ({len(images_dict)} images, "
                f"tasks={tasks})")

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        # Use runsync for fast requests (< 30s), fall back to async for longer
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 408 or 'timeout' in str(e).lower():
                # Switch to async mode
                logger.info("Sync timed out, switching to async...")
                return _run_async(payload, headers)
            raise

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

        result['hmr'] = {
            'betas': np.array(hmr['betas'], dtype=np.float32),
            'vertices': verts,
            'pose': np.zeros(72, dtype=np.float32),
            'joints_3d': None,
            'confidence': hmr.get('confidence', 0.85),
            'backend': hmr.get('backend', 'hmr2_cloud'),
        }

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

    return result


def is_configured():
    """Check if RunPod cloud GPU is configured."""
    return bool(RUNPOD_API_KEY and RUNPOD_ENDPOINT)
