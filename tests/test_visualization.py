import unittest
import numpy as np
import os
import tempfile
import cv2
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.visualization import (
    generate_growth_heatmap,
    generate_side_by_side,
    generate_symmetry_visual,
    _draw_legend,
    _draw_label
)

class TestVisualization(unittest.TestCase):
    def setUp(self):
        # Temp file paths
        fd1, self.out_heatmap = tempfile.mkstemp(suffix='.png')
        os.close(fd1)
        fd2, self.out_sbs = tempfile.mkstemp(suffix='.png')
        os.close(fd2)
        fd3, self.out_sym = tempfile.mkstemp(suffix='.png')
        os.close(fd3)

        # Synthetic images and contours
        self.img1 = np.zeros((300, 300, 3), dtype=np.uint8)
        self.img2 = np.zeros((300, 300, 3), dtype=np.uint8)
        
        self.contour1 = np.array([[100, 100], [200, 100], [200, 200], [100, 200]]).reshape(-1, 1, 2).astype(np.int32)
        self.contour2 = np.array([[90, 90], [210, 90], [210, 210], [90, 210]]).reshape(-1, 1, 2).astype(np.int32)

    def tearDown(self):
        for path in [self.out_heatmap, self.out_sbs, self.out_sym]:
            if os.path.exists(path):
                os.remove(path)

    def test_generate_growth_heatmap(self):
        """Test heatmap generation with valid inputs."""
        res = generate_growth_heatmap(self.img1, self.img2, self.contour1, self.contour2, self.out_heatmap)
        self.assertEqual(res, self.out_heatmap)
        self.assertTrue(os.path.exists(self.out_heatmap))
        img = cv2.imread(self.out_heatmap)
        self.assertIsNotNone(img)

    def test_generate_side_by_side(self):
        """Test side-by-side concatenation with separator."""
        res = generate_side_by_side(self.img1, self.img2, self.contour1, self.contour2, self.out_sbs)
        self.assertEqual(res, self.out_sbs)
        self.assertTrue(os.path.exists(self.out_sbs))
        img = cv2.imread(self.out_sbs)
        self.assertIsNotNone(img)
        # Expected width: 300 + 4 (separator) + 300 = 604
        self.assertEqual(img.shape[1], 604)

    def test_generate_symmetry_visual(self):
        """Test symmetry visual generation with data dict."""
        sym_data = {
            "dominant_side": "Right",
            "risk_level": "moderate",
            "symmetry_indices": {
                "area_px2": {"left": 1000, "right": 1100, "imbalance_pct": 9.5}
            }
        }
        res = generate_symmetry_visual(self.img1, self.img2, self.contour1, self.contour2, self.out_sym, sym_data)
        self.assertEqual(res, self.out_sym)
        self.assertTrue(os.path.exists(self.out_sym))
        img = cv2.imread(self.out_sym)
        self.assertIsNotNone(img)

    def test_draw_legend(self):
        """Test legend drawing handles empty/valid metrics without crashing."""
        canvas = np.zeros((200, 200, 3), dtype=np.uint8)
        _draw_legend(canvas, 200, 200, {"growth_pct": 5.0})
        _draw_legend(canvas, 200, 200, None)
        self.assertTrue(True)


    def test_draw_label(self):
        """Test generic label drawing without crashing."""
        canvas = np.zeros((100, 100, 3), dtype=np.uint8)
        _draw_label(canvas, "Test", (10, 10))
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
