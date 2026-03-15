import numpy as np
import pytest
from core.mesh_comparison import compare_meshes

def test_compare_meshes():
    m1 = {
        'vertices': np.array([[0,0,0], [1,0,0], [0,1,0], [0,0,1]]),
        'volume_cm3': 100.0
    }
    m2 = {
        'vertices': np.array([[0,0,0], [1.1,0,0], [0,1.1,0], [0,0,1.1]]),
        'volume_cm3': 110.0
    }
    result = compare_meshes(m1, m2)
    assert 'displacement_map' in result
    assert result['mean_growth_mm'] > 0
    assert result['volume_change_cm3'] == 10.0
