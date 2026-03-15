"""
Auto-detection of muscle groups from image landmarks.
Uses pose landmarks to classify the dominant muscle group in frame.
"""
import numpy as np
import logging
from core.body_segmentation import get_pose_landmarks

logger = logging.getLogger(__name__)


def classify_muscle_group(image_bgr: np.ndarray) -> str:
    """
    Analyzes pose landmarks to determine which muscle group is being scanned.
    Returns: 'bicep', 'tricep', 'quad', 'hamstring', 'calf', 'shoulder', or 'unknown'
    """
    landmarks = get_pose_landmarks(image_bgr)
    if not landmarks:
        return 'unknown'

    # 1. Check for upper body / arm focus
    has_arms = all(k in landmarks for k in ['LEFT_SHOULDER', 'LEFT_ELBOW', 'LEFT_WRIST'])
    
    # 2. Check for lower body focus
    has_legs = all(k in landmarks for k in ['LEFT_HIP', 'LEFT_KNEE', 'LEFT_ANKLE'])

    if has_arms:
        # Measure elbow angle to distinguish bicep vs tricep
        # (Simplified: if wrist is above elbow, likely bicep flex)
        shoulder = landmarks['LEFT_SHOULDER']
        elbow = landmarks['LEFT_ELBOW']
        wrist = landmarks['LEFT_WRIST']
        
        if wrist[1] < elbow[1]:
            return 'bicep'
        else:
            return 'tricep'

    if has_legs:
        # Distinguish quad vs calf based on which joints are more centered
        hip = landmarks['LEFT_HIP']
        knee = landmarks['LEFT_KNEE']
        ankle = landmarks['LEFT_ANKLE']
        
        # If knee-to-ankle is larger part of frame than hip-to-knee
        leg_len = abs(hip[1] - knee[1])
        calf_len = abs(knee[1] - ankle[1])
        
        if calf_len > leg_len * 0.8:
            return 'calf'
        return 'quad'

    return 'unknown'


def classify_with_confidence(image_bgr: np.ndarray) -> dict:
    """
    Returns classification result with confidence scores.
    """
    landmarks = get_pose_landmarks(image_bgr)
    if not landmarks:
        return {'muscle_group': 'unknown', 'confidence': 0.0}

    group = classify_muscle_group(image_bgr)
    
    # Confidence based on landmark visibility/count
    conf = min(1.0, len(landmarks) / 12.0)
    
    return {
        'muscle_group': group,
        'confidence': round(conf, 2),
        'landmarks_detected': list(landmarks.keys())
    }
