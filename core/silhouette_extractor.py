"""
silhouette_extractor.py — Extract body outline from scan photos.

Returns the body contour as an ordered 2D point array in mm coordinates,
ready for use by silhouette_matcher.py to deform the 3D mesh.

Pipeline:
  1. Load and auto-orient image (EXIF + MatePad landscape fix)
  2. Segment body (MediaPipe) or fallback to GrabCut
  3. Find largest contour
  4. Convert pixel coordinates → mm using calibration ratio
"""

import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


def extract_silhouette(image_path: str, camera_distance_cm: float):
    """
    Extract body silhouette from a scan image.

    Args:
        image_path:          Path to the captured scan image.
        camera_distance_cm:  Distance from camera to subject in cm.
                             Used for px → mm calibration.

    Returns:
        contour_mm: (K, 2) float32 — body outline in mm (x_mm, y_mm from image top-left)
                    None if extraction failed.
        mask:       (H, W) uint8 — binary body mask (255 = body, 0 = background)
                    None if extraction failed.
        ratio_mm_px: float — mm per pixel ratio used (for caller reference)
    """
    from core.vision_medical import _auto_orient
    from core.body_segmentation import segment_body
    from core.calibration import get_px_to_mm_ratio

    # ── Load ──────────────────────────────────────────────────────────────────
    img = _auto_orient(image_path)
    if img is None:
        logger.warning("silhouette_extractor: could not load %s", image_path)
        return None, None, None

    # ── Calibration ratio ─────────────────────────────────────────────────────
    ratio = get_px_to_mm_ratio(
        image_path,
        method='distance',
        camera_distance_cm=camera_distance_cm,
    )
    if not ratio or ratio <= 0:
        # Rough fallback: assume typical phone at 100cm gives ~0.25 mm/px
        ratio = camera_distance_cm * 0.0025
        logger.warning("silhouette_extractor: calibration failed, using fallback ratio %.4f", ratio)

    # ── Segmentation ──────────────────────────────────────────────────────────
    # Try SAM 2 first (best quality), fall back to MediaPipe, then GrabCut
    mask = _segment_sam2(img)
    if mask is None:
        mask = segment_body(img)
    if mask is None:
        logger.info("silhouette_extractor: MediaPipe unavailable, trying GrabCut fallback")
        mask = _grabcut_body_mask(img)

    if mask is None:
        logger.warning("silhouette_extractor: segmentation failed for %s", image_path)
        return None, None, ratio

    # Ensure binary uint8
    mask = (mask > 127).astype(np.uint8) * 255

    # ── Contour extraction ────────────────────────────────────────────────────
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        logger.warning("silhouette_extractor: no contours found in mask")
        return None, mask, ratio

    # Largest contour = body (ignore small noise blobs)
    main = max(contours, key=cv2.contourArea)
    if cv2.contourArea(main) < 1000:
        logger.warning("silhouette_extractor: largest contour too small (< 1000 px²)")
        return None, mask, ratio

    # Quality check: body contour should be taller than wide and occupy
    # a reasonable fraction of the image height (rejects blank walls, desks, etc.)
    x_bb, y_bb, w_bb, h_bb = cv2.boundingRect(main)
    aspect = h_bb / (w_bb + 1)
    if aspect < 1.2:
        logger.warning(
            "silhouette_extractor: aspect ratio %.2f < 1.2 — likely not a person (too wide)",
            aspect,
        )
        return None, mask, ratio
    img_h = mask.shape[0]
    if h_bb < img_h * 0.3:
        logger.warning(
            "silhouette_extractor: contour height %dpx < 30%% of image — likely bad segmentation",
            h_bb,
        )
        return None, mask, ratio

    # Squeeze (K, 1, 2) → (K, 2) and convert px → mm
    pts_px = main.squeeze().astype(np.float32)
    if pts_px.ndim == 1:
        # Single point — shouldn't happen with a valid body
        return None, mask, ratio

    contour_mm = pts_px * ratio  # (K, 2) float32 in mm

    logger.info(
        "silhouette_extractor: %s — %d contour points, ratio=%.4f mm/px",
        image_path, len(contour_mm), ratio,
    )
    return contour_mm, mask, ratio


# ── SAM 2 segmentation ────────────────────────────────────────────────────────

def _segment_sam2(image):
    """
    Segment body using SAM 2. Returns (H, W) uint8 mask (255=body, 0=bg).
    Falls back gracefully if SAM 2 not installed.
    """
    try:
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        import torch

        predictor = SAM2ImagePredictor.from_pretrained("facebook/sam2-hiera-tiny")

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        predictor.set_image(rgb)

        h, w = image.shape[:2]
        # Use center point as body prompt (person typically centred in scan photo)
        input_point = np.array([[w // 2, h // 2]])
        input_label = np.array([1])  # foreground

        masks, scores, _ = predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=True,
        )

        best_idx = scores.argmax()
        mask = (masks[best_idx] * 255).astype(np.uint8)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        logger.info("silhouette_extractor: SAM 2 segmentation succeeded")
        return mask

    except ImportError:
        return None  # SAM 2 not installed — use MediaPipe
    except Exception as e:
        logger.warning(f"SAM 2 failed: {e}")
        return None


# ── GrabCut fallback ──────────────────────────────────────────────────────────

def _grabcut_body_mask(img: np.ndarray) -> np.ndarray:
    """
    Rough body segmentation via GrabCut when MediaPipe is unavailable.

    Assumes the subject is centred in the frame with some margin.
    Returns uint8 mask (255=foreground, 0=background) or None.
    """
    h, w = img.shape[:2]
    # Initialise rect: 10% margin on each side
    margin_x = int(w * 0.10)
    margin_y = int(h * 0.05)
    rect = (margin_x, margin_y, w - 2 * margin_x, h - 2 * margin_y)

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    mask_gc   = np.zeros((h, w), np.uint8)

    try:
        cv2.grabCut(img, mask_gc, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
    except Exception as e:
        logger.warning("GrabCut failed: %s", e)
        return None

    # GrabCut values: 0=BGD, 1=FGD, 2=PR_BGD, 3=PR_FGD
    binary = np.where((mask_gc == cv2.GC_FGD) | (mask_gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  kernel)

    return binary
