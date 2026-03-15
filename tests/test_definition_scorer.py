import numpy as np
import pytest
import cv2
from core.definition_scorer import score_muscle_definition, generate_definition_heatmap


def _make_contour(x, y, w, h):
    """Helper: rectangular contour."""
    return np.array([[x,y],[x+w,y],[x+w,y+h],[x,y+h]], dtype=np.int32).reshape(-1,1,2)


class TestScoreMuscleDefinition:
    def test_textured_image_scores_higher(self):
        """A noisy/textured image should score higher than a blank one."""
        contour = _make_contour(50, 50, 200, 200)

        # Blank image
        blank = np.zeros((300, 300, 3), dtype=np.uint8)
        blank[50:250, 50:250] = 128  # uniform gray ROI
        r_blank = score_muscle_definition(blank, contour)

        # Noisy image (simulates texture)
        noisy = blank.copy()
        noise = np.random.RandomState(42).randint(0, 100, (200, 200, 3), dtype=np.uint8)
        noisy[50:250, 50:250] = np.clip(noisy[50:250, 50:250].astype(int) + noise, 0, 255).astype(np.uint8)
        r_noisy = score_muscle_definition(noisy, contour)

        assert r_noisy['overall_definition'] > r_blank['overall_definition']

    def test_returns_all_keys(self):
        img = np.random.RandomState(0).randint(0, 255, (300, 300, 3), dtype=np.uint8)
        contour = _make_contour(50, 50, 200, 200)
        result = score_muscle_definition(img, contour)
        for key in ['texture_score', 'edge_density', 'contrast_score', 'overall_definition', 'grade']:
            assert key in result, f"Missing key: {key}"

    def test_scores_in_range(self):
        img = np.random.RandomState(1).randint(0, 255, (300, 300, 3), dtype=np.uint8)
        contour = _make_contour(50, 50, 200, 200)
        result = score_muscle_definition(img, contour)
        for key in ['texture_score', 'edge_density', 'contrast_score', 'overall_definition']:
            assert 0 <= result[key] <= 100, f"{key}={result[key]} out of range"

    def test_grade_values(self):
        img = np.random.RandomState(2).randint(0, 255, (300, 300, 3), dtype=np.uint8)
        contour = _make_contour(50, 50, 200, 200)
        result = score_muscle_definition(img, contour)
        assert result['grade'] in ['Shredded', 'Defined', 'Lean', 'Smooth', 'Bulking']


class TestGenerateDefinitionHeatmap:
    def test_returns_valid_image(self):
        img = np.random.RandomState(3).randint(0, 255, (300, 300, 3), dtype=np.uint8)
        contour = _make_contour(50, 50, 200, 200)
        result = generate_definition_heatmap(img, contour)
        assert result is not None
        assert result.shape[:2] == (300, 300)
        assert result.dtype == np.uint8

    def test_none_inputs(self):
        result = generate_definition_heatmap(None, None)
        assert result is None
