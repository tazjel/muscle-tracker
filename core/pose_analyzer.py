import cv2
import logging
import math
import numpy as np

logger = logging.getLogger(__name__)

try:
    import mediapipe as mp
    mp_pose = mp.solutions.pose
    pose_detector = mp_pose.Pose(
        static_image_mode=True,
        model_complexity=2,
        enable_segmentation=True,
        min_detection_confidence=0.5
    )
    HAVE_MEDIAPIPE = True
except (ImportError, AttributeError, Exception):
    logger.warning("Mediapipe unavailable or broken. Markerless metrology disabled.")
    mp_pose = None
    pose_detector = None
    HAVE_MEDIAPIPE = False


# --- G12: Pose Correction Engine ---
# MediaPipe landmark indices
_LM = {
    "nose": 0,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16,
    "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28,
}

# Ideal joint angles (degrees) and tolerances per muscle group + pose
# Each entry: (joint_a, joint_b, joint_c, ideal_angle, tolerance, axis_label)
# The angle is measured at joint_b between vectors BA and BC.
POSE_RULES = {
    "bicep": [
        # Elbow angle ~90° for peak measurement
        ("right_shoulder", "right_elbow", "right_wrist", 90.0, 15.0, "elbow flexion"),
        # Shoulder abduction ~45° (arm lifted to show peak)
        ("right_hip", "right_shoulder", "right_elbow", 45.0, 20.0, "shoulder abduction"),
    ],
    "tricep": [
        # Elbow near full extension ~170° for horseshoe visibility
        ("right_shoulder", "right_elbow", "right_wrist", 170.0, 15.0, "elbow extension"),
        # Shoulder abduction ~30°
        ("right_hip", "right_shoulder", "right_elbow", 30.0, 20.0, "shoulder abduction"),
    ],
    "quad": [
        # Standing straight — knee near full extension ~175°
        ("right_hip", "right_knee", "right_ankle", 175.0, 10.0, "knee extension"),
        # Hip angle upright ~175°
        ("right_shoulder", "right_hip", "right_knee", 175.0, 15.0, "hip alignment"),
    ],
    "calf": [
        # Standing — knee straight ~175°
        ("right_hip", "right_knee", "right_ankle", 175.0, 10.0, "knee extension"),
    ],
    "delt": [
        # Arm at side, slight abduction ~15° for cap visibility
        ("right_hip", "right_shoulder", "right_elbow", 15.0, 15.0, "shoulder abduction"),
        # Elbow relaxed ~160°
        ("right_shoulder", "right_elbow", "right_wrist", 160.0, 20.0, "elbow angle"),
    ],
    "lat": [
        # Arms spread wide — shoulder abduction ~90° for lat spread
        ("right_hip", "right_shoulder", "right_elbow", 90.0, 15.0, "shoulder abduction"),
        ("left_hip", "left_shoulder", "left_elbow", 90.0, 15.0, "shoulder abduction"),
    ],
}


def _angle_between(a, b, c):
    """Calculate angle at point B in degrees, given 3 (x, y) points."""
    ba = np.array([a[0] - b[0], a[1] - b[1]])
    bc = np.array([c[0] - b[0], c[1] - b[1]])
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return math.degrees(math.acos(cos_angle))


def _correction_instruction(axis_label, current_angle, ideal_angle, tolerance):
    """Generate a human-readable correction instruction."""
    diff = current_angle - ideal_angle
    abs_diff = abs(diff)

    if abs_diff <= tolerance:
        return None  # Within acceptable range

    direction = ""
    if "elbow" in axis_label:
        direction = "Bend elbow more" if diff > 0 else "Extend elbow more"
    elif "shoulder abduction" in axis_label:
        direction = "Lower arm slightly" if diff > 0 else "Raise arm slightly"
    elif "knee" in axis_label:
        direction = "Bend knee slightly" if diff > 0 else "Straighten leg"
    elif "hip" in axis_label:
        direction = "Lean back slightly" if diff > 0 else "Stand more upright"
    else:
        direction = "Decrease angle" if diff > 0 else "Increase angle"

    return {
        "axis": axis_label,
        "current_angle": round(current_angle, 1),
        "ideal_angle": round(ideal_angle, 1),
        "deviation": round(abs_diff, 1),
        "instruction": f"{direction} ({abs_diff:.0f}° correction needed for {axis_label})",
    }


def analyze_pose(img, muscle_group="bicep"):
    """
    G12: Analyze user pose and return correction instructions.

    Detects MediaPipe landmarks, measures joint angles relevant to the
    requested muscle group, and generates natural-language fix instructions
    if any angle falls outside the ideal range.

    Args:
        img: BGR image (numpy array)
        muscle_group: One of the keys in POSE_RULES

    Returns:
        dict with:
          - status: "ok" | "corrections_needed" | "error"
          - pose_score: 0-100 (100 = perfect pose)
          - corrections: list of correction dicts (empty if pose is good)
          - angles: dict of measured angles
    """
    if not HAVE_MEDIAPIPE:
        return {"status": "error", "message": "MediaPipe not installed"}

    # Normalize muscle group name
    group_key = muscle_group.lower().replace("_", "").replace(" ", "")
    # Map common names to rule keys
    group_map = {
        "bicep": "bicep", "biceps": "bicep", "biceppeak": "bicep",
        "tricep": "tricep", "triceps": "tricep", "tricephorseshoe": "tricep",
        "quad": "quad", "quads": "quad", "quadsweep": "quad",
        "calf": "calf", "calves": "calf", "calfdiamond": "calf",
        "delt": "delt", "delts": "delt", "deltcap": "delt", "shoulder": "delt",
        "lat": "lat", "lats": "lat", "latspread": "lat",
    }
    group_key = group_map.get(group_key, group_key)

    rules = POSE_RULES.get(group_key)
    if rules is None:
        return {
            "status": "error",
            "message": f"No pose rules for muscle group '{muscle_group}'",
            "available_groups": list(POSE_RULES.keys()),
        }

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = pose_detector.process(img_rgb)

    if not results.pose_landmarks:
        return {"status": "error", "message": "No pose detected in image"}

    h, w = img.shape[:2]
    landmarks = results.pose_landmarks.landmark

    def lm_xy(name):
        idx = _LM[name]
        lm = landmarks[idx]
        return (lm.x * w, lm.y * h)

    corrections = []
    angles = {}
    total_deviation = 0.0
    max_possible_deviation = 0.0

    for (ja, jb, jc, ideal, tol, axis_label) in rules:
        try:
            a, b, c = lm_xy(ja), lm_xy(jb), lm_xy(jc)
        except (KeyError, IndexError):
            continue

        angle = _angle_between(a, b, c)
        angles[axis_label] = round(angle, 1)

        deviation = abs(angle - ideal)
        total_deviation += deviation
        max_possible_deviation += 180.0  # theoretical max

        fix = _correction_instruction(axis_label, angle, ideal, tol)
        if fix is not None:
            corrections.append(fix)

    # Score: 100 when all angles are perfect, decays with deviation
    if max_possible_deviation > 0:
        pose_score = max(0.0, 100.0 * (1.0 - total_deviation / max_possible_deviation))
    else:
        pose_score = 0.0

    status = "ok" if len(corrections) == 0 else "corrections_needed"

    return {
        "status": status,
        "muscle_group": group_key,
        "pose_score": round(pose_score, 1),
        "angles": angles,
        "corrections": corrections,
        "num_corrections": len(corrections),
    }

def get_px_to_mm_ratio_from_pose(img, user_height_cm):
    """
    Estimates the mm-per-pixel ratio using MediaPipe pose detection
    and the user's known height in cm.
    
    Assumes the user is fully visible in the frame (head to toe).
    """
    if not HAVE_MEDIAPIPE:
        logger.error("Mediapipe is required for pose calibration.")
        return None

    if user_height_cm is None or user_height_cm <= 0:
        logger.error("Valid user height (cm) required for pose calibration.")
        return None

    # Convert BGR to RGB for MediaPipe
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = pose_detector.process(img_rgb)

    if not results.pose_landmarks:
        logger.warning("No pose landmarks detected.")
        return None

    # Get image dimensions
    h, w = img.shape[:2]

    # Find the bounding box of the person based on landmarks
    y_coords = [landmark.y * h for landmark in results.pose_landmarks.landmark]

    if not y_coords:
        return None

    # We add a slight margin because landmarks (like ankle and eye/nose)
    # don't cover the absolute top of the head or bottom of the feet.
    # Typically, eye to top of head is about 10-12cm, ankle to floor is about 5-8cm.
    # For a standard adult, we can approximate the full pixel height by scaling the bounding box.
    # Let's use a standard multiplier, e.g. 1.05 to account for top of head and bottom of feet.
    min_y = min(y_coords)
    max_y = max(y_coords)
    person_px_height = (max_y - min_y) * 1.08  # 8% padding for head/feet

    if person_px_height <= 0:
        return None

    user_height_mm = user_height_cm * 10.0
    ratio = user_height_mm / person_px_height
    
    logger.info("Pose calibration: %.4f mm/px (height_cm=%.1f, px_height=%.1f px)",
                ratio, user_height_cm, person_px_height)
    
    return ratio

def get_muscle_crop(img, muscle_group="bicep"):
    """
    Uses pose landmarks to automatically crop the image to the specified muscle group.
    Returns (cropped_image, (x, y, w, h)) or (None, None) if failed.
    """
    if not HAVE_MEDIAPIPE:
        return None, None

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = pose_detector.process(img_rgb)

    if not results.pose_landmarks:
        return None, None

    h, w = img.shape[:2]
    landmarks = results.pose_landmarks.landmark

    # Basic logic to crop around the right bicep (shoulder to elbow)
    if muscle_group == "bicep":
        # Right shoulder (12) and Right elbow (14)
        # Or Left shoulder (11) and Left elbow (13)
        # Let's just pick one side for demonstration, e.g., right side
        r_shoulder = landmarks[12]
        r_elbow = landmarks[14]
        
        y1 = min(r_shoulder.y, r_elbow.y) * h
        y2 = max(r_shoulder.y, r_elbow.y) * h
        x1 = min(r_shoulder.x, r_elbow.x) * w
        x2 = max(r_shoulder.x, r_elbow.x) * w
        
        # Add padding
        padding = max(x2 - x1, y2 - y1) * 0.5
        y1 = max(0, int(y1 - padding))
        y2 = min(h, int(y2 + padding))
        x1 = max(0, int(x1 - padding))
        x2 = min(w, int(x2 + padding))
        
        if x2 > x1 and y2 > y1:
            return img[y1:y2, x1:x2], (x1, y1, x2 - x1, y2 - y1)
            
    return None, None
