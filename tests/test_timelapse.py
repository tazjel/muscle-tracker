import numpy as np
import pytest
import os
import tempfile
from core.timelapse import generate_progress_timelapse, generate_comparison_slider_image


def _make_image(h=300, w=300, color=(100, 100, 100)):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


def _make_contour():
    return np.array([[50,50],[250,50],[250,250],[50,250]], dtype=np.int32).reshape(-1,1,2)


class TestGenerateComparisonSlider:
    def test_generates_valid_image(self):
        before = _make_image(color=(50, 50, 50))
        after = _make_image(color=(200, 200, 200))
        contour = _make_contour()
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            path = f.name
        try:
            result = generate_comparison_slider_image(
                before, after, contour, contour, position=0.5, output_path=path
            )
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_position_extremes(self):
        before = _make_image()
        after = _make_image()
        contour = _make_contour()
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            path = f.name
        try:
            # position=0.0 should be all before
            result = generate_comparison_slider_image(
                before, after, contour, contour, position=0.0, output_path=path
            )
            assert os.path.exists(result)
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestGenerateProgressTimelapse:
    def test_generates_output(self):
        """Test with in-memory images saved to temp files."""
        import cv2
        imgs = []
        paths = []
        for i in range(3):
            img = _make_image(color=(50 + i*50, 50 + i*50, 50 + i*50))
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                cv2.imwrite(f.name, img)
                paths.append(f.name)

        contours = [_make_contour()] * 3
        metrics = [
            {'area_mm2': 1000 + i*100, 'scan_date': f'2026-03-0{i+1}'}
            for i in range(3)
        ]
        with tempfile.NamedTemporaryFile(suffix='.gif', delete=False) as f:
            out_path = f.name
        try:
            result = generate_progress_timelapse(paths, contours, metrics, output_path=out_path)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            for p in paths + [out_path]:
                if os.path.exists(p):
                    os.unlink(p)
