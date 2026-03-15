import numpy as np
import logging

logger = logging.getLogger(__name__)


def estimate_muscle_volume(area_front_mm2, area_side_mm2,
                           width_front_mm, width_side_mm,
                           model="elliptical_cylinder"):
    """
    Estimates 3D muscle volume from two perpendicular 2D views.

    Models:
      - "elliptical_cylinder": V = pi * a * b * h
        where a = width_front/2, b = width_side/2,
        and h is derived from the areas.

      - "prismatoid": Prismoidal approximation using both
        cross-sectional areas for tapered muscle shapes.

    Args:
        area_front_mm2: Muscle area from the front view (mm²)
        area_side_mm2: Muscle area from the side view (mm²)
        width_front_mm: Muscle width from the front view (mm)
        width_side_mm: Muscle width from the side view (mm)
        model: Volume estimation model to use

    Returns:
        dict with volume_cm3, model used, and intermediate values
    """
    # Input validation
    inputs = {
        "area_front_mm2": area_front_mm2,
        "area_side_mm2": area_side_mm2,
        "width_front_mm": width_front_mm,
        "width_side_mm": width_side_mm,
    }
    for name, val in inputs.items():
        if val is None or val <= 0:
            logger.warning("Invalid input %s = %s", name, val)
            return {"volume_cm3": 0.0, "model": model, "error": f"Invalid {name}"}

    if model == "elliptical_cylinder":
        result = _elliptical_cylinder(
            area_front_mm2, area_side_mm2,
            width_front_mm, width_side_mm
        )
    elif model == "prismatoid":
        result = _prismatoid(
            area_front_mm2, area_side_mm2,
            width_front_mm, width_side_mm
        )
    else:
        logger.error("Unknown volume model: %s", model)
        return {"volume_cm3": 0.0, "model": model, "error": f"Unknown model: {model}"}

    result["model"] = model
    return result


def _elliptical_cylinder(area_front, area_side, width_front, width_side):
    """
    Elliptical Cylinder: V = pi * a * b * h

    Derivation:
      - Semi-axis a = width_front / 2  (half-width from front view)
      - Semi-axis b = width_side / 2   (half-width from side view)
      - Height h from front view: h_f = area_front / width_front
      - Height h from side view:  h_s = area_side / width_side
      - Average height: h = (h_f + h_s) / 2

    The front view silhouette is a rectangle of width_front x h,
    and the side view silhouette is a rectangle of width_side x h.
    The cross-section is an ellipse with semi-axes a and b.
    """
    a = width_front / 2.0
    b = width_side / 2.0

    h_front = area_front / width_front
    h_side = area_side / width_side
    h = (h_front + h_side) / 2.0

    volume_mm3 = np.pi * a * b * h
    volume_cm3 = volume_mm3 / 1000.0  # 1 cm³ = 1000 mm³

    return {
        "volume_cm3": round(volume_cm3, 2),
        "volume_mm3": round(volume_mm3, 2),
        "semi_axis_a_mm": round(a, 2),
        "semi_axis_b_mm": round(b, 2),
        "height_mm": round(h, 2),
        "height_front_mm": round(h_front, 2),
        "height_side_mm": round(h_side, 2),
    }


def _prismatoid(area_front, area_side, width_front, width_side):
    """
    Prismoidal formula for tapered muscle shapes.

    Uses Simpson's rule: V = (h/6) * (A_top + 4*A_mid + A_bottom)

    For muscles that taper (like biceps), we model:
      - A_top and A_bottom as smaller ellipses (60% of max)
      - A_mid as the full elliptical cross-section
      - h derived from the silhouette areas
    """
    a = width_front / 2.0
    b = width_side / 2.0

    h_front = area_front / width_front
    h_side = area_side / width_side
    h = (h_front + h_side) / 2.0

    a_mid = np.pi * a * b
    taper = 0.6
    a_end = np.pi * (a * taper) * (b * taper)

    # Simpson's rule
    volume_mm3 = (h / 6.0) * (a_end + 4 * a_mid + a_end)
    volume_cm3 = volume_mm3 / 1000.0

    return {
        "volume_cm3": round(volume_cm3, 2),
        "volume_mm3": round(volume_mm3, 2),
        "semi_axis_a_mm": round(a, 2),
        "semi_axis_b_mm": round(b, 2),
        "height_mm": round(h, 2),
        "cross_section_mid_mm2": round(a_mid, 2),
        "cross_section_end_mm2": round(a_end, 2),
        "taper_factor": taper,
    }


def compare_volumes(vol_before, vol_after):
    """Compare two volume measurements and return gain analysis."""
    v1 = vol_before.get("volume_cm3", 0.0)
    v2 = vol_after.get("volume_cm3", 0.0)

    if v1 <= 0:
        return {"delta_cm3": v2, "gain_pct": 0.0, "verdict": "Baseline"}

    delta = v2 - v1
    gain_pct = (delta / v1) * 100

    if gain_pct > 5.0:
        verdict = "Significant Gain"
    elif gain_pct > 1.0:
        verdict = "Moderate Gain"
    elif gain_pct > 0:
        verdict = "Slight Gain"
    elif gain_pct > -1.0:
        verdict = "Stable"
    elif gain_pct > -5.0:
        verdict = "Moderate Loss"
    else:
        verdict = "Significant Loss"

    return {
        "volume_before_cm3": round(v1, 2),
        "volume_after_cm3": round(v2, 2),
        "delta_cm3": round(delta, 2),
        "gain_pct": round(gain_pct, 2),
        "verdict": verdict,
    }
