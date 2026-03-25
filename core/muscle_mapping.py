"""
muscle_mapping.py — Project 2D definition scores onto 3D mesh UV space.

Maps 2D muscle definition scores (from definition_scorer.py) to anatomical 
regions on the MPFB2 mesh using the part-ID mapping.
"""
import numpy as np
import cv2
import logging
import os

logger = logging.getLogger(__name__)

# Map internal muscle_group names to SMPL-equivalent part IDs
# Matches _MPFB2_TO_SMPL in texture_factory.py and region_to_parts in body_deform.py
MUSCLE_TO_PARTS = {
    'pectorals': [6, 9],    # chest (spine2, spine3)
    'abs':       [0, 3],    # abdomen (pelvis, spine1)
    'obliques':  [3],       # spine1
    'bicep_l':   [16],      # L shoulder
    'bicep_r':   [17],      # R shoulder
    'quadriceps_l': [1],    # L upper leg
    'quadriceps_r': [2],    # R upper leg
    'calves_l':  [4],       # L knee
    'calves_r':  [5],       # R knee
    'forearms_l': [18],     # L elbow
    'forearms_r': [19],     # R elbow
    'traps':     [12],      # neck/upper traps
    'glutes':    [0],       # pelvis
}

def generate_3d_definition_map(part_ids, scores_dict, atlas_size=1024):
    """
    Generate a UV-space heatmap of muscle definition.
    
    Args:
        part_ids: (N,) int array mapping vertices to SMPL part IDs.
        scores_dict: dict {muscle_group: score_0_to_100}
        atlas_size: target UV map resolution.
        
    Returns:
        (atlas_size, atlas_size) float32 map where value = definition score (0-1).
    """
    n_verts = len(part_ids)
    vert_scores = np.zeros(n_verts, dtype=np.float32)
    
    # Assign scores to vertices based on part mapping
    for muscle, score in scores_dict.items():
        if muscle in MUSCLE_TO_PARTS:
            pids = MUSCLE_TO_PARTS[muscle]
            mask = np.isin(part_ids, pids)
            vert_scores[mask] = max(vert_scores[mask].max() if mask.any() else 0, score / 100.0)
            
    return vert_scores

def create_definition_texture(uvs, faces, vert_scores, atlas_size=1024):
    """
    Rasterize per-vertex definition scores into a UV texture.
    """
    heatmap = np.zeros((atlas_size, atlas_size), dtype=np.float32)
    
    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    
    # Fill triangles with average vertex score
    for f in faces:
        pts = np.array([[u_px[f[0]], v_px[f[0]]],
                        [u_px[f[1]], v_px[f[1]]],
                        [u_px[f[2]], v_px[f[2]]]], dtype=np.int32)
        
        # Skip wrap-around triangles
        if (pts[:, 0].max() - pts[:, 0].min() > atlas_size // 2 or
            pts[:, 1].max() - pts[:, 1].min() > atlas_size // 2):
            continue
            
        avg_score = (vert_scores[f[0]] + vert_scores[f[1]] + vert_scores[f[2]]) / 3.0
        cv2.fillConvexPoly(heatmap, pts.reshape(-1, 1, 2), float(avg_score))
        
    # Smooth for a natural heatmap look
    kernel = atlas_size // 32 | 1
    heatmap = cv2.GaussianBlur(heatmap, (kernel, kernel), 0)
    
    return heatmap

def colorize_definition_map(heatmap_01):
    """
    Convert a 0-1 definition map into a BGR heatmap (Red = Shredded, Blue = Smooth).
    """
    # Use JET or VIRIDIS colormap
    u8 = (heatmap_01 * 255).astype(np.uint8)
    colored = cv2.applyColorMap(u8, cv2.COLORMAP_JET)
    return colored
