"""
smpl_fitting.py — Lightweight parametric body model from user measurements.

This is NOT a full SMPL neural model (that requires ~300 MB weights).
Instead it uses the body_profile measurements to build an anatomically
proportioned body mesh (torso + arms + legs in A-pose) driven by
ground-truth measurements rather than silhouettes.

The resulting mesh is exported as GLB and can be loaded directly in the
3D viewer with ?model=<url>.

Coordinate system (right-hand, Z-up):
  X = left–right (positive = right side of body)
  Y = front–back (positive = front)
  Z = height from floor (positive = up)
All coordinates are in mm.
"""

import math
import numpy as np
import os


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


def _ellipse_ring(cx, cy, z, a, b, segments=32):
    """Return list of (x, y, z) vertex positions for one horizontal ellipse ring."""
    ring = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        ring.append((cx + a * math.cos(angle),
                     cy + b * math.sin(angle),
                     z))
    return ring


def _connect_rings(verts, faces, ring_a_start, ring_b_start, segments):
    """Add quads (2 triangles each) between two consecutive rings."""
    for s in range(segments):
        s_next = (s + 1) % segments
        a0 = ring_a_start + s
        a1 = ring_a_start + s_next
        b0 = ring_b_start + s
        b1 = ring_b_start + s_next
        faces.append([a0, b0, a1])
        faces.append([a1, b0, b1])


def _build_limb(rings, segments=32):
    """Build a tube mesh from a list of (cx, cy, z, a, b) ring definitions.

    Returns (vertices_list, faces_list) with LOCAL indices starting at 0.
    Adds a cap at both ends of the tube.
    """
    verts = []
    faces = []
    ring_starts = []
    for cx, cy, z, a, b in rings:
        ring_starts.append(len(verts))
        verts.extend(_ellipse_ring(cx, cy, z, a, b, segments))
    for i in range(len(rings) - 1):
        _connect_rings(verts, faces, ring_starts[i], ring_starts[i + 1], segments)
    # End cap (last ring in the list)
    cap_end = len(verts)
    verts.append((rings[-1][0], rings[-1][1], rings[-1][2]))
    rs = ring_starts[-1]
    for s in range(segments):
        faces.append([rs + s, cap_end, rs + (s + 1) % segments])
    # Start cap (first ring in the list)
    cap_start = len(verts)
    verts.append((rings[0][0], rings[0][1], rings[0][2]))
    rs0 = ring_starts[0]
    for s in range(segments):
        faces.append([rs0 + (s + 1) % segments, cap_start, rs0 + s])
    return verts, faces


def _merge_meshes(parts):
    """Merge multiple (verts_list, faces_list) into one mesh.

    Each part's face indices are offset by the cumulative vertex count.
    Returns (all_verts list, all_faces list).
    """
    all_verts = []
    all_faces = []
    offset = 0
    for verts, faces in parts:
        all_verts.extend(verts)
        for f in faces:
            all_faces.append([f[0] + offset, f[1] + offset, f[2] + offset])
        offset += len(verts)
    return all_verts, all_faces


def build_body_mesh(profile: dict = None, segments: int = 32) -> dict:
    """
    Build a full body mesh (torso + arms + legs, A-pose) from body profile measurements.

    Args:
        profile: dict with measurement keys (see DEFAULT_PROFILE).
                 Missing keys fall back to DEFAULT_PROFILE values.
        segments: number of vertices per cross-section ring (higher = smoother).

    Returns:
        dict with:
          'vertices'      — np.float32 (N, 3), units = mm
          'faces'         — np.uint32  (M, 3)
          'body_part_ids' — np.int32   (N,)  0=torso 1=r_arm 2=l_arm 3=r_leg 4=l_leg
          'volume_cm3'    — float
          'num_vertices'  — int
          'num_faces'     — int
    """
    p = {**DEFAULT_PROFILE, **(profile or {})}

    def cm(key):
        return p[key] * 10  # cm → mm

    # ── Key anatomy heights (mm from floor) ───────────────────────────────────
    z_knee      = cm('floor_to_knee_cm')
    z_mid_thigh = z_knee + cm('knee_to_belly_cm') * 0.50  # 720mm
    z_hip       = z_knee + cm('knee_to_belly_cm') * 0.80  # 840mm – max hip girth
    z_waist     = z_knee + cm('knee_to_belly_cm')          # 920mm
    z_chest_bot = z_waist + cm('torso_length_cm') * 0.35
    z_chest     = z_waist + cm('torso_length_cm') * 0.65
    z_shoulder  = z_waist + cm('torso_length_cm')
    z_neck_base = z_shoulder + cm('neck_to_shoulder_cm') * 0.50
    z_neck_top  = z_shoulder + cm('neck_to_shoulder_cm')
    z_head      = z_neck_top + cm('shoulder_to_head_cm') * 0.50
    z_crown     = z_neck_top + cm('shoulder_to_head_cm')

    # ── Circumferences in mm ──────────────────────────────────────────────────
    calf_circ    = cm('calf_circumference_cm')
    quad_circ    = cm('quadricep_circumference_cm')
    hip_circ     = cm('hip_circumference_cm')
    waist_circ   = cm('waist_circumference_cm')
    chest_circ   = cm('chest_circumference_cm')
    neck_circ    = cm('neck_circumference_cm')
    head_circ    = cm('head_circumference_cm')
    shoulder_w   = cm('shoulder_width_cm')
    bicep_circ   = cm('bicep_circumference_cm')
    forearm_circ = cm('forearm_circumference_cm')
    thigh_circ   = cm('thigh_circumference_cm')

    # ── Torso: 35 rings via anchor interpolation ───────────────────────────────
    anchors = [
        (0,            calf_circ * 0.75),
        (z_knee * 0.3, calf_circ),
        (z_knee,       calf_circ * 0.95),
        (z_mid_thigh,  quad_circ),
        (z_hip,        hip_circ),
        (z_waist,      waist_circ),
        (z_chest_bot,  (chest_circ + waist_circ) / 2),
        (z_chest,      chest_circ),
        (z_shoulder,   shoulder_w * math.pi),   # width → approx circ
        (z_neck_base,  neck_circ),
        (z_neck_top,   neck_circ * 0.9),
        (z_head,       head_circ),
        (z_crown,      head_circ * 0.7),
    ]
    anchor_zs    = [a[0] for a in anchors]
    anchor_circs = [a[1] for a in anchors]

    num_rings = 35
    z_levels = np.linspace(0.0, z_crown, num_rings)
    circs    = np.interp(z_levels, anchor_zs, anchor_circs)

    def aspect_at_z(z):
        """Front-back / left-right ratio per height zone."""
        if z < z_knee:       return 0.85
        if z < z_waist:      return 0.70
        if z < z_chest:      return 0.65
        if z < z_shoulder:   return 0.60
        return 0.95

    torso_rings = []
    for i in range(num_rings):
        z = float(z_levels[i])
        circ = float(circs[i])
        a = circ / (2 * math.pi)
        b = a * aspect_at_z(z)
        torso_rings.append((0.0, 0.0, z, a, b))

    # ── Arms (A-pose — tips hang DOWN, z decreases from shoulder) ────────────
    r_bicep   = bicep_circ / (2 * math.pi)
    r_forearm = forearm_circ / (2 * math.pi)
    r_wrist   = r_forearm * 0.60
    r_hand    = r_wrist * 1.10
    sx = shoulder_w / 2  # x offset of shoulder joint

    right_arm_rings = [
        (sx,      0, z_shoulder,       r_bicep * 1.10, r_bicep * 0.90),
        (sx + 30, 0, z_shoulder -  50, r_bicep,        r_bicep * 0.85),
        (sx + 50, 0, z_shoulder - 180, r_bicep,        r_bicep * 0.80),
        (sx + 50, 0, z_shoulder - 350, r_forearm * 1.1, r_forearm),
        (sx + 40, 0, z_shoulder - 400, r_forearm,      r_forearm * 0.90),
        (sx + 30, 0, z_shoulder - 600, r_forearm * 0.85, r_forearm * 0.80),
        (sx + 20, 0, z_shoulder - 750, r_wrist,        r_wrist),
        (sx + 15, 0, z_shoulder - 800, r_hand,         r_hand * 0.50),
    ]
    left_arm_rings = [(-cx, cy, z, a, b) for cx, cy, z, a, b in right_arm_rings]

    # ── Legs (from hip socket DOWN to floor) ─────────────────────────────────
    hip_offset = hip_circ / (2 * math.pi) * 0.45
    r_thigh_r  = thigh_circ / (2 * math.pi)
    r_calf_r   = calf_circ  / (2 * math.pi)
    r_ankle_r  = r_calf_r * 0.70
    r_foot     = r_ankle_r * 1.30

    right_leg_rings = [
        (hip_offset,  0, z_waist,       r_thigh_r,        r_thigh_r * 0.80),
        (hip_offset,  0, z_hip,         r_thigh_r * 1.05, r_thigh_r * 0.80),
        (hip_offset,  0, z_knee + 100,  r_thigh_r * 0.90, r_thigh_r * 0.70),
        (hip_offset,  0, z_knee,        r_calf_r  * 1.10, r_calf_r  * 0.90),
        (hip_offset,  0, z_knee - 100,  r_calf_r  * 1.05, r_calf_r  * 0.85),
        (hip_offset,  0, z_knee * 0.40, r_calf_r,         r_calf_r  * 0.80),
        (hip_offset,  0, 80,            r_ankle_r,        r_ankle_r),
        (hip_offset, 20, 0,             r_foot,           r_foot    * 0.50),
    ]
    left_leg_rings = [(-cx, cy, z, a, b) for cx, cy, z, a, b in right_leg_rings]

    # ── Build meshes for each part ────────────────────────────────────────────
    torso_verts, torso_faces = _build_limb(torso_rings,     segments)
    r_arm_verts, r_arm_faces = _build_limb(right_arm_rings, segments)
    l_arm_verts, l_arm_faces = _build_limb(left_arm_rings,  segments)
    r_leg_verts, r_leg_faces = _build_limb(right_leg_rings, segments)
    l_leg_verts, l_leg_faces = _build_limb(left_leg_rings,  segments)

    # ── Assign body part IDs per vertex ───────────────────────────────────────
    # 0=torso, 1=right_arm, 2=left_arm, 3=right_leg, 4=left_leg
    part_ids = (
        [0] * len(torso_verts) +
        [1] * len(r_arm_verts) +
        [2] * len(l_arm_verts) +
        [3] * len(r_leg_verts) +
        [4] * len(l_leg_verts)
    )

    all_verts, all_faces = _merge_meshes([
        (torso_verts, torso_faces),
        (r_arm_verts, r_arm_faces),
        (l_arm_verts, l_arm_faces),
        (r_leg_verts, r_leg_faces),
        (l_leg_verts, l_leg_faces),
    ])

    verts_np    = np.array(all_verts, dtype=np.float32)
    faces_np    = np.array(all_faces, dtype=np.uint32)
    part_ids_np = np.array(part_ids,  dtype=np.int32)

    # ── Volume estimate (torso only, simplified) ───────────────────────────────
    vol_mm3 = 0.0
    for i in range(len(torso_rings) - 1):
        _, _, z0, a0, b0 = torso_rings[i]
        _, _, z1, a1, b1 = torso_rings[i + 1]
        h = abs(z1 - z0)
        area_avg = math.pi * ((a0 + a1) / 2) * ((b0 + b1) / 2)
        vol_mm3 += area_avg * h
    vol_cm3 = round(vol_mm3 / 1000.0, 2)

    return {
        'vertices':      verts_np,
        'faces':         faces_np,
        'body_part_ids': part_ids_np,
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
