import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

# All available pro physique templates
AVAILABLE_TEMPLATES = [
    "bicep_peak",
    "tricep_horseshoe",
    "quad_sweep",
    "calf_diamond",
    "delt_cap",
    "lat_spread",
]


def calculate_shape_score(contour_actual, contour_ideal):
    """
    Compares two contours using Hu Moments and returns a similarity score (0-100).

    Uses multiple match methods and averages for robust comparison:
      - CONTOURS_MATCH_I1: Based on reciprocals of Hu moments
      - CONTOURS_MATCH_I2: Based on absolute differences
      - CONTOURS_MATCH_I3: Based on relative differences

    Returns dict with overall score and per-method breakdown.
    """
    if contour_actual is None or contour_ideal is None:
        return {"score": 0.0, "error": "Missing contour data"}

    methods = {
        "I1": cv2.CONTOURS_MATCH_I1,
        "I2": cv2.CONTOURS_MATCH_I2,
        "I3": cv2.CONTOURS_MATCH_I3,
    }

    scores = {}
    for name, method in methods.items():
        match_val = cv2.matchShapes(contour_actual, contour_ideal, method, 0.0)
        # Normalize: 0.0 = perfect match → 100, higher = worse
        # Using exponential decay for smoother scoring
        score = 100.0 * np.exp(-match_val * 3.0)
        scores[name] = round(max(0.0, score), 2)

    # Weighted average (I1 is most reliable for shape comparison)
    overall = scores["I1"] * 0.5 + scores["I2"] * 0.3 + scores["I3"] * 0.2

    grade = _score_to_grade(overall)

    return {
        "score": round(overall, 2),
        "grade": grade,
        "method_scores": scores,
    }


def score_muscle_shape(contour_actual, template_name):
    """
    Score a detected muscle contour against a named pro template.

    Args:
        contour_actual: Detected muscle contour (OpenCV format)
        template_name: One of AVAILABLE_TEMPLATES

    Returns dict with score, grade, and recommendations.
    """
    ideal = load_ideal_template(template_name)
    if ideal is None:
        return {"error": f"Unknown template: {template_name}",
                "available": AVAILABLE_TEMPLATES}

    result = calculate_shape_score(contour_actual, ideal)
    result["template"] = template_name
    result["recommendations"] = _get_recommendations(template_name, result["score"])
    return result


def load_ideal_template(template_name):
    """
    Generate a pro-standard geometric ideal contour for a muscle group.

    Each template is a parametric curve that represents the ideal
    shape for competitive/clinical assessment.
    """
    generators = {
        "bicep_peak": _template_bicep_peak,
        "tricep_horseshoe": _template_tricep_horseshoe,
        "quad_sweep": _template_quad_sweep,
        "calf_diamond": _template_calf_diamond,
        "delt_cap": _template_delt_cap,
        "lat_spread": _template_lat_spread,
    }

    gen = generators.get(template_name)
    if gen is None:
        return None
    return gen()


def _template_bicep_peak():
    """
    Ideal bicep: Smooth arc with a pronounced peak at the top.
    Key feature: high peak-to-base ratio indicating muscle belly fullness.
    """
    points = []
    for t in np.linspace(0, np.pi, 60):
        x = 100 * np.cos(t)
        y = 80 * np.sin(t) * (1 + 0.5 * np.sin(t))  # peaked arc
        points.append([int(x + 150), int(y + 150)])
    # Close the contour along the base
    for x in np.linspace(100 + 150, -100 + 150, 20):
        points.append([int(x), 150])
    return np.array(points).reshape((-1, 1, 2)).astype(np.int32)


def _template_tricep_horseshoe():
    """
    Ideal tricep (rear view): Horseshoe / inverted-U shape.
    Three heads visible: lateral (outer), long (inner), medial (lower).
    """
    points = []
    # Outer lateral head (left arm of horseshoe)
    for t in np.linspace(0, np.pi * 0.8, 25):
        x = -40 + 15 * np.sin(t * 2)
        y = 150 * t / (np.pi * 0.8)
        points.append([int(x + 150), int(y + 50)])
    # Bottom curve (medial head)
    for t in np.linspace(-np.pi, 0, 20):
        x = 40 * np.cos(t)
        y = 170 + 20 * np.sin(t)
        points.append([int(x + 150), int(y + 50)])
    # Inner long head (right arm of horseshoe)
    for t in np.linspace(np.pi * 0.8, 0, 25):
        x = 40 - 15 * np.sin(t * 2)
        y = 150 * t / (np.pi * 0.8)
        points.append([int(x + 150), int(y + 50)])
    # Top connecting bar
    for x in np.linspace(40, -40, 10):
        points.append([int(x + 150), 50])
    return np.array(points).reshape((-1, 1, 2)).astype(np.int32)


def _template_quad_sweep():
    """
    Ideal quad (front view): Vastus lateralis sweep.
    Key feature: convex lateral flare from knee to mid-thigh.
    """
    points = []
    # Outer sweep (lateral)
    for t in np.linspace(0, 1, 30):
        x = 50 * np.sin(np.pi * t) * (1 + 0.4 * np.sin(np.pi * t))
        y = 200 * t
        points.append([int(x + 150), int(y + 50)])
    # Inner line (medial, straighter)
    for t in np.linspace(1, 0, 30):
        x = -30 * np.sin(np.pi * t * 0.8)
        y = 200 * t
        points.append([int(x + 150), int(y + 50)])
    return np.array(points).reshape((-1, 1, 2)).astype(np.int32)


def _template_calf_diamond():
    """
    Ideal calf (rear view): Gastrocnemius diamond shape.
    Key feature: widest point at upper 1/3, tapering to Achilles insertion.
    """
    points = []
    n = 60
    for i in range(n):
        t = 2 * np.pi * i / n
        # Asymmetric diamond: peak width at upper third
        r_base = 40
        # Vertical modulation: wider at top, narrow at bottom
        vert = np.cos(t)
        horiz = np.sin(t)
        # Shift peak upward
        r = r_base * (1 + 0.3 * np.cos(t - 0.5))
        x = r * horiz
        y = 80 * vert * (1 - 0.25 * vert)  # asymmetric height
        points.append([int(x + 150), int(y + 150)])
    return np.array(points).reshape((-1, 1, 2)).astype(np.int32)


def _template_delt_cap():
    """
    Ideal deltoid (side/front view): Rounded cannonball cap.
    Key feature: full hemispherical dome with slight anterior bias.
    """
    points = []
    # Upper dome
    for t in np.linspace(-0.15, np.pi + 0.15, 50):
        x = 90 * np.cos(t)
        y = 70 * np.sin(t) * (1 + 0.15 * np.cos(t))  # forward bias
        points.append([int(x + 150), int(y + 100)])
    # Flat base (arm attachment)
    for x in np.linspace(-90 + 150, 90 + 150, 15):
        points.append([int(x), 100])
    return np.array(points).reshape((-1, 1, 2)).astype(np.int32)


def _template_lat_spread():
    """
    Ideal lat (rear view): V-taper spread.
    Key feature: wide upper back tapering to narrow waist.
    """
    points = []
    # Right side (outer edge) — top to bottom
    for t in np.linspace(0, 1, 30):
        x = 80 * (1 - 0.5 * t)  # taper inward
        y = 200 * t
        x += 10 * np.sin(np.pi * t)  # slight convex bulge
        points.append([int(x + 150), int(y + 50)])
    # Bottom (waist)
    for x in np.linspace(40 + 150, -40 + 150, 10):
        points.append([int(x), 250])
    # Left side (outer edge) — bottom to top
    for t in np.linspace(1, 0, 30):
        x = -80 * (1 - 0.5 * t)
        y = 200 * t
        x -= 10 * np.sin(np.pi * t)
        points.append([int(x + 150), int(y + 50)])
    # Top (shoulder line)
    for x in np.linspace(-80 + 150, 80 + 150, 10):
        points.append([int(x), 50])
    return np.array(points).reshape((-1, 1, 2)).astype(np.int32)


def _score_to_grade(score):
    """Convert numerical score to clinical grade."""
    if score >= 90:
        return "S"   # Elite / Pro
    elif score >= 75:
        return "A"   # Advanced
    elif score >= 60:
        return "B"   # Intermediate
    elif score >= 40:
        return "C"   # Developing
    elif score >= 20:
        return "D"   # Beginner
    else:
        return "F"   # Needs work


def _get_recommendations(template_name, score):
    """Generate training recommendations based on shape score."""
    recs = {
        "bicep_peak": {
            "focus": "Peak development",
            "exercises": ["Incline dumbbell curls", "Spider curls", "Concentration curls"],
            "tip": "Supinate at the top of each curl to maximise peak contraction",
        },
        "tricep_horseshoe": {
            "focus": "Horseshoe definition",
            "exercises": ["Overhead tricep extensions", "Dips", "Close-grip bench press"],
            "tip": "Emphasize full lockout and controlled eccentric for all three heads",
        },
        "quad_sweep": {
            "focus": "Lateral sweep development",
            "exercises": ["Hack squats (narrow stance)", "Leg extensions", "Front squats"],
            "tip": "Narrow foot placement targets the vastus lateralis for outer sweep",
        },
        "calf_diamond": {
            "focus": "Gastrocnemius fullness",
            "exercises": ["Standing calf raises", "Donkey calf raises", "Seated calf raises"],
            "tip": "Pause at full stretch and peak contraction — calves respond to time under tension",
        },
        "delt_cap": {
            "focus": "3D shoulder roundness",
            "exercises": ["Lateral raises", "Face pulls", "Overhead press"],
            "tip": "Hit all three heads equally — rear delts are most commonly underdeveloped",
        },
        "lat_spread": {
            "focus": "V-taper width",
            "exercises": ["Wide-grip pull-ups", "Meadows rows", "Straight-arm pulldowns"],
            "tip": "Focus on the mind-muscle connection at peak contraction to maximise lat activation",
        },
    }

    rec = recs.get(template_name, {})

    if score >= 75:
        rec["assessment"] = "Strong shape — focus on maintaining and refining"
    elif score >= 50:
        rec["assessment"] = "Good foundation — targeted training will improve shape score"
    else:
        rec["assessment"] = "Prioritize the recommended exercises to develop this muscle shape"

    return rec
