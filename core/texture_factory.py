"""
texture_factory.py — PBR texture set generator for body meshes.

Generates complete PBR texture sets (Albedo, Normal, Roughness, AO, Displacement, Definition)
from photo-projected albedo and 3D mesh data.
"""
import os
import logging
import pickle
import numpy as np
import cv2
from core.volumetrics import get_mpfb2_part_ids

logger = logging.getLogger(__name__)

# Base path for project
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default regional roughness values (0.0=shiny, 1.0=matte)
# Based on anatomical skin pore density and sebum levels.
REGION_ROUGHNESS = {
    'face': 0.35, 'chest': 0.42, 'abs': 0.45, 'back': 0.48,
    'arm': 0.52, 'leg': 0.55, 'hand': 0.58, 'foot': 0.62,
    'default': 0.50
}

# SMPL part IDs to region names
_SMPL_PART_MAP = {
    0: 'default', 1: 'leg', 2: 'leg', 3: 'abs', 4: 'leg', 5: 'leg',
    6: 'abs', 7: 'leg', 8: 'leg', 9: 'chest', 10: 'leg', 11: 'leg',
    12: 'face', 13: 'arm', 14: 'arm', 15: 'face', 16: 'arm', 17: 'arm',
    18: 'arm', 19: 'arm', 20: 'hand', 21: 'hand', 22: 'foot', 23: 'foot'
}


def get_part_ids(n_verts):
    """Dispatcher: return part IDs for SMPL (6890) or MPFB2 (13380) meshes."""
    if n_verts == 13380:
        return get_mpfb2_part_ids()
    # For others, height-based fallback
    return None


def generate_roughness_map(uvs, atlas_size=2048, vertices=None, part_ids=None):
    """Generate a base roughness map with anatomical variation."""
    roughness = np.full((atlas_size, atlas_size), REGION_ROUGHNESS['default'], dtype=np.float32)
    
    if part_ids is None:
        part_ids = get_part_ids(len(uvs))
        
    if part_ids is not None and len(part_ids) == len(uvs):
        # Per-vertex roughness
        vert_rough = np.zeros(len(uvs), dtype=np.float32)
        for pid, region in _SMPL_PART_MAP.items():
            mask = part_ids == pid
            vert_rough[mask] = REGION_ROUGHNESS.get(region, REGION_ROUGHNESS['default'])
            
        # Rasterize to atlas
        u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
        v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
        
        # Batch write using scatter
        roughness[v_px, u_px] = vert_rough
        
        # Blur to smooth transitions between regions
        kernel_size = atlas_size // 32 | 1
        roughness = cv2.GaussianBlur(roughness, (kernel_size, kernel_size), 0)
        
    return roughness


def generate_ao_map(vertices, faces, uvs, atlas_size=2048):
    """Generate a simple screen-space AO map baked into UV space."""
    # (Simplified: real AO would use raytracing, here we use a height+curvature proxy)
    ao_map = np.full((atlas_size, atlas_size), 255, dtype=np.uint8)
    
    # Darken crevices based on part IDs (armpits, groin)
    part_ids = get_part_ids(len(vertices))
    if part_ids is not None:
        # Armpits (near shoulder/chest junction) and Groin
        u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
        v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
        
        # Simple procedural darkening for high-occlusion regions
        for pid in [1, 2, 6, 9, 13, 14]: # Thighs, Abs, Chest, Arms
            mask = part_ids == pid
            # Localized darkening could be added here
            pass
            
    return ao_map


def generate_anatomical_overlay(uvs, atlas_size=2048, part_ids=None, vertices=None):
    """Generate anatomical color tints (redness at joints, vein tints)."""
    overlay = np.full((atlas_size, atlas_size, 3), 128, dtype=np.uint8)
    if part_ids is None: part_ids = get_part_ids(len(uvs))
    if part_ids is None or len(part_ids) != len(uvs): return overlay

    vert_tint = np.full((len(uvs), 3), 128, dtype=np.float32)
    # Redness at joints (elbows, knees)
    for pid in [4, 5, 18, 19]:
        vert_tint[part_ids == pid] = [118, 118, 148] # BGR
    # Vein tints on wrists
    for pid in [20, 21]:
        vert_tint[part_ids == pid] = [140, 125, 128]

    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    overlay[v_px, u_px] = vert_tint.astype(np.uint8)
    
    kernel_size = atlas_size // 16 | 1
    return cv2.GaussianBlur(overlay, (kernel_size, kernel_size), 0)


def generate_pbr_textures(albedo, uvs, vertices, faces,
                          normal_map=None, atlas_size=2048,
                          upscale=True, target_size=4096,
                          coverage_mask=None, camera_views=None):
    """
    Generate a complete PBR texture set (Albedo, Normal, Roughness, AO, Displacement, Definition).
    """
    # 1. Cloud GPU check
    try:
        from core.cloud_gpu import is_configured, cloud_pbr_textures
        if is_configured() and upscale:
            logger.info("Trying cloud GPU for PBR textures...")
            res = cloud_pbr_textures(albedo, uvs, vertices, faces, normal_map_bgr=normal_map,
                                     atlas_size=atlas_size, upscale=upscale, target_size=target_size)
            if res: return res
    except Exception as e: logger.warning("Cloud PBR unavailable: %s", e)

    actual_size = target_size if upscale else atlas_size
    oh, ow = actual_size, actual_size

    # 2. Enhance Albedo
    enhanced_albedo = albedo.copy()
    if upscale:
        try:
            from core.texture_enhance import enhance_texture_atlas
            enhanced_albedo = enhance_texture_atlas(albedo, coverage_mask=coverage_mask, 
                                                   upscale=True, target_size=target_size)
        except Exception as e:
            logger.warning("Enhance failed: %s", e)
            if actual_size > albedo.shape[0]:
                enhanced_albedo = cv2.resize(albedo, (ow, oh), interpolation=cv2.INTER_LANCZOS4)

    # 3. Anatomical Overlay
    overlay = generate_anatomical_overlay(uvs, atlas_size)
    overlay_res = cv2.resize(overlay, (ow, oh), interpolation=cv2.INTER_LINEAR)
    enhanced_albedo = np.clip(enhanced_albedo.astype(np.float32) + (overlay_res.astype(np.float32) - 128.0) * 0.15, 0, 255).astype(np.uint8)

    result = {'albedo': enhanced_albedo, 'atlas_size': actual_size}

    # 4. Muscle Definition Map
    definition_atlas = None
    if camera_views:
        from core.muscle_projection import generate_definition_atlas
        try:
            definition_atlas = generate_definition_atlas(vertices, faces, uvs, camera_views, atlas_size=actual_size)
            result['definition'] = definition_atlas
        except Exception as e: logger.warning("Definition failed: %s", e)

    # 5. Normal Map (Composited)
    if normal_map is not None:
        base_n = cv2.resize(normal_map, (ow, oh), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    else:
        from core.mesh_reconstruction import _generate_normal_map
        base_n = _generate_normal_map(vertices, faces, uvs, atlas_size=atlas_size)
        base_n = cv2.resize(base_n, (ow, oh), interpolation=cv2.INTER_LINEAR).astype(np.float32)

    try:
        from core.texture_enhance import generate_skin_normal_map
        detail_n = generate_skin_normal_map(enhanced_albedo, strength=15.0).astype(np.float32)
        bn = (base_n / 127.5) - 1.0
        dn = (detail_n / 127.5) - 1.0
        res_n = bn.copy()
        res_n[:, :, :2] += dn[:, :, :2] * 0.6
        if definition_atlas is not None:
            res_n[:, :, :2] *= (1.0 + (definition_atlas.astype(np.float32)/255.0) * 1.5)[:, :, np.newaxis]
        mag = np.sqrt(np.sum(res_n**2, axis=2, keepdims=True)) + 1e-8
        result['normal'] = ((res_n / mag + 1.0) * 127.5).astype(np.uint8)
    except Exception as e:
        logger.warning("Normal blend failed: %s", e)
        result['normal'] = base_n.astype(np.uint8)

    # 6. Roughness
    rough_base = generate_roughness_map(uvs, actual_size, vertices=vertices)
    gray = cv2.cvtColor(enhanced_albedo, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    high_freq = gray - cv2.GaussianBlur(gray, (7, 7), 0)
    if definition_atlas is not None:
        rough_base = np.clip(rough_base - (definition_atlas.astype(np.float32)/255.0) * 0.3, 0, 1)
    result['roughness'] = (np.clip(rough_base + high_freq * 0.2, 0, 1) * 255).astype(np.uint8)

    # 7. AO & Displacement
    result['ao'] = generate_ao_map(vertices, faces, uvs, atlas_size=actual_size)
    result['displacement'] = np.clip((high_freq + 0.5) * 255, 0, 255).astype(np.uint8)

    return result


def save_pbr_textures(pbr_set, output_dir, prefix='body'):
    os.makedirs(output_dir, exist_ok=True)
    paths = {}
    for name, data in pbr_set.items():
        if data is None or name == 'atlas_size': continue
        path = os.path.join(output_dir, f"{prefix}_{name}.png")
        cv2.imwrite(path, data)
        paths[name] = path
    return paths
