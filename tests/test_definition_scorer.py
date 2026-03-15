import numpy as np
import pytest
import cv2
from core.definition_scorer import score_muscle_definition, generate_definition_heatmap

def test_score_muscle_definition():
    # Synthetic image with noise (texture)
    img = np.random.randint(0, 255, (500, 500, 3), dtype=np.uint8)
    contour = np.array([[100, 100], [400, 100], [400, 400], [100, 400]], dtype=np.int32).reshape(-1, 1, 2)
    result = score_muscle_definition(img, contour)
    assert 'overall_definition' in result
    assert result['overall_definition'] > 0
    assert 'grade' in result

def test_generate_definition_heatmap():
    img = np.random.randint(0, 255, (500, 500, 3), dtype=np.uint8)
    contour = np.array([[100, 100], [400, 100], [400, 400], [100, 400]], dtype=np.int32).reshape(-1, 1, 2)
    result = generate_definition_heatmap(img, contour)
    assert result is not None
    assert result.shape == (500, 500, 3)
    assert np.any(result > 0)
