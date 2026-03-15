import numpy as np
import pytest
from core.muscle_classifier import classify_muscle_group, classify_with_confidence, _angle_degrees


def test_angle_degrees_90():
    p1 = (0, 1)
    vertex = (0, 0)
    p2 = (1, 0)
    assert abs(_angle_degrees(p1, vertex, p2) - 90.0) < 1.0


def test_angle_degrees_180():
    p1 = (-1, 0)
    vertex = (0, 0)
    p2 = (1, 0)
    assert abs(_angle_degrees(p1, vertex, p2) - 180.0) < 1.0


def test_angle_degrees_0():
    p1 = (1, 0)
    vertex = (0, 0)
    p2 = (1, 0)
    assert _angle_degrees(p1, vertex, p2) < 1.0


def test_classify_blank_image_returns_unknown():
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = classify_muscle_group(img)
    # With no landmarks, it should return 'unknown'
    assert result == 'unknown'


def test_classify_with_confidence_structure():
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = classify_with_confidence(img)
    assert 'muscle_group' in result
    assert 'confidence' in result
    assert 'method' in result
    assert 0.0 <= result['confidence'] <= 1.0
    assert result['muscle_group'] in ['bicep', 'tricep', 'quad', 'hamstring', 'calf', 'shoulder', 'unknown']
