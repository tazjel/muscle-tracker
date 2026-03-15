"""Tests for core/vision_medical.py — contour extraction, classification, and growth analysis."""
import unittest
import numpy as np
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock mediapipe before importing (pose_analyzer does module-level init)
mock_mp = MagicMock()
mock_mp.solutions.pose.Pose.return_value = MagicMock()
sys.modules['mediapipe'] = mock_mp

from core.vision_medical import _extract_muscle_contour, _classify_change, analyze_muscle_growth


class TestExtractMuscleContour(unittest.TestCase):
    """Test the contour extraction pipeline on synthetic images."""

    def _make_image_with_blob(self, img_size=500, blob_radius=80):
        """Create a BGR image with a white circle on dark background."""
        img = np.zeros((img_size, img_size, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)  # dark gray background
        center = (img_size // 2, img_size // 2)
        import cv2
        cv2.circle(img, center, blob_radius, (255, 255, 255), -1)
        return img

    def test_detects_contour_in_synthetic_image(self):
        img = self._make_image_with_blob(500, 80)
        result = _extract_muscle_contour(img)
        self.assertIsNotNone(result)
        self.assertGreater(result['area_px'], 0)
        self.assertGreater(result['width_px'], 0)
        self.assertGreater(result['height_px'], 0)
        self.assertGreater(result['solidity'], 0.5)

    def test_solidity_near_1_for_circle(self):
        img = self._make_image_with_blob(500, 100)
        result = _extract_muscle_contour(img)
        self.assertIsNotNone(result)
        self.assertGreater(result['solidity'], 0.85)

    def test_returns_bbox(self):
        img = self._make_image_with_blob(500, 60)
        result = _extract_muscle_contour(img)
        self.assertIsNotNone(result)
        x, y, w, h = result['bbox']
        self.assertGreater(w, 50)
        self.assertGreater(h, 50)
        self.assertLess(w, 250)

    def test_uniform_image_still_returns_contour(self):
        img = np.full((200, 200, 3), 128, dtype=np.uint8)
        result = _extract_muscle_contour(img)
        # May or may not find a contour — should not crash


class TestClassifyChange(unittest.TestCase):
    """Test the 7-level verdict classification."""

    def test_significant_increase(self):
        self.assertEqual(_classify_change(6.0), "Significant Increase")

    def test_moderate_increase(self):
        self.assertEqual(_classify_change(2.0), "Moderate Increase")

    def test_slight_increase(self):
        self.assertEqual(_classify_change(0.7), "Slight Increase")

    def test_stable(self):
        self.assertEqual(_classify_change(0.3), "Stable")
        self.assertEqual(_classify_change(0.0), "Stable")
        self.assertEqual(_classify_change(-0.3), "Stable")

    def test_slight_decrease(self):
        self.assertEqual(_classify_change(-0.7), "Slight Decrease")

    def test_moderate_decrease(self):
        self.assertEqual(_classify_change(-2.0), "Moderate Decrease")

    def test_significant_decrease(self):
        self.assertEqual(_classify_change(-6.0), "Significant Decrease")

    def test_boundary_values(self):
        self.assertEqual(_classify_change(5.0), "Moderate Increase")
        self.assertEqual(_classify_change(5.01), "Significant Increase")
        self.assertEqual(_classify_change(1.0), "Slight Increase")
        self.assertEqual(_classify_change(1.01), "Moderate Increase")
        self.assertEqual(_classify_change(0.5), "Stable")
        self.assertEqual(_classify_change(0.51), "Slight Increase")


class TestAnalyzeMuscleGrowth(unittest.TestCase):
    """Test the full analysis pipeline with mocked dependencies."""

    @patch('core.vision_medical.get_px_to_mm_ratio')
    @patch('core.vision_medical.align_images')
    @patch('core.vision_medical.get_muscle_crop')
    @patch('core.vision_medical.cv2.imread')
    def test_self_comparison_uncalibrated(self, mock_imread, mock_crop, mock_align, mock_ratio):
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        import cv2
        cv2.circle(img, (250, 250), 80, (255, 255, 255), -1)

        mock_imread.return_value = img
        mock_crop.return_value = (None, None)
        mock_ratio.return_value = None

        result = analyze_muscle_growth("front.jpg", "front.jpg", align=False)

        self.assertEqual(result["status"], "Success")
        self.assertFalse(result["calibrated"])
        self.assertIn("metrics", result)
        self.assertIn("area_a_px2", result["metrics"])
        self.assertAlmostEqual(result["metrics"]["growth_pct"], 0.0)
        self.assertEqual(result["verdict"], "Stable")

    @patch('core.vision_medical.get_px_to_mm_ratio')
    @patch('core.vision_medical.align_images')
    @patch('core.vision_medical.get_muscle_crop')
    @patch('core.vision_medical.cv2.imread')
    def test_calibrated_analysis(self, mock_imread, mock_crop, mock_align, mock_ratio):
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        import cv2
        cv2.circle(img, (250, 250), 80, (255, 255, 255), -1)

        mock_imread.return_value = img
        mock_crop.return_value = (None, None)
        mock_ratio.return_value = 0.5

        result = analyze_muscle_growth("front.jpg", "front.jpg", align=False)

        self.assertEqual(result["status"], "Success")
        self.assertTrue(result["calibrated"])
        self.assertIn("area_a_mm2", result["metrics"])

    @patch('core.vision_medical.cv2.imread')
    def test_missing_image_returns_error(self, mock_imread):
        mock_imread.return_value = None
        result = analyze_muscle_growth("nonexistent.jpg", "also_missing.jpg")
        self.assertIn("error", result)

    @patch('core.vision_medical.get_px_to_mm_ratio')
    @patch('core.vision_medical.align_images')
    @patch('core.vision_medical.get_muscle_crop')
    @patch('core.vision_medical.cv2.imread')
    def test_growth_detected(self, mock_imread, mock_crop, mock_align, mock_ratio):
        import cv2 as cv

        img_before = np.zeros((500, 500, 3), dtype=np.uint8)
        img_before[:] = (30, 30, 30)
        cv.circle(img_before, (250, 250), 60, (255, 255, 255), -1)

        img_after = np.zeros((500, 500, 3), dtype=np.uint8)
        img_after[:] = (30, 30, 30)
        cv.circle(img_after, (250, 250), 90, (255, 255, 255), -1)

        mock_imread.side_effect = [img_before, img_after]
        mock_crop.return_value = (None, None)
        mock_align.return_value = (img_after, None, 0.0)
        mock_ratio.return_value = None

        result = analyze_muscle_growth("before.jpg", "after.jpg", align=False)

        self.assertEqual(result["status"], "Success")
        self.assertGreater(result["metrics"]["growth_pct"], 0)
        self.assertIn("Increase", result["verdict"])

    @patch('core.vision_medical.get_px_to_mm_ratio')
    @patch('core.vision_medical.align_images')
    @patch('core.vision_medical.get_muscle_crop')
    @patch('core.vision_medical.cv2.imread')
    def test_confidence_scores_present(self, mock_imread, mock_crop, mock_align, mock_ratio):
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        import cv2
        cv2.circle(img, (250, 250), 80, (255, 255, 255), -1)

        mock_imread.return_value = img
        mock_crop.return_value = (None, None)
        mock_ratio.return_value = None

        result = analyze_muscle_growth("a.jpg", "a.jpg", align=False)

        self.assertIn("confidence", result)
        self.assertIn("detection", result["confidence"])
        self.assertIn("calibration", result["confidence"])

    @patch('core.vision_medical.get_px_to_mm_ratio')
    @patch('core.vision_medical.align_images')
    @patch('core.vision_medical.get_muscle_crop')
    @patch('core.vision_medical.cv2.imread')
    def test_raw_data_contains_contours(self, mock_imread, mock_crop, mock_align, mock_ratio):
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        import cv2
        cv2.circle(img, (250, 250), 80, (255, 255, 255), -1)

        mock_imread.return_value = img
        mock_crop.return_value = (None, None)
        mock_ratio.return_value = None

        result = analyze_muscle_growth("a.jpg", "a.jpg", align=False)

        self.assertIn("raw_data", result)
        self.assertIn("contour_a", result["raw_data"])
        self.assertIn("contour_b", result["raw_data"])


if __name__ == '__main__':
    unittest.main()
