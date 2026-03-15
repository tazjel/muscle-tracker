import numpy as np
import pytest
from core.volumetrics_advanced import slice_volume_estimate, compare_volume_models


def make_ellipse_contour(cx=100, cy=150, rx=30, ry=50, n_points=100):
    """Create an elliptical contour as OpenCV-style array."""
    angles = np.linspace(0, 2 * np.pi, n_points)
    x = (cx + rx * np.cos(angles)).astype(np.int32)
    y = (cy + ry * np.sin(angles)).astype(np.int32)
    return np.stack([x, y], axis=1).reshape(-1, 1, 2)


def test_slice_volume_positive():
    contour = make_ellipse_contour()
    result = slice_volume_estimate(contour, pixels_per_cm=10.0)
    assert result['volume_cm3'] > 0
    assert result['model'] == 'slice_elliptical'


def test_slice_volume_scales_with_calibration():
    contour = make_ellipse_contour()
    result_10 = slice_volume_estimate(contour, pixels_per_cm=10.0)
    result_20 = slice_volume_estimate(contour, pixels_per_cm=20.0)
    # More pixels per cm = smaller physical size = smaller volume
    assert result_20['volume_cm3'] < result_10['volume_cm3']


def test_slice_volume_invalid_contour():
    result = slice_volume_estimate(None, pixels_per_cm=10.0)
    assert 'error' in result
    assert result['volume_cm3'] == 0.0


def test_slice_volume_zero_calibration():
    contour = make_ellipse_contour()
    result = slice_volume_estimate(contour, pixels_per_cm=0.0)
    assert 'error' in result


def test_slice_volume_more_slices_more_detail():
    contour = make_ellipse_contour()
    result_5 = slice_volume_estimate(contour, pixels_per_cm=10.0, num_slices=5)
    result_50 = slice_volume_estimate(contour, pixels_per_cm=10.0, num_slices=50)
    # Both should give positive volumes, more slices give more detail
    assert result_5['volume_cm3'] > 0
    assert result_50['volume_cm3'] > 0
    assert len(result_50['slice_widths_cm']) > len(result_5['slice_widths_cm'])


def test_compare_volume_models_structure():
    contour = make_ellipse_contour()
    result = compare_volume_models(contour, pixels_per_cm=10.0)
    assert 'slice_model' in result
    assert 'cylinder_model' in result
    assert result['recommended'] == 'slice_elliptical'
    assert result['cylinder_model']['volume_cm3'] > 0
