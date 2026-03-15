import numpy as np
import pytest
import os
from core.mesh_reconstruction import reconstruct_mesh_from_silhouettes, export_obj, export_stl

def test_reconstruct_mesh():
    cf = np.array([[100, 100], [200, 100], [200, 300], [100, 300]], dtype=np.int32).reshape(-1, 1, 2)
    cs = np.array([[100, 100], [180, 100], [180, 300], [100, 300]], dtype=np.int32).reshape(-1, 1, 2)
    result = reconstruct_mesh_from_silhouettes(cf, cs, 1.0, 1.0, num_slices=10)
    assert 'vertices' in result
    assert result['num_vertices'] > 0
    assert result['volume_cm3'] > 0

def test_export_obj():
    verts = np.array([[0,0,0], [1,0,0], [0,1,0]])
    faces = np.array([[0,1,2]])
    path = 'test.obj'
    export_obj(verts, faces, path)
    assert os.path.exists(path)
    with open(path, 'r') as f:
        lines = f.readlines()
        assert lines[0].startswith('v')
        assert lines[-1].startswith('f')
    os.remove(path)

def test_export_stl():
    verts = np.array([[0,0,0], [1,0,0], [0,1,0]])
    faces = np.array([[0,1,2]])
    path = 'test.stl'
    export_stl(verts, faces, path)
    assert os.path.exists(path)
    assert os.path.getsize(path) == 80 + 4 + 50 # header + count + 1 face (50 bytes)
    os.remove(path)
