import cv2
import numpy as np
import os

def generate_progress_timelapse(image_paths, contours, metrics_list, output_path='progress.gif', fps=2):
    if not image_paths: return None
    import PIL.Image
    
    frames = []
    for i, path in enumerate(image_paths):
        img = cv2.imread(path)
        if img is None: continue
        
        # Overlay contour and info
        annotated = img.copy()
        if i < len(contours) and contours[i] is not None:
            cv2.drawContours(annotated, [contours[i]], -1, (200, 180, 0), 2)
            
        if i < len(metrics_list) and metrics_list[i]:
            m = metrics_list[i]
            txt = 'Date: {} | Vol: {:.1f}cm3'.format(m.get('scan_date', 'N/A'), m.get('volume_cm3', 0))
            cv2.putText(annotated, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
        # Convert BGR to RGB for PIL
        rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        frames.append(PIL.Image.fromarray(rgb))
        
    if frames:
        frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=1000//fps, loop=0)
        return output_path
    return None

def generate_comparison_slider_image(img_before, img_after, contour_before, contour_after, position=0.5, output_path='slider.png'):
    if img_before is None or img_after is None: return None
    
    h, w = img_before.shape[:2]
    split_x = int(w * position)
    
    # Resize after to match before if needed
    if img_after.shape[:2] != (h, w):
        img_after = cv2.resize(img_after, (w, h))
        
    res = np.zeros_like(img_before)
    res[:, :split_x] = img_before[:, :split_x]
    res[:, split_x:] = img_after[:, split_x:]
    
    # Draw divider
    cv2.line(res, (split_x, 0), (split_x, h), (255, 255, 255), 2)
    
    # Labels
    cv2.putText(res, 'BEFORE', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(res, 'AFTER', (w - 120, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    cv2.imwrite(output_path, res)
    return output_path
