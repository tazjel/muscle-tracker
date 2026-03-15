import cv2
import numpy as np

def generate_body_map(scan_records, output_path='body_map.png'):
    # Create a blank canvas for the body map
    img = np.full((800, 600, 3), 25, dtype=np.uint8) # Dark background
    
    # Body regions (simplified coordinates for front view silhouette)
    # format: name, (x, y, w, h)
    regions = {
        'shoulder': (250, 150, 100, 50),
        'chest': (250, 200, 100, 80),
        'bicep_l': (200, 200, 40, 80),
        'bicep_r': (360, 200, 40, 80),
        'abs': (260, 280, 80, 100),
        'quad_l': (240, 400, 50, 150),
        'quad_r': (310, 400, 50, 150),
        'calf_l': (240, 560, 40, 120),
        'calf_r': (320, 560, 40, 120)
    }
    
    # Map input records to latest stats
    stats = {}
    for r in scan_records:
        g = r['muscle_group'].lower()
        side = r.get('side', '').lower()
        key = g
        if side in ['left', 'right']:
            key = '{}_{}'.format(g, side[0])
        elif key not in regions and '{}_l'.format(key) in regions:
            # duplicate for both sides if not specified
            stats['{}_l'.format(key)] = r
            stats['{}_r'.format(key)] = r
            continue
        stats[key] = r

    # Draw regions
    for name, rect in regions.items():
        x, y, w, h = rect
        color = (60, 60, 60) # Default gray
        label = 'N/A'
        
        if name in stats:
            s = stats[name]
            score = s.get('shape_score', 50)
            # color: green (100) to red (0)
            if score > 80: color = (0, 200, 0)
            elif score > 60: color = (0, 200, 200)
            else: color = (0, 0, 200)
            label = '{:.1f}cm3'.format(s.get('volume_cm3', 0))
            
        cv2.rectangle(img, (x, y), (x+w, y+h), color, -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (100, 100, 100), 1)
        cv2.putText(img, name.split('_')[0].title(), (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        cv2.putText(img, label, (x+2, y+h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

    cv2.putText(img, 'Muscle Tracker - Body Map', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 180, 0), 2)
    cv2.imwrite(output_path, img)
    return output_path

def generate_body_map_data(scan_records):
    res = {}
    for r in scan_records:
        g = r['muscle_group']
        if g not in res or r['scan_date'] > res[g]['scan_date']:
            res[g] = r
    return res
