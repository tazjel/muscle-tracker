import os
import pytest
from core.body_map import generate_body_map, generate_body_map_data

def test_generate_body_map():
    records = [
        {'muscle_group': 'bicep', 'side': 'left', 'volume_cm3': 450.0, 'shape_score': 85},
        {'muscle_group': 'quad', 'side': 'right', 'volume_cm3': 1200.0, 'shape_score': 70}
    ]
    path = 'test_body_map.png'
    res_path = generate_body_map(records, path)
    assert os.path.exists(res_path)
    os.remove(res_path)

def test_generate_body_map_data():
    records = [
        {'muscle_group': 'bicep', 'scan_date': '2026-01-01', 'val': 1},
        {'muscle_group': 'bicep', 'scan_date': '2026-02-01', 'val': 2}
    ]
    res = generate_body_map_data(records)
    assert res['bicep']['val'] == 2
