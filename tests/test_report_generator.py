import unittest
import numpy as np
import os
import tempfile
import cv2
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.report_generator import generate_clinical_report, _render_header, _render_footer, _draw_progress_bar

class TestReportGenerator(unittest.TestCase):
    def setUp(self):
        # Create temp files for output
        fd, self.temp_path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        
        # Test data setup
        self.scan_result = {
            "status": "Success",
            "verdict": "Moderate Increase",
            "confidence": {"detection": 85.0, "alignment": 70.0, "calibration": "high"},
            "metrics": {"growth_pct": 3.5, "area_delta_mm2": 120.0}
        }
        
        self.volume_result = {
            "volume_cm3": 157.08, "model": "elliptical_cylinder",
            "height_mm": 100, "semi_axis_a_mm": 25, "semi_axis_b_mm": 20
        }
        
        self.shape_result = {
            "score": 82.0, "grade": "A", "template": "bicep_peak",
            "recommendations": {"assessment": "Strong shape"}
        }

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.remove(self.temp_path)

    def test_generate_clinical_report_scan_only(self):
        """Test generating report with only scan_result."""
        generate_clinical_report(self.scan_result, output_path=self.temp_path, patient_name="Patient")
        self.assertTrue(os.path.exists(self.temp_path))
        img = cv2.imread(self.temp_path)
        self.assertIsNotNone(img)

    def test_generate_clinical_report_scan_and_volume(self):
        """Test generating report with scan and volume results."""
        generate_clinical_report(self.scan_result, volume_result=self.volume_result, output_path=self.temp_path)
        self.assertTrue(os.path.exists(self.temp_path))
        img = cv2.imread(self.temp_path)
        self.assertIsNotNone(img)

    def test_generate_clinical_report_all_sections(self):
        """Test generating report with all available sections."""
        # Using shape_result as symmetry/trend placeholders to satisfy the generic argument check
        # _render_symmetry_section expects 'symmetry_indices' -> 'composite_pct', 'dominant_side', 'risk_level'
        sym_result = {
            "status": "Success",
            "symmetry_indices": {"composite_pct": 5.0},
            "dominant_side": "Right",
            "risk_level": "low",
            "verdict": "Good"
        }
        
        # _render_trend_section expects 'trend' -> 'direction', 'weekly_rate_cm3', 'consistency_r2', 'projected_30d_cm3'
        trend_res = {
            "status": "Success",
            "trend": {
                "direction": "gaining",
                "weekly_rate_cm3": 10.5,
                "consistency_r2": 0.85,
                "projected_30d_cm3": 45.0
            },
            "periods": [{"volume_change_cm3": 5.0}, {"volume_change_cm3": -2.0}]
        }
        
        generate_clinical_report(
            self.scan_result, volume_result=self.volume_result, 
            symmetry_result=sym_result, shape_result=self.shape_result, 
            trend_result=trend_res, output_path=self.temp_path
        )
        self.assertTrue(os.path.exists(self.temp_path))
        img = cv2.imread(self.temp_path)
        self.assertIsNotNone(img)

    def test_render_header(self):
        """Test header rendering shape."""
        header = _render_header("Patient Name", "2026-03-15")
        self.assertEqual(header.shape, (120, 1200, 3))
        self.assertEqual(header.dtype, np.uint8)

    def test_render_footer(self):
        """Test footer rendering shape."""
        footer = _render_footer()
        self.assertEqual(footer.shape, (50, 1200, 3))
        self.assertEqual(footer.dtype, np.uint8)

    def test_draw_progress_bar_edge_cases(self):
        """Test progress bar handles edge cases without crashing."""
        img = np.zeros((100, 500, 3), dtype=np.uint8)
        
        # Test boundaries
        _draw_progress_bar(img, 50, 50, 400, 20, 0.0)
        _draw_progress_bar(img, 50, 50, 400, 20, 1.0)
        
        # Test out of bounds (negative / >1.0)
        _draw_progress_bar(img, 50, 50, 400, 20, -0.5)
        _draw_progress_bar(img, 50, 50, 400, 20, 1.5)

        
        # We just need it not to crash
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
