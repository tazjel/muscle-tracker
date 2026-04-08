"""
hmr_shape.py — Predict SMPL body shape from photos using HMR2.0/TokenHMR.

Input: 1-4 BGR images (np.ndarray) with direction labels
Output: dict with 'betas' (10,), 'vertices' (6890,3), 'joints' (24,3), 'pose' (72,)

Falls back to MediaPipe keypoint → SMPL optimization if HMR2.0 unavailable.
"""
import logging
import cv2
import os

logger = logging.getLogger(__name__)

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

# Lazy-load heavy imports
_hmr_model = None
_hmr_backend = None  # 'hmr2' | 'keypoint'
_hmr_cfg = None


def _load_hmr():
    """Try HMR2.0 (4D-Humans) → keypoint fallback."""
    global _hmr_model, _hmr_backend, _hmr_cfg
    if _hmr_model is not None:
        return

    # Try HMR2.0 via 4D-Humans
    try:
        from hmr2.configs import CACHE_DIR_4DHUMANS
        from hmr2.models import download_models, load_hmr2, DEFAULT_CHECKPOINT
        import torch

        # Download model weights if not cached (~2.5GB first time)
        download_models(CACHE_DIR_4DHUMANS)
        model, model_cfg = load_hmr2(DEFAULT_CHECKPOINT)

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model = model.to(device).eval()
        _hmr_model = (model, device)
        _hmr_backend = 'hmr2'
        _hmr_cfg = model_cfg
        logger.info(f"HMR2.0 (4D-Humans) loaded on {device}")
        return
    except Exception as e:
        logger.warning(f"HMR2.0 unavailable: {e}")

    # Keypoint fallback
    _hmr_backend = 'keypoint'
    _hmr_model = True  # sentinel
    logger.info("HMR2.0 not installed — using MediaPipe keypoint fallback for shape estimation")


def predict_shape(images, directions=None, prefer_gpu='local'):
    """
    Predict SMPL body shape from 1-4 images.

    Args:
        images: list of (H,W,3) uint8 BGR arrays
        directions: list of str ('front','back','left','right'), same len as images
                    If None, assumes ['front'] for 1 image, etc.
        prefer_gpu: 'local' (default — use local HMR2.0/keypoint, never RunPod),
                    'runpod' (force RunPod CameraHMR),
                    'auto' (try local first, RunPod only if local fails)

    Returns:
        dict with keys:
            'betas': (10,) float32 — SMPL shape blend weights
            'vertices': (6890, 3) float32 — SMPL mesh vertices (mm), or None
            'pose': (72,) float32 — SMPL pose params (axis-angle per joint)
            'joints_3d': (24, 3) float32 — 3D joint positions (mm), or None
            'confidence': float — 0-1 prediction confidence
            'backend': str — which method was used
        or None on failure
    """
    # LOCAL FIRST: Only use RunPod when explicitly requested
    if prefer_gpu == 'runpod':
        result = _predict_runpod_hmr(images, directions)
        if result is not None:
            return result
        logger.warning("RunPod CameraHMR failed and prefer_gpu='runpod', returning None")
        return None


    # Local inference (default path)
    _load_hmr()
    if _hmr_backend in ('hmr2', 'tokenhmr'):
        result = _predict_hmr(images, directions)
    else:
        result = _predict_keypoint(images, directions)

    # Auto mode: if local failed, try RunPod as last resort
    if result is None and prefer_gpu == 'auto':
        logger.info("Local HMR failed, trying RunPod as last resort...")
        result = _predict_runpod_hmr(images, directions)

    return result


def _predict_runpod_hmr(images, directions):
    """
    Run shape prediction on RunPod GPU (CameraHMR or HMR2.0).

    CameraHMR uses 138 dense keypoints for better shape estimation,
    especially for body volume/muscularity capture.
    """
    import os
    import base64

    endpoint_id = os.environ.get('RUNPOD_ENDPOINT_ID', '')
    api_key = os.environ.get('RUNPOD_API_KEY', '')
    if not endpoint_id or not api_key:
        return None

    try:
        import requests

        # Encode images to base64
        images_b64 = []
        for img in images:
            _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            images_b64.append(base64.b64encode(buf.tobytes()).decode('ascii'))

        dirs = directions or ['front'] * len(images)

        url = f"https://api.runpod.ai/v2/{endpoint_id}/runsync"
        resp = requests.post(url, json={
            'input': {
                'action': 'hmr',
                'images': images_b64,
                'directions': dirs,
            }
        }, headers={'Authorization': f'Bearer {api_key}'}, timeout=120)

        data = resp.json()
        output = data.get('output', {})
        if output.get('status') != 'success':
            logger.warning(f"RunPod HMR failed: {output.get('message', 'unknown')}")
            return None

        betas = np.array(output['betas'], dtype=np.float32)

        # Decode vertices if present
        verts = None
        if output.get('vertices_b64'):
            verts_shape = output.get('vertices_shape', [6890, 3])
            verts = np.frombuffer(
                base64.b64decode(output['vertices_b64']), dtype=np.float32
            ).reshape(verts_shape)

        logger.info(f"RunPod HMR: betas[:3]={betas[:3].round(2)}, backend={output.get('backend', 'hmr2')}")

        return {
            'betas': betas,
            'vertices': verts,
            'pose': np.zeros(72, dtype=np.float32),
            'joints_3d': None,
            'confidence': float(output.get('confidence', 0.85)),
            'backend': f"runpod_{output.get('backend', 'hmr2')}",
        }

    except Exception as e:
        logger.warning(f"RunPod HMR call failed: {e}")
        return None


def _predict_hmr(images, directions):
    """Run HMR2.0 (4D-Humans) on each image, average betas across views."""
    import torch
    model, device = _hmr_model

    # 4D-Humans uses ViTDetDataset for preprocessing — we replicate it here
    # since our scan photos have the person centered (no detectron2 needed)
    img_size = _hmr_cfg.MODEL.IMAGE_SIZE if _hmr_cfg else 256
    img_mean = 255.0 * np.array(_hmr_cfg.MODEL.IMAGE_MEAN if _hmr_cfg else [0.485, 0.456, 0.406])
    img_std = 255.0 * np.array(_hmr_cfg.MODEL.IMAGE_STD if _hmr_cfg else [0.229, 0.224, 0.225])

    all_betas = []
    best_verts = None
    best_joints = None

    for i, img in enumerate(images):
        try:
            h, w = img.shape[:2]

            # Person is centered in scan photos — use full image as bbox
            # Crop to square (centered), then resize to img_size
            if h > w:
                pad = (h - w) // 2
                square = img[pad:pad+w, :, :]
            elif w > h:
                pad = (w - h) // 2
                square = img[:, pad:pad+h, :]
            else:
                square = img

            # Resize to model input size (typically 256x256)
            resized = cv2.resize(square, (img_size, img_size), interpolation=cv2.INTER_LINEAR)

            # BGR → RGB, then to (3, H, W) float tensor
            rgb = resized[:, :, ::-1].copy().astype(np.float32)
            tensor = np.transpose(rgb, (2, 0, 1))  # (3, H, W)

            # Normalize with ImageNet stats (applied to 0-255 range)
            for c in range(3):
                tensor[c] = (tensor[c] - img_mean[c]) / img_std[c]

            tensor = torch.from_numpy(tensor).unsqueeze(0).float().to(device)

            # 4D-Humans forward expects batch dict with 'img' key
            batch = {'img': tensor}
            with torch.no_grad():
                output = model(batch)

            betas = output['pred_smpl_params']['betas'][0].cpu().numpy()
            all_betas.append(betas[:10])

            # Keep vertices from front view (or first successful)
            if best_verts is None:
                best_verts = output['pred_vertices'][0].cpu().numpy()
                if 'pred_keypoints_3d' in output:
                    best_joints = output['pred_keypoints_3d'][0, :24].cpu().numpy()

            logger.info(f"HMR2 prediction {i} ({directions[i] if directions else '?'}): "
                        f"betas[:3]={betas[:3].round(2)}")

        except Exception as e:
            logger.warning(f"HMR prediction failed for image {i}: {e}")
            continue

    if not all_betas:
        logger.error("All HMR predictions failed")
        return None

    # Average betas across views for robustness
    avg_betas = np.mean(all_betas, axis=0).astype(np.float32)
    logger.info(f"HMR2 averaged betas from {len(all_betas)} views: {avg_betas[:3].round(2)}")

    # Use HMR2's own SMPL to reconstruct with averaged betas
    verts = None
    joints = None
    try:
        # The model has its own SMPL layer — recompute with averaged betas
        import torch as th
        betas_tensor = th.tensor(avg_betas).unsqueeze(0).float().to(device)
        # Use neutral pose (T-pose) for body shape
        smpl_layer = model.smpl
        body_pose = th.eye(3, device=device).unsqueeze(0).expand(1, 23, -1, -1)
        global_orient = th.eye(3, device=device).unsqueeze(0).unsqueeze(0)
        with th.no_grad():
            smpl_out = smpl_layer(betas=betas_tensor, body_pose=body_pose,
                                  global_orient=global_orient, pose2rot=False)
            verts = smpl_out.vertices[0].cpu().numpy() * 1000  # m → mm
            joints = smpl_out.joints[0, :24].cpu().numpy() * 1000
        # SMPL is Y-up, our pipeline is Z-up — swap Y↔Z
        verts = verts[:, [0, 2, 1]]  # (X, Y, Z) → (X, Z, Y)
        if joints is not None:
            joints = joints[:, [0, 2, 1]]
        logger.info(f"SMPL mesh reconstructed: {verts.shape[0]} verts, "
                    f"height={verts[:,2].max()-verts[:,2].min():.0f}mm")
    except Exception as e:
        logger.warning(f"SMPL reconstruction with averaged betas failed: {e}")
        # Fall back to raw HMR vertices
        if best_verts is not None:
            verts = best_verts * 1000
            verts = verts[:, [0, 2, 1]]  # Y-up → Z-up
            if best_joints is not None:
                joints = best_joints * 1000
                joints = joints[:, [0, 2, 1]]

    return {
        'betas': avg_betas,
        'vertices': verts,
        'pose': np.zeros(72, dtype=np.float32),  # T-pose for shape comparison
        'joints_3d': joints,
        'confidence': 0.85,  # HMR2.0 is generally high confidence
        'backend': 'hmr2',
    }


def _predict_keypoint(images, directions):
    """
    Fallback: Use MediaPipe pose keypoints to estimate body proportions,
    then solve for SMPL betas that match those proportions.
    Less accurate but requires no model downloads.
    """
    try:
        import mediapipe as mp
    except ImportError:
        logger.warning("MediaPipe not available for keypoint fallback")
        return None

    # Use first (front) image
    img = images[0]
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # MediaPipe API changed: try new API first, then legacy
    try:
        # New API (mediapipe >= 0.10.14)
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions
        from mediapipe.tasks.python import BaseOptions
        import mediapipe.tasks.python.vision as vision
        import os

        model_path = os.path.join(os.path.dirname(mp.__file__),
                                  'modules', 'pose_landmarker', 'pose_landmarker_heavy.task')
        if not os.path.exists(model_path):
            # Try to find any pose model
            model_path = None
            for root, dirs, files in os.walk(os.path.dirname(mp.__file__)):
                for f in files:
                    if 'pose_landmarker' in f and f.endswith('.task'):
                        model_path = os.path.join(root, f)
                        break
                if model_path:
                    break

        if model_path:
            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                num_poses=1,
            )
            with PoseLandmarker.create_from_options(options) as landmarker:
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                detection = landmarker.detect(mp_image)
                if not detection.pose_landmarks:
                    logger.error("MediaPipe pose detection failed (new API)")
                    return None
                landmarks = detection.pose_landmarks[0]
                h, w = img.shape[:2]

                class LM:
                    def __init__(self, l): self.x, self.y = l.x, l.y

                lm = [LM(l) for l in landmarks]
        else:
            raise ImportError("No pose model found")

    except (ImportError, Exception) as new_api_err:
        # Legacy API (mediapipe < 0.10.14)
        try:
            mp_pose = mp.solutions.pose
            with mp_pose.Pose(static_image_mode=True, model_complexity=2) as pose:
                results = pose.process(rgb)
            if not results.pose_landmarks:
                logger.error("MediaPipe pose detection failed")
                return None
            h, w = img.shape[:2]
            lm = results.pose_landmarks.landmark
        except AttributeError:
            logger.error(f"MediaPipe pose unavailable: new API error: {new_api_err}")
            return None

    # Extract key ratios from 2D landmarks
    l_shoulder = np.array([lm[11].x * w, lm[11].y * h])
    r_shoulder = np.array([lm[12].x * w, lm[12].y * h])
    l_hip = np.array([lm[23].x * w, lm[23].y * h])
    r_hip = np.array([lm[24].x * w, lm[24].y * h])
    l_ankle = np.array([lm[27].x * w, lm[27].y * h])
    r_ankle = np.array([lm[28].x * w, lm[28].y * h])
    nose = np.array([lm[0].x * w, lm[0].y * h])

    shoulder_w = np.linalg.norm(r_shoulder - l_shoulder)
    hip_w = np.linalg.norm(r_hip - l_hip)
    torso_h = np.mean([np.linalg.norm(l_shoulder - l_hip), np.linalg.norm(r_shoulder - r_hip)])
    leg_h = np.mean([np.linalg.norm(l_hip - l_ankle), np.linalg.norm(r_hip - r_ankle)])
    head_to_hip = np.linalg.norm(nose - np.mean([l_hip, r_hip], axis=0))
    total_h = head_to_hip + leg_h

    # Map ratios to approximate SMPL betas (first 3 components)
    betas = np.zeros(10, dtype=np.float32)
    betas[0] = (total_h / h - 0.7) * 5.0
    betas[1] = (shoulder_w / max(hip_w, 1) - 1.0) * 3.0
    betas[2] = (leg_h / max(torso_h, 1) - 1.5) * 2.0

    return {
        'betas': betas,
        'vertices': None,
        'pose': np.zeros(72, dtype=np.float32),
        'joints_3d': None,
        'confidence': 0.3,
        'backend': 'keypoint',
    }


def transfer_shape_to_anny(smpl_vertices, anny_vertices):
    """
    Transfer SMPL shape deformation to Anny mesh via nearest-vertex displacement.

    Args:
        smpl_vertices: (6890, 3) float32 — deformed SMPL vertices in mm
        anny_vertices: (N, 3) float32 — base Anny mesh vertices

    Returns:
        (N, 3) float32 — deformed Anny vertices
    """
    from scipy.spatial import cKDTree

    smpl_center = smpl_vertices.mean(axis=0)
    anny_center = anny_vertices.mean(axis=0)

    # Scale SMPL to match Anny height
    smpl_height = smpl_vertices[:, 2].max() - smpl_vertices[:, 2].min()
    anny_height = anny_vertices[:, 2].max() - anny_vertices[:, 2].min()
    scale = anny_height / max(smpl_height, 1.0)

    smpl_scaled = (smpl_vertices - smpl_center) * scale + anny_center

    # For each Anny vertex, find 4 nearest SMPL vertices
    tree = cKDTree(smpl_scaled)
    dists, indices = tree.query(anny_vertices, k=4)

    # Inverse-distance weighted interpolation
    weights = 1.0 / np.maximum(dists, 0.01)
    weights /= weights.sum(axis=1, keepdims=True)

    result = np.zeros_like(anny_vertices)
    for k in range(4):
        result += weights[:, k:k+1] * smpl_scaled[indices[:, k]]

    # Blend: 70% transferred shape, 30% original Anny (preserve fine detail)
    output = 0.7 * result + 0.3 * anny_vertices
    return output.astype(np.float32)
