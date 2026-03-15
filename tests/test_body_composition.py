import numpy as np
import pytest
from core.body_composition import estimate_body_composition, estimate_lean_mass, generate_composition_visual

def test_estimate_body_composition_basic():
    landmarks = {
        'LEFT_HIP': (100, 400),
        'RIGHT_HIP': (200, 400),
        'LEFT_SHOULDER': (100, 100),
        'RIGHT_SHOULDER': (200, 100)
    }
    result = estimate_body_composition(landmarks, user_weight_kg=80.0, user_height_cm=180.0, gender='male')
    assert 'bmi' in result
    assert result['bmi'] == 24.7
    assert 'waist_to_hip_ratio' in result
    assert result['estimated_body_fat_pct'] > 0

def test_estimate_lean_mass():
    result = estimate_lean_mass(80.0, 15.0)
    assert result['fat_mass_kg'] == 12.0
    assert result['lean_mass_kg'] == 68.0

def test_generate_composition_visual():
    img = np.zeros((500, 500, 3), dtype=np.uint8)
    landmarks = {'LEFT_HIP': (100, 400), 'RIGHT_HIP': (200, 400)}
    comp_res = {'bmi': 24.7, 'classification': 'Fit'}
    result = generate_composition_visual(img, landmarks, comp_res)
    assert result is not None
    assert np.any(result > 0)
