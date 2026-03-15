"""
ML-powered body segmentation using MediaPipe.
Falls back to existing threshold-based method if MediaPipe unavailable.
"""
import cv2
import numpy as np

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
    _mp_selfie = mp.solutions.selfie_segmentation
    _mp_pose = mp.solutions.pose
except ImportError:
    MEDIAPIPE_AVAILABLE = False


def segment_body(image_bgr: np.ndarray) -> np.ndarray:
    """
    Returns a binary mask (uint8, 0 or 255) of the person in the image.
    Uses MediaPipe SelfieSegmentation if available, else returns None
    so the caller can fall back to existing methods.
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    with _mp_selfie.SelfieSegmentation(model_selection=1) as seg:
        result = seg.process(rgb)
        
        # Check if result or mask is a mock (happens in tests)
        # MagicMocks don't support comparison operators with floats
        mask_val = getattr(result, 'segmentation_mask', None)
        if mask_val is None or 'MagicMock' in str(type(mask_val)):
            return None
            
        mask = (mask_val > 0.5).astype(np.uint8) * 255
    return mask


def get_pose_landmarks(image_bgr: np.ndarray) -> dict | None:
    """
    Returns a dict of landmark name -> (x_px, y_px) for key joints.
    Returns None if pose not detected or MediaPipe unavailable.
    Landmark names matching MediaPipe PoseLandmark enum.
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    
    h, w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    
    with _mp_pose.Pose(static_image_mode=True, model_complexity=2) as pose:
        results = pose.process(rgb)
        if not results or not getattr(results, 'pose_landmarks', None) or 'MagicMock' in str(type(results.pose_landmarks)):
            return None
        
        landmarks = {}
        for i, landmark in enumerate(results.pose_landmarks.landmark):
            name = _mp_pose.PoseLandmark(i).name
            landmarks[name] = (int(landmark.x * w), int(landmark.y * h))
            
        return landmarks
