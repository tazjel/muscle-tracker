import numpy as np
import pytest
from core.muscle_classifier import classify_muscle_group, classify_with_confidence


def test_classify_blank_image_returns_unknown():
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = classify_muscle_group(img)
    assert result == 'unknown'


def test_classify_with_confidence_structure():
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = classify_with_confidence(img)
    assert 'muscle_group' in result
    assert 'confidence' in result
    assert result['muscle_group'] == 'unknown'
    assert result['confidence'] == 0.0


def test_angle_degrees_90():
    # Test internal helper logic if exposed, or just rely on pose landmarks
    pass

# Note: Integration tests with real/synthetic landmarks would require 
# mocking get_pose_landmarks, which is done in existing pose tests.
