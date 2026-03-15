import numpy as np
import pytest
import os
import tempfile
from core.mesh_comparison import compare_meshes, export_colored_obj


class TestCompareMeshes:
    def test_identical_meshes_zero_displacement(self):
        mesh = {
            'vertices': np.array([[0,0,0],[1,0,0],[0,1,0],[1,1,0]], dtype=np.float64),
            'faces': np.array([[0,1,2],[1,2,3]], dtype=np.int32),
            'volume_cm3': 10.0,
        }
        result = compare_meshes(mesh, mesh)
        assert result['mean_growth_mm'] == pytest.approx(0.0, abs=0.01)
        assert result['volume_change_cm3'] == pytest.approx(0.0, abs=0.1)

    def test_grown_mesh_positive_displacement(self):
        before = {
            'vertices': np.array([[0,0,0],[1,0,0],[0,1,0],[1,1,0]], dtype=np.float64),
            'faces': np.array([[0,1,2],[1,2,3]], dtype=np.int32),
            'volume_cm3': 10.0,
        }
        # Scale up by 1.5x
        after = {
            'vertices': before['vertices'] * 1.5,
            'faces': before['faces'].copy(),
            'volume_cm3': 15.0,
        }
        result = compare_meshes(before, after)
        assert result['mean_growth_mm'] > 0
        assert result['max_growth_mm'] > 0
        assert 'displacement_map' in result
        assert len(result['displacement_map']) == len(after['vertices'])

    def test_displacement_map_shape(self):
        mesh_a = {
            'vertices': np.random.RandomState(0).randn(100, 3).astype(np.float64),
            'faces': np.array([[0,1,2]], dtype=np.int32),
            'volume_cm3': 5.0,
        }
        mesh_b = {
            'vertices': mesh_a['vertices'] + 0.1,
            'faces': mesh_a['faces'].copy(),
            'volume_cm3': 5.5,
        }
        result = compare_meshes(mesh_a, mesh_b)
        assert result['displacement_map'].shape == (100,)


class TestExportColoredObj:
    def test_writes_colored_obj(self):
        verts = np.array([[0,0,0],[1,0,0],[0,1,0]], dtype=np.float64)
        faces = np.array([[0,1,2]], dtype=np.int32)
        disp = np.array([0.0, 5.0, -3.0], dtype=np.float64)
        with tempfile.NamedTemporaryFile(suffix='.obj', delete=False) as f:
            path = f.name
        try:
            export_colored_obj(verts, faces, disp, path)
            content = open(path).read()
            assert 'v ' in content
            assert 'f ' in content
        finally:
            os.unlink(path)
