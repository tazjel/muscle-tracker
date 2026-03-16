"""
Session Analyzer — Auto Mode 2 coverage engine.

Receives a burst session (images + sensor log) and determines:
- Which angular zones around the subject are covered
- Overall profile completion %
- What to capture next + specific user instructions
"""

import cv2
import numpy as np
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Angular zones (compass buckets) needed for a complete profile
# Each bucket: (label, center_deg, half_width_deg)
ANGLE_ZONES = [
    ('front',       0,   40),
    ('front_right', 45,  30),
    ('right',       90,  40),
    ('back_right',  135, 30),
    ('back',        180, 40),
    ('back_left',   225, 30),
    ('left',        270, 40),
    ('front_left',  315, 30),
]

# Minimum zones required for GREEN (mandatory)
REQUIRED_ZONES = {'front', 'right', 'back', 'left'}

# Bonus zones (improve quality but not required for GREEN)
BONUS_ZONES = {'front_right', 'back_right', 'back_left', 'front_left'}

# Instructions per missing zone (priority order)
ZONE_INSTRUCTIONS = {
    'front':       ('Face the camera directly, stand upright — 1 meter away',
                    'Face the camera, feet shoulder-width apart'),
    'back':        ('Turn your BACK to the camera — 1 meter away',
                    'Stand still, back straight'),
    'right':       ('Turn so your RIGHT side faces the camera',
                    'Stand sideways, right shoulder toward camera'),
    'left':        ('Turn so your LEFT side faces the camera',
                    'Stand sideways, left shoulder toward camera'),
    'front_right': ('Face the camera then turn 45° to your left',
                    'Quarter turn — diagonal front-right'),
    'back_right':  ('Face away then turn 45° to your right',
                    'Quarter turn — diagonal back-right'),
    'back_left':   ('Face away then turn 45° to your left',
                    'Quarter turn — diagonal back-left'),
    'front_left':  ('Face the camera then turn 45° to your right',
                    'Quarter turn — diagonal front-left'),
}


def _compass_from_mag(mag_x: float, mag_y: float) -> float:
    """Convert magnetometer X/Y to compass heading (0-360°, 0=North/front)."""
    heading = math.degrees(math.atan2(mag_y, mag_x))
    return (heading + 360) % 360


def _pitch_from_accel(ax: float, ay: float, az: float) -> float:
    """Estimate pitch angle in degrees from accelerometer."""
    return math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))


def _zone_for_compass(compass_deg: float) -> Optional[str]:
    """Return the zone label that best matches a given compass heading."""
    best_zone = None
    best_dist = 999
    for label, center, half_width in ANGLE_ZONES:
        diff = abs(((compass_deg - center) + 180) % 360 - 180)
        if diff <= half_width and diff < best_dist:
            best_dist = diff
            best_zone = label
    return best_zone


def _frame_quality(image_path: str) -> float:
    """Quick sharpness score for a frame (0-1). Filters blurry shots."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return 0.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Laplacian variance as sharpness proxy
        score = cv2.Laplacian(gray, cv2.CV_64F).var()
        return min(score / 500.0, 1.0)
    except Exception:
        return 0.0


def _has_body_content(image_path: str) -> bool:
    """
    Quick check: does this frame contain skin-toned content (likely body)?
    Uses HSV skin detection heuristic.
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return False
        img_small = cv2.resize(img, (160, 120))
        hsv = cv2.cvtColor(img_small, cv2.COLOR_BGR2HSV)
        # Skin tone range in HSV
        lower = np.array([0, 20, 70], dtype=np.uint8)
        upper = np.array([20, 150, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        skin_ratio = np.sum(mask > 0) / (160 * 120)
        return skin_ratio > 0.05  # At least 5% skin pixels
    except Exception:
        return False


def analyze_session(frames_with_sensors: list, image_paths: list) -> dict:
    """
    Main analysis function.

    frames_with_sensors: list of dicts:
        {timestamp, filename, accel_x, accel_y, accel_z,
         gyro_x, gyro_y, gyro_z, mag_x, mag_y, mag_z,
         compass_deg (optional), pitch_deg (optional)}

    image_paths: dict mapping filename → absolute path

    Returns:
        {
            progress_pct: int,
            covered_zones: list[str],
            missing_required: list[str],
            missing_bonus: list[str],
            is_complete: bool,
            instructions: str,
            detail: str,
            frame_stats: {total, usable, mapped}
        }
    """
    covered = set()
    total_frames = len(frames_with_sensors)
    usable = 0
    mapped = 0

    for frame in frames_with_sensors:
        fname = frame.get('filename', '')
        img_path = image_paths.get(fname)

        # Compute compass from magnetometer if not provided
        compass = frame.get('compass_deg')
        if compass is None:
            mx = frame.get('mag_x', 0)
            my = frame.get('mag_y', 0)
            compass = _compass_from_mag(mx, my)

        # Skip frames with bad orientation (phone lying flat/pointing up)
        pitch = frame.get('pitch_deg')
        if pitch is None:
            ax = frame.get('accel_x', 0)
            ay = frame.get('accel_y', 0)
            az = frame.get('accel_z', 9.8)
            pitch = _pitch_from_accel(ax, ay, az)

        # Skip if phone is pointing too far up or down (not at subject)
        if abs(pitch) > 60:
            continue

        # Quality check on actual image
        if img_path:
            quality = _frame_quality(img_path)
            has_body = _has_body_content(img_path)
            if quality < 0.05 or not has_body:
                continue
        usable += 1

        # Map compass to zone
        zone = _zone_for_compass(compass)
        if zone:
            covered.add(zone)
            mapped += 1

    # Calculate progress
    covered_required = covered & REQUIRED_ZONES
    covered_bonus = covered & BONUS_ZONES

    # Progress: required zones = 80%, bonus zones = 20%
    req_pct = len(covered_required) / len(REQUIRED_ZONES) * 80
    bonus_pct = len(covered_bonus) / len(BONUS_ZONES) * 20
    progress_pct = int(req_pct + bonus_pct)

    missing_required = sorted(REQUIRED_ZONES - covered_required,
                              key=lambda z: list(REQUIRED_ZONES).index(z) if z in REQUIRED_ZONES else 99)
    missing_bonus = sorted(BONUS_ZONES - covered_bonus)
    is_complete = len(missing_required) == 0

    # Build instructions for next session
    if is_complete:
        if missing_bonus:
            next_zone = missing_bonus[0]
            instr, detail = ZONE_INSTRUCTIONS[next_zone]
            instructions = f'Almost perfect! {instr} for extra precision'
        else:
            instructions = 'Profile complete!'
            detail = 'All angles captured — dashboard ready'
    else:
        next_zone = missing_required[0]
        instr, detail = ZONE_INSTRUCTIONS[next_zone]
        instructions = instr

    # Priority zone label for display
    priority_zone = missing_required[0] if missing_required else (missing_bonus[0] if missing_bonus else None)

    return {
        'progress_pct': min(progress_pct, 99) if not is_complete else 100,
        'covered_zones': sorted(covered),
        'missing_required': missing_required,
        'missing_bonus': missing_bonus,
        'is_complete': is_complete,
        'instructions': instructions,
        'detail': detail,
        'priority_zone': priority_zone,
        'frame_stats': {
            'total': total_frames,
            'usable': usable,
            'mapped': mapped,
        }
    }
