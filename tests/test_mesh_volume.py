"""
Tests for core/mesh_volume.py — divergence-theorem volume computation.
"""
import numpy as np
import math
import pytest
from core.mesh_volume import compute_mesh_volume_cm3


def _unit_cube():
    """Simple 1mm-side cube (12 triangles)."""
    v = np.array([
        [0,0,0],[1,0,0],[1,1,0],[0,1,0],
        [0,0,1],[1,0,1],[1,1,1],[0,1,1],
    ], dtype=float)
    f = np.array([
        [0,1,2],[0,2,3],  # bottom
        [4,6,5],[4,7,6],  # top
        [0,4,5],[0,5,1],  # front
        [2,6,7],[2,7,3],  # back
        [0,3,7],[0,7,4],  # left
        [1,5,6],[1,6,2],  # right
    ])
    return v, f


class TestMeshVolume:
    def test_unit_cube_approx_1mm3(self):
        v, f = _unit_cube()
        vol = compute_mesh_volume_cm3(v, f)
        # 1mm³ = 0.001 cm³
        assert abs(vol - 0.001) < 0.0005

    def test_returns_float(self):
        v, f = _unit_cube()
        assert isinstance(compute_mesh_volume_cm3(v, f), float)

    def test_returns_zero_for_none(self):
        assert compute_mesh_volume_cm3(None, None) == 0.0

    def test_returns_zero_for_empty(self):
        assert compute_mesh_volume_cm3(np.array([]), np.array([])) == 0.0

    def test_larger_cube_scales_correctly(self):
        # 10mm cube → 1000 mm³ → 1.0 cm³
        v, f = _unit_cube()
        v = v * 10.0
        vol = compute_mesh_volume_cm3(v, f)
        assert abs(vol - 1.0) < 0.05

    def test_out_of_range_faces_returns_zero(self):
        v = np.array([[0,0,0],[1,0,0],[0,1,0]], dtype=float)
        f = np.array([[0, 1, 99]])  # index 99 out of range
        assert compute_mesh_volume_cm3(v, f) == 0.0
