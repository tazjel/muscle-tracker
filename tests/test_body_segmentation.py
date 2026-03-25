import numpy as np
import pytest
from core.body_segmentation import segment_body, get_pose_landmarks, extract_muscle_roi, MEDIAPIPE_AVAILABLE


def make_test_image(h=480, w=320):
    """Create a synthetic BGR image."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[100:400, 100:220] = 200  # simulate a person silhouette
    return img


def test_segment_body_returns_correct_types():
    img = make_test_image()
    result = segment_body(img)
    if MEDIAPIPE_AVAILABLE and result is not None:
        assert result.shape == (480, 320)
        assert result.dtype == np.uint8
        assert set(np.unique(result)).issubset({0, 255})


def test_segment_body_black_image_returns_mask():
    """Black image should return a valid mask (all zeros) not crash."""
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = segment_body(img)
    # Either None (no mediapipe) or a valid uint8 array — must not raise
    if result is not None:
        assert result.shape == (480, 320)


def test_get_pose_landmarks_returns_none_on_blank():
    """Blank image has no person — should return None without crashing."""
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = get_pose_landmarks(img)
    assert result is None or isinstance(result, dict)


def test_extract_muscle_roi_no_landmarks():
    img = make_test_image()
    result = extract_muscle_roi(img, 'bicep', None)
    assert result is None


def test_extract_muscle_roi_unknown_group():
    img = make_test_image()
    fake_landmarks = {
        'LEFT_SHOULDER': (100, 100),
        'LEFT_ELBOW': (100, 200),
    }
    result = extract_muscle_roi(img, 'unknown_muscle', fake_landmarks)
    assert result is None


def test_extract_muscle_roi_valid():
    img = make_test_image()
    fake_landmarks = {
        'LEFT_SHOULDER': (110, 120),
        'LEFT_ELBOW': (110, 220),
    }
    result = extract_muscle_roi(img, 'bicep', fake_landmarks)
    assert result is not None
    assert result.ndim == 3
    assert result.shape[2] == 3
