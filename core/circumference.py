import numpy as np
import cv2
import math

def estimate_circumference(contour, pixels_per_mm, method='elliptical'):
    if contour is None or pixels_per_mm <= 0:
        return {}
    x, y, w, h = cv2.boundingRect(contour)
    width_mm = w / pixels_per_mm
    if method == 'elliptical':
        a = width_mm / 2
        b = (0.6 * width_mm) / 2
        circ_mm = math.pi * (3*(a+b) - math.sqrt((3*a+b)*(a+3*b)))
        conf = 'elliptical estimate'
    elif method == 'perimeter':
        per_px = cv2.arcLength(contour, True)
        circ_mm = per_px / pixels_per_mm
        conf = 'direct perimeter'
    else:
        return {'error': 'unknown method'}
    return {
        'circumference_mm': round(circ_mm, 2),
        'circumference_cm': round(circ_mm / 10.0, 2),
        'circumference_inches': round(circ_mm / 25.4, 2),
        'method': method,
        'confidence_note': conf
    }

def estimate_circumference_from_two_views(width_front_mm, width_side_mm):
    if width_front_mm <= 0 or width_side_mm <= 0:
        return 0.0
    a = width_front_mm / 2
    b = width_side_mm / 2
    circ_mm = math.pi * (3*(a+b) - math.sqrt((3*a+b)*(a+3*b)))
    return round(circ_mm, 2)

def track_circumference_change(circ_before_mm, circ_after_mm):
    if circ_before_mm <= 0:
        return {}
    delta_mm = circ_after_mm - circ_before_mm
    change_pct = (delta_mm / circ_before_mm) * 100.0
    verdict = 'Stable'
    if change_pct > 3.0: verdict = 'Significant Growth'
    elif change_pct > 1.0: verdict = 'Moderate Growth'
    elif change_pct < -3.0: verdict = 'Significant Decrease'
    elif change_pct < -1.0: verdict = 'Moderate Decrease'
    return {
        'delta_mm': round(delta_mm, 2),
        'delta_cm': round(delta_mm / 10.0, 2),
        'delta_inches': round(delta_mm / 25.4, 2),
        'change_pct': round(change_pct, 2),
        'verdict': verdict
    }
