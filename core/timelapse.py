import numpy as np
import cv2
import imageio
import os

def generate_progress_timelapse(image_paths, contours, metrics_list,
                                output_path="progress.gif", fps=2):
    if not image_paths:
        return None
        
    frames = []
    # Target size for all frames (base it on the first image)
    first_img = cv2.imread(image_paths[0])
    if first_img is None:
        return None
    h, w = first_img.shape[:2]
    
    for i, path in enumerate(image_paths):
        img = cv2.imread(path)
        if img is None:
            continue
            
        # Resize to match first frame
        if img.shape[:2] != (h, w):
            img = cv2.resize(img, (w, h))
            
        # Draw contour if available
        if contours and i < len(contours) and contours[i] is not None:
            cv2.drawContours(img, [contours[i]], -1, (0, 255, 0), 2)
            
        # Draw metrics
        if metrics_list and i < len(metrics_list):
            m = metrics_list[i]
            date = m.get('scan_date', 'N/A')
            vol = m.get('volume_cm3', 'N/A')
            
            # Text box
            cv2.rectangle(img, (0, h - 60), (w, h), (0, 0, 0), -1)
            font = cv2.FONT_HERSHEY_SIMPLEX
            text = f"Date: {date} | Vol: {vol} cm3"
            
            if i > 0:
                prev_vol = metrics_list[i-1].get('volume_cm3')
                if prev_vol and vol != 'N/A' and prev_vol != 0:
                    growth = ((float(vol) - float(prev_vol)) / float(prev_vol)) * 100
                    text += f" ({growth:+.1f}%)"
            
            cv2.putText(img, text, (10, h - 25), font, 0.6, (255, 255, 255), 1)
            
        # Convert BGR to RGB for imageio
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        frames.append(img_rgb)
        
    if not frames:
        return None
        
    imageio.mimsave(output_path, frames, fps=fps)
    return output_path

def generate_comparison_slider_image(img_before, img_after,
                                     contour_before, contour_after,
                                     position=0.5, output_path="slider.png"):
    if img_before is None or img_after is None:
        return None
        
    h, w = img_before.shape[:2]
    # Ensure same size
    if img_after.shape[:2] != (h, w):
        img_after = cv2.resize(img_after, (w, h))
        
    # Draw contours
    vis_before = img_before.copy()
    if contour_before is not None:
        cv2.drawContours(vis_before, [contour_before], -1, (0, 255, 0), 2)
        
    vis_after = img_after.copy()
    if contour_after is not None:
        cv2.drawContours(vis_after, [contour_after], -1, (0, 255, 0), 2)
        
    # Split
    split_x = int(w * position)
    result = np.zeros((h, w, 3), dtype=np.uint8)
    result[:, :split_x] = vis_before[:, :split_x]
    result[:, split_x:] = vis_after[:, split_x:]
    
    # Divider line
    cv2.line(result, (split_x, 0), (split_x, h), (255, 255, 255), 2)
    
    # Labels
    cv2.putText(result, "BEFORE", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(result, "AFTER", (w - 120, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    cv2.imwrite(output_path, result)
    return output_path
