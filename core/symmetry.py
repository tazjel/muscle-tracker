import cv2
import numpy as np
import logging
from core.vision_medical import analyze_muscle_growth

logger = logging.getLogger(__name__)


def compare_symmetry(img_left_path, img_right_path, marker_size_mm=20.0,
                     muscle_group=None):
    """
    Compares left and right limbs for muscle imbalance analysis.

    Uses self-comparison mode (image vs itself) to extract absolute
    measurements from each limb, then computes symmetry indices.

    Args:
        img_left_path: Photo of left limb
        img_right_path: Photo of right limb
        marker_size_mm: Calibration marker size
        muscle_group: Optional muscle group label

    Returns dict with symmetry index, dominant side, and per-metric breakdown.
    """
    # Analyze each limb independently (self-comparison for absolute metrics)
    res_left = analyze_muscle_growth(img_left_path, img_left_path,
                                     marker_size_mm, align=False)
    res_right = analyze_muscle_growth(img_right_path, img_right_path,
                                      marker_size_mm, align=False)

    if "error" in res_left:
        return {"error": f"Left limb analysis failed: {res_left['error']}"}
    if "error" in res_right:
        return {"error": f"Right limb analysis failed: {res_right['error']}"}

    # Determine unit from metric keys
    unit = "mm" if res_left.get("calibrated", False) else "px"

    # Extract absolute measurements from the 'a' side (self-comparison)
    area_l = res_left['metrics'].get(f'area_a_{unit}2', 0.0)
    area_r = res_right['metrics'].get(f'area_a_{unit}2', 0.0)
    width_l = res_left['metrics'].get(f'width_a_{unit}', 0.0)
    width_r = res_right['metrics'].get(f'width_a_{unit}', 0.0)
    height_l = res_left['metrics'].get(f'height_a_{unit}', 0.0)
    height_r = res_right['metrics'].get(f'height_a_{unit}', 0.0)

    # Calculate Symmetry Indices (SI)
    # SI = |Right - Left| / ((Left + Right) / 2) * 100
    si_area = _symmetry_index(area_l, area_r)
    si_width = _symmetry_index(width_l, width_r)
    si_height = _symmetry_index(height_l, height_r)

    # Composite symmetry score (weighted average)
    composite_si = si_area * 0.5 + si_width * 0.3 + si_height * 0.2

    # Determine dominant side based on area (primary indicator)
    diff_area = area_r - area_l
    if abs(diff_area) < 0.01:
        dominant = "Equal"
    elif diff_area > 0:
        dominant = "Right"
    else:
        dominant = "Left"

    # Clinical verdict
    if composite_si < 3.0:
        verdict = "Excellent symmetry — within normal range"
        risk = "low"
    elif composite_si < 10.0:
        verdict = f"Mild asymmetry — {dominant} side dominant"
        risk = "moderate"
    elif composite_si < 20.0:
        verdict = f"Notable asymmetry — {dominant} side significantly larger"
        risk = "elevated"
    else:
        verdict = f"Severe asymmetry — {dominant} side much larger, corrective training recommended"
        risk = "high"

    return {
        "status": "Success",
        "analysis_type": "Symmetry Audit",
        "muscle_group": muscle_group or "unspecified",
        "calibrated": unit == "mm",
        "dominant_side": dominant,
        "risk_level": risk,
        "symmetry_indices": {
            "composite_pct": round(composite_si, 2),
            f"area_{unit}2": {
                "left": round(area_l, 2),
                "right": round(area_r, 2),
                "imbalance_pct": round(si_area, 2),
            },
            f"width_{unit}": {
                "left": round(width_l, 2),
                "right": round(width_r, 2),
                "imbalance_pct": round(si_width, 2),
            },
            f"height_{unit}": {
                "left": round(height_l, 2),
                "right": round(height_r, 2),
                "imbalance_pct": round(si_height, 2),
            },
        },
        "verdict": verdict,
    }


def _symmetry_index(val_left, val_right):
    """Calculate symmetry index as a percentage difference."""
    avg = (val_left + val_right) / 2.0
    if avg <= 0:
        return 0.0
    return abs(val_right - val_left) / avg * 100
