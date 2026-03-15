import numpy as np
import cv2
import math


def _width_to_circumference_mm(width_mm):
    """Estimate circumference from width using elliptical cross-section (depth ≈ 60% of width)."""
    a = width_mm / 2.0
    b = a * 0.60
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def estimate_body_composition(landmarks, contour_torso=None,
                               waist_width_mm=None, hip_width_mm=None,
                               neck_circumference_mm=None,
                               user_weight_kg=None, user_height_cm=None,
                               gender='male'):
    """
    Estimate body composition metrics from pose landmarks and measurements.

    Uses Navy body fat formula when circumferences are available:
      Men:   86.010 * log10(waist_circ - neck_circ) - 70.041 * log10(height) + 36.76
      Women: 163.205 * log10(waist_circ + hip_circ - neck_circ) - 97.684 * log10(height) - 78.387

    Returns dict with: bmi, waist_to_hip_ratio, estimated_body_fat_pct,
                       classification, confidence
    """
    res = {}

    # 1. BMI
    if user_weight_kg and user_height_cm:
        res['bmi'] = round(user_weight_kg / ((user_height_cm / 100.0) ** 2), 1)

    # 2. Waist/hip measurements — use provided or estimate from landmarks
    waist_w = waist_width_mm
    hip_w = hip_width_mm

    if waist_w is None and landmarks and 'LEFT_HIP' in landmarks and 'RIGHT_HIP' in landmarks:
        hip_dist = math.sqrt(
            (landmarks['LEFT_HIP'][0] - landmarks['RIGHT_HIP'][0]) ** 2 +
            (landmarks['LEFT_HIP'][1] - landmarks['RIGHT_HIP'][1]) ** 2
        )
        hip_w = hip_dist
        # Estimate waist width from shoulder–hip distance (waist ≈ 80% of hip width)
        if 'LEFT_SHOULDER' in landmarks and 'RIGHT_SHOULDER' in landmarks:
            shoulder_dist = math.sqrt(
                (landmarks['LEFT_SHOULDER'][0] - landmarks['RIGHT_SHOULDER'][0]) ** 2 +
                (landmarks['LEFT_SHOULDER'][1] - landmarks['RIGHT_SHOULDER'][1]) ** 2
            )
            waist_w = (shoulder_dist + hip_dist) / 2.0 * 0.75
        else:
            waist_w = hip_dist * 0.82

    if waist_w and hip_w and hip_w > 0:
        res['waist_to_hip_ratio'] = round(waist_w / hip_w, 2)

    # 3. Body fat — Navy method (preferred) or BMI-based fallback
    if user_height_cm:
        # Derive circumferences
        waist_circ_mm = _width_to_circumference_mm(waist_w) if waist_w else None
        hip_circ_mm = _width_to_circumference_mm(hip_w) if hip_w else None
        neck_circ_mm = neck_circumference_mm  # already a circumference

        bf = None
        if waist_circ_mm and neck_circ_mm:
            waist_cm = waist_circ_mm / 10.0
            neck_cm = neck_circ_mm / 10.0
            height_cm = user_height_cm
            try:
                if gender == 'male':
                    diff = waist_cm - neck_cm
                    if diff > 0:
                        bf = (86.010 * math.log10(diff)
                              - 70.041 * math.log10(height_cm)
                              + 36.76)
                else:
                    hip_cm = hip_circ_mm / 10.0 if hip_circ_mm else waist_cm * 1.1
                    diff = waist_cm + hip_cm - neck_cm
                    if diff > 0:
                        bf = (163.205 * math.log10(diff)
                              - 97.684 * math.log10(height_cm)
                              - 78.387)
            except (ValueError, ZeroDivisionError):
                bf = None

        # Fallback: BMI-based estimate if Navy method couldn't run
        if bf is None and 'bmi' in res:
            bmi = res['bmi']
            whr = res.get('waist_to_hip_ratio', 0.85)
            if gender == 'male':
                bf = (1.20 * bmi) + (0.23 * 30) - 16.2
                if whr > 0.9:
                    bf += 3
            else:
                bf = (1.20 * bmi) + (0.23 * 30) - 5.4
                if whr > 0.85:
                    bf += 3

        if bf is not None:
            res['estimated_body_fat_pct'] = round(max(3.0, min(50.0, bf)), 1)

    # 4. Classification
    if 'estimated_body_fat_pct' in res:
        bf = res['estimated_body_fat_pct']
        if gender == 'male':
            if bf < 14:
                res['classification'] = 'Athletic'
            elif bf < 18:
                res['classification'] = 'Fit'
            elif bf < 25:
                res['classification'] = 'Average'
            else:
                res['classification'] = 'Above Average'
        else:
            if bf < 21:
                res['classification'] = 'Athletic'
            elif bf < 25:
                res['classification'] = 'Fit'
            elif bf < 32:
                res['classification'] = 'Average'
            else:
                res['classification'] = 'Above Average'

    res['confidence'] = 'high' if (waist_width_mm and hip_width_mm) else 'estimated'
    return res


def estimate_lean_mass(body_weight_kg, body_fat_pct):
    """Calculate lean body mass and fat mass."""
    if body_weight_kg is None or body_fat_pct is None:
        return {}
    fat_mass = body_weight_kg * (body_fat_pct / 100.0)
    lean_mass = body_weight_kg - fat_mass
    return {
        'fat_mass_kg': round(fat_mass, 2),
        'lean_mass_kg': round(lean_mass, 2),
    }


def generate_composition_visual(image_bgr, landmarks, composition_result):
    """Draw body composition annotations on the image."""
    if image_bgr is None:
        return None
    annotated = image_bgr.copy()

    # Metrics box
    cv2.rectangle(annotated, (10, 10), (280, 160), (30, 30, 30), -1)
    cv2.rectangle(annotated, (10, 10), (280, 160), (200, 180, 0), 1)

    y = 38
    display_keys = ['bmi', 'waist_to_hip_ratio', 'estimated_body_fat_pct', 'classification']
    for k in display_keys:
        if k in composition_result:
            label = k.replace('_', ' ').title()
            cv2.putText(annotated, f'{label}: {composition_result[k]}',
                        (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            y += 26

    # Landmark lines
    if landmarks and 'LEFT_HIP' in landmarks and 'RIGHT_HIP' in landmarks:
        cv2.line(annotated,
                 tuple(map(int, landmarks['LEFT_HIP'])),
                 tuple(map(int, landmarks['RIGHT_HIP'])),
                 (0, 255, 255), 2)
    if landmarks and 'LEFT_SHOULDER' in landmarks and 'RIGHT_SHOULDER' in landmarks:
        cv2.line(annotated,
                 tuple(map(int, landmarks['LEFT_SHOULDER'])),
                 tuple(map(int, landmarks['RIGHT_SHOULDER'])),
                 (0, 200, 255), 2)

    return annotated
