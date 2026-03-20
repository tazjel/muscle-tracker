import numpy as np
import cv2

def score_muscle_definition(image_bgr, contour, muscle_group="bicep"):
    """
    Analyzes texture, edge density, and contrast within a muscle contour.
    """
    if image_bgr is None or contour is None or len(contour) < 3:
        return {
            'texture_score': 0.0, 'edge_density': 0.0, 'contrast_score': 0.0,
            'overall_definition': 0.0, 'grade': 'Bulking'
        }

    # 1. Mask ROI
    h, w = image_bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)
    
    # Crop to bounding box for faster processing
    x, y, bw, bh = cv2.boundingRect(contour)
    if bw < 5 or bh < 5:
        return {
            'texture_score': 0.0, 'edge_density': 0.0, 'contrast_score': 0.0,
            'overall_definition': 0.0, 'grade': 'Bulking'
        }
        
    roi_bgr = image_bgr[y:y+bh, x:x+bw]
    roi_mask = mask[y:y+bh, x:x+bw]
    
    # 2. Preprocess
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # 3. Gabor Filter (Texture)
    texture_vals = []
    # ksize, sigma, theta, lambda, gamma
    for theta in [0, np.pi/4, np.pi/2, 3*np.pi/4]:
        kernel = cv2.getGaborKernel((21, 21), 5.0, theta, 10.0, 0.5, 0, ktype=cv2.CV_32F)
        filtered = cv2.filter2D(gray, cv2.CV_32F, kernel)
        # Only consider inside mask
        val = np.mean(np.abs(filtered[roi_mask > 0]))
        texture_vals.append(val)
    
    # Normalize texture score (heuristic normalization)
    texture_score = min(100.0, np.mean(texture_vals) * 2.5)

    # 4. Laplacian Variance (Edge Density)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    # Mask it
    laplacian_masked = laplacian[roi_mask > 0]
    edge_density = min(100.0, np.var(laplacian_masked) / 20.0)

    # 5. Local Standard Deviation (Contrast)
    # Mean of local 5x5 std devs
    mean, std = cv2.meanStdDev(gray, mask=roi_mask)
    contrast_score = min(100.0, float(std[0,0]) * 2.0)

    # 6. Overall Definition
    overall = 0.4 * texture_score + 0.35 * edge_density + 0.25 * contrast_score
    overall = round(min(100.0, float(overall)), 2)

    # 7. Grade
    if overall >= 80: grade = 'Shredded'
    elif overall >= 65: grade = 'Defined'
    elif overall >= 50: grade = 'Lean'
    elif overall >= 35: grade = 'Smooth'
    else: grade = 'Bulking'

    return {
        'texture_score': round(float(texture_score), 2),
        'edge_density': round(float(edge_density), 2),
        'contrast_score': round(float(contrast_score), 2),
        'overall_definition': overall,
        'grade': grade
    }

def generate_definition_heatmap(image_bgr, contour):
    """
    Generates a heatmap of local Laplacian variance.
    """
    if image_bgr is None or contour is None:
        return None
        
    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Local variance using a sliding window (kernel-based)
    # E[X^2] - (E[X])^2
    gray_f = gray.astype(np.float32)
    mean = cv2.blur(gray_f, (15, 15))
    sq_mean = cv2.blur(gray_f**2, (15, 15))
    var = sq_mean - mean**2
    
    # Normalize variance to 0-255 for heatmap
    var_norm = cv2.normalize(var, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap = cv2.applyColorMap(var_norm, cv2.COLORMAP_JET)
    
    # Mask to contour
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)
    
    # Composite: background (darkened) + heatmap (in contour)
    result = (image_bgr * 0.3).astype(np.uint8)
    heatmap_masked = cv2.bitwise_and(heatmap, heatmap, mask=mask)
    result = cv2.add(result, heatmap_masked)
    
    return result
