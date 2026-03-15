import numpy as np
import cv2
import math

def estimate_body_composition(landmarks, contour_torso=None, waist_width_mm=None, hip_width_mm=None, user_weight_kg=None, user_height_cm=None, gender='male'):
    if not landmarks and waist_width_mm is None:
        return {}
    
    res = {}
    
    # 1. BMI
    if user_weight_kg and user_height_cm:
        res['bmi'] = round(user_weight_kg / ((user_height_cm/100)**2), 1)
        
    # 2. WHR (Waist-to-Hip Ratio)
    w_w = waist_width_mm
    h_w = hip_width_mm
    
    if w_w is None and 'LEFT_HIP' in landmarks and 'RIGHT_HIP' in landmarks:
        # Estimate waist/hip widths from landmarks if not provided
        # This is a very rough estimate based on landmark distances
        hip_dist = math.sqrt((landmarks['LEFT_HIP'][0]-landmarks['RIGHT_HIP'][0])**2 + (landmarks['LEFT_HIP'][1]-landmarks['RIGHT_HIP'][1])**2)
        h_w = hip_dist # in pixels, but ratio remains same
        
        # Estimate waist as slightly above hips
        if 'LEFT_SHOULDER' in landmarks and 'LEFT_HIP' in landmarks:
            # Waist is ~1/3 of the way up from hip to shoulder
            w_w = hip_dist * 0.9 # placeholder logic
            
    if w_w and h_w:
        res['waist_to_hip_ratio'] = round(w_w / h_w, 2)
        
    # 3. Navy Body Fat (Simplified for photo estimate)
    # Men: 86.010 * log10(waist - neck) - 70.041 * log10(height) + 36.76
    # We use estimated circumferences
    if user_height_cm:
        # Very rough fallback if circumferences not available: use WHR + BMI
        if 'bmi' in res and 'waist_to_hip_ratio' in res:
            if gender == 'male':
                bf = res['bmi'] * 1.2 + 0.23 * 30 - 16.2 # Generic formula
                if res['waist_to_hip_ratio'] > 0.9: bf += 5
            else:
                bf = res['bmi'] * 1.2 + 0.23 * 30 - 5.4
                if res['waist_to_hip_ratio'] > 0.85: bf += 5
            res['estimated_body_fat_pct'] = round(max(5, min(50, bf)), 1)
            
    # 4. Classification
    if 'estimated_body_fat_pct' in res:
        bf = res['estimated_body_fat_pct']
        if gender == 'male':
            if bf < 14: res['classification'] = 'Athletic'
            elif bf < 18: res['classification'] = 'Fit'
            elif bf < 25: res['classification'] = 'Average'
            else: res['classification'] = 'Above Average'
        else:
            if bf < 21: res['classification'] = 'Athletic'
            elif bf < 25: res['classification'] = 'Fit'
            elif bf < 32: res['classification'] = 'Average'
            else: res['classification'] = 'Above Average'
            
    res['confidence'] = 'estimated' if not (waist_width_mm and hip_width_mm) else 'high'
    return res

def estimate_lean_mass(body_weight_kg, body_fat_pct):
    if not body_weight_kg or not body_fat_pct: return {}
    fat_mass = body_weight_kg * (body_fat_pct / 100.0)
    lean_mass = body_weight_kg - fat_mass
    return {
        'fat_mass_kg': round(fat_mass, 2),
        'lean_mass_kg': round(lean_mass, 2)
    }

def generate_composition_visual(image_bgr, landmarks, composition_result):
    if image_bgr is None: return None
    annotated = image_bgr.copy()
    h, w = image_bgr.shape[:2]
    
    # Draw metrics box
    cv2.rectangle(annotated, (10, 10), (250, 150), (40, 40, 40), -1)
    cv2.rectangle(annotated, (10, 10), (250, 150), (200, 180, 0), 1)
    
    y = 40
    for k, v in composition_result.items():
        if k in ['bmi', 'waist_to_hip_ratio', 'estimated_body_fat_pct', 'classification']:
            label = k.replace('_', ' ').title()
            cv2.putText(annotated, '{}: {}'.format(label, v), (20, y), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y += 25
            
    # Draw landmark lines if available
    if 'LEFT_HIP' in landmarks and 'RIGHT_HIP' in landmarks:
        cv2.line(annotated, tuple(map(int, landmarks['LEFT_HIP'])), 
                 tuple(map(int, landmarks['RIGHT_HIP'])), (0, 255, 255), 2)
                 
    return annotated
