import cv2
import numpy as np

def score_muscle_definition(image_bgr, contour, muscle_group='bicep'):
    if image_bgr is None or contour is None:
        return {}
    
    # 1. Extract ROI
    x, y, w, h = cv2.boundingRect(contour)
    roi = image_bgr[y:y+h, x:x+w].copy()
    
    # Mask ROI to keep only muscle pixels
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    shifted_contour = contour.copy()
    shifted_contour[:, :, 0] -= x
    shifted_contour[:, :, 1] -= y
    cv2.fillPoly(roi_mask, [shifted_contour], 255)
    
    # 2. Texture Analysis
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Laplacian variance (sharpness/edge density)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    # Filter Laplacian by mask
    laplacian_muscle = laplacian[roi_mask > 0]
    edge_density = np.var(laplacian_muscle) if laplacian_muscle.size > 0 else 0
    
    # Local contrast variance
    # Simple approach: local StdDev
    # Using a 5x5 sliding window
    mean, stddev = cv2.meanStdDev(gray, mask=roi_mask)
    contrast_score = stddev[0][0]
    
    # 3. Striation Analysis (Gabor Filters - simplified)
    # We'll use a Sobel filter to detect directional edges (fibers)
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    sobel_mag = np.sqrt(sobelx**2 + sobely**2)
    striation_score = np.mean(sobel_mag[roi_mask > 0]) if np.any(roi_mask > 0) else 0
    
    # Normalize scores to 0-100 range
    # Values based on typical muscle photo ranges
    norm_edge = min(100, (edge_density / 500.0) * 100)
    norm_contrast = min(100, (contrast_score / 50.0) * 100)
    norm_striation = min(100, (striation_score / 20.0) * 100)
    
    overall = (norm_edge * 0.4 + norm_contrast * 0.3 + norm_striation * 0.3)
    
    grade = 'Bulking'
    if overall > 85: grade = 'Shredded'
    elif overall > 70: grade = 'Defined'
    elif overall > 50: grade = 'Lean'
    elif overall > 30: grade = 'Smooth'
    
    return {
        'overall_definition': round(overall, 1),
        'edge_density_score': round(norm_edge, 1),
        'contrast_score': round(norm_contrast, 1),
        'striation_score': round(norm_striation, 1),
        'grade': grade,
        'muscle_group': muscle_group
    }

def generate_definition_heatmap(image_bgr, contour):
    if image_bgr is None or contour is None: return None
    
    x, y, w, h = cv2.boundingRect(contour)
    roi = image_bgr[y:y+h, x:x+w].copy()
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Compute local variance as texture proxy
    # Using blurred version to find local variance
    mean = cv2.blur(gray, (15, 15))
    sq_mean = cv2.blur(gray**2, (15, 15))
    variance = sq_mean - mean**2
    
    # Normalize variance for heatmap
    var_norm = cv2.normalize(variance, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
    heatmap = cv2.applyColorMap(var_norm, cv2.COLORMAP_JET)
    
    # Mask heatmap to contour
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    sc = contour.copy()
    sc[:, :, 0] -= x; sc[:, :, 1] -= y
    cv2.fillPoly(roi_mask, [sc], 255)
    
    heatmap = cv2.bitwise_and(heatmap, heatmap, mask=roi_mask)
    
    # Overlay on original image
    res = image_bgr.copy()
    overlay = res[y:y+h, x:x+w]
    cv2.addWeighted(heatmap, 0.6, overlay, 0.4, 0, overlay)
    
    return res
