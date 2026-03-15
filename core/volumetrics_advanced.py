"""
Advanced volumetric analysis using slice-integration.
More accurate than single-cylinder for tapered/irregular muscles.
"""
import numpy as np
import cv2


def slice_volume_estimate(contour: np.ndarray, pixels_per_cm: float,
                          num_slices: int = 20) -> dict:
    """
    Estimates muscle volume by dividing the contour bounding box into
    horizontal slices, computing elliptical cross-section per slice,
    then integrating.

    Args:
        contour: OpenCV contour array (N, 1, 2) of pixel coordinates
        pixels_per_cm: calibration scale factor
        num_slices: number of horizontal slices (more = more accurate)

    Returns:
        dict with keys:
            volume_cm3: float
            slice_widths_cm: list of float (one per slice)
            slice_heights_cm: list of float
            slice_volumes_cm3: list of float
            model: 'slice_elliptical'
    """
    if contour is None or len(contour) < 5 or pixels_per_cm <= 0:
        return {'volume_cm3': 0.0, 'model': 'slice_elliptical', 'error': 'invalid_input'}

    pts = contour.reshape(-1, 2)
    x_vals = pts[:, 0]
    y_vals = pts[:, 1]
    y_min, y_max = int(y_vals.min()), int(y_vals.max())

    if y_max <= y_min:
        return {'volume_cm3': 0.0, 'model': 'slice_elliptical', 'error': 'degenerate_contour'}

    slice_height_px = (y_max - y_min) / num_slices
    slice_height_cm = slice_height_px / pixels_per_cm

    slice_widths_cm = []
    slice_heights_cm = []
    slice_volumes_cm3 = []

    # Build a mask to query contour width at each slice
    h = y_max - y_min + 1
    w = int(x_vals.max()) - int(x_vals.min()) + 1
    offset_x = int(x_vals.min())
    offset_y = y_min
    mask = np.zeros((h + 1, w + 1), dtype=np.uint8)
    shifted = contour.copy()
    shifted[:, :, 0] -= offset_x
    shifted[:, :, 1] -= offset_y
    cv2.fillPoly(mask, [shifted], 255)

    for i in range(num_slices):
        sy = int(i * slice_height_px)
        ey = int((i + 1) * slice_height_px)
        ey = min(ey, h)
        if sy >= h:
            break
        slice_row = mask[sy:ey, :]
        if slice_row.size == 0:
            continue
        col_sums = slice_row.sum(axis=0)
        filled_cols = np.where(col_sums > 0)[0]
        if len(filled_cols) < 2:
            continue
        width_px = filled_cols[-1] - filled_cols[0]
        width_cm = width_px / pixels_per_cm
        # Assume depth ≈ 60% of width (typical for limb cross-sections)
        depth_cm = width_cm * 0.6
        # Elliptical cross-section area = π * a * b where a=width/2, b=depth/2
        area_cm2 = np.pi * (width_cm / 2) * (depth_cm / 2)
        vol = area_cm2 * slice_height_cm
        slice_widths_cm.append(round(width_cm, 3))
        slice_heights_cm.append(round(slice_height_cm, 3))
        slice_volumes_cm3.append(round(vol, 4))

    total_volume = sum(slice_volumes_cm3)
    return {
        'volume_cm3': round(total_volume, 2),
        'slice_widths_cm': slice_widths_cm,
        'slice_heights_cm': slice_heights_cm,
        'slice_volumes_cm3': slice_volumes_cm3,
        'num_slices_computed': len(slice_volumes_cm3),
        'model': 'slice_elliptical',
    }


def compare_volume_models(contour: np.ndarray, pixels_per_cm: float) -> dict:
    """
    Run both the slice model and a simple cylinder model, return both results
    so the caller can compare or choose.
    """
    # Simple cylinder fallback using bounding box
    pts = contour.reshape(-1, 2) if contour is not None else np.array([[0, 0]])
    x_vals = pts[:, 0]
    y_vals = pts[:, 1]
    width_px = x_vals.max() - x_vals.min() if len(x_vals) > 1 else 0
    height_px = y_vals.max() - y_vals.min() if len(y_vals) > 1 else 0
    width_cm = width_px / pixels_per_cm if pixels_per_cm > 0 else 0
    height_cm = height_px / pixels_per_cm if pixels_per_cm > 0 else 0
    radius_cm = width_cm / 2
    cylinder_vol = np.pi * radius_cm ** 2 * height_cm

    slice_result = slice_volume_estimate(contour, pixels_per_cm)

    return {
        'slice_model': slice_result,
        'cylinder_model': {
            'volume_cm3': round(cylinder_vol, 2),
            'model': 'cylinder',
        },
        'recommended': 'slice_elliptical',
    }
