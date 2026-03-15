import numpy as np
import pytest
import cv2
from core.measurement_overlay import draw_measurement_overlay, draw_volume_cross_section, draw_pose_skeleton

def test_draw_measurement_overlay_valid():
    img = np.zeros((500, 500, 3), dtype=np.uint8)
    contour = np.array([[100, 100], [300, 100], [300, 400], [100, 400]], dtype=np.int32).reshape(-1, 1, 2)
    metrics = {
        'area_a_mm2': 10000.0,
        'width_a_mm': 200.0,
        'height_a_mm': 300.0
    }
    result = draw_measurement_overlay(img, contour, metrics, calibrated=True)
    assert result is not None
    assert result.shape == (500, 500, 3)
    assert np.any(result > 0)

def test_draw_volume_cross_section_valid():
    img = np.zeros((500, 500, 3), dtype=np.uint8)
    contour = np.array([[100, 100], [300, 100], [300, 400], [100, 400]], dtype=np.int32).reshape(-1, 1, 2)
    slice_data = {
        'slice_widths_cm': [10.0, 12.0, 15.0, 12.0, 10.0]
    }
    result = draw_volume_cross_section(img, slice_data, contour)
    assert result is not None
    assert np.any(result > 0)

def test_draw_pose_skeleton_valid():
    img = np.zeros((500, 500, 3), dtype=np.uint8)
    landmarks = {
        'LEFT_SHOULDER': (200, 100),
        'LEFT_ELBOW': (200, 200),
        'LEFT_WRIST': (200, 300)
    }
    corrections = [{'axis': 'elbow', 'instruction': 'Bend more'}]
    result = draw_pose_skeleton(img, landmarks, corrections)
    assert result is not None
    assert np.any(result > 0)
