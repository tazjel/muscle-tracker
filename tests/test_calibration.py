import unittest
import numpy as np
import cv2
import sys
import os
from unittest.mock import patch, MagicMock

# Mock mediapipe before importing core modules
mock_mp = MagicMock()
sys.modules['mediapipe'] = mock_mp
sys.modules['mediapipe.solutions'] = mock_mp.solutions
sys.modules['mediapipe.solutions.pose'] = mock_mp.solutions.pose

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.calibration import get_px_to_mm_ratio, _detect_green_marker, _detect_aruco

class TestCalibration(unittest.TestCase):
    def setUp(self):
        # Create a synthetic image with no markers
        self.blank_img = np.zeros((500, 500, 3), dtype=np.uint8)
        
        # Create a synthetic image with a green circle
        self.green_img = np.zeros((500, 500, 3), dtype=np.uint8)
        cv2.circle(self.green_img, (250, 250), 50, (0, 255, 0), -1)  # BGR green circle, radius=50, diam=100
        
        # We need a dummy temp file path for get_px_to_mm_ratio
        self.dummy_path = "dummy_test_image.jpg"
        cv2.imwrite(self.dummy_path, self.blank_img)
        self.green_path = "dummy_green_image.jpg"
        cv2.imwrite(self.green_path, self.green_img)

    def tearDown(self):
        if os.path.exists(self.dummy_path):
            os.remove(self.dummy_path)
        if os.path.exists(self.green_path):
            os.remove(self.green_path)

    @patch('core.calibration.get_px_to_mm_ratio_from_pose', return_value=None)
    def test_auto_no_markers(self, mock_pose):
        ratio = get_px_to_mm_ratio(self.dummy_path, method="auto")
        self.assertIsNone(ratio)

    def test_green_method_with_circle(self):
        ratio = get_px_to_mm_ratio(self.green_path, marker_size_mm=20.0, method="green")
        # Diameter is approx 100 pixels. Ratio should be ~ 20.0 / 100 = 0.2
        self.assertIsNotNone(ratio)
        self.assertAlmostEqual(ratio, 0.2, places=1)

    def test_detect_green_marker_with_circle(self):
        ratio = _detect_green_marker(self.green_img, 20.0)
        self.assertIsNotNone(ratio)
        self.assertAlmostEqual(ratio, 0.2, places=1)

    def test_detect_green_marker_no_green(self):
        ratio = _detect_green_marker(self.blank_img, 20.0)
        self.assertIsNone(ratio)

    def test_detect_aruco_no_marker(self):
        ratio = _detect_aruco(self.blank_img, 20.0)
        self.assertIsNone(ratio)

    def test_get_px_to_mm_ratio_nonexistent_file(self):
        ratio = get_px_to_mm_ratio("does_not_exist_at_all.jpg")
        self.assertIsNone(ratio)

    def test_get_px_to_mm_ratio_unknown_method(self):
        ratio = get_px_to_mm_ratio(self.dummy_path, method="unknown")
        self.assertIsNone(ratio)

if __name__ == '__main__':
    unittest.main()
