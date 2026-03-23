"""
Runtime deformation of the MPFB2 template mesh to match user measurements.

Only vertex positions change — faces and UVs are preserved.
Template mesh is in meters, Z-up (Blender convention).
Profile measurements are in cm.
Output vertices are in mm (matching the rest of the pipeline).
"""
import os
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

_MESHES_DIR = os.path.join(os.path.dirname(__file__), '..', 'meshes')
_SEG_PATH = os.path.join(os.path.dirname(__file__), '..', 'web_app',
                         'static', 'viewer3d', 'template_vert_segmentation.json')

# Default male athletic body (same keys as smpl_fitting.DEFAULT_PROFILE)
_DEFAULT = {
    'height_cm': 168,
    'chest_circumference_cm': 97,
    'waist_circumference_cm': 90,
    'hip_circumference_cm': 92,
    'thigh_circumference_cm': 53,
    'calf_circumference_cm': 34,
    'bicep_circumference_cm': 32,
    'forearm_circumference_cm': 29,
    'neck_circumference_cm': 35,
    'shoulder_width_cm': 37,
    # Phenotype shape key factors (0.0–1.0)
    'muscle_factor': 0.5,
    'weight_factor': 0.5,
    'gender_factor': 1.0,   # 1.0 = male, 0.0 = female
}

# Template mesh reference measurements (computed once from the generated mesh).
# Will be populated lazily on first call.
_template_ref = None
_template_cache = None
_shape_delta_cache = None


def _load_template():
    """Load and cache template mesh data."""
    global _template_cache
    if _template_cache is not None:
        return _template_cache

    verts = np.load(os.path.join(_MESHES_DIR, 'template_verts.npy'))  # (N,3) float32, meters
    faces = np.load(os.path.join(_MESHES_DIR, 'template_faces.npy'))  # (M,3) int32
    uvs = np.load(os.path.join(_MESHES_DIR, 'template_uvs.npy'))     # (N,2) float32

    with open(_SEG_PATH) as f:
        seg = json.load(f)
    # Convert to numpy index arrays
    seg = {k: np.array(v, dtype=np.int32) for k, v in seg.items()}

    _template_cache = {
        'verts': verts.copy(),
        'faces': faces,
        'uvs': uvs,
        'seg': seg,
    }
    return _template_cache


def _load_shape_deltas():
    """Load and cache shape key delta arrays from meshes/shape_deltas/."""
    global _shape_delta_cache
    if _shape_delta_cache is not None:
        return _shape_delta_cache

    index_path = os.path.join(_MESHES_DIR, 'shape_deltas', 'index.json')
    if not os.path.exists(index_path):
        _shape_delta_cache = {}
        return _shape_delta_cache

    with open(index_path) as f:
        index = json.load(f)

    result = {}
    for key_name, info in index.items():
        npy_path = os.path.join(_MESHES_DIR, 'shape_deltas', info['file'])
        if not os.path.exists(npy_path):
            continue
        category = info.get('category', '')
        if category == 'gender_male':
            profile_key = 'gender_factor'
            invert = False   # target = gender_factor directly
        elif category == 'gender_female':
            profile_key = 'gender_factor'
            invert = True    # target = 1.0 - gender_factor (0=female applies these)
        elif category == 'muscle':
            profile_key = 'muscle_factor'
            invert = False
        elif category == 'weight':
            profile_key = 'weight_factor'
            invert = False
        else:
            continue
        result[key_name] = {
            'delta': np.load(npy_path),
            'baked_value': float(info['baked_value']),
            'profile_key': profile_key,
            'invert': invert,
        }

    _shape_delta_cache = result
    logger.info('Loaded %d shape key deltas', len(result))
    return result


def _cross_section_circumference(verts_2d):
    """Approximate circumference from 2D cross-section points (XY plane).

    Uses convex hull perimeter as a robust approximation.
    """
    if len(verts_2d) < 3:
        return 0.0
    from scipy.spatial import ConvexHull
    try:
        hull = ConvexHull(verts_2d)
        # Perimeter = sum of edge lengths around the hull
        pts = verts_2d[hull.vertices]
        pts_rolled = np.roll(pts, -1, axis=0)
        return float(np.sum(np.linalg.norm(pts_rolled - pts, axis=1)))
    except Exception:
        return 0.0


def _compute_template_measurements(verts, seg):
    """Compute the template mesh's reference circumferences (in meters)."""
    global _template_ref
    if _template_ref is not None:
        return _template_ref

    ref = {}

    # Height: Z range
    ref['height_m'] = float(verts[:, 2].max() - verts[:, 2].min())

    # For each circumference, gather the relevant muscle group vertices
    # and compute cross-section circumference in the XY plane at the group's
    # mean Z height.
    circ_groups = {
        'chest':   ['pectorals', 'traps'],
        'waist':   ['abs', 'obliques'],
        'hip':     ['glutes'],
        'thigh':   ['quads_l', 'quads_r'],
        'calf':    ['calves_l', 'calves_r'],
        'bicep':   ['biceps_l', 'biceps_r'],
        'forearm': ['forearms_l', 'forearms_r'],
        'neck':    ['traps'],  # upper traps region
    }

    for region, groups in circ_groups.items():
        # Collect all vertex indices for this region
        all_idx = np.concatenate([seg[g] for g in groups if g in seg])
        if len(all_idx) == 0:
            ref[f'{region}_circ_m'] = 0.1  # fallback
            continue

        region_verts = verts[all_idx]

        if region == 'neck':
            # Use top 30% of traps vertices (neck area)
            z_min, z_max = region_verts[:, 2].min(), region_verts[:, 2].max()
            z_thresh = z_min + 0.7 * (z_max - z_min)
            mask = region_verts[:, 2] > z_thresh
            if mask.sum() >= 3:
                region_verts = region_verts[mask]

        # For paired groups (thigh, calf, bicep, forearm), compute per-side
        # and average, since each side is half the body
        if region in ('thigh', 'calf', 'bicep', 'forearm'):
            left_g = [g for g in groups if g.endswith('_l')]
            right_g = [g for g in groups if g.endswith('_r')]
            circs = []
            for side_groups in (left_g, right_g):
                side_idx = np.concatenate([seg[g] for g in side_groups if g in seg])
                if len(side_idx) < 3:
                    continue
                sv = verts[side_idx]
                circ = _cross_section_circumference(sv[:, :2])
                circs.append(circ)
            ref[f'{region}_circ_m'] = float(np.mean(circs)) if circs else 0.1
        else:
            # Full cross-section at mean Z height — use all vertices in a Z band
            z_mean = region_verts[:, 2].mean()
            z_band = 0.02  # 2cm band
            all_in_band = verts[(verts[:, 2] > z_mean - z_band) &
                                (verts[:, 2] < z_mean + z_band)]
            if len(all_in_band) >= 3:
                circ = _cross_section_circumference(all_in_band[:, :2])
            else:
                circ = _cross_section_circumference(region_verts[:, :2])
            ref[f'{region}_circ_m'] = circ

    _template_ref = ref
    logger.info('Template ref measurements: %s',
                {k: f'{v:.3f}m' for k, v in ref.items()})
    return ref


# Mapping from profile keys to region names
_PROFILE_TO_REGION = {
    'chest_circumference_cm': 'chest',
    'waist_circumference_cm': 'waist',
    'hip_circumference_cm': 'hip',
    'thigh_circumference_cm': 'thigh',
    'calf_circumference_cm': 'calf',
    'bicep_circumference_cm': 'bicep',
    'forearm_circumference_cm': 'forearm',
    'neck_circumference_cm': 'neck',
}

# Which muscle groups each region affects
_REGION_GROUPS = {
    'chest':   ['pectorals', 'traps'],
    'waist':   ['abs', 'obliques'],
    'hip':     ['glutes'],
    'thigh':   ['quads_l', 'quads_r'],
    'calf':    ['calves_l', 'calves_r'],
    'bicep':   ['biceps_l', 'biceps_r'],
    'forearm': ['forearms_l', 'forearms_r'],
    'neck':    ['traps'],
}


def deform_template(profile: dict = None) -> dict:
    """Deform the MPFB2 template mesh to match user body measurements.

    Args:
        profile: dict with measurement keys (cm). Missing keys use defaults.

    Returns:
        dict with:
          'vertices'      - np.float32 (N, 3), units = mm
          'faces'         - np.uint32  (M, 3)
          'uvs'           - np.float32 (N, 2)
          'body_part_ids' - np.int32   (N,)  (all zeros)
          'volume_cm3'    - float
          'num_vertices'  - int
          'num_faces'     - int
    """
    p = {**_DEFAULT, **(profile or {})}
    tmpl = _load_template()
    verts = tmpl['verts'].copy()  # meters
    faces = tmpl['faces']
    uvs = tmpl['uvs']
    seg = tmpl['seg']

    ref = _compute_template_measurements(verts, seg)

    # ── Step 0: Apply shape key phenotype deltas ──────────────────────────
    # Apply BEFORE height/circumference scaling so deltas remain in template
    # coordinate space. Each delta is (N, 3) float32 in meters.
    # NOTE: Only apply muscle/weight deltas. Gender/ethnicity keys (gender_male,
    # gender_female) are mutually-exclusive ethnicity variants that compound
    # when applied together, producing malformed meshes.
    shape_deltas = _load_shape_deltas()
    _SAFE_CATEGORIES = ('muscle', 'weight')
    for key_name, info in shape_deltas.items():
        if info.get('category', '') not in _SAFE_CATEGORIES:
            continue
        factor = p.get(info['profile_key'])
        if factor is None:
            continue
        target = (1.0 - factor) if info['invert'] else factor
        diff = target - info['baked_value']
        if abs(diff) > 0.01:
            verts += info['delta'] * diff

    # ── Step 1: Scale height ──────────────────────────────────────────────
    target_h = p['height_cm'] / 100.0  # meters
    template_h = ref['height_m']
    if template_h > 0:
        h_scale = target_h / template_h
        verts[:, 2] *= h_scale
        # Also scale XY slightly to maintain proportions (cube-root scaling)
        xy_scale_from_height = h_scale ** 0.33
    else:
        h_scale = 1.0
        xy_scale_from_height = 1.0

    # ── Step 2: Proportional XY scaling ──────────────────────────────────
    # Apply height-proportional scaling to XY to maintain proportions.
    # NOTE: Per-region PCA bone-axis scaling is disabled because the vertex
    # segmentation (template_vert_segmentation.json) is for SMPL (6890 verts)
    # not the MPFB2 template (13380 verts). Using wrong indices creates spikes.
    # The muscle/weight shape deltas from Step 0 handle body composition.
    verts[:, 0] *= xy_scale_from_height
    verts[:, 1] *= xy_scale_from_height

    # ── Convert to mm (pipeline convention) ───────────────────────────────
    verts_mm = (verts * 1000.0).astype(np.float32)

    # Volume via divergence theorem
    volume_cm3 = _mesh_volume_cm3(verts_mm, faces)

    try:
        from core.texture_factory import get_part_ids
        _part_ids = get_part_ids(len(verts_mm))
    except Exception:
        _part_ids = None

    return {
        'vertices': verts_mm,
        'faces': faces.astype(np.uint32),
        'uvs': uvs,
        'body_part_ids': _part_ids if _part_ids is not None else np.zeros(len(verts_mm), dtype=np.int32),
        'volume_cm3': volume_cm3,
        'num_vertices': len(verts_mm),
        'num_faces': len(faces),
        'mesh_type': 'mpfb2',
    }


def _smooth_boundaries(verts, faces, scale_factors, iterations=5, strength=0.4):
    """Distance-weighted Laplacian smoothing on boundary vertices.

    Extends 2 rings out from scale-factor boundaries for gradual blending.
    """
    n = len(verts)
    adj = [[] for _ in range(n)]
    for f in faces:
        for i in range(3):
            a, b = int(f[i]), int(f[(i + 1) % 3])
            adj[a].append(b)
            adj[b].append(a)

    # Find direct boundary vertices (1-ring)
    boundary = set()
    for i in range(n):
        si = scale_factors[i]
        for j in adj[i]:
            if abs(scale_factors[j] - si) > 0.01:
                boundary.add(i)
                boundary.add(j)
                break

    if not boundary:
        return

    # Extend to 2-ring for smoother falloff
    extended = set(boundary)
    for v in list(boundary):
        for nb in adj[v]:
            extended.add(nb)

    boundary_list = list(extended)
    logger.debug('Smoothing %d boundary vertices (2-ring)', len(boundary_list))

    # Distance from boundary center → reduced strength for outer ring
    core = boundary
    for _ in range(iterations):
        new_pos = verts.copy()
        for i in boundary_list:
            neighbors = adj[i]
            if not neighbors:
                continue
            avg = verts[neighbors].mean(axis=0)
            s = strength if i in core else strength * 0.5
            new_pos[i] = verts[i] * (1 - s) + avg * s
        verts[boundary_list] = new_pos[boundary_list]


def _mesh_volume_cm3(verts_mm, faces):
    """Signed volume via divergence theorem. Input in mm, output in cm³."""
    v0 = verts_mm[faces[:, 0]]
    v1 = verts_mm[faces[:, 1]]
    v2 = verts_mm[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    vol_mm3 = abs(float(np.sum(v0 * cross) / 6.0))
    return vol_mm3 / 1000.0  # mm³ → cm³
