import os
import cv2
import numpy as np
import logging
from core.calibration import get_px_to_mm_ratio
from core.alignment import align_images
from core.pose_analyzer import get_muscle_crop

logger = logging.getLogger(__name__)

# Contour filtering thresholds
MIN_CONTOUR_AREA_RATIO = 0.005   # Minimum 0.5% of image area
MAX_CONTOUR_AREA_RATIO = 0.90    # Maximum 90% of image area


def analyze_muscle_growth(img_a_path, img_b_path, marker_size_mm=20.0,
                          align=True, muscle_group=None, user_height_cm=None):
    """
    High-precision muscle growth analysis between two images.

    Args:
        img_a_path: Path to "before" image
        img_b_path: Path to "after" image
        marker_size_mm: Known calibration marker size
        align: Whether to auto-align images
        muscle_group: Optional muscle group hint for ROI filtering
        user_height_cm: Optional known user height for markerless calibration

    Returns dict with status, metrics, raw_data, and confidence scores.
    """
    img_a = cv2.imread(img_a_path)
    img_b_orig = cv2.imread(img_b_path)

    if img_a is None:
        return {"error": f"Failed to load image: {img_a_path}"}
    if img_b_orig is None:
        return {"error": f"Failed to load image: {img_b_path}"}

    # Optional markerless crop using MediaPipe pose
    if muscle_group:
        crop_a, _ = get_muscle_crop(img_a, muscle_group)
        if crop_a is not None:
            img_a = crop_a
        crop_b, _ = get_muscle_crop(img_b_orig, muscle_group)
        if crop_b is not None:
            img_b_orig = crop_b

    # Alignment
    align_confidence = 0.0
    img_b = img_b_orig
    if align and img_a_path != img_b_path:
        img_b, matrix, align_confidence = align_images(img_a, img_b_orig)
    elif img_a_path == img_b_path:
        # Self-comparison mode (single-image volumetric scan)
        align = False

    # Calibration
    ratio_a = get_px_to_mm_ratio(img_a_path, marker_size_mm, user_height_cm=user_height_cm)
    ratio_b = get_px_to_mm_ratio(img_b_path, marker_size_mm, user_height_cm=user_height_cm)
    use_mm = (ratio_a is not None and ratio_b is not None)

    if not use_mm:
        logger.warning("Calibration marker not detected — using pixel units")
        ratio_a = ratio_a or 1.0
        ratio_b = ratio_b or 1.0

    # Extract muscle contours
    res_a = _extract_muscle_contour(img_a)
    res_b = _extract_muscle_contour(img_b)

    if res_a is None:
        return {"error": "No muscle contour detected in 'before' image"}
    if res_b is None:
        return {"error": "No muscle contour detected in 'after' image"}

    # Scale measurements
    r2_a = ratio_a ** 2 if use_mm else 1.0
    r2_b = ratio_b ** 2 if use_mm else 1.0

    area_a = res_a['area_px'] * r2_a
    area_b = res_b['area_px'] * r2_b
    width_a = res_a['width_px'] * (ratio_a if use_mm else 1.0)
    width_b = res_b['width_px'] * (ratio_b if use_mm else 1.0)
    height_a = res_a['height_px'] * (ratio_a if use_mm else 1.0)
    height_b = res_b['height_px'] * (ratio_b if use_mm else 1.0)

    delta_area = area_b - area_a
    delta_width = width_b - width_a
    unit = "mm" if use_mm else "px"

    growth_pct = (delta_area / area_a * 100) if area_a > 0 else 0.0

    # Confidence scoring
    detection_confidence = min(res_a['solidity'], res_b['solidity']) * 100

    return {
        "status": "Success",
        "calibrated": use_mm,
        "aligned": align,
        "verdict": _classify_change(growth_pct),
        "confidence": {
            "detection": round(detection_confidence, 1),
            "alignment": round(align_confidence, 1),
            "calibration": "high" if use_mm else "uncalibrated",
        },
        "metrics": {
            f"area_a_{unit}2": round(area_a, 2),
            f"area_b_{unit}2": round(area_b, 2),
            f"area_delta_{unit}2": round(delta_area, 2),
            "growth_pct": round(growth_pct, 2),
            f"width_a_{unit}": round(width_a, 2),
            f"width_b_{unit}": round(width_b, 2),
            f"width_delta_{unit}": round(delta_width, 2),
            f"height_a_{unit}": round(height_a, 2),
            f"height_b_{unit}": round(height_b, 2),
        },
        "raw_data": {
            "img_a": img_a,
            "img_b": img_b,
            "contour_a": res_a['contour'],
            "contour_b": res_b['contour'],
        }
    }


def _extract_muscle_contour(img):
    """
    Extract the primary muscle contour from an image using adaptive
    thresholding with morphological noise reduction.
    """
    h, w = img.shape[:2]
    image_area = h * w

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # CLAHE for better contrast in varying lighting
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Adaptive threshold
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 3
    )

    # Morphological cleanup — remove noise, close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Filter contours by area ratio
    valid_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        ratio = area / image_area
        if MIN_CONTOUR_AREA_RATIO <= ratio <= MAX_CONTOUR_AREA_RATIO:
            valid_contours.append(cnt)

    if not valid_contours:
        # Fallback: use the largest contour regardless
        valid_contours = [max(contours, key=cv2.contourArea)]

    main_contour = max(valid_contours, key=cv2.contourArea)
    area_px = cv2.contourArea(main_contour)
    x, y, w_box, h_box = cv2.boundingRect(main_contour)

    # Solidity = contour area / convex hull area (measure of contour quality)
    hull = cv2.convexHull(main_contour)
    hull_area = cv2.contourArea(hull)
    solidity = area_px / hull_area if hull_area > 0 else 0.0

    return {
        "contour": main_contour,
        "area_px": area_px,
        "width_px": float(w_box),
        "height_px": float(h_box),
        "bbox": (x, y, w_box, h_box),
        "solidity": solidity,
    }


def _classify_change(growth_pct):
    """Classify growth percentage into clinical verdict."""
    if growth_pct > 5.0:
        return "Significant Increase"
    elif growth_pct > 1.0:
        return "Moderate Increase"
    elif growth_pct > 0.5:
        return "Slight Increase"
    elif growth_pct < -5.0:
        return "Significant Decrease"
    elif growth_pct < -1.0:
        return "Moderate Decrease"
    elif growth_pct < -0.5:
        return "Slight Decrease"
    else:
        return "Stable"
