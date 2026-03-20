import numpy as np
import cv2
import math

def estimate_body_composition(landmarks=None, contour_torso=None,
                              waist_width_mm=None, hip_width_mm=None,
                              neck_circumference_mm=None,
                              user_weight_kg=None, user_height_cm=None,
                              gender='male'):
    result = {'bmi': 0.0, 'waist_to_hip_ratio': 0.0, 'estimated_body_fat_pct': 0.0,
              'classification': 'Average', 'confidence': 'low'}
    
    if landmarks is None:
        landmarks = {}

    # 1. BMI Calculation
    if user_weight_kg and user_height_cm:
        height_m = user_height_cm / 100.0
        result['bmi'] = round(user_weight_kg / (height_m ** 2), 2)
        result['confidence'] = 'estimated'

    # 2. WHR Calculation
    waist_w = waist_width_mm
    hip_w = hip_width_mm

    if waist_w is None and 'LEFT_HIP' in landmarks and 'RIGHT_HIP' in landmarks:
        p1 = np.array(landmarks['LEFT_HIP'])
        p2 = np.array(landmarks['RIGHT_HIP'])
        hip_w = float(np.linalg.norm(p1 - p2))
        waist_w = hip_w * 0.85
        result['confidence'] = 'estimated'
    elif waist_w and hip_w:
        result['confidence'] = 'high'

    if hip_w and hip_w > 0:
        result['waist_to_hip_ratio'] = round(waist_w / hip_w, 3)

    # 3. Body Fat Calculation (Navy Method)
    if user_height_cm and (waist_w or waist_width_mm):
        height_in = user_height_cm / 2.54
        w_mm = float(waist_w if waist_w else waist_width_mm)
        waist_circ_in = (w_mm / 25.4) * math.pi * 0.65
        
        if hip_w:
            hip_circ_in = (float(hip_w) / 25.4) * math.pi * 0.75
        else:
            hip_circ_in = (waist_circ_in * 1.1)
        
        if neck_circumference_mm:
            neck_circ_in = neck_circumference_mm / 25.4
        elif 'LEFT_SHOULDER' in landmarks and 'RIGHT_SHOULDER' in landmarks:
            s1 = np.array(landmarks['LEFT_SHOULDER'])
            s2 = np.array(landmarks['RIGHT_SHOULDER'])
            shoulder_w = float(np.linalg.norm(s1 - s2))
            neck_circ_in = (shoulder_w / 25.4 if shoulder_w > 0 else (w_mm / 25.4) * 0.8) * 0.38 * math.pi * 0.6
        else:
            neck_circ_in = (w_mm / 25.4) * 0.4

        try:
            if gender.lower() == 'male':
                if waist_circ_in > neck_circ_in:
                    bf = 86.010 * math.log10(waist_circ_in - neck_circ_in) - 70.041 * math.log10(height_in) + 36.76
                    result['estimated_body_fat_pct'] = round(bf, 1)
            else:
                if (waist_circ_in + hip_circ_in) > neck_circ_in:
                    bf = 163.205 * math.log10(waist_circ_in + hip_circ_in - neck_circ_in) - 97.684 * math.log10(height_in) - 78.387
                    result['estimated_body_fat_pct'] = round(bf, 1)
        except (ValueError, ZeroDivisionError):
            pass

    # 4. Classification
    bf = result.get('estimated_body_fat_pct', 0)
    if gender.lower() == 'male':
        if bf < 14: result['classification'] = 'Athletic'
        elif bf < 18: result['classification'] = 'Fit'
        elif bf < 25: result['classification'] = 'Average'
        else: result['classification'] = 'Above Average'
    else:
        if bf < 21: result['classification'] = 'Athletic'
        elif bf < 25: result['classification'] = 'Fit'
        elif bf < 32: result['classification'] = 'Average'
        else: result['classification'] = 'Above Average'

    return result

def estimate_lean_mass(body_weight_kg, body_fat_pct):
    if body_weight_kg is None or body_fat_pct is None:
        return {}
    fat_mass = body_weight_kg * (body_fat_pct / 100.0)
    lean_mass = body_weight_kg - fat_mass
    return {
        'fat_mass_kg': round(fat_mass, 2),
        'lean_mass_kg': round(lean_mass, 2)
    }

def generate_composition_visual(image_bgr, landmarks, composition_result):
    if image_bgr is None:
        return None
    
    vis = image_bgr.copy()
    h, w = vis.shape[:2]
    
    cv2.rectangle(vis, (10, 10), (250, 120), (0, 0, 0), -1)
    cv2.rectangle(vis, (10, 10), (250, 120), (0, 255, 0), 1)
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    y = 35
    for key, val in composition_result.items():
        if key in ['bmi', 'classification', 'waist_to_hip_ratio', 'estimated_body_fat_pct']:
            text = f"{key.replace('_', ' ').title()}: {val}"
            cv2.putText(vis, text, (20, y), font, 0.5, (255, 255, 255), 1)
            y += 20
    
    if landmarks:
        for name, pt in landmarks.items():
            if isinstance(pt, (tuple, list)) and len(pt) >= 2:
                cv2.circle(vis, (int(pt[0]), int(pt[1])), 5, (0, 255, 0), -1)
            
    return vis
