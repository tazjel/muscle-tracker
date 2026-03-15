"""
Precise 3D mesh volume via the divergence theorem.
More accurate than the 2D slice estimate when a real mesh is available.
"""
import numpy as np


def compute_mesh_volume_cm3(vertices, faces):
    """
    Signed volume of a closed triangular mesh using the divergence theorem.

    Parameters
    ----------
    vertices : array-like, shape (N, 3)  — vertex positions in mm
    faces    : array-like, shape (M, 3)  — triangle vertex indices

    Returns
    -------
    float — volume in cm³ (always positive, 0.0 on bad input)
    """
    if vertices is None or faces is None:
        return 0.0

    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces,    dtype=np.int64)

    if v.ndim != 2 or v.shape[1] != 3 or len(v) == 0:
        return 0.0
    if f.ndim != 2 or f.shape[1] != 3 or len(f) == 0:
        return 0.0
    if f.max() >= len(v):
        return 0.0

    v0 = v[f[:, 0]]
    v1 = v[f[:, 1]]
    v2 = v[f[:, 2]]

    # Divergence theorem: V = (1/6) * |Σ v0 · (v1 × v2)|
    cross    = np.cross(v1, v2)
    vol_mm3  = abs(np.sum(v0 * cross)) / 6.0

    return round(vol_mm3 / 1000.0, 3)
