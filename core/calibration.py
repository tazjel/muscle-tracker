import cv2
import numpy as np
import os
import logging
from .pose_analyzer import get_px_to_mm_ratio_from_pose

logger = logging.getLogger(__name__)

# ArUco dictionary for precision markers (preferred over color-based)
ARUCO_DICT_TYPE = cv2.aruco.DICT_4X4_50

# Common phone camera sensor widths (mm) keyed by EXIF Make/Model substrings.
# Used as fallback when EXIF doesn't report sensor dimensions directly.
_SENSOR_DB = {
    'SM-A245':  6.4,   # Samsung Galaxy A24 — 1/2.76" sensor
    'SM-A546':  7.6,   # Samsung Galaxy A54
    'SM-S91':   7.2,   # Samsung Galaxy S23 series
    'SM-S92':   9.8,   # Samsung Galaxy S24 Ultra
    'HUAWEI':   6.4,   # Generic Huawei mid-range
    'MAR-':     6.4,   # Huawei MatePad variants
    'PIXEL':    7.1,   # Google Pixel 6/7/8 main sensor
    'IPHONE':   7.0,   # iPhone 13/14/15 main sensor (approx)
}
_DEFAULT_SENSOR_WIDTH_MM = 6.4  # Conservative mid-range phone default


def _read_exif_focal_length(image_path):
    """Extract focal length (mm) and camera model from JPEG EXIF."""
    try:
        from PIL import Image as PILImage
        from PIL.ExifTags import TAGS
        pil = PILImage.open(image_path)
        exif = pil._getexif()
        if not exif:
            return None, None
        focal = None
        model = None
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'FocalLength':
                # value is an IFDRational or tuple
                focal = float(value) if not isinstance(value, tuple) else value[0] / value[1]
            elif tag == 'Model':
                model = str(value).upper()
        return focal, model
    except Exception as e:
        logger.debug("EXIF read failed for %s: %s", image_path, e)
        return None, None


def _sensor_width_for_model(model_str):
    """Look up sensor width from model string, return mm."""
    if model_str:
        for key, width in _SENSOR_DB.items():
            if key in model_str:
                return width
    return _DEFAULT_SENSOR_WIDTH_MM


def calibrate_from_distance(image_path, distance_cm):
    """
    Compute mm-per-pixel ratio using known camera-to-subject distance and EXIF focal length.

    Uses pinhole camera model:
        mm_per_px = (distance_mm * sensor_width_mm) / (focal_length_mm * image_width_px)

    Returns the ratio (mm/pixel) or None if EXIF data is missing.
    """
    if distance_cm is None or distance_cm <= 0:
        return None

    focal_mm, model = _read_exif_focal_length(image_path)
    if focal_mm is None or focal_mm <= 0:
        logger.warning("No EXIF focal length in %s — distance calibration unavailable", image_path)
        return None

    img = cv2.imread(image_path)
    if img is None:
        return None
    image_width_px = img.shape[1]

    sensor_width_mm = _sensor_width_for_model(model)
    distance_mm = distance_cm * 10.0

    ratio = (distance_mm * sensor_width_mm) / (focal_mm * image_width_px)
    logger.info("Distance calibration: %.4f mm/px (dist=%.0fcm, focal=%.2fmm, sensor=%.1fmm, width=%dpx, model=%s)",
                ratio, distance_cm, focal_mm, sensor_width_mm, image_width_px, model or 'unknown')
    return ratio


def get_px_to_mm_ratio(image_path, marker_size_mm=20.0, method="auto",
                       user_height_cm=None, camera_distance_cm=None):
    """
    Detects a calibration marker and returns the mm-per-pixel ratio.

    Supports methods:
      - "distance": Uses EXIF focal length + known camera-to-subject distance (most reliable for muscle scans)
      - "pose": Uses MediaPipe pose landmarks and known user height (markerless)
      - "aruco": Uses ArUco fiducial markers (most accurate, lighting-invariant)
      - "green": Uses green color detection (original clinical sticker method)
      - "auto": Tries distance first, then pose, then ArUco, then green

    Returns the ratio (mm/pixel) or None if calibration fails.
    """
    if not os.path.exists(image_path):
        logger.warning("Calibration image not found: %s", image_path)
        return None

    if method == "auto":
        # Distance-based is most reliable for close-up muscle scans
        if camera_distance_cm:
            ratio = calibrate_from_distance(image_path, camera_distance_cm)
            if ratio is not None:
                return ratio

        img = cv2.imread(image_path)
        if img is None:
            logger.warning("Failed to read calibration image: %s", image_path)
            return None

        if user_height_cm:
            ratio = get_px_to_mm_ratio_from_pose(img, user_height_cm)
            if ratio is not None:
                return ratio

        ratio = _detect_aruco(img, marker_size_mm)
        if ratio is not None:
            return ratio

        return _detect_green_marker(img, marker_size_mm)

    elif method == "distance":
        return calibrate_from_distance(image_path, camera_distance_cm)
    elif method == "pose" and user_height_cm:
        img = cv2.imread(image_path)
        if img is None:
            return None
        return get_px_to_mm_ratio_from_pose(img, user_height_cm)
    elif method == "aruco":
        img = cv2.imread(image_path)
        if img is None:
            return None
        return _detect_aruco(img, marker_size_mm)
    elif method == "green":
        img = cv2.imread(image_path)
        if img is None:
            return None
        return _detect_green_marker(img, marker_size_mm)
    else:
        logger.error("Unknown or invalid calibration method: %s", method)
        return None


def _detect_aruco(img, marker_size_mm):
    """
    Detect ArUco marker and compute mm/px ratio with sub-pixel accuracy.
    Tries multiple dictionaries and uses adaptive thresholding.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    for dict_type in [cv2.aruco.DICT_4X4_50, cv2.aruco.DICT_5X5_100, cv2.aruco.DICT_6X6_250]:
        dictionary = cv2.aruco.getPredefinedDictionary(dict_type)
        params = cv2.aruco.DetectorParameters()
        # Adaptive thresholding for varied lighting conditions
        params.adaptiveThreshWinSizeMin = 3
        params.adaptiveThreshWinSizeMax = 23
        params.adaptiveThreshWinSizeStep = 10
        params.adaptiveThreshConstant = 7
        # Sub-pixel corner refinement
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.cornerRefinementWinSize = 5

        detector = cv2.aruco.ArucoDetector(dictionary, params)
        corners, ids, _ = detector.detectMarkers(gray)

        if ids is not None and len(ids) > 0:
            c = corners[0][0]  # (4, 2)
            sides = [np.linalg.norm(c[(i + 1) % 4] - c[i]) for i in range(4)]
            avg_side_px = np.mean(sides)
            if avg_side_px <= 0:
                continue
            ratio = marker_size_mm / avg_side_px
            logger.info(
                "ArUco calibration: %.4f mm/px (dict=%d, marker %d, side=%.1f px)",
                ratio, dict_type, ids[0][0], avg_side_px,
            )
            return ratio

    return None


def _detect_green_marker(img, marker_size_mm):
    """Detect a green circular calibration sticker and compute mm/px ratio."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    lower_green = np.array([35, 50, 50])
    upper_green = np.array([85, 255, 255])

    mask = cv2.inRange(hsv, lower_green, upper_green)

    # Morphological cleanup to reduce noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Find the most circular contour (highest circularity score)
    best_contour = None
    best_circularity = 0.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity > best_circularity:
            best_circularity = circularity
            best_contour = cnt

    if best_contour is None:
        return None

    (x, y), radius = cv2.minEnclosingCircle(best_contour)
    pixel_diameter = radius * 2

    if pixel_diameter <= 0:
        return None

    ratio = marker_size_mm / pixel_diameter
    logger.info("Green marker calibration: %.4f mm/px (circularity=%.2f, diameter=%.1f px)",
                ratio, best_circularity, pixel_diameter)
    return ratio
