"""
hmr_shape.py — Predict SMPL body shape from photos using HMR2.0/TokenHMR.

Input: 1-4 BGR images (np.ndarray) with direction labels
Output: dict with 'betas' (10,), 'vertices' (6890,3), 'joints' (24,3), 'pose' (72,)

Falls back to MediaPipe keypoint → SMPL optimization if HMR2.0 unavailable.
"""
import numpy as np
import logging
import cv2

logger = logging.getLogger(__name__)

# Lazy-load heavy imports
_hmr_model = None
_hmr_backend = None  # 'hmr2' | 'tokenhmr' | 'keypoint'


def _load_hmr():
    """Try HMR2.0 → TokenHMR → keypoint fallback."""
    global _hmr_model, _hmr_backend
    if _hmr_model is not None:
        return

    # Try HMR2.0
    try:
        from hmr2.models import HMR2
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = HMR2.from_pretrained().to(device).eval()
        _hmr_model = (model, device)
        _hmr_backend = 'hmr2'
        logger.info(f"HMR2.0 loaded on {device}")
        return
    except Exception as e:
        logger.warning(f"HMR2.0 unavailable: {e}")

    # Try TokenHMR
    try:
        from tokenhmr.models import TokenHMR
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = TokenHMR.from_pretrained().to(device).eval()
        _hmr_model = (model, device)
        _hmr_backend = 'tokenhmr'
        logger.info(f"TokenHMR loaded on {device}")
        return
    except Exception as e:
        logger.warning(f"TokenHMR unavailable: {e}")

    # Keypoint fallback
    _hmr_backend = 'keypoint'
    _hmr_model = True  # sentinel
    logger.info("HMR2.0/TokenHMR not installed — using MediaPipe keypoint fallback for shape estimation")


def predict_shape(images, directions=None):
    """
    Predict SMPL body shape from 1-4 images.

    Args:
        images: list of (H,W,3) uint8 BGR arrays
        directions: list of str ('front','back','left','right'), same len as images
                    If None, assumes ['front'] for 1 image, etc.

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
    _load_hmr()

    if _hmr_backend in ('hmr2', 'tokenhmr'):
        return _predict_hmr(images, directions)
    else:
        return _predict_keypoint(images, directions)


def _predict_hmr(images, directions):
    """Run HMR2.0 or TokenHMR on each image, average betas."""
    import torch
    model, device = _hmr_model

    all_betas = []
    best_pose = None
    best_verts = None
    best_confidence = 0.0

    for i, img in enumerate(images):
        try:
            # Preprocess: BGR→RGB, resize to 256x256, normalize
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            rgb = cv2.resize(rgb, (256, 256))
            tensor = torch.from_numpy(rgb).float().permute(2, 0, 1) / 255.0
            # ImageNet normalize
            mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
            std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
            tensor = (tensor - mean) / std
            tensor = tensor.unsqueeze(0).to(device)

            with torch.no_grad():
                output = model(tensor)

            betas = output['pred_smpl_params']['betas'][0].cpu().numpy()
            all_betas.append(betas[:10])  # first 10 shape components

            conf = float(output.get('confidence', [0.5])[0]) if 'confidence' in output else 0.5
            if conf > best_confidence:
                best_confidence = conf
                best_pose = output['pred_smpl_params']['body_pose'][0].cpu().numpy()
                best_verts = output['pred_vertices'][0].cpu().numpy()
        except Exception as e:
            logger.warning(f"HMR prediction failed for image {i}: {e}")
            continue

    if not all_betas:
        logger.error("All HMR predictions failed")
        return None

    # Average betas across views for robustness
    avg_betas = np.mean(all_betas, axis=0).astype(np.float32)

    # Reconstruct mesh with averaged betas
    verts = None
    joints = None
    try:
        import smplx
        import torch as th
        import os
        model_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'models', 'smpl'),
            os.path.expanduser('~/.smpl'),
            os.path.join(os.path.dirname(__file__), '..', 'lib', 'smpl'),
        ]
        smpl_path = None
        for p in model_paths:
            if os.path.isdir(p):
                smpl_path = p
                break

        if smpl_path:
            smpl = smplx.create(smpl_path, model_type='smpl', gender='neutral')
            with th.no_grad():
                result = smpl(betas=th.tensor(avg_betas).unsqueeze(0).float())
                verts = result.vertices[0].numpy() * 1000  # m → mm
                joints = result.joints[0, :24].numpy() * 1000
        else:
            logger.warning("SMPL model not found — use HMR vertices directly")
            verts = best_verts * 1000 if best_verts is not None else None
    except Exception as e:
        logger.warning(f"SMPL reconstruction failed: {e}")
        verts = best_verts * 1000 if best_verts is not None else None

    return {
        'betas': avg_betas,
        'vertices': verts,
        'pose': best_pose.flatten()[:72] if best_pose is not None else np.zeros(72, dtype=np.float32),
        'joints_3d': joints,
        'confidence': best_confidence,
        'backend': _hmr_backend,
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

    mp_pose = mp.solutions.pose
    with mp_pose.Pose(static_image_mode=True, model_complexity=2) as pose:
        results = pose.process(rgb)

    if not results.pose_landmarks:
        logger.error("MediaPipe pose detection failed")
        return None

    h, w = img.shape[:2]
    lm = results.pose_landmarks.landmark

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
