"""
skin_audit.py — Automated quality control for skin rendering realism.
Calculates the Edge Warmth Ratio (EWR): the ratio of red-tinted light scattering
vs specular reflection at mesh silhouette edges.
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

def calculate_ewr(image_bgr, body_mask):
    """
    Calculates the Edge Warmth Ratio (EWR) for a rendered image.
    Real skin with SSS shows a subtle red glow at the edges (light scattering).
    
    Args:
        image_bgr: Rendered image (from viewer screenshot or Blender)
        body_mask: Binary mask of the body area
        
    Returns:
        float: EWR score (higher = better SSS effect). Realistic range: 1.15 - 1.40.
    """
    if image_bgr is None or body_mask is None:
        return 0.0
        
    # 1. Identify Silhouette Edges
    # Dilate mask slightly, then subtract original to get boundary pixels
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(body_mask, kernel, iterations=1)
    edges = cv2.bitwise_and(dilated, cv2.bitwise_not(body_mask))
    
    if np.sum(edges) == 0:
        return 0.0
        
    # 2. Extract Edge Pixels
    edge_pixels = image_bgr[edges > 0]
    
    # 3. Calculate Warmth (Red vs Blue/Green ratio)
    # Skin scattering is typically red-shifted
    red = edge_pixels[:, 2].astype(np.float32)
    green = edge_pixels[:, 1].astype(np.float32)
    blue = edge_pixels[:, 0].astype(np.float32)
    
    # Average warmth ratio at the edge
    # Avoid division by zero
    warmth = red / (np.maximum(green, 1.0) * 0.5 + np.maximum(blue, 1.0) * 0.5)
    avg_ewr = np.mean(warmth)
    
    # 4. Reference comparison
    # Calculate warmth of the interior body area for baseline
    body_pixels = image_bgr[body_mask > 0]
    red_b = body_pixels[:, 2].astype(np.float32)
    green_b = body_pixels[:, 1].astype(np.float32)
    blue_b = body_pixels[:, 0].astype(np.float32)
    baseline_warmth = np.mean(red_b / (np.maximum(green_b, 1.0) * 0.5 + np.maximum(blue_b, 1.0) * 0.5))
    
    # Normalized EWR (Edge Warmth vs Body Warmth)
    normalized_ewr = avg_ewr / (baseline_warmth + 1e-8)
    
    logger.info("Skin Audit: EWR = %.3f (Baseline: %.3f)", normalized_ewr, baseline_warmth)
    return normalized_ewr

def audit_pbr_parameters(ewr_score):
    """
    Suggests adjustments to Three.js PBR parameters based on EWR score.
    """
    status = "Ideal"
    adjustments = {}
    
    if ewr_score < 1.05:
        status = "Flat / Plastic"
        adjustments = {
            'attenuationDistance': 0.05, # Increase scattering distance
            'thickness': 2.0,            # Increase volume depth
            'attenuationColor': '#ff3300' # Saturated red
        }
    elif ewr_score < 1.15:
        status = "Sub-optimal"
        adjustments = {
            'attenuationDistance': 0.03,
            'thickness': 1.5
        }
    elif ewr_score > 1.50:
        status = "Too Red / Wax-like"
        adjustments = {
            'attenuationDistance': 0.01,
            'thickness': 0.5
        }
        
    return {
        'status': status,
        'ewr': round(float(ewr_score), 3),
        'suggested_pbr': adjustments
    }
