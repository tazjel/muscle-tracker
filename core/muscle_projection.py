"""
muscle_projection.py — Map 2D muscle highlights to 3D MPFB2 mesh vertices.

This module bridges the gap between vision (image masks) and 3D visualization.
It uses the MPFB2 segmentation to apply localized definition scores.
"""
import numpy as np
import cv2
import logging
from core.volumetrics import get_mpfb2_part_ids

logger = logging.getLogger(__name__)

def project_muscle_intensity(vertices, part_ids, image_masks):
    """
    Apply definition intensity to mesh vertices based on 2D image masks.
    
    Args:
        vertices: (N, 3) MPFB2 vertices
        part_ids: (N,) mapping of vertices to muscle groups
        image_masks: Dict mapping 'muscle_name' to (H, W) intensity mask [0, 1]
        
    Returns:
        vertex_intensities: (N,) float32 definition scores [0, 1]
    """
    # Initialize with base anatomical definition
    intensities = np.zeros(len(vertices), dtype=np.float32)
    
    # Mapping from internal group names to standard muscle IDs
    MUSCLE_MAP = {
        'abs': 3, 'chest': 9, 'bicep_l': 16, 'bicep_r': 17, 
        'quad_l': 4, 'quad_r': 5, 'back': 6
    }
    
    for muscle, mask in image_masks.items():
        if muscle not in MUSCLE_MAP: continue
        p_id = MUSCLE_MAP[muscle]
        
        # Select vertices belonging to this muscle group
        idx = np.where(part_ids == p_id)[0]
        if len(idx) == 0: continue
        
        # Apply intensity from mask (Simplified projection for local fallback)
        # In a full pipeline, this involves 3D-to-2D projection
        intensities[idx] = np.mean(mask) if mask.any() else 0.1
        
    return intensities

def generate_muscle_normals(base_normals, intensities, strength=1.5):
    """
    Deform normals to accentuate muscle definition based on scan intensity.
    Creates that 'carved' cinematic look.
    """
    # perturb normals outward based on muscle intensity
    perturbed = base_normals.copy()
    perturbed[:, 0] *= (1.0 + intensities * strength)
    perturbed[:, 1] *= (1.0 + intensities * strength)
    
    # Normalize
    norms = np.linalg.norm(perturbed, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return perturbed / norms
