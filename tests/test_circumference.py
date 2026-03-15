import numpy as np
import pytest
from core.circumference import estimate_circumference, estimate_circumference_from_two_views, track_circumference_change

def test_estimate_circumference_elliptical():
    # rectangle 200x300
    contour = np.array([[100, 100], [300, 100], [300, 400], [100, 400]], dtype=np.int32).reshape(-1, 1, 2)
    result = estimate_circumference(contour, pixels_per_mm=1.0, method='elliptical')
    assert 'circumference_mm' in result
    assert result['circumference_mm'] > 400

def test_estimate_circumference_perimeter():
    contour = np.array([[100, 100], [300, 100], [300, 400], [100, 400]], dtype=np.int32).reshape(-1, 1, 2)
    result = estimate_circumference(contour, pixels_per_mm=1.0, method='perimeter')
    # 200 + 300 + 200 + 300 = 1000
    assert result['circumference_mm'] == 1000.0

def test_estimate_circumference_from_two_views():
    result = estimate_circumference_from_two_views(100.0, 80.0)
    assert result > 200

def test_track_circumference_change():
    result = track_circumference_change(300.0, 310.0)
    assert result['change_pct'] == 3.33
    assert result['verdict'] == 'Significant Growth'
