import cv2
import numpy as np
import os
import logging
from .pose_analyzer import get_px_to_mm_ratio_from_pose

logger = logging.getLogger(__name__)

# ArUco dictionary for precision markers (preferred over color-based)
ARUCO_DICT_TYPE = cv2.aruco.DICT_4X4_50


def get_px_to_mm_ratio(image_path, marker_size_mm=20.0, method="auto", user_height_cm=None):
    """
    Detects a calibration marker and returns the mm-per-pixel ratio.

    Supports three methods:
      - "pose": Uses MediaPipe pose landmarks and known user height (markerless)
      - "aruco": Uses ArUco fiducial markers (most accurate, lighting-invariant)
      - "green": Uses green color detection (original clinical sticker method)
      - "auto": Tries pose first (if height provided), then ArUco, then green

    Returns the ratio (mm/pixel) or None if calibration fails.
    """
    if not os.path.exists(image_path):
        logger.warning("Calibration image not found: %s", image_path)
        return None

    img = cv2.imread(image_path)
    if img is None:
        logger.warning("Failed to read calibration image: %s", image_path)
        return None

    if method == "auto":
        if user_height_cm:
            ratio = get_px_to_mm_ratio_from_pose(img, user_height_cm)
            if ratio is not None:
                return ratio
        
        ratio = _detect_aruco(img, marker_size_mm)
        if ratio is not None:
            return ratio
            
        return _detect_green_marker(img, marker_size_mm)
        
    elif method == "pose" and user_height_cm:
        return get_px_to_mm_ratio_from_pose(img, user_height_cm)
    elif method == "aruco":
        return _detect_aruco(img, marker_size_mm)
    elif method == "green":
        return _detect_green_marker(img, marker_size_mm)
    else:
        logger.error("Unknown or invalid calibration method: %s", method)
        return None


def _detect_aruco(img, marker_size_mm):
    """Detect ArUco marker and compute mm/px ratio from its known side length."""
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_TYPE)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    corners, ids, _ = detector.detectMarkers(img)

    if ids is None or len(ids) == 0:
        return None

    # Use the first detected marker
    marker_corners = corners[0][0]  # shape (4, 2)

    # Average the four side lengths for robustness
    side_lengths = []
    for i in range(4):
        p1 = marker_corners[i]
        p2 = marker_corners[(i + 1) % 4]
        side_lengths.append(np.linalg.norm(p2 - p1))

    avg_side_px = np.mean(side_lengths)
    if avg_side_px <= 0:
        return None

    ratio = marker_size_mm / avg_side_px
    logger.info("ArUco calibration: %.4f mm/px (marker %d, side=%.1f px)",
                ratio, ids[0][0], avg_side_px)
    return ratio


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
