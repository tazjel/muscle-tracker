"""
uv_canonical.py — Extract or compute canonical SMPL UV coordinates.

Loads UVs from the SMPL model file (SMPL_NEUTRAL.pkl) or computes
optimal conformal mapping. Saves to meshes/smpl_canonical_vert_uvs.npy.
"""
import numpy as np
import pickle
import os
import logging

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_CANONICAL_PATH = os.path.join(_PROJECT_ROOT, 'meshes', 'smpl_canonical_vert_uvs.npy')
_SMPL_PKL_PATHS = [
    os.path.join(_PROJECT_ROOT, 'runpod', 'SMPL_NEUTRAL.pkl'),
    os.path.expanduser('~/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl'),
]


def _find_smpl_pkl():
    """Find SMPL_NEUTRAL.pkl from known paths."""
    for p in _SMPL_PKL_PATHS:
        if os.path.exists(p):
            return p
    return None


def extract_uvs_from_pkl(pkl_path=None):
    """
    Extract UV coordinates from SMPL_NEUTRAL.pkl.

    The SMPL pickle may contain 'vt' (per-face-vertex UVs) and 'ft' (UV face indices).
    We convert these to per-vertex UVs (6890, 2) by averaging UV coords for shared vertices.

    Returns:
        (6890, 2) float32 UV array, or None if pkl has no UV data.
    """
    if pkl_path is None:
        pkl_path = _find_smpl_pkl()
    if pkl_path is None:
        logger.warning("SMPL_NEUTRAL.pkl not found")
        return None

    with open(pkl_path, 'rb') as f:
        data = pickle.load(f, encoding='latin1')

    # Check for UV data in the pickle
    vt = data.get('vt')  # (V_uv, 2) UV vertex positions
    ft = data.get('ft')  # (F, 3) UV face indices

    if vt is not None and ft is not None:
        vt = np.array(vt, dtype=np.float32)
        ft = np.array(ft, dtype=np.int32)
        faces = np.array(data['f'], dtype=np.int32)

        logger.info("SMPL pkl has UV data: vt=%s, ft=%s", vt.shape, ft.shape)

        # Map per-face UVs to per-vertex UVs by averaging
        n_verts = int(data.get('v_template', data.get('v_posed', np.zeros((6890, 3)))).shape[0])
        uv_sum = np.zeros((n_verts, 2), dtype=np.float64)
        uv_count = np.zeros(n_verts, dtype=np.float64)

        for fi in range(len(faces)):
            for ci in range(3):
                vi = faces[fi, ci]       # mesh vertex index
                ui = ft[fi, ci]          # UV vertex index
                uv_sum[vi] += vt[ui]
                uv_count[vi] += 1.0

        mask = uv_count > 0
        uv_sum[mask] /= uv_count[mask, np.newaxis]

        # Fill any vertices with no UV assignment using cylindrical fallback
        if not mask.all():
            v_template = np.array(data.get('v_template', np.zeros((n_verts, 3))), dtype=np.float32)
            missing = ~mask
            cx = v_template[missing, 0].mean()
            cy = v_template[missing, 1].mean()
            angles = np.arctan2(v_template[missing, 1] - cy, v_template[missing, 0] - cx)
            uv_sum[missing, 0] = (angles + np.pi) / (2 * np.pi)
            z = v_template[missing, 2]
            z_min, z_max = z.min(), z.max()
            uv_sum[missing, 1] = (z - z_min) / (z_max - z_min + 1e-6)
            logger.info("Filled %d missing UV vertices with cylindrical fallback", missing.sum())

        return uv_sum.astype(np.float32)

    logger.info("SMPL pkl has no UV data (vt/ft keys missing)")
    return None


def compute_conformal_uvs(vertices, faces):
    """
    Compute conformal UV mapping for arbitrary mesh via Tutte embedding.

    Uses boundary detection + harmonic mapping for a clean UV layout.

    Args:
        vertices: (N, 3) float32
        faces: (F, 3) int

    Returns:
        (N, 2) float32 UV coordinates in [0, 1]
    """
    from scipy import sparse
    from scipy.sparse.linalg import spsolve

    n_verts = len(vertices)
    faces = np.array(faces, dtype=np.int32)

    # Build adjacency and find boundary
    edges = set()
    edge_faces = {}
    for fi, f in enumerate(faces):
        for i in range(3):
            e = tuple(sorted([f[i], f[(i + 1) % 3]]))
            edges.add(e)
            edge_faces.setdefault(e, []).append(fi)

    boundary_edges = [e for e, fs in edge_faces.items() if len(fs) == 1]

    if not boundary_edges:
        # Closed mesh — use cylindrical projection as fallback
        logger.info("Closed mesh detected, using cylindrical UV projection")
        cx = vertices[:, 0].mean()
        cy = vertices[:, 1].mean()
        angles = np.arctan2(vertices[:, 1] - cy, vertices[:, 0] - cx)
        u = (angles + np.pi) / (2 * np.pi)
        z_min, z_max = vertices[:, 2].min(), vertices[:, 2].max()
        v = (vertices[:, 2] - z_min) / (z_max - z_min + 1e-6)
        return np.stack([u, v], axis=1).astype(np.float32)

    # Order boundary vertices into a loop
    adj = {}
    for e in boundary_edges:
        adj.setdefault(e[0], []).append(e[1])
        adj.setdefault(e[1], []).append(e[0])

    boundary = [boundary_edges[0][0]]
    visited = {boundary[0]}
    while True:
        curr = boundary[-1]
        found = False
        for nb in adj.get(curr, []):
            if nb not in visited:
                boundary.append(nb)
                visited.add(nb)
                found = True
                break
        if not found:
            break

    boundary_set = set(boundary)
    interior = [i for i in range(n_verts) if i not in boundary_set]

    # Map boundary to unit circle
    n_bd = len(boundary)
    uv = np.zeros((n_verts, 2), dtype=np.float64)
    for i, vi in enumerate(boundary):
        angle = 2 * np.pi * i / n_bd
        uv[vi, 0] = 0.5 + 0.5 * np.cos(angle)
        uv[vi, 1] = 0.5 + 0.5 * np.sin(angle)

    # Solve Laplacian for interior vertices (harmonic mapping)
    if interior:
        int_map = {v: i for i, v in enumerate(interior)}
        n_int = len(interior)

        rows, cols, vals = [], [], []
        rhs_u = np.zeros(n_int)
        rhs_v = np.zeros(n_int)

        # Cotangent weights
        for f in faces:
            for i in range(3):
                vi, vj, vk = f[i], f[(i + 1) % 3], f[(i + 2) % 3]
                edge1 = vertices[vi] - vertices[vk]
                edge2 = vertices[vj] - vertices[vk]
                cos_angle = np.dot(edge1, edge2) / (np.linalg.norm(edge1) * np.linalg.norm(edge2) + 1e-10)
                cos_angle = np.clip(cos_angle, -0.999, 0.999)
                w = cos_angle / np.sqrt(1 - cos_angle ** 2 + 1e-10) * 0.5

                for a, b in [(vi, vj), (vj, vi)]:
                    if a in int_map:
                        ai = int_map[a]
                        rows.append(ai)
                        cols.append(ai)
                        vals.append(w)
                        if b in int_map:
                            bi = int_map[b]
                            rows.append(ai)
                            cols.append(bi)
                            vals.append(-w)
                        else:
                            rhs_u[ai] += w * uv[b, 0]
                            rhs_v[ai] += w * uv[b, 1]

        L = sparse.csr_matrix((vals, (rows, cols)), shape=(n_int, n_int))
        uv_int_u = spsolve(L, rhs_u)
        uv_int_v = spsolve(L, rhs_v)

        for i, vi in enumerate(interior):
            uv[vi, 0] = uv_int_u[i]
            uv[vi, 1] = uv_int_v[i]

    # Normalize to [0, 1]
    for ch in range(2):
        mn, mx = uv[:, ch].min(), uv[:, ch].max()
        if mx > mn:
            uv[:, ch] = (uv[:, ch] - mn) / (mx - mn)

    return uv.astype(np.float32)


def get_canonical_uvs(force_recompute=False):
    """
    Get canonical SMPL UV coordinates. Loads from cache, extracts from pkl,
    or computes conformal mapping.

    Args:
        force_recompute: if True, ignore cached file and recompute

    Returns:
        (6890, 2) float32 UV array
    """
    # Try cached file first
    if not force_recompute and os.path.exists(_CANONICAL_PATH):
        uvs = np.load(_CANONICAL_PATH)
        if uvs.shape == (6890, 2):
            logger.info("Loaded cached canonical UVs from %s", _CANONICAL_PATH)
            return uvs
        logger.warning("Cached UVs have unexpected shape %s, recomputing", uvs.shape)

    # Try extracting from SMPL pkl
    uvs = extract_uvs_from_pkl()
    if uvs is not None and uvs.shape == (6890, 2):
        os.makedirs(os.path.dirname(_CANONICAL_PATH), exist_ok=True)
        np.save(_CANONICAL_PATH, uvs)
        logger.info("Extracted and saved canonical UVs to %s", _CANONICAL_PATH)
        return uvs

    # Fallback: compute from mesh geometry
    pkl_path = _find_smpl_pkl()
    if pkl_path:
        with open(pkl_path, 'rb') as f:
            data = pickle.load(f, encoding='latin1')
        v_template = np.array(data['v_template'], dtype=np.float32)
        faces = np.array(data['f'], dtype=np.int32)
        uvs = compute_conformal_uvs(v_template, faces)
        if uvs is not None:
            os.makedirs(os.path.dirname(_CANONICAL_PATH), exist_ok=True)
            np.save(_CANONICAL_PATH, uvs)
            logger.info("Computed conformal UVs and saved to %s", _CANONICAL_PATH)
            return uvs

    logger.error("Could not obtain canonical UVs from any source")
    return None


def validate_uvs(uvs, faces=None):
    """
    Validate UV coordinates for quality issues.

    Returns dict with diagnostics:
        valid: bool
        range_ok: bool (all values in [0,1])
        coverage: float (fraction of UV space used)
        overlap_ratio: float (estimated overlap)
    """
    result = {
        'valid': True,
        'range_ok': True,
        'coverage': 0.0,
        'overlap_ratio': 0.0,
        'n_vertices': len(uvs),
    }

    # Range check
    if uvs.min() < -0.01 or uvs.max() > 1.01:
        result['range_ok'] = False
        result['valid'] = False

    # Coverage estimate (rasterize to small grid)
    grid_size = 256
    grid = np.zeros((grid_size, grid_size), dtype=np.uint8)
    u_px = np.clip((uvs[:, 0] * (grid_size - 1)).astype(int), 0, grid_size - 1)
    v_px = np.clip((uvs[:, 1] * (grid_size - 1)).astype(int), 0, grid_size - 1)
    grid[v_px, u_px] = 1
    result['coverage'] = float(grid.sum()) / (grid_size * grid_size)

    # Overlap estimate (check if multiple vertices map to same UV texel)
    if faces is not None:
        coords = set()
        overlaps = 0
        for vi in range(len(uvs)):
            key = (int(uvs[vi, 0] * 1000), int(uvs[vi, 1] * 1000))
            if key in coords:
                overlaps += 1
            coords.add(key)
        result['overlap_ratio'] = overlaps / max(len(uvs), 1)

    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    uvs = get_canonical_uvs(force_recompute=True)
    if uvs is not None:
        print(f"UV shape: {uvs.shape}")
        print(f"UV range: [{uvs.min():.4f}, {uvs.max():.4f}]")
        diag = validate_uvs(uvs)
        print(f"Diagnostics: {diag}")
    else:
        print("FAILED to generate UVs")
