"""
Tests for core/pipeline.py — unified scan pipeline.
"""
import os
import tempfile
import numpy as np
import cv2
import pytest
from core.pipeline import full_scan_pipeline


def _make_test_image(path, with_circle=True):
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    if with_circle:
        cv2.circle(img, (150, 150), 80, (200, 150, 100), -1)
    cv2.imwrite(path, img)


class TestPipeline:
    def test_returns_dict_on_valid_image(self, tmp_path):
        img_path = str(tmp_path / 'front.jpg')
        _make_test_image(img_path)
        result = full_scan_pipeline(img_path)
        assert isinstance(result, dict)

    def test_no_error_key_on_success(self, tmp_path):
        img_path = str(tmp_path / 'front.jpg')
        _make_test_image(img_path)
        result = full_scan_pipeline(img_path)
        assert 'error' not in result

    def test_returns_error_on_missing_file(self):
        result = full_scan_pipeline('/nonexistent/path/image.jpg')
        assert 'error' in result

    def test_has_errors_list(self, tmp_path):
        img_path = str(tmp_path / 'front.jpg')
        _make_test_image(img_path)
        result = full_scan_pipeline(img_path)
        assert 'errors' in result
        assert isinstance(result['errors'], list)

    def test_volume_cm3_present(self, tmp_path):
        img_path = str(tmp_path / 'front.jpg')
        _make_test_image(img_path)
        result = full_scan_pipeline(img_path)
        assert 'volume_cm3' in result
        assert isinstance(result.get('volume_cm3'), (int, float))

    def test_calibrated_key_present(self, tmp_path):
        img_path = str(tmp_path / 'front.jpg')
        _make_test_image(img_path)
        result = full_scan_pipeline(img_path)
        assert 'calibrated' in result

    def test_body_composition_present(self, tmp_path):
        img_path = str(tmp_path / 'front.jpg')
        _make_test_image(img_path)
        result = full_scan_pipeline(img_path, user_weight_kg=80, user_height_cm=175)
        assert 'body_composition' in result
        assert isinstance(result['body_composition'], dict)

    def test_annotated_image_saved(self, tmp_path):
        img_path = str(tmp_path / 'front.jpg')
        _make_test_image(img_path)
        out_dir  = str(tmp_path)
        result   = full_scan_pipeline(img_path, output_dir=out_dir)
        if result.get('annotated_img'):
            assert os.path.exists(result['annotated_img'])

    def test_with_side_image(self, tmp_path):
        front = str(tmp_path / 'front.jpg')
        side  = str(tmp_path / 'side.jpg')
        _make_test_image(front)
        _make_test_image(side)
        result = full_scan_pipeline(front, image_side_path=side)
        assert 'error' not in result
        assert 'volume_cm3' in result
