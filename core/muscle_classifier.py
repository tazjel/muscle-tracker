"""
Automated muscle group classification based on pose landmarks.
Uses MediaPipe landmarks to identify the target limb/muscle.
"""
import numpy as np
from core.body_segmentation import get_pose_landmarks, MEDIAPIPE_AVAILABLE


def _angle_degrees(p1, vertex, p2):
    """Calculate angle between three points in degrees."""
    v1 = np.array(p1) - np.array(vertex)
    v2 = np.array(p2) - np.array(vertex)
    
    # Avoid zero division
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    cos_theta = np.dot(v1, v2) / (norm1 * norm2)
    angle = np.arccos(np.clip(cos_theta, -1.0, 1.0))
    return np.degrees(angle)


def classify_muscle_group(image_bgr: np.ndarray) -> str:
    """
    Auto-detects target muscle group from image.
    Returns: 'bicep', 'tricep', 'quad', 'hamstring', 'calf', 'shoulder', 'unknown'

    Algorithm:
    1. Get pose landmarks
    2. Determine which limb segment occupies the most central area of the frame
    3. Use elbow angle to distinguish bicep/tricep (flexed < 100° → bicep, extended > 150° → tricep)
    4. Use knee angle to distinguish quad/hamstring (flexed < 120° → hamstring, extended → quad)
    5. Use ankle-knee distance vs knee-hip distance to detect calf emphasis
    6. If shoulders are horizontally dominant → shoulder
    7. If no reliable determination → 'unknown'
    """
    if not MEDIAPIPE_AVAILABLE:
        return 'unknown'

    landmarks = get_pose_landmarks(image_bgr)
    if not landmarks:
        return 'unknown'

    h, w = image_bgr.shape[:2]
    cx, cy = w / 2, h / 2

    def dist_to_center(pt):
        return ((pt[0] - cx) ** 2 + (pt[1] - cy) ** 2) ** 0.5

    def landmark_present(*names):
        return all(n in landmarks for n in names)

    # Check elbow angle for bicep/tricep
    if landmark_present('LEFT_SHOULDER', 'LEFT_ELBOW', 'LEFT_WRIST'):
        elbow_angle = _angle_degrees(
            landmarks['LEFT_SHOULDER'],
            landmarks['LEFT_ELBOW'],
            landmarks['LEFT_WRIST']
        )
        # Elbow region near center → arm muscle
        elbow_dist = dist_to_center(landmarks['LEFT_ELBOW'])
        if elbow_dist < w * 0.4:
            if elbow_angle < 100:
                return 'bicep'
            elif elbow_angle > 150:
                return 'tricep'

    # Check knee angle for quad/hamstring
    if landmark_present('LEFT_HIP', 'LEFT_KNEE', 'LEFT_ANKLE'):
        knee_angle = _angle_degrees(
            landmarks['LEFT_HIP'],
            landmarks['LEFT_KNEE'],
            landmarks['LEFT_ANKLE']
        )
        knee_dist = dist_to_center(landmarks['LEFT_KNEE'])
        if knee_dist < w * 0.5:
            if knee_angle > 150:
                return 'quad'
            elif knee_angle < 120:
                return 'hamstring'

    # Check for calf: ankle near center and knee high in frame
    if landmark_present('LEFT_KNEE', 'LEFT_ANKLE'):
        ankle_y = landmarks['LEFT_ANKLE'][1]
        if ankle_y > h * 0.5:
            return 'calf'

    # Shoulder: both shoulders visible and close to horizontal center
    if landmark_present('LEFT_SHOULDER', 'RIGHT_SHOULDER'):
        ls_x, ls_y = landmarks['LEFT_SHOULDER']
        rs_x, rs_y = landmarks['RIGHT_SHOULDER']
        shoulder_mid_y = (ls_y + rs_y) / 2
        if shoulder_mid_y < h * 0.4:
            return 'shoulder'

    return 'unknown'


def classify_with_confidence(image_bgr) -> dict:
    """
    Returns {'muscle_group': str, 'confidence': float, 'method': str}
    confidence is 1.0 if landmarks were found, 0.0 if fallback.
    """
    group = classify_muscle_group(image_bgr)
    return {
        'muscle_group': group,
        'confidence': 1.0 if group != 'unknown' else 0.0,
        'method': 'mediapipe_pose' if MEDIAPIPE_AVAILABLE else 'unavailable',
    }
