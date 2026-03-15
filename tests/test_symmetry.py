import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.symmetry import compare_symmetry

class TestSymmetry(unittest.TestCase):
    
    @patch('core.symmetry.analyze_muscle_growth')
    def test_compare_symmetry_success_uncalibrated(self, mock_analyze):
        """Test basic symmetry calculation with uncalibrated pixel values."""
        # Mock results for left side
        mock_analyze.side_effect = [
            {
                "status": "Success",
                "calibrated": False,
                "metrics": {
                    "area_a_px2": 1000.0,
                    "width_a_px": 100.0,
                    "height_a_px": 50.0
                }
            },
            # Mock results for right side (10% larger in area)
            {
                "status": "Success",
                "calibrated": False,
                "metrics": {
                    "area_a_px2": 1100.0,
                    "width_a_px": 105.0,
                    "height_a_px": 52.0
                }
            }
        ]
        
        result = compare_symmetry("left.jpg", "right.jpg")
        
        self.assertEqual(result["status"], "Success")
        self.assertEqual(result["dominant_side"], "Right")
        self.assertIn("imbalance_pct", result["symmetry_indices"]["area_px2"])
        
        # SI_area = |1100-1000| / ((1100+1000)/2) * 100 = 100 / 1050 * 100 = 9.5238
        self.assertAlmostEqual(result["symmetry_indices"]["area_px2"]["imbalance_pct"], 9.52, places=2)
        self.assertEqual(result["risk_level"], "moderate")

    @patch('core.symmetry.analyze_muscle_growth')
    def test_compare_symmetry_success_calibrated(self, mock_analyze):
        """Test symmetry with calibrated mm values."""
        mock_analyze.side_effect = [
            {
                "status": "Success",
                "calibrated": True,
                "metrics": {
                    "area_a_mm2": 5000.0,
                    "width_a_mm": 50.0,
                    "height_a_mm": 100.0
                }
            },
            {
                "status": "Success",
                "calibrated": True,
                "metrics": {
                    "area_a_mm2": 5100.0,
                    "width_a_mm": 51.0,
                    "height_a_mm": 100.0
                }
            }
        ]
        
        result = compare_symmetry("left.jpg", "right.jpg")
        self.assertTrue(result["calibrated"])
        self.assertEqual(result["risk_level"], "low") # Composite SI will be < 3.0

    @patch('core.symmetry.analyze_muscle_growth')
    def test_identical_limbs(self, mock_analyze):
        """Test 0% imbalance for identical measurements."""
        mock_data = {
            "status": "Success",
            "calibrated": False,
            "metrics": {
                "area_a_px2": 1000.0,
                "width_a_px": 100.0,
                "height_a_px": 100.0
            }
        }
        mock_analyze.side_effect = [mock_data, mock_data]
        
        result = compare_symmetry("left.jpg", "right.jpg")
        self.assertEqual(result["dominant_side"], "Equal")
        self.assertEqual(result["symmetry_indices"]["composite_pct"], 0.0)
        self.assertEqual(result["risk_level"], "low")

    @patch('core.symmetry.analyze_muscle_growth')
    def test_severe_imbalance(self, mock_analyze):
        """Test 'high' risk level for severe asymmetry."""
        mock_analyze.side_effect = [
            {
                "status": "Success",
                "metrics": {"area_a_px2": 1000.0, "width_a_px": 100.0, "height_a_px": 100.0}
            },
            {
                "status": "Success",
                "metrics": {"area_a_px2": 1500.0, "width_a_px": 150.0, "height_a_px": 100.0}
            }
        ]
        
        result = compare_symmetry("left.jpg", "right.jpg")
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["dominant_side"], "Right")

    @patch('core.symmetry.analyze_muscle_growth')
    def test_analysis_failure_left(self, mock_analyze):
        """Test graceful failure if left limb analysis fails."""
        mock_analyze.side_effect = [{"error": "Left failed"}, {"status": "Success"}]
        result = compare_symmetry("left.jpg", "right.jpg")
        self.assertIn("error", result)
        self.assertIn("Left limb analysis failed", result["error"])

    @patch('core.symmetry.analyze_muscle_growth')
    def test_analysis_failure_right(self, mock_analyze):
        """Test graceful failure if right limb analysis fails."""
        mock_analyze.side_effect = [{"status": "Success"}, {"error": "Right failed"}]
        result = compare_symmetry("left.jpg", "right.jpg")
        self.assertIn("error", result)
        self.assertIn("Right limb analysis failed", result["error"])

if __name__ == '__main__':
    unittest.main()
