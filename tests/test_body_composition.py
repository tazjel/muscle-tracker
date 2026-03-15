import numpy as np
import pytest
import math
from core.body_composition import estimate_body_composition, estimate_lean_mass, generate_composition_visual


class TestEstimateBodyComposition:
    def test_bmi_calculation(self):
        result = estimate_body_composition(
            landmarks={}, user_weight_kg=80.0, user_height_cm=180.0
        )
        assert result['bmi'] == pytest.approx(24.7, abs=0.1)

    def test_whr_from_direct_measurements(self):
        result = estimate_body_composition(
            landmarks={},
            waist_width_mm=400.0,
            hip_width_mm=500.0
        )
        assert result['waist_to_hip_ratio'] == pytest.approx(0.8, abs=0.01)
        assert result['confidence'] == 'high'

    def test_whr_from_landmarks(self):
        landmarks = {
            'LEFT_HIP': (100, 400),
            'RIGHT_HIP': (300, 400),
            'LEFT_SHOULDER': (120, 100),
            'RIGHT_SHOULDER': (280, 100),
        }
        result = estimate_body_composition(landmarks=landmarks)
        assert 'waist_to_hip_ratio' in result
        assert 0.5 < result['waist_to_hip_ratio'] < 1.2
        assert result['confidence'] == 'estimated'

    def test_navy_body_fat_male(self):
        """Navy method should NOT use age. Only waist, neck, height."""
        result = estimate_body_composition(
            landmarks={},
            waist_width_mm=420.0,
            hip_width_mm=500.0,
            neck_circumference_mm=380.0,
            user_weight_kg=80.0,
            user_height_cm=180.0,
            gender='male'
        )
        assert 'estimated_body_fat_pct' in result
        bf = result['estimated_body_fat_pct']
        assert 5 <= bf <= 45  # reasonable range
        assert 'classification' in result
        assert result['classification'] in ['Athletic', 'Fit', 'Average', 'Above Average']

    def test_navy_body_fat_female(self):
        result = estimate_body_composition(
            landmarks={},
            waist_width_mm=380.0,
            hip_width_mm=520.0,
            neck_circumference_mm=340.0,
            user_weight_kg=65.0,
            user_height_cm=165.0,
            gender='female'
        )
        assert 'estimated_body_fat_pct' in result
        bf = result['estimated_body_fat_pct']
        assert 10 <= bf <= 50

    def test_empty_input_returns_minimal(self):
        result = estimate_body_composition(landmarks={})
        assert isinstance(result, dict)
        assert 'confidence' in result

    def test_classification_athletic_male(self):
        """Low body fat should classify as Athletic."""
        result = estimate_body_composition(
            landmarks={},
            waist_width_mm=340.0,
            hip_width_mm=480.0,
            neck_circumference_mm=400.0,
            user_weight_kg=75.0,
            user_height_cm=180.0,
            gender='male'
        )
        if 'classification' in result:
            # With small waist and large neck, body fat should be low
            assert result['estimated_body_fat_pct'] < 25


class TestEstimateLeanMass:
    def test_basic(self):
        result = estimate_lean_mass(80.0, 15.0)
        assert result['fat_mass_kg'] == pytest.approx(12.0, abs=0.01)
        assert result['lean_mass_kg'] == pytest.approx(68.0, abs=0.01)

    def test_zero_body_fat(self):
        result = estimate_lean_mass(80.0, 0.0)
        assert result['lean_mass_kg'] == pytest.approx(80.0, abs=0.01)
        assert result['fat_mass_kg'] == pytest.approx(0.0, abs=0.01)

    def test_missing_inputs(self):
        result = estimate_lean_mass(None, 15.0)
        assert result == {} or result is None or 'lean_mass_kg' not in result


class TestGenerateCompositionVisual:
    def test_returns_valid_image(self):
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        landmarks = {'LEFT_HIP': (100, 400), 'RIGHT_HIP': (300, 400)}
        comp = {'bmi': 24.7, 'classification': 'Fit', 'waist_to_hip_ratio': 0.85}
        result = generate_composition_visual(img, landmarks, comp)
        assert result is not None
        assert result.shape == (500, 500, 3)
        assert result.dtype == np.uint8
        assert np.any(result > 0)

    def test_none_image_returns_none(self):
        result = generate_composition_visual(None, {}, {})
        assert result is None
