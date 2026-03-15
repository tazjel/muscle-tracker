"""
ML-powered body segmentation using MediaPipe.
Falls back to existing threshold-based method if MediaPipe unavailable.
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    import mediapipe as mp
    # Check if the specific submodules we need are actually available
    # Some environments have broken mediapipe installations
    import mediapipe.python.solutions.selfie_segmentation as mp_selfie
    import mediapipe.python.solutions.pose as mp_pose
    MEDIAPIPE_AVAILABLE = True
    _mp_selfie = mp_selfie
    _mp_pose = mp_pose
except ImportError:
    try:
        from mediapipe.solutions import selfie_segmentation as mp_selfie
        from mediapipe.solutions import pose as mp_pose
        MEDIAPIPE_AVAILABLE = True
        _mp_selfie = mp_selfie
        _mp_pose = mp_pose
    except ImportError:
        logger.warning("MediaPipe solutions not found. ML segmentation disabled.")
        MEDIAPIPE_AVAILABLE = False


def segment_body(image_bgr: np.ndarray) -> np.ndarray:
    """
    Returns a binary mask (uint8, 0 or 255) of the person in the image.
    Uses MediaPipe SelfieSegmentation if available, else returns None
    so the caller can fall back to existing methods.
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    try:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        with _mp_selfie.SelfieSegmentation(model_selection=1) as seg:
            result = seg.process(rgb)
            mask = (result.segmentation_mask > 0.5).astype(np.uint8) * 255
        return mask
    except Exception as e:
        logger.error(f"MediaPipe segmentation failed: {e}")
        return None


def get_pose_landmarks(image_bgr: np.ndarray) -> dict | None:
    """
    Returns a dict of landmark name -> (x_px, y_px) for key joints.
    Returns None if pose not detected or MediaPipe unavailable.
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    try:
        h, w = image_bgr.shape[:2]
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        with _mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5) as pose:
            result = pose.process(rgb)
            if not result.pose_landmarks:
                return None
            mp_names = [
                'LEFT_SHOULDER', 'RIGHT_SHOULDER',
                'LEFT_ELBOW', 'RIGHT_ELBOW',
                'LEFT_WRIST', 'RIGHT_WRIST',
                'LEFT_HIP', 'RIGHT_HIP',
                'LEFT_KNEE', 'RIGHT_KNEE',
                'LEFT_ANKLE', 'RIGHT_ANKLE',
            ]
            lm = result.pose_landmarks.landmark
            mp_enum = _mp_pose.PoseLandmark
            return {
                name: (int(lm[mp_enum[name].value].x * w),
                       int(lm[mp_enum[name].value].y * h))
                for name in mp_names
                if lm[mp_enum[name].value].visibility > 0.5
            }
    except Exception as e:
        logger.error(f"MediaPipe pose detection failed: {e}")
        return None


def extract_muscle_roi(image_bgr: np.ndarray, muscle_group: str,
                       landmarks: dict) -> np.ndarray | None:
    """
    Given pose landmarks, crop the image to the relevant muscle region.
    Returns cropped BGR image, or None if landmarks insufficient.
    """
    if not landmarks:
        return None
    h, w = image_bgr.shape[:2]
    pad = 40  # pixels of padding around the ROI

    rois = {
        'bicep': ('LEFT_SHOULDER', 'LEFT_ELBOW'),
        'tricep': ('LEFT_SHOULDER', 'LEFT_ELBOW'),
        'quad': ('LEFT_HIP', 'LEFT_KNEE'),
        'hamstring': ('LEFT_HIP', 'LEFT_KNEE'),
        'calf': ('LEFT_KNEE', 'LEFT_ANKLE'),
        'shoulder': ('LEFT_SHOULDER', 'RIGHT_SHOULDER'),
    }
    if muscle_group not in rois:
        return None
    p1_name, p2_name = rois[muscle_group]
    if p1_name not in landmarks or p2_name not in landmarks:
        return None
    x1, y1 = landmarks[p1_name]
    x2, y2 = landmarks[p2_name]
    x_min = max(0, min(x1, x2) - pad)
    y_min = max(0, min(y1, y2) - pad)
    x_max = min(w, max(x1, x2) + pad)
    y_max = min(h, max(y1, y2) + pad)
    if x_max <= x_min or y_max <= y_min:
        return None
    return image_bgr[y_min:y_max, x_min:x_max]
