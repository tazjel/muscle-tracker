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
    
    # Load part mapping generated via KDTree
    map_path = os.path.join(_MESHES_DIR, 'mpfb2_to_smpl_regions.npy')
    if os.path.exists(map_path):
        part_ids = np.load(map_path)
    else:
        logger.warning("MPFB2-to-SMPL mapping missing, using zeros")
        part_ids = np.zeros(len(verts), dtype=np.int32)

    with open(_SEG_PATH) as f:
        seg = json.load(f)
    # Convert to numpy index arrays
    seg = {k: np.array(v, dtype=np.int32) for k, v in seg.items()}

    _template_cache = {
        'verts': verts.copy(),
        'faces': faces,
        'uvs': uvs,
        'seg': seg,
        'part_ids': part_ids,
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


def _compute_template_measurements(verts, part_ids):
    """Compute the template mesh's reference circumferences (in meters)."""
    global _template_ref
    if _template_ref is not None:
        return _template_ref

    ref = {}

    # Height: Z range
    ref['height_m'] = float(verts[:, 2].max() - verts[:, 2].min())

    # Map part IDs to regions (SMPL standard)
    region_to_parts = {
        'waist':   [0, 3],
        'hip':     [0, 1, 2],
        'chest':   [6, 9],
        'neck':    [12],
        'thigh_l': [1],
        'thigh_r': [2],
        'calf_l':  [4],
        'calf_r':  [5],
        'bicep_l': [16],
        'bicep_r': [17],
        'forearm_l': [18],
        'forearm_r': [19],
    }

    for region, pids in region_to_parts.items():
        # Mask vertices in these parts
        mask = np.isin(part_ids, pids)
        if not mask.any():
            ref[f'{region}_circ_m'] = 0.1
            continue
            
        region_verts = verts[mask]
        
        # Compute cross-section at the centroid Z of the region
        z_mean = region_verts[:, 2].mean()
        z_band = 0.02 # 2cm
        all_in_band = verts[(verts[:, 2] > z_mean - z_band) & 
                            (verts[:, 2] < z_mean + z_band)]
        
        if len(all_in_band) >= 3:
            ref[f'{region}_circ_m'] = _cross_section_circumference(all_in_band[:, :2])
        else:
            ref[f'{region}_circ_m'] = _cross_section_circumference(region_verts[:, :2])

    _template_ref = ref
    logger.info('Template ref measurements: %s',
                {k: f'{v:.3f}m' for k, v in ref.items()})
    return ref


def deform_template(profile: dict = None) -> dict:
    """Deform the MPFB2 template mesh to match user body measurements.

    Args:
        profile: dict with measurement keys (cm). Missing keys use defaults.

    Returns:
        dict with:
          'vertices'      - np.float32 (N, 3), units = mm
          'faces'         - np.uint32  (M, 3)
          'uvs'           - np.float32 (N, 2)
          'body_part_ids' - np.int32   (N,)
          'volume_cm3'    - float
          'num_vertices'  - int
          'num_faces'     - int
    """
    p = {**_DEFAULT, **(profile or {})}
    tmpl = _load_template()
    verts = tmpl['verts'].copy()  # meters
    faces = tmpl['faces']
    uvs = tmpl['uvs']
    part_ids = tmpl['part_ids']

    ref = _compute_template_measurements(verts, part_ids)

    # ── Step 0: Apply shape key phenotype deltas ──────────────────────────
    # Apply BEFORE height/circumference scaling so deltas remain in template
    # coordinate space. Each delta is (N, 3) float32 in meters.
    shape_deltas = _load_shape_deltas()
    _SAFE_CATEGORIES = ('muscle', 'weight', 'gender_male', 'gender_female')
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
    target_h = p['height_cm'] / 100.0
    template_h = ref['height_m']
    h_scale = target_h / template_h if template_h > 0 else 1.0
    verts[:, 2] *= h_scale

    # ── Step 2: Per-region PCA scaling ──────────────────────────────────
    # Apply individual scaling to regions based on circumferences
    scale_factors = np.ones(len(verts), dtype=np.float32)
    
    region_mapping = {
        'chest_circumference_cm': 'chest',
        'waist_circumference_cm': 'waist',
        'hip_circumference_cm': 'hip',
        'thigh_circumference_cm': ['thigh_l', 'thigh_r'],
        'calf_circumference_cm':  ['calf_l', 'calf_r'],
        'bicep_circumference_cm': ['bicep_l', 'bicep_r'],
        'forearm_circumference_cm': ['forearm_l', 'forearm_r'],
        'neck_circumference_cm': 'neck',
    }
    
    part_to_region = {
        0: 'waist', 3: 'waist',
        1: 'thigh_l', 2: 'thigh_r',
        4: 'calf_l', 5: 'calf_r',
        6: 'chest', 9: 'chest',
        12: 'neck',
        16: 'bicep_l', 17: 'bicep_r',
        18: 'forearm_l', 19: 'forearm_r'
    }

    for prof_key, region_names in region_mapping.items():
        if prof_key not in p: continue
        target_circ = p[prof_key] / 100.0
        
        if isinstance(region_names, str):
            region_names = [region_names]
            
        for reg in region_names:
            ref_circ = ref.get(f'{reg}_circ_m', 0.5)
            s = target_circ / ref_circ if ref_circ > 0 else 1.0
            
            # Apply scale factor to vertices in this region's parts
            for pid, rname in part_to_region.items():
                if rname == reg:
                    scale_factors[part_ids == pid] = s

    # Smooth the scale factor transitions to avoid spikes
    _smooth_scale_factors(scale_factors, faces, iterations=10)
    
    # Apply scaling (XY only)
    verts[:, 0] *= scale_factors
    verts[:, 1] *= scale_factors

    # ── Convert to mm (pipeline convention) ───────────────────────────────
    verts_mm = (verts * 1000.0).astype(np.float32)

    # Volume via divergence theorem
    volume_cm3 = _mesh_volume_cm3(verts_mm, faces)

    try:
        from core.texture_factory import get_part_ids
        _part_ids = get_part_ids(len(verts_mm))
    except Exception:
        _part_ids = part_ids

    return {
        'vertices': verts_mm,
        'faces': faces.astype(np.uint32),
        'uvs': uvs,
        'body_part_ids': _part_ids,
        'volume_cm3': volume_cm3,
        'num_vertices': len(verts_mm),
        'num_faces': len(faces),
        'mesh_type': 'mpfb2',
    }


def _smooth_scale_factors(factors, faces, iterations=5):
    """Laplacian smoothing of scalar factors over the mesh."""
    n = len(factors)
    adj = [[] for _ in range(n)]
    for f in faces:
        for i in range(3):
            a, b = int(f[i]), int(f[(i+1)%3])
            adj[a].append(b); adj[b].append(a)
            
    for _ in range(iterations):
        new_factors = factors.copy()
        for i in range(n):
            if adj[i]:
                # Use mean of neighbors
                neighbors = list(set(adj[i]))
                new_factors[i] = factors[neighbors].mean()
        factors[:] = new_factors


def _mesh_volume_cm3(verts_mm, faces):
    """Signed volume via divergence theorem. Input in mm, output in cm³."""
    v0 = verts_mm[faces[:, 0]]
    v1 = verts_mm[faces[:, 1]]
    v2 = verts_mm[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    vol_mm3 = abs(float(np.sum(v0 * cross) / 6.0))
    return vol_mm3 / 1000.0  # mm³ → cm³
