import cv2
import logging
import math
import os
import numpy as np

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
_POSE_MODEL = os.path.join(_MODELS_DIR, 'pose_landmarker.task')

HAVE_MEDIAPIPE = False
_landmarker = None

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions
    if os.path.exists(_POSE_MODEL):
        HAVE_MEDIAPIPE = True
        logger.info("Pose analyzer: MediaPipe Tasks API loaded (v%s)", mp.__version__)
    else:
        logger.warning("Pose model not found at %s", _POSE_MODEL)
except (ImportError, Exception) as e:
    logger.warning("MediaPipe unavailable for pose analyzer: %s", e)


def _detect_pose(img_bgr):
    """Run pose detection on an image, return landmarks list or None."""
    if not HAVE_MEDIAPIPE:
        return None, None
    try:
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_POSE_MODEL),
            num_poses=1,
            min_pose_detection_confidence=0.5,
        )
        with PoseLandmarker.create_from_options(options) as landmarker:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                data=cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
            result = landmarker.detect(mp_image)
            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                return result.pose_landmarks[0], img_bgr.shape[:2]
            return None, None
    except Exception as e:
        logger.error("Pose detection failed: %s", e)
        return None, None


# --- G12: Pose Correction Engine ---
_LM = {
    "nose": 0,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16,
    "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28,
}

POSE_RULES = {
    "bicep": [
        ("right_shoulder", "right_elbow", "right_wrist", 90.0, 15.0, "elbow flexion"),
        ("right_hip", "right_shoulder", "right_elbow", 45.0, 20.0, "shoulder abduction"),
    ],
    "tricep": [
        ("right_shoulder", "right_elbow", "right_wrist", 170.0, 15.0, "elbow extension"),
        ("right_hip", "right_shoulder", "right_elbow", 30.0, 20.0, "shoulder abduction"),
    ],
    "quad": [
        ("right_hip", "right_knee", "right_ankle", 175.0, 10.0, "knee extension"),
        ("right_shoulder", "right_hip", "right_knee", 175.0, 15.0, "hip alignment"),
    ],
    "calf": [
        ("right_hip", "right_knee", "right_ankle", 175.0, 10.0, "knee extension"),
    ],
    "delt": [
        ("right_hip", "right_shoulder", "right_elbow", 15.0, 15.0, "shoulder abduction"),
        ("right_shoulder", "right_elbow", "right_wrist", 160.0, 20.0, "elbow angle"),
    ],
    "lat": [
        ("right_hip", "right_shoulder", "right_elbow", 90.0, 15.0, "shoulder abduction"),
        ("left_hip", "left_shoulder", "left_elbow", 90.0, 15.0, "shoulder abduction"),
    ],
}


def _angle_between(a, b, c):
    ba = np.array([a[0] - b[0], a[1] - b[1]])
    bc = np.array([c[0] - b[0], c[1] - b[1]])
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return math.degrees(math.acos(cos_angle))


def _correction_instruction(axis_label, current_angle, ideal_angle, tolerance):
    diff = current_angle - ideal_angle
    abs_diff = abs(diff)
    if abs_diff <= tolerance:
        return None
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
    """G12: Analyze user pose and return correction instructions."""
    if not HAVE_MEDIAPIPE:
        return {"status": "error", "message": "MediaPipe not installed"}

    group_key = muscle_group.lower().replace("_", "").replace(" ", "")
    group_map = {
        "bicep": "bicep", "biceps": "bicep",
        "tricep": "tricep", "triceps": "tricep",
        "quad": "quad", "quads": "quad", "quadricep": "quad",
        "calf": "calf", "calves": "calf",
        "delt": "delt", "delts": "delt", "deltoid": "delt", "shoulder": "delt",
        "lat": "lat", "lats": "lat",
    }
    group_key = group_map.get(group_key, group_key)

    rules = POSE_RULES.get(group_key)
    if rules is None:
        return {"status": "error", "message": f"No pose rules for '{muscle_group}'",
                "available_groups": list(POSE_RULES.keys())}

    landmarks, (h, w) = _detect_pose(img)
    if landmarks is None:
        return {"status": "error", "message": "No pose detected in image"}

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
        max_possible_deviation += 180.0
        fix = _correction_instruction(axis_label, angle, ideal, tol)
        if fix is not None:
            corrections.append(fix)

    if max_possible_deviation > 0:
        pose_score = max(0.0, 100.0 * (1.0 - total_deviation / max_possible_deviation))
    else:
        pose_score = 0.0

    return {
        "status": "ok" if not corrections else "corrections_needed",
        "muscle_group": group_key,
        "pose_score": round(pose_score, 1),
        "angles": angles,
        "corrections": corrections,
        "num_corrections": len(corrections),
    }


def get_px_to_mm_ratio_from_pose(img, user_height_cm):
    """Estimate mm-per-pixel ratio using pose detection and known user height."""
    if not HAVE_MEDIAPIPE:
        logger.error("Mediapipe is required for pose calibration.")
        return None
    if user_height_cm is None or user_height_cm <= 0:
        return None

    landmarks, (h, w) = _detect_pose(img)
    if landmarks is None:
        logger.warning("No pose landmarks detected.")
        return None

    y_coords = [lm.y * h for lm in landmarks]
    if not y_coords:
        return None

    min_y = min(y_coords)
    max_y = max(y_coords)
    person_px_height = (max_y - min_y) * 1.08

    if person_px_height <= 0:
        return None

    user_height_mm = user_height_cm * 10.0
    ratio = user_height_mm / person_px_height
    logger.info("Pose calibration: %.4f mm/px (height=%.1fcm, px=%.1f)",
                ratio, user_height_cm, person_px_height)
    return ratio


def get_muscle_crop(img, muscle_group="bicep"):
    """Crop image to the specified muscle group using pose landmarks."""
    if not HAVE_MEDIAPIPE:
        return None, None

    landmarks, (h, w) = _detect_pose(img)
    if landmarks is None:
        return None, None

    if muscle_group == "bicep":
        r_shoulder = landmarks[12]
        r_elbow = landmarks[14]
        y1 = min(r_shoulder.y, r_elbow.y) * h
        y2 = max(r_shoulder.y, r_elbow.y) * h
        x1 = min(r_shoulder.x, r_elbow.x) * w
        x2 = max(r_shoulder.x, r_elbow.x) * w
        padding = max(x2 - x1, y2 - y1) * 0.5
        y1 = max(0, int(y1 - padding))
        y2 = min(h, int(y2 + padding))
        x1 = max(0, int(x1 - padding))
        x2 = min(w, int(x2 + padding))
        if x2 > x1 and y2 > y1:
            return img[y1:y2, x1:x2], (x1, y1, x2 - x1, y2 - y1)

    return None, None
