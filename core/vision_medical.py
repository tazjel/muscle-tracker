import os
import cv2
import numpy as np
import logging
from core.calibration import get_px_to_mm_ratio
from core.alignment import align_images
from core.pose_analyzer import get_muscle_crop
from core.body_segmentation import segment_body, get_pose_landmarks, extract_muscle_roi

logger = logging.getLogger(__name__)


def _auto_orient(image_path):
    """Load image with correct EXIF orientation applied."""
    try:
        from PIL import Image as PILImage, ImageOps
        pil = PILImage.open(image_path)
        pil = ImageOps.exif_transpose(pil)
        rgb = np.array(pil)
        if len(rgb.shape) == 3 and rgb.shape[2] == 3:
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return rgb
    except Exception:
        return cv2.imread(image_path)

# Contour filtering thresholds
MIN_CONTOUR_AREA_RATIO = 0.005   # Minimum 0.5% of image area
MAX_CONTOUR_AREA_RATIO = 0.90    # Maximum 90% of image area

# Max realistic width (mm) per muscle group — used to sanity-check calibration
# when no ROI crop was applied (full-body in frame).
# Typical muscle width (mm) per muscle group — used to scale contour
# when no ROI crop was possible (full-body in frame, no pose landmarks).
_MAX_MUSCLE_WIDTH_MM = {
    'bicep': 130, 'tricep': 130, 'forearm': 100,
    'quadricep': 200, 'hamstring': 180, 'calf': 150,
    'glute': 320, 'deltoid': 180, 'lat': 350,
    'chest': 350,
}
_DEFAULT_MAX_WIDTH_MM = 200


def analyze_muscle_growth(img_a_path, img_b_path, marker_size_mm=20.0,
                          align=True, muscle_group=None, user_height_cm=None,
                          camera_distance_cm=None):
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
    img_a = _auto_orient(img_a_path)
    img_b_orig = _auto_orient(img_b_path)

    if img_a is None:
        return {"error": f"Failed to load image: {img_a_path}"}
    if img_b_orig is None:
        return {"error": f"Failed to load image: {img_b_path}"}

    # ML-powered ROI crop — try original, if no pose try 90° rotations
    landmarks_a = get_pose_landmarks(img_a)
    if landmarks_a is None:
        for rot in [cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_90_CLOCKWISE]:
            rotated = cv2.rotate(img_a, rot)
            landmarks_a = get_pose_landmarks(rotated)
            if landmarks_a is not None:
                img_a = rotated
                logger.info("Image A: pose detected after rotation")
                break
    landmarks_b = get_pose_landmarks(img_b_orig)
    if landmarks_b is None:
        for rot in [cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_90_CLOCKWISE]:
            rotated = cv2.rotate(img_b_orig, rot)
            landmarks_b = get_pose_landmarks(rotated)
            if landmarks_b is not None:
                img_b_orig = rotated
                logger.info("Image B: pose detected after rotation")
                break
    
    if muscle_group and landmarks_a and landmarks_b:
        crop_a = extract_muscle_roi(img_a, muscle_group, landmarks_a)
        if crop_a is not None:
            img_a = crop_a
        crop_b = extract_muscle_roi(img_b_orig, muscle_group, landmarks_b)
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
    ratio_a = get_px_to_mm_ratio(img_a_path, marker_size_mm, user_height_cm=user_height_cm, camera_distance_cm=camera_distance_cm)
    ratio_b = get_px_to_mm_ratio(img_b_path, marker_size_mm, user_height_cm=user_height_cm, camera_distance_cm=camera_distance_cm)
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

    # Sanity clamp: if no ROI crop happened (no pose landmarks), the contour
    # likely covers the whole body. Scale down to realistic muscle dimensions.
    roi_cropped = (landmarks_a is not None or landmarks_b is not None)
    if use_mm and not roi_cropped and muscle_group:
        max_w = _MAX_MUSCLE_WIDTH_MM.get(muscle_group, _DEFAULT_MAX_WIDTH_MM)
        raw_width = max(width_a, width_b)
        if raw_width > max_w * 1.5:
            scale = max_w / raw_width
            logger.info("Sanity clamp: width %.0fmm > max %.0fmm for %s, scale=%.2f",
                        raw_width, max_w, muscle_group, scale)
            width_a *= scale
            width_b *= scale
            height_a *= scale
            height_b *= scale
            area_a *= scale * scale
            area_b *= scale * scale

    delta_area = area_b - area_a
    delta_width = width_b - width_a
    unit = "mm" if use_mm else "px"

    growth_pct = (delta_area / area_a * 100) if area_a > 0 else 0.0

    # Confidence scoring
    detection_confidence = min(res_a['solidity'], res_b['solidity']) * 100

    return {
        "status": "Success",
        "calibrated": use_mm,
        "ratio": ratio_a if use_mm else None,
        "aligned": align,
        "verdict": _classify_change(growth_pct),
        "segmentation_method": res_a.get('method', 'unknown'),
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
    Extract the primary muscle contour from an image using ML segmentation
    with thresholding fallback.
    """
    h, w = img.shape[:2]
    image_area = h * w
    method = "threshold_fallback"

    # 1. Try ML-powered segmentation first
    mask = segment_body(img)
    
    if mask is not None:
        method = "mediapipe"
    else:
        # Fallback: Threshold-based segmentation
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        mask = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 3
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
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
        valid_contours = [max(contours, key=cv2.contourArea)]

    main_contour = max(valid_contours, key=cv2.contourArea)
    area_px = cv2.contourArea(main_contour)
    x, y, w_box, h_box = cv2.boundingRect(main_contour)

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
        "method": method,
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
