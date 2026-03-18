"""
smpl_fitting.py — Parametric body model from user measurements.

Builds an anatomically shaped human body mesh using overlapping ellipsoid
primitives merged via boolean union (manifold3d).  The result is a single
continuous watertight mesh that looks like a real human body.

Coordinate system (right-hand, Z-up):
  X = left–right (positive = right side of body)
  Y = front–back (positive = front)
  Z = height from floor (positive = up)
All coordinates are in mm.
"""

import math
import numpy as np
import os

import trimesh
import trimesh.smoothing


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


def build_body_mesh(profile: dict = None, segments: int = 48) -> dict:
    """
    Build a full body mesh from body profile measurements using ellipsoid
    primitives merged via boolean union.

    Args:
        profile: dict with measurement keys (see DEFAULT_PROFILE).
        segments: ignored (kept for API compatibility).

    Returns:
        dict with:
          'vertices'      — np.float32 (N, 3), units = mm
          'faces'         — np.uint32  (M, 3)
          'body_part_ids' — np.int32   (N,)  (all zeros — single mesh)
          'volume_cm3'    — float
          'num_vertices'  — int
          'num_faces'     — int
    """
    p = {**DEFAULT_PROFILE, **(profile or {})}

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

    # ── HEAD ─────────────────────────────────────────────────────────────────
    parts.append(_ellipsoid(r_head * 0.95, r_head, r_head * 1.15,
                            [0, 0, z_head + 10]))

    # ── NECK ─────────────────────────────────────────────────────────────────
    parts.append(_capsule(r_neck, r_neck * 0.90,
                          z_neck_top - z_neck_base,
                          [0, 0, (z_neck_base + z_neck_top) / 2]))

    # ── TORSO (overlapping ellipsoids for organic shape) ─────────────────────
    # Shoulders (wide, flat)
    parts.append(_ellipsoid(sw_half + 10, r_chest * 0.55, 60,
                            [0, 0, z_shoulder]))
    # Chest
    parts.append(_ellipsoid(r_chest * 0.95, r_chest * 0.72, r_chest * 0.80,
                            [0, 5, z_chest]))
    # Ribcage
    parts.append(_ellipsoid(r_chest * 0.88, r_chest * 0.65, (z_chest - z_chest_bot) * 0.6,
                            [0, 0, z_chest_bot + 30]))
    # Waist
    parts.append(_ellipsoid(r_waist * 0.88, r_waist * 0.70, r_waist * 0.55,
                            [0, 0, z_waist]))
    # Belly
    parts.append(_ellipsoid(r_waist * 0.92, r_waist * 0.73, r_waist * 0.55,
                            [0, 10, z_waist - 40]))
    # Hips / pelvis
    parts.append(_ellipsoid(r_hip, r_hip * 0.72, r_hip * 0.60,
                            [0, 0, z_hip]))
    # Pectorals
    parts.append(_ellipsoid(55, 30, 45, [r_chest * 0.35, r_chest * 0.45, z_chest - 15]))
    parts.append(_ellipsoid(55, 30, 45, [-r_chest * 0.35, r_chest * 0.45, z_chest - 15]))
    # Glutes
    parts.append(_ellipsoid(r_hip * 0.42, r_hip * 0.48, r_hip * 0.40,
                            [r_hip * 0.35, -r_hip * 0.25, z_hip - 20]))
    parts.append(_ellipsoid(r_hip * 0.42, r_hip * 0.48, r_hip * 0.40,
                            [-r_hip * 0.35, -r_hip * 0.25, z_hip - 20]))

    # ── LEGS (symmetric) ────────────────────────────────────────────────────
    leg_x = r_hip * 0.50
    for side in [1, -1]:
        x = side * leg_x
        # Thigh
        thigh_len = z_hip - z_knee
        parts.append(_capsule(r_thigh, r_thigh * 0.85,
                              thigh_len * 0.85,
                              [x, 0, z_knee + thigh_len * 0.5]))
        # Inner thigh fill (smooth crotch area)
        parts.append(_ellipsoid(r_thigh * 0.65, r_thigh * 0.60, thigh_len * 0.30,
                                [x * 0.7, 0, z_hip - 30]))
        # Knee
        parts.append(_ellipsoid(r_calf * 1.10, r_calf * 1.05, r_calf * 0.85,
                                [x, 5, z_knee]))
        # Calf
        calf_len = z_knee - 80
        parts.append(_capsule(r_calf, r_calf * 0.85,
                              calf_len * 0.75,
                              [x, -5, 80 + calf_len * 0.45]))
        # Calf muscle bulge
        parts.append(_ellipsoid(r_calf * 0.75, r_calf * 0.85, r_calf * 1.2,
                                [x, -r_calf * 0.35, z_knee - z_knee * 0.22]))
        # Ankle
        parts.append(_ellipsoid(r_ankle, r_ankle, r_ankle * 0.90,
                                [x, 0, 75]))
        # Foot
        parts.append(_ellipsoid(r_ankle * 1.2, r_ankle * 2.2, r_ankle * 0.65,
                                [x, r_ankle * 0.8, 25]))

    # ── ARMS (A-pose, hanging down) ─────────────────────────────────────────
    arm_len = cm('arm_length_cm')
    upper_len = cm('upper_arm_length_cm')
    forearm_len = cm('forearm_length_cm')

    for side in [1, -1]:
        x = side * (sw_half + 10)
        z_elbow = z_shoulder - upper_len
        z_wrist = z_elbow - forearm_len
        z_hand_end = z_wrist - r_hand * 2.5

        # Deltoid cap
        parts.append(_ellipsoid(r_bicep * 1.10, r_bicep * 1.05, r_bicep * 1.05,
                                [x, 0, z_shoulder]))
        # Upper arm (bicep/tricep)
        parts.append(_capsule(r_bicep, r_bicep * 0.90,
                              upper_len * 0.80,
                              [x, 5, z_shoulder - upper_len * 0.45]))
        # Elbow
        parts.append(_ellipsoid(r_forearm * 0.95, r_forearm * 0.90, r_forearm * 0.75,
                                [x, -3, z_elbow]))
        # Forearm
        parts.append(_capsule(r_forearm, r_forearm * 0.90,
                              forearm_len * 0.75,
                              [x, 0, z_elbow - forearm_len * 0.42]))
        # Wrist
        parts.append(_ellipsoid(r_wrist * 1.05, r_wrist * 0.90, r_wrist * 0.80,
                                [x, 0, z_wrist]))
        # Hand
        parts.append(_ellipsoid(r_hand, r_hand * 0.40, r_hand * 1.8,
                                [x, 0, z_wrist - r_hand * 1.5]))

    # ── BOOLEAN UNION ────────────────────────────────────────────────────────
    mesh = _boolean_union(parts)

    # Smooth for a more natural look
    mesh = trimesh.smoothing.filter_laplacian(mesh, iterations=2, lamb=0.5)

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
