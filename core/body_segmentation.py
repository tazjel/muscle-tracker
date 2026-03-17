"""
ML-powered body segmentation and pose detection using MediaPipe Tasks API (0.10.x+).
Falls back to threshold-based method if MediaPipe unavailable.
"""
import cv2
import numpy as np
import logging
import os

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
_POSE_MODEL = os.path.join(_MODELS_DIR, 'pose_landmarker.task')
_SEG_MODEL = os.path.join(_MODELS_DIR, 'selfie_segmenter.tflite')

MEDIAPIPE_AVAILABLE = False

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    from mediapipe.tasks.python.vision import (
        ImageSegmenter, ImageSegmenterOptions,
        PoseLandmarker, PoseLandmarkerOptions,
    )
    if os.path.exists(_POSE_MODEL) and os.path.exists(_SEG_MODEL):
        MEDIAPIPE_AVAILABLE = True
        logger.info("MediaPipe Tasks API loaded (v%s)", mp.__version__)
    else:
        logger.warning("MediaPipe model files not found in %s", _MODELS_DIR)
except (ImportError, Exception) as e:
    logger.warning("MediaPipe Tasks API unavailable: %s", e)


def segment_body(image_bgr: np.ndarray) -> np.ndarray:
    """
    Returns a binary mask (uint8, 0 or 255) of the person in the image.
    Uses MediaPipe ImageSegmenter if available, else returns None.
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    try:
        options = ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=_SEG_MODEL),
            output_category_mask=False,
        )
        with ImageSegmenter.create_from_options(options) as segmenter:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                data=cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
            result = segmenter.segment(mp_image)
            if result.confidence_masks:
                mask_raw = result.confidence_masks[0].numpy_view()
                # Squeeze to 2D if needed
                if mask_raw.ndim == 3:
                    mask_raw = mask_raw[:, :, 0]
                # Use low threshold — muscle close-ups have lower confidence
                mask = (mask_raw > 0.1).astype(np.uint8) * 255
                # If mask covers < 5% of image, ML didn't detect a body — return None for fallback
                if mask.sum() / 255 < (mask_raw.shape[0] * mask_raw.shape[1] * 0.05):
                    return None
                return mask
        return None
    except Exception as e:
        logger.error("MediaPipe segmentation failed: %s", e)
        return None


# Pose landmark name mapping (Tasks API uses index-based access)
_POSE_LANDMARK_NAMES = {
    'LEFT_SHOULDER': 11, 'RIGHT_SHOULDER': 12,
    'LEFT_ELBOW': 13, 'RIGHT_ELBOW': 14,
    'LEFT_WRIST': 15, 'RIGHT_WRIST': 16,
    'LEFT_HIP': 23, 'RIGHT_HIP': 24,
    'LEFT_KNEE': 25, 'RIGHT_KNEE': 26,
    'LEFT_ANKLE': 27, 'RIGHT_ANKLE': 28,
}


def get_pose_landmarks(image_bgr: np.ndarray) -> dict | None:
    """
    Returns a dict of landmark name -> (x_px, y_px) for key joints.
    Returns None if pose not detected or MediaPipe unavailable.
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    try:
        h, w = image_bgr.shape[:2]
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_POSE_MODEL),
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        with PoseLandmarker.create_from_options(options) as landmarker:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                data=cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
            result = landmarker.detect(mp_image)
            if not result.pose_landmarks or len(result.pose_landmarks) == 0:
                return None
            lm = result.pose_landmarks[0]
            landmarks = {}
            for name, idx in _POSE_LANDMARK_NAMES.items():
                if idx < len(lm) and lm[idx].visibility > 0.5:
                    landmarks[name] = (int(lm[idx].x * w), int(lm[idx].y * h))
            return landmarks if landmarks else None
    except Exception as e:
        logger.error("MediaPipe pose detection failed: %s", e)
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
    pad = 40

    # For muscles that span both sides (quadricep, hamstring) use bilateral ROI:
    # x range from RIGHT landmark to LEFT landmark (full width of both legs),
    # y range from hip to knee.
    bilateral_rois = {
        'quadricep': ('RIGHT_HIP', 'LEFT_HIP', 'RIGHT_KNEE', 'LEFT_KNEE'),
        'hamstring': ('RIGHT_HIP', 'LEFT_HIP', 'RIGHT_KNEE', 'LEFT_KNEE'),
        'glute': ('RIGHT_HIP', 'LEFT_HIP', 'RIGHT_KNEE', 'LEFT_KNEE'),
    }
    if muscle_group in bilateral_rois:
        pts = bilateral_rois[muscle_group]
        coords = [landmarks[p] for p in pts if p in landmarks]
        if len(coords) < 2:
            return None
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        x_min = max(0, min(xs) - pad)
        x_max = min(w, max(xs) + pad)
        y_min = max(0, min(ys) - pad)
        y_max = min(h, max(ys) + pad)
        if x_max <= x_min or y_max <= y_min:
            return None
        return image_bgr[y_min:y_max, x_min:x_max]

    rois = {
        'bicep': ('LEFT_SHOULDER', 'LEFT_ELBOW'),
        'tricep': ('LEFT_SHOULDER', 'LEFT_ELBOW'),
        'calf': ('LEFT_KNEE', 'LEFT_ANKLE'),
        'deltoid': ('LEFT_SHOULDER', 'RIGHT_SHOULDER'),
        'lat': ('LEFT_SHOULDER', 'LEFT_HIP'),
        'chest': ('LEFT_SHOULDER', 'RIGHT_SHOULDER'),
        'forearm': ('LEFT_ELBOW', 'LEFT_WRIST'),
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
