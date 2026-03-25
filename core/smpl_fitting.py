"""
smpl_fitting.py — Parametric body model from user measurements.

Primary method: Anny (NAVER) parametric body model — 13,718 vertices,
anatomically correct topology derived from MakeHuman.

Fallback: Ellipsoid boolean union (when Anny is unavailable).

Coordinate system (right-hand, Z-up):
  X = left–right (positive = right side of body)
  Y = front–back (positive = front)
  Z = height from floor (positive = up)
All coordinates are in mm.
"""

import math
import numpy as np
import os
import warnings
import json
import logging

import trimesh
import trimesh.smoothing

logger = logging.getLogger(__name__)

# ── Default profile (user's personal measurements) ────────────────────────────
DEFAULT_PROFILE = {
    'height_cm':                168,
    'weight_kg':                63,
    # Segment lengths
    'floor_to_knee_cm':         52,
    'knee_to_belly_cm':         40,
    'torso_length_cm':          50,
    'shoulder_to_head_cm':      25,
    'neck_to_shoulder_cm':      15,
    'arm_length_cm':            80,
    'upper_arm_length_cm':      35,
    'forearm_length_cm':        45,
    # Circumferences (cm)
    'head_circumference_cm':    56,
    'neck_circumference_cm':    35,
    'chest_circumference_cm':   97,
    'waist_circumference_cm':   90,
    'hip_circumference_cm':     92,
    'thigh_circumference_cm':   53,
    'quadricep_circumference_cm': 52,
    'calf_circumference_cm':    34,
    'bicep_circumference_cm':   32,
    'forearm_circumference_cm': 29,
    # Extra
    'shoulder_width_cm':        37,
    'skin_tone_hex':            'C4956A',
    'gender':                   'male',
}

def _build_mpfb2_mesh(profile: dict) -> dict | None:
    """
    Build the 13380-vertex MPFB2 (MakeHuman) mesh with phenotype deltas.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    meshes_dir = os.path.join(root, 'meshes')
    
    try:
        verts = np.load(os.path.join(meshes_dir, 'template_verts.npy'))
        faces = np.load(os.path.join(meshes_dir, 'template_faces.npy'))
        uvs = np.load(os.path.join(meshes_dir, 'template_uvs.npy'))
    except FileNotFoundError:
        logger.warning("MPFB2 template files missing in meshes/")
        return None

    # Apply phenotype deltas
    deltas_dir = os.path.join(meshes_dir, 'shape_deltas')
    
    # Calculate phenotype values from profile
    height_cm = profile.get('height_cm', 168)
    weight_kg = profile.get('weight_kg', 63)
    gender = str(profile.get('gender', 'male')).lower()
    
    # Simple mapping for now: weight/muscle params based on BMI and chest-to-waist
    bmi = weight_kg / ((height_cm / 100) ** 2)
    weight_val = max(-1.0, min(1.0, (bmi - 22) / 10))  # 0.0 is average (BMI 22)
    
    chest = profile.get('chest_circumference_cm', 97)
    waist = profile.get('waist_circumference_cm', 90)
    muscle_val = max(-1.0, min(1.0, (chest / max(waist, 1) - 1.05) / 0.2))

    # Load and apply deltas
    def apply_delta(name, weight):
        if abs(weight) < 0.01: return
        path = os.path.join(deltas_dir, f"{name}.npy")
        if os.path.exists(path):
            delta = np.load(path)
            nonlocal verts
            verts += delta * weight

    # Apply Gender (Male/Female deltas are relative to a neutral base)
    if gender in ('male', 'm'):
        apply_delta('md__ca__ma__yn', 1.0)
    else:
        apply_delta('md__ca__fe__yn', 1.0)

    apply_delta('macro_muscle', muscle_val)
    apply_delta('macro_weight', weight_val)

    # Scale to height
    h_range = verts[:, 2].max() - verts[:, 2].min()
    target_mm = height_cm * 10.0
    scale = target_mm / max(h_range, 0.01)
    verts *= scale

    # Floor at Z=0
    verts[:, 2] -= verts[:, 2].min()

    # Get body part IDs from texture factory cache or similar
    from core.texture_factory import get_part_ids
    part_ids = get_part_ids(len(verts))
    if part_ids is None:
        part_ids = np.zeros(len(verts), dtype=np.int32)

    return {
        'vertices': verts.astype(np.float32),
        'faces': faces.astype(np.uint32),
        'uvs': uvs.astype(np.float32),
        'body_part_ids': part_ids,
        'volume_cm3': 0.0, # Will be computed by caller
        'num_vertices': len(verts),
        'num_faces': len(faces),
    }

def _build_anny_mesh(profile: dict) -> dict | None:
    """
    Build a realistic body mesh using Anny (NAVER) parametric model.
    Returns dict with vertices/faces/etc. or None if Anny unavailable.

    Anny phenotype parameters:
      gender:      0.0 = female, 1.0 = male
      age:         0.0 = baby, 0.25 = child, 0.5 = young adult, 1.0 = elderly
      muscle:      0.0 = min, 0.5 = average, 1.0 = max
      weight:      0.0 = min, 0.5 = average, 1.0 = max
      height:      0.0 = short, 0.5 = average, 1.0 = tall
      proportions: 0.0 = ideal, 1.0 = uncommon
    """
    try:
        import anny
        import torch
    except ImportError:
        return None

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = anny.create_fullbody_model()

    # Map user measurements to Anny phenotype parameters
    height_cm = profile.get('height_cm', 168)
    weight_kg = profile.get('weight_kg', 63)

    # Height: map 150–200cm → 0.0–1.0
    height_param = max(0.0, min(1.0, (height_cm - 150) / 50))

    # Weight: estimate from BMI relative to height
    bmi = weight_kg / ((height_cm / 100) ** 2)
    # BMI 15–35 → weight param 0.0–1.0
    weight_param = max(0.0, min(1.0, (bmi - 15) / 20))

    # Muscle: estimate from chest-to-waist ratio (higher = more muscular)
    chest = profile.get('chest_circumference_cm', 97)
    waist = profile.get('waist_circumference_cm', 90)
    bicep = profile.get('bicep_circumference_cm', 32)
    # Chest/waist ratio 1.0-1.3 + bicep size influence
    cw_ratio = chest / max(waist, 1)
    muscle_from_ratio = max(0.0, min(1.0, (cw_ratio - 0.95) / 0.35))
    muscle_from_bicep = max(0.0, min(1.0, (bicep - 25) / 15))
    muscle_param = 0.6 * muscle_from_ratio + 0.4 * muscle_from_bicep

    # Map gender string to Anny parameter (0=male, 1=female)
    gender_str = str(profile.get('gender', 'male')).lower()
    gender_val = 1.0 if gender_str in ('female', 'f', '1') else 0.0

    phenotype = {
        'gender': gender_val,
        'age': 0.5,               # young adult
        'muscle': muscle_param,
        'weight': weight_param,
        'height': height_param,
        'proportions': 0.5,       # average proportions
    }

    with torch.no_grad():
        result = model(phenotype_kwargs=phenotype)

    verts = result['vertices'][0].numpy()  # (13718, 3)

    # Anny is already Z-up — scale to mm
    height_range = verts[:, 2].max() - verts[:, 2].min()
    target_mm = height_cm * 10.0
    scale = target_mm / max(height_range, 0.01)
    verts_mm = (verts * scale).astype(np.float32)

    # Center X/Y, floor at Z=0
    verts_mm[:, 0] -= verts_mm[:, 0].mean()
    verts_mm[:, 1] -= verts_mm[:, 1].mean()
    verts_mm[:, 2] -= verts_mm[:, 2].min()

    # Triangulate quad faces (geometry indices)
    fq = model.faces.numpy()
    geo_tri = np.vstack([fq[:, [0, 1, 2]], fq[:, [0, 2, 3]]]).astype(np.uint32)

    # Triangulate UV face indices (same split pattern)
    uv_fq = model.face_texture_coordinate_indices.numpy()
    uv_tri = np.vstack([uv_fq[:, [0, 1, 2]], uv_fq[:, [0, 2, 3]]]).astype(np.uint32)

    # Expand vertices to match UV count: one vertex per unique UV index
    all_uv_coords = model.texture_coordinates.numpy()  # (21334, 2)
    num_uv = all_uv_coords.shape[0]

    # Build expanded vertex array: UV index → geometry vertex position
    expanded_verts = np.zeros((num_uv, 3), dtype=np.float32)
    for fi in range(len(geo_tri)):
        for vi in range(3):
            geo_idx = geo_tri[fi, vi]
            uv_idx = uv_tri[fi, vi]
            expanded_verts[uv_idx] = verts_mm[geo_idx]

    # Use UV-indexed faces as the final face array
    faces_tri = uv_tri
    uvs = all_uv_coords.astype(np.float32)

    # Update verts_mm to the expanded version
    verts_mm = expanded_verts

    # Volume via trimesh
    try:
        mesh = trimesh.Trimesh(vertices=verts_mm, faces=faces_tri)
        vol_cm3 = round(abs(mesh.volume) / 1000.0, 2) if mesh.is_volume else 0.0
    except Exception:
        vol_cm3 = 0.0

    return {
        'vertices':      verts_mm,
        'faces':         faces_tri,
        'uvs':           uvs,
        'body_part_ids': np.zeros(len(verts_mm), dtype=np.int32),
        'volume_cm3':    vol_cm3,
        'num_vertices':  len(verts_mm),
        'num_faces':     len(faces_tri),
    }


def _ellipsoid(rx, ry, rz, center, subdivisions=2):
    """Create an ellipsoid mesh centered at `center`."""
    s = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
    s.vertices *= [rx, ry, rz]
    s.apply_translation(center)
    return s


def _capsule(rx, ry, height, center):
    """Create an elliptical capsule (cylinder with rounded ends)."""
    r = max(rx, ry)
    c = trimesh.creation.capsule(height=height, radius=r, count=[24, 12])
    c.vertices[:, 0] *= rx / r
    c.vertices[:, 1] *= ry / r
    c.apply_translation(center)
    return c


def _boolean_union(parts):
    """Merge all parts into a single watertight mesh via boolean union."""
    result = parts[0]
    for p in parts[1:]:
        try:
            result = result.union(p)
        except Exception:
            result = trimesh.util.concatenate([result, p])
    return result


def build_body_mesh(profile: dict = None, segments: int = 48,
                    images: list = None, directions: list = None,
                    image_paths: list = None) -> dict:
    """
    Build a full body mesh from body profile measurements.
    Prioritizes MPFB2 template fitting, then Anny, then Ellipsoid fallback.

    Args:
        profile: dict with measurement keys (see DEFAULT_PROFILE).
        segments: ignored (kept for API compatibility).
        images: optional list of (H,W,3) BGR arrays.
        directions: optional list of direction strings ('front', 'left', etc.).
        image_paths: optional list of strings (alternative to 'images').

    Returns:
        dict with vertices, faces, body_part_ids, and volume.
    """
    import logging
    _logger = logging.getLogger(__name__)

    p = {**DEFAULT_PROFILE, **(profile or {})}

    # ── 1. Try MPFB2 template (High fidelity) ──────────────────────────────
    mesh = _build_mpfb2_mesh(p)
    
    if mesh is None:
        # ── 2. Fallback to Anny ────────────────────────────────────────────
        mesh = _build_anny_mesh(p)

    if mesh is not None:
        # ── 3. Silhouette refinement (if scan images provided) ─────────────
        # Note: images/directions/image_paths allows deforming the template to fit photo
        actual_images = image_paths if image_paths else images
        if actual_images and directions:
            try:
                from core.silhouette_extractor import extract_silhouette
                from core.silhouette_matcher import fit_mesh_to_silhouettes
                
                silhouette_views = []
                for i, img_src in enumerate(actual_images):
                    dir_name = directions[i]
                    
                    # If img_src is a path, extract_silhouette handles it. 
                    # If it is a numpy array, we need a temp path for now or 
                    # update extract_silhouette to handle arrays.
                    temp_path = None
                    if isinstance(img_src, np.ndarray):
                        import cv2
                        import tempfile
                        fd, temp_path = tempfile.mkstemp(suffix=".jpg")
                        os.close(fd)
                        cv2.imwrite(temp_path, img_src)
                        path_to_use = temp_path
                    else:
                        path_to_use = img_src
                        
                    # Extract silhouette
                    # Assuming camera distance is stored in profile or use default 100cm
                    dist_cm = p.get('camera_distance_cm', 100.0)
                    contour_mm, mask, ratio = extract_silhouette(path_to_use, dist_cm)
                    
                    if temp_path: os.remove(temp_path)
                    
                    if contour_mm is not None:
                        silhouette_views.append({
                            'contour_mm': contour_mm,
                            'direction': dir_name,
                            'distance_mm': dist_cm * 10,
                            'camera_height_mm': p.get('camera_height_cm', 65.0) * 10
                        })
                
                if silhouette_views:
                    _logger.info("Refining %s mesh with %d silhouette views", 
                                "MPFB2" if mesh['num_vertices'] == 13380 else "Anny",
                                len(silhouette_views))
                    mesh['vertices'] = fit_mesh_to_silhouettes(
                        mesh['vertices'], mesh['faces'], silhouette_views
                    )
            except Exception as e:
                _logger.warning(f"Silhouette refinement failed: {e}")

        # Compute volume of the final mesh
        try:
            m = trimesh.Trimesh(vertices=mesh['vertices'], faces=mesh['faces'])
            mesh['volume_cm3'] = round(abs(m.volume) / 1000.0, 2) if m.is_volume else 0.0
        except Exception:
            mesh['volume_cm3'] = 0.0
            
        return mesh

    # ── 4. Fallback: Ellipsoid boolean union (Basic) ───────────────────────
    def cm(key):
        return p[key] * 10  # cm → mm

    # ── Key heights (mm from floor) ──────────────────────────────────────────
    z_knee      = cm('floor_to_knee_cm')
    z_hip       = z_knee + cm('knee_to_belly_cm') * 0.80
    z_waist     = z_knee + cm('knee_to_belly_cm')
    z_chest_bot = z_waist + cm('torso_length_cm') * 0.35
    z_chest     = z_waist + cm('torso_length_cm') * 0.65
    z_shoulder  = z_waist + cm('torso_length_cm')
    z_neck_base = z_shoulder + cm('neck_to_shoulder_cm') * 0.50
    z_neck_top  = z_shoulder + cm('neck_to_shoulder_cm')
    z_head      = z_neck_top + cm('shoulder_to_head_cm') * 0.50
    z_crown     = z_neck_top + cm('shoulder_to_head_cm')

    # ── Radii from circumferences ────────────────────────────────────────────
    def circ_r(key):
        return cm(key) / (2 * math.pi)

    r_head    = circ_r('head_circumference_cm')
    r_neck    = circ_r('neck_circumference_cm')
    r_chest   = circ_r('chest_circumference_cm')
    r_waist   = circ_r('waist_circumference_cm')
    r_hip     = circ_r('hip_circumference_cm')
    r_thigh   = circ_r('thigh_circumference_cm')
    r_calf    = circ_r('calf_circumference_cm')
    r_bicep   = circ_r('bicep_circumference_cm')
    r_forearm = circ_r('forearm_circumference_cm')
    sw_half   = cm('shoulder_width_cm') / 2

    r_ankle  = r_calf * 0.65
    r_wrist  = r_forearm * 0.60
    r_hand   = r_wrist * 1.3

    parts = []

    # ── HEAD (cranium + jaw for realistic shape) ─────────────────────────────
    # Main cranium — slightly elongated top
    parts.append(_ellipsoid(r_head * 0.95, r_head * 0.98, r_head * 1.18,
                            [0, 0, z_head + 12]))
    # Jaw / lower face — narrower, forward
    parts.append(_ellipsoid(r_head * 0.72, r_head * 0.68, r_head * 0.45,
                            [0, r_head * 0.15, z_head - r_head * 0.35]))
    # Brow ridge — subtle forehead prominence
    parts.append(_ellipsoid(r_head * 0.80, r_head * 0.30, r_head * 0.25,
                            [0, r_head * 0.55, z_head + r_head * 0.30]))

    # ── NECK (with trapezius taper) ──────────────────────────────────────────
    parts.append(_capsule(r_neck, r_neck * 0.88,
                          z_neck_top - z_neck_base,
                          [0, 0, (z_neck_base + z_neck_top) / 2]))
    # Sternocleidomastoid muscles (neck side muscles)
    for side in [1, -1]:
        parts.append(_ellipsoid(r_neck * 0.30, r_neck * 0.35, (z_neck_top - z_neck_base) * 0.5,
                                [side * r_neck * 0.55, r_neck * 0.15,
                                 (z_neck_base + z_neck_top) / 2]))

    # ── TORSO (anatomically detailed) ────────────────────────────────────────
    # Trapezius (upper back → neck, diamond shape)
    parts.append(_ellipsoid(sw_half * 0.70, r_chest * 0.30, 80,
                            [0, -r_chest * 0.20, z_shoulder + 20]))
    # Shoulders (wide, flat — clavicle shelf)
    parts.append(_ellipsoid(sw_half + 12, r_chest * 0.50, 55,
                            [0, 0, z_shoulder]))
    # Upper chest
    parts.append(_ellipsoid(r_chest * 0.93, r_chest * 0.68, r_chest * 0.45,
                            [0, 8, z_chest + 20]))
    # Main chest
    parts.append(_ellipsoid(r_chest * 0.95, r_chest * 0.72, r_chest * 0.75,
                            [0, 5, z_chest]))
    # Ribcage
    parts.append(_ellipsoid(r_chest * 0.88, r_chest * 0.65, (z_chest - z_chest_bot) * 0.6,
                            [0, 0, z_chest_bot + 30]))
    # Waist
    parts.append(_ellipsoid(r_waist * 0.86, r_waist * 0.68, r_waist * 0.55,
                            [0, 0, z_waist]))
    # Belly — subtle forward mass
    parts.append(_ellipsoid(r_waist * 0.90, r_waist * 0.72, r_waist * 0.55,
                            [0, 12, z_waist - 40]))
    # Hips / pelvis
    parts.append(_ellipsoid(r_hip, r_hip * 0.72, r_hip * 0.60,
                            [0, 0, z_hip]))

    # Pectorals (shaped with upper + lower heads for definition)
    for side in [1, -1]:
        # Upper pec
        parts.append(_ellipsoid(50, 25, 35,
                                [side * r_chest * 0.33, r_chest * 0.48, z_chest + 5]))
        # Lower pec (fuller, rounder)
        parts.append(_ellipsoid(55, 32, 40,
                                [side * r_chest * 0.35, r_chest * 0.45, z_chest - 20]))
        # Pec–delt tie-in (smooth transition)
        parts.append(_ellipsoid(25, 20, 30,
                                [side * (r_chest * 0.55), r_chest * 0.30, z_chest + 10]))

    # Serratus anterior (finger-like muscles on side of ribcage)
    for side in [1, -1]:
        for i in range(3):
            z_pos = z_chest - 30 - i * 25
            parts.append(_ellipsoid(18, 15, 18,
                                    [side * (r_chest * 0.80), r_chest * 0.10, z_pos]))

    # Latissimus dorsi (back width — V-taper)
    for side in [1, -1]:
        parts.append(_ellipsoid(r_chest * 0.45, r_chest * 0.40, r_chest * 0.60,
                                [side * r_chest * 0.55, -r_chest * 0.30, z_chest - 40]))
        # Lower lat insertion
        parts.append(_ellipsoid(r_chest * 0.30, r_chest * 0.25, r_chest * 0.35,
                                [side * r_chest * 0.40, -r_chest * 0.25, z_waist + 30]))

    # Spinal erectors (lower back)
    for side in [1, -1]:
        parts.append(_ellipsoid(r_waist * 0.18, r_waist * 0.22, r_waist * 0.50,
                                [side * r_waist * 0.12, -r_waist * 0.50, z_waist + 20]))

    # Abdominals (rectus abdominis — 3 pairs of "blocks")
    ab_width = r_waist * 0.18
    ab_depth = r_waist * 0.12
    ab_gap = 8  # linea alba gap
    for i, z_frac in enumerate([0.20, 0.40, 0.58]):
        z_ab = z_waist + (z_chest_bot - z_waist) * z_frac
        ab_h = 28 - i * 3  # slightly smaller going up
        for side in [1, -1]:
            parts.append(_ellipsoid(ab_width, ab_depth, ab_h,
                                    [side * (ab_width + ab_gap), r_waist * 0.55, z_ab]))

    # External obliques (side waist muscles)
    for side in [1, -1]:
        parts.append(_ellipsoid(r_waist * 0.30, r_waist * 0.25, r_waist * 0.40,
                                [side * r_waist * 0.65, r_waist * 0.15, z_waist + 20]))

    # Glutes (upper + lower for realistic shape)
    for side in [1, -1]:
        # Gluteus maximus (main mass)
        parts.append(_ellipsoid(r_hip * 0.42, r_hip * 0.50, r_hip * 0.42,
                                [side * r_hip * 0.33, -r_hip * 0.28, z_hip - 15]))
        # Gluteus medius (upper outer)
        parts.append(_ellipsoid(r_hip * 0.28, r_hip * 0.25, r_hip * 0.25,
                                [side * r_hip * 0.50, -r_hip * 0.10, z_hip + 15]))

    # ── LEGS (anatomically detailed, symmetric) ─────────────────────────────
    leg_x = r_hip * 0.50
    for side in [1, -1]:
        x = side * leg_x
        thigh_len = z_hip - z_knee
        z_mid_thigh = z_knee + thigh_len * 0.55

        # Main thigh cylinder
        parts.append(_capsule(r_thigh, r_thigh * 0.82,
                              thigh_len * 0.85,
                              [x, 0, z_knee + thigh_len * 0.5]))
        # Inner thigh fill (adductors)
        parts.append(_ellipsoid(r_thigh * 0.55, r_thigh * 0.50, thigh_len * 0.35,
                                [x * 0.70, 0, z_hip - 40]))
        # Rectus femoris (front of thigh — main quad)
        parts.append(_ellipsoid(r_thigh * 0.40, r_thigh * 0.30, thigh_len * 0.40,
                                [x, r_thigh * 0.50, z_mid_thigh]))
        # Vastus lateralis (outer quad)
        parts.append(_ellipsoid(r_thigh * 0.35, r_thigh * 0.25, thigh_len * 0.35,
                                [x + side * r_thigh * 0.40, r_thigh * 0.20, z_mid_thigh - 15]))
        # Vastus medialis (inner quad — "teardrop")
        parts.append(_ellipsoid(r_thigh * 0.28, r_thigh * 0.22, r_thigh * 0.50,
                                [x - side * r_thigh * 0.30, r_thigh * 0.25, z_knee + 40]))
        # Hamstrings (back of thigh — biceps femoris)
        parts.append(_ellipsoid(r_thigh * 0.38, r_thigh * 0.30, thigh_len * 0.40,
                                [x + side * r_thigh * 0.15, -r_thigh * 0.40, z_mid_thigh]))
        # Hamstrings (semitendinosus — inner back)
        parts.append(_ellipsoid(r_thigh * 0.30, r_thigh * 0.25, thigh_len * 0.35,
                                [x - side * r_thigh * 0.20, -r_thigh * 0.35, z_mid_thigh - 10]))
        # IT band area (outer thigh)
        parts.append(_ellipsoid(r_thigh * 0.20, r_thigh * 0.15, thigh_len * 0.50,
                                [x + side * r_thigh * 0.55, 0, z_mid_thigh]))

        # Knee — patella + condyles
        parts.append(_ellipsoid(r_calf * 1.08, r_calf * 1.05, r_calf * 0.80,
                                [x, 5, z_knee]))
        # Patella (kneecap — front bulge)
        parts.append(_ellipsoid(r_calf * 0.40, r_calf * 0.35, r_calf * 0.35,
                                [x, r_calf * 0.70, z_knee + 5]))

        # Calf (gastrocnemius — two heads)
        calf_len = z_knee - 80
        z_mid_calf = 80 + calf_len * 0.45
        parts.append(_capsule(r_calf, r_calf * 0.82,
                              calf_len * 0.75,
                              [x, -5, z_mid_calf]))
        # Gastrocnemius medial head (inner calf bulge)
        parts.append(_ellipsoid(r_calf * 0.50, r_calf * 0.55, r_calf * 1.0,
                                [x - side * r_calf * 0.15, -r_calf * 0.35, z_knee - calf_len * 0.25]))
        # Gastrocnemius lateral head (outer calf bulge)
        parts.append(_ellipsoid(r_calf * 0.45, r_calf * 0.50, r_calf * 0.90,
                                [x + side * r_calf * 0.20, -r_calf * 0.30, z_knee - calf_len * 0.28]))
        # Tibialis anterior (shin muscle — front)
        parts.append(_ellipsoid(r_calf * 0.35, r_calf * 0.30, calf_len * 0.40,
                                [x + side * r_calf * 0.20, r_calf * 0.35, z_knee - calf_len * 0.30]))
        # Soleus (deep calf — lower, wider)
        parts.append(_ellipsoid(r_calf * 0.60, r_calf * 0.50, r_calf * 0.70,
                                [x, -r_calf * 0.15, z_knee - calf_len * 0.50]))

        # Ankle — with Achilles tendon taper
        parts.append(_ellipsoid(r_ankle * 1.05, r_ankle * 0.95, r_ankle * 0.90,
                                [x, 0, 75]))
        # Achilles tendon
        parts.append(_ellipsoid(r_ankle * 0.30, r_ankle * 0.40, r_ankle * 1.2,
                                [x, -r_ankle * 0.55, 85]))

        # Foot — heel + ball + arch
        parts.append(_ellipsoid(r_ankle * 1.15, r_ankle * 2.0, r_ankle * 0.55,
                                [x, r_ankle * 0.6, 25]))
        # Heel prominence
        parts.append(_ellipsoid(r_ankle * 0.70, r_ankle * 0.75, r_ankle * 0.50,
                                [x, -r_ankle * 0.50, 30]))

    # ── ARMS (A-pose, anatomically detailed) ─────────────────────────────────
    arm_len = cm('arm_length_cm')
    upper_len = cm('upper_arm_length_cm')
    forearm_len = cm('forearm_length_cm')

    for side in [1, -1]:
        x = side * (sw_half + 10)
        z_elbow = z_shoulder - upper_len
        z_wrist = z_elbow - forearm_len
        z_hand_end = z_wrist - r_hand * 2.5
        z_mid_upper = z_shoulder - upper_len * 0.45

        # Deltoid — 3 heads for rounded shoulder cap
        # Anterior deltoid (front)
        parts.append(_ellipsoid(r_bicep * 0.55, r_bicep * 0.65, r_bicep * 0.70,
                                [x, r_bicep * 0.30, z_shoulder - 10]))
        # Lateral deltoid (side — widest point)
        parts.append(_ellipsoid(r_bicep * 0.70, r_bicep * 0.55, r_bicep * 0.75,
                                [x + side * r_bicep * 0.25, 0, z_shoulder - 5]))
        # Posterior deltoid (rear)
        parts.append(_ellipsoid(r_bicep * 0.50, r_bicep * 0.55, r_bicep * 0.65,
                                [x, -r_bicep * 0.30, z_shoulder - 12]))
        # Deltoid cap (smooth merger)
        parts.append(_ellipsoid(r_bicep * 1.08, r_bicep * 1.00, r_bicep * 0.90,
                                [x, 0, z_shoulder]))

        # Bicep (biceps brachii — front of upper arm)
        parts.append(_ellipsoid(r_bicep * 0.55, r_bicep * 0.50, upper_len * 0.40,
                                [x, r_bicep * 0.35, z_mid_upper]))
        # Brachialis (underneath bicep — adds width)
        parts.append(_ellipsoid(r_bicep * 0.45, r_bicep * 0.40, upper_len * 0.35,
                                [x + side * r_bicep * 0.15, r_bicep * 0.10, z_mid_upper - 10]))
        # Tricep (back of upper arm — 3 heads merged)
        parts.append(_ellipsoid(r_bicep * 0.50, r_bicep * 0.55, upper_len * 0.45,
                                [x, -r_bicep * 0.30, z_mid_upper + 5]))
        # Main upper arm cylinder (structural)
        parts.append(_capsule(r_bicep * 0.88, r_bicep * 0.85,
                              upper_len * 0.78,
                              [x, 3, z_mid_upper]))

        # Elbow — olecranon process (bony back)
        parts.append(_ellipsoid(r_forearm * 0.92, r_forearm * 0.88, r_forearm * 0.72,
                                [x, -3, z_elbow]))
        parts.append(_ellipsoid(r_forearm * 0.35, r_forearm * 0.40, r_forearm * 0.30,
                                [x, -r_forearm * 0.55, z_elbow - 5]))

        # Forearm — main cylinder
        parts.append(_capsule(r_forearm * 0.95, r_forearm * 0.88,
                              forearm_len * 0.75,
                              [x, 0, z_elbow - forearm_len * 0.42]))
        # Forearm extensors (top/outer mass)
        parts.append(_ellipsoid(r_forearm * 0.40, r_forearm * 0.35, forearm_len * 0.35,
                                [x + side * r_forearm * 0.20, r_forearm * 0.20,
                                 z_elbow - forearm_len * 0.25]))
        # Forearm flexors (bottom/inner mass)
        parts.append(_ellipsoid(r_forearm * 0.35, r_forearm * 0.35, forearm_len * 0.30,
                                [x - side * r_forearm * 0.10, -r_forearm * 0.15,
                                 z_elbow - forearm_len * 0.30]))

        # Wrist — bony narrowing
        parts.append(_ellipsoid(r_wrist * 1.05, r_wrist * 0.85, r_wrist * 0.75,
                                [x, 0, z_wrist]))
        # Hand — palm + fingers suggestion
        parts.append(_ellipsoid(r_hand * 0.95, r_hand * 0.38, r_hand * 1.7,
                                [x, 0, z_wrist - r_hand * 1.4]))
        # Thumb mound
        parts.append(_ellipsoid(r_hand * 0.35, r_hand * 0.35, r_hand * 0.50,
                                [x + side * r_hand * 0.50, r_hand * 0.15,
                                 z_wrist - r_hand * 0.8]))

    # ── BOOLEAN UNION ────────────────────────────────────────────────────────
    mesh = _boolean_union(parts)

    # Multi-pass smoothing for organic, natural look
    # Pass 1: Aggressive smoothing to blend boolean seams
    mesh = trimesh.smoothing.filter_laplacian(mesh, iterations=3, lamb=0.5)
    # Pass 2: Gentle smoothing to preserve muscle definition
    mesh = trimesh.smoothing.filter_laplacian(mesh, iterations=2, lamb=0.3)

    verts_np = np.array(mesh.vertices, dtype=np.float32)
    faces_np = np.array(mesh.faces,    dtype=np.uint32)

    # Volume from the watertight mesh
    vol_cm3 = round(abs(mesh.volume) / 1000.0, 2) if mesh.is_volume else 0.0

    return {
        'vertices':      verts_np,
        'faces':         faces_np,
        'body_part_ids': np.zeros(len(verts_np), dtype=np.int32),
        'volume_cm3':    vol_cm3,
        'num_vertices':  len(verts_np),
        'num_faces':     len(faces_np),
    }


def fit_body_model(profile: dict = None, output_dir: str = 'meshes',
                   base_name: str = None) -> dict:
    """
    High-level entry point: build mesh, export GLB + OBJ, return paths.

    Args:
        profile:    body profile dict (see DEFAULT_PROFILE).
        output_dir: directory to write files.
        base_name:  stem for output files (auto-generated if None).

    Returns:
        dict with 'glb_path', 'obj_path', 'volume_cm3',
                  'num_vertices', 'num_faces'.
    """
    import time
    from core.mesh_reconstruction import export_obj, export_glb

    mesh = build_body_mesh(profile)
    os.makedirs(output_dir, exist_ok=True)

    if base_name is None:
        base_name = f'body_{int(time.time())}'

    obj_path = os.path.join(output_dir, base_name + '.obj')
    glb_path = os.path.join(output_dir, base_name + '.glb')

    export_obj(mesh['vertices'], mesh['faces'], obj_path)
    try:
        export_glb(mesh['vertices'], mesh['faces'], glb_path)
    except Exception:
        glb_path = None

    return {
        'glb_path':     glb_path,
        'obj_path':     obj_path,
        'volume_cm3':   mesh['volume_cm3'],
        'num_vertices': mesh['num_vertices'],
        'num_faces':    mesh['num_faces'],
    }
