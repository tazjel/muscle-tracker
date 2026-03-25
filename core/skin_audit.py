"""
skin_audit.py — Analyze skin rendering quality.

Implements the 'Edge Warmth Ratio' (EWR) metric to detect 'plastic' skin.
Realistic skin has warmer (redder) edges due to subsurface scattering (SSS).
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

def detect_plastic_skin(image_bgr):
    """
    Computes the Edge Warmth Ratio (EWR).
    
    EWR = (Mean Redness of Edges) / (Mean Redness of Interior)
    
    Realistic Skin (SSS active): EWR > 1.10
    Plastic Skin (Flat render): EWR < 1.05
    """
    if image_bgr is None:
        return None
        
    h, w = image_bgr.shape[:2]
    
    # 1. Isolate skin using a rough range
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    lower_skin = np.array([0, 20, 70], dtype=np.uint8)
    upper_skin = np.array([20, 255, 255], dtype=np.uint8)
    skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)
    
    if cv2.countNonZero(skin_mask) < (h * w * 0.05):
        return {"ewr": 1.0, "status": "no_skin_detected"}

    # 2. Get edges within skin mask
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    # Mask edges to skin only
    skin_edges = cv2.bitwise_and(edges, edges, mask=skin_mask)
    
    # Dilate edges slightly to capture the 'warm glow' area
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    skin_edges_dilated = cv2.dilate(skin_edges, kernel, iterations=1)
    
    # 3. Get interior (skin mask minus edges)
    skin_interior = cv2.subtract(skin_mask, skin_edges_dilated)
    
    # 4. Compute Redness (R channel intensity or R/G ratio)
    # Using R/(G+B) for normalized redness
    b, g, r = cv2.split(image_bgr.astype(np.float32))
    redness = r / (g + b + 1e-6)
    
    mean_red_edge = np.mean(redness[skin_edges_dilated > 0]) if np.any(skin_edges_dilated > 0) else 0
    mean_red_interior = np.mean(redness[skin_interior > 0]) if np.any(skin_interior > 0) else 1
    
    ewr = mean_red_edge / (mean_red_interior + 1e-6)
    
    status = "realistic" if ewr > 1.10 else "plastic" if ewr < 1.05 else "borderline"
    
    return {
        "ewr": round(float(ewr), 3),
        "mean_red_edge": round(float(mean_red_edge), 3),
        "mean_red_interior": round(float(mean_red_interior), 3),
        "status": status
    }
