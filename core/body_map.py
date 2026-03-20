import numpy as np
import cv2
import os

def generate_body_map_data(scan_records):
    """
    Aggregates scan records into a dict keyed by muscle_group,
    keeping only the latest scan per muscle.
    """
    if not scan_records:
        return {}
        
    latest = {}
    for r in scan_records:
        mg = r.get('muscle_group', 'unknown')
        date = r.get('scan_date', '0000-00-00')
        
        if mg not in latest or date >= latest[mg].get('scan_date', ''):
            latest[mg] = r
            
    return latest

def generate_body_map(scan_records, output_path="body_map.png"):
    """
    Draws a human figure with muscle regions colored by score.
    """
    img = np.full((800, 600, 3), 240, dtype=np.uint8) # Light gray background
    
    # Simple human outline
    # Head
    cv2.circle(img, (300, 80), 40, (100, 100, 100), 2)
    # Torso
    cv2.rectangle(img, (240, 120), (360, 350), (100, 100, 100), 2)
    # Arms
    cv2.line(img, (240, 140), (160, 320), (100, 100, 100), 2) # Left
    cv2.line(img, (360, 140), (440, 320), (100, 100, 100), 2) # Right
    # Legs
    cv2.line(img, (260, 350), (240, 650), (100, 100, 100), 2) # Left
    cv2.line(img, (340, 350), (360, 650), (100, 100, 100), 2) # Right
    
    # Define muscle regions (polygons or circles)
    # x, y, label_pos
    muscle_map = {
        'bicep_left':  {'poly': [[210, 200], [240, 180], [250, 230], [220, 250]], 'side': 'left', 'mg': 'bicep'},
        'bicep_right': {'poly': [[390, 200], [360, 180], [350, 230], [380, 250]], 'side': 'right', 'mg': 'bicep'},
        'quad_left':   {'poly': [[250, 400], [300, 400], [290, 500], [240, 500]], 'side': 'left', 'mg': 'quad'},
        'quad_right':  {'poly': [[350, 400], [300, 400], [310, 500], [360, 500]], 'side': 'right', 'mg': 'quad'},
        'shoulder_left':  {'poly': [[230, 120], [260, 120], [240, 160], [220, 150]], 'side': 'left', 'mg': 'shoulder'},
        'shoulder_right': {'poly': [[370, 120], [340, 120], [360, 160], [380, 150]], 'side': 'right', 'mg': 'shoulder'},
    }
    
    # Normalize input records to a quick-lookup dict
    # Keyed by "mg_side"
    data = {}
    for r in scan_records:
        mg = r.get('muscle_group', '')
        side = r.get('side', '')
        key = f"{mg}_{side}"
        data[key] = r

    font = cv2.FONT_HERSHEY_SIMPLEX
    
    for key, region in muscle_map.items():
        poly = np.array(region['poly'], dtype=np.int32)
        
        # Color based on score
        record = data.get(key)
        if not record:
            # Try side-agnostic lookup if side matches
            # Wait, test uses records with 'side'
            color = (200, 200, 200) # Gray
            label = f"{region['mg'].title()} {region['side'].title()}"
        else:
            score = record.get('shape_score', 0)
            if score >= 75: color = (100, 200, 100) # Green
            elif score >= 50: color = (100, 200, 255) # Yellow/Orange
            else: color = (100, 100, 255) # Red
            
            vol = record.get('volume_cm3', 0)
            label = f"{region['mg'].title()}: {vol}cm3"
            
        cv2.fillPoly(img, [poly], color)
        cv2.polylines(img, [poly], True, (50, 50, 50), 1)
        
        # Draw label
        cx, cy = np.mean(poly, axis=0).astype(int)
        cv2.putText(img, label, (cx - 40, cy), font, 0.4, (0, 0, 0), 1)

    cv2.imwrite(output_path, img)
    return output_path
