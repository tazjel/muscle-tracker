import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Clinical color palette (BGR)
COLOR_BEFORE = (200, 120, 50)    # Steel blue
COLOR_AFTER = (50, 200, 255)     # Gold/amber
COLOR_GROWTH = (0, 220, 100)     # Growth zone green
COLOR_LOSS = (80, 80, 220)       # Loss zone red
COLOR_TEXT_BG = (30, 30, 30)     # Dark background for text
COLOR_WHITE = (255, 255, 255)


def generate_growth_heatmap(img_a, img_b, contour_a, contour_b,
                            output_path, metrics=None):
    """
    Generates a clinical-grade growth heatmap with difference zones.

    Shows:
      - Before contour (blue)
      - After contour (gold)
      - Growth zones (green) — areas present in After but not Before
      - Loss zones (red) — areas present in Before but not After
      - Metric overlay if provided
    """
    H, W = img_a.shape[:2]

    # Base canvas: desaturated blend of both images
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    canvas = cv2.cvtColor(gray_a, cv2.COLOR_GRAY2BGR)

    # Create difference masks
    mask_a = np.zeros((H, W), dtype=np.uint8)
    mask_b = np.zeros((H, W), dtype=np.uint8)
    cv2.fillPoly(mask_a, [contour_a], 255)
    cv2.fillPoly(mask_b, [contour_b], 255)

    # Growth = in B but not in A, Loss = in A but not in B
    growth_mask = cv2.bitwise_and(mask_b, cv2.bitwise_not(mask_a))
    loss_mask = cv2.bitwise_and(mask_a, cv2.bitwise_not(mask_b))

    # Apply zone colors
    overlay = canvas.copy()
    overlay[growth_mask > 0] = COLOR_GROWTH
    overlay[loss_mask > 0] = COLOR_LOSS

    # Draw contour outlines
    cv2.drawContours(overlay, [contour_a], -1, COLOR_BEFORE, 2)
    cv2.drawContours(overlay, [contour_b], -1, COLOR_AFTER, 2)

    # Blend
    alpha = 0.45
    cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0, canvas)

    # Re-draw contours on top (sharp, not blended)
    cv2.drawContours(canvas, [contour_a], -1, COLOR_BEFORE, 2)
    cv2.drawContours(canvas, [contour_b], -1, COLOR_AFTER, 2)

    # Legend panel
    _draw_legend(canvas, H, W, metrics)

    cv2.imwrite(output_path, canvas)
    logger.info("Heatmap saved: %s", output_path)
    return output_path


def generate_side_by_side(img_a, img_b, contour_a, contour_b,
                          output_path, labels=("Before", "After")):
    """
    Creates a side-by-side comparison with contour overlays and labels.
    """
    H, W = img_a.shape[:2]

    # Ensure same dimensions
    img_b_resized = cv2.resize(img_b, (W, H))

    # Draw contours on copies
    panel_a = img_a.copy()
    panel_b = img_b_resized.copy()
    cv2.drawContours(panel_a, [contour_a], -1, COLOR_BEFORE, 3)
    cv2.drawContours(panel_b, [contour_b], -1, COLOR_AFTER, 3)

    # Add labels
    _draw_label(panel_a, labels[0], COLOR_BEFORE)
    _draw_label(panel_b, labels[1], COLOR_AFTER)

    # Separator line
    separator = np.full((H, 4, 3), 255, dtype=np.uint8)

    combined = np.hstack([panel_a, separator, panel_b])
    cv2.imwrite(output_path, combined)
    logger.info("Side-by-side saved: %s", output_path)
    return output_path


def generate_symmetry_visual(img_left, img_right, contour_left, contour_right,
                             output_path, symmetry_data=None):
    """
    Creates a mirrored symmetry comparison visual.
    Left image is flipped horizontally so both limbs face the same direction.
    """
    H, W = img_left.shape[:2]
    img_right_resized = cv2.resize(img_right, (W, H))

    # Flip left image for direct comparison
    img_left_flipped = cv2.flip(img_left, 1)
    contour_left_flipped = contour_left.copy()
    contour_left_flipped[:, :, 0] = W - contour_left_flipped[:, :, 0]

    panel_l = img_left_flipped.copy()
    panel_r = img_right_resized.copy()
    cv2.drawContours(panel_l, [contour_left_flipped], -1, (255, 150, 0), 3)
    cv2.drawContours(panel_r, [contour_right], -1, (0, 150, 255), 3)

    _draw_label(panel_l, "LEFT (mirrored)", (255, 150, 0))
    _draw_label(panel_r, "RIGHT", (0, 150, 255))

    separator = np.full((H, 4, 3), 200, dtype=np.uint8)
    combined = np.hstack([panel_l, separator, panel_r])

    # Add symmetry metrics bar at bottom if available
    if symmetry_data:
        bar_h = 50
        bar = np.full((bar_h, combined.shape[1], 3), 30, dtype=np.uint8)
        si = symmetry_data.get("symmetry_indices", {})
        composite = si.get("composite_pct", 0.0)
        dominant = symmetry_data.get("dominant_side", "Equal")
        text = f"Symmetry Index: {composite:.1f}%  |  Dominant: {dominant}"
        color = (0, 220, 100) if composite < 5 else (0, 180, 255) if composite < 15 else (80, 80, 220)
        cv2.putText(bar, text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        combined = np.vstack([combined, bar])

    cv2.imwrite(output_path, combined)
    logger.info("Symmetry visual saved: %s", output_path)
    return output_path


def _draw_legend(canvas, H, W, metrics=None):
    """Draw a legend panel on the image."""
    y_start = 20
    line_h = 28

    # Semi-transparent background
    overlay = canvas.copy()
    cv2.rectangle(overlay, (5, 5), (280, y_start + line_h * 5), COLOR_TEXT_BG, -1)
    cv2.addWeighted(overlay, 0.7, canvas, 0.3, 0, canvas)

    items = [
        ("BEFORE", COLOR_BEFORE),
        ("AFTER", COLOR_AFTER),
        ("GROWTH ZONE", COLOR_GROWTH),
        ("LOSS ZONE", COLOR_LOSS),
    ]

    for i, (label, color) in enumerate(items):
        y = y_start + i * line_h
        cv2.circle(canvas, (20, y), 8, color, -1)
        cv2.putText(canvas, label, (35, y + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_WHITE, 1)

    if metrics:
        y = y_start + len(items) * line_h
        growth_pct = metrics.get("growth_pct", 0.0)
        sign = "+" if growth_pct >= 0 else ""
        cv2.putText(canvas, f"Growth: {sign}{growth_pct:.1f}%", (15, y + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_WHITE, 1)


def _draw_label(img, text, color):
    """Draw a label bar at the top of an image."""
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (img.shape[1], 40), COLOR_TEXT_BG, -1)
    cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)
    cv2.putText(img, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
