import unittest
import numpy as np
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.segmentation import (
    load_ideal_template, 
    calculate_shape_score, 
    score_muscle_shape, 
    _score_to_grade,
    AVAILABLE_TEMPLATES
)

class TestSegmentation(unittest.TestCase):
    
    def test_load_ideal_templates(self):
        """Verify all 6 templates load correctly with proper format."""
        for name in AVAILABLE_TEMPLATES:
            contour = load_ideal_template(name)
            self.assertIsNotNone(contour, f"Template {name} failed to load")
            self.assertIsInstance(contour, np.ndarray)
            self.assertEqual(contour.dtype, np.int32)
            # OpenCV contours have shape (N, 1, 2)
            self.assertEqual(len(contour.shape), 3)
            self.assertEqual(contour.shape[1], 1)
            self.assertEqual(contour.shape[2], 2)
            self.assertGreater(contour.shape[0], 0)

    def test_load_unknown_template(self):
        """Verify unknown template returns None."""
        self.assertIsNone(load_ideal_template("non_existent_muscle"))

    def test_calculate_shape_score_self(self):
        """Similarity score should be 100 when comparing a template to itself."""
        for name in AVAILABLE_TEMPLATES:
            contour = load_ideal_template(name)
            result = calculate_shape_score(contour, contour)
            self.assertEqual(result["score"], 100.0, f"Self-match failed for {name}")
            self.assertEqual(result["grade"], "S")

    def test_calculate_shape_score_different(self):
        """Similarity score should be < 100 when comparing different shapes."""
        bicep = load_ideal_template("bicep_peak")
        lat = load_ideal_template("lat_spread")
        result = calculate_shape_score(bicep, lat)
        self.assertLess(result["score"], 100.0)
        self.assertNotEqual(result["grade"], "S")

    def test_calculate_shape_score_invalid_input(self):
        """Verify error handling for None inputs."""
        result = calculate_shape_score(None, np.array([]))
        self.assertIn("error", result)
        self.assertEqual(result["score"], 0.0)

    def test_score_muscle_shape_valid(self):
        """Verify full scoring pipeline with recommendations."""
        contour = load_ideal_template("bicep_peak")
        result = score_muscle_shape(contour, "bicep_peak")
        self.assertEqual(result["template"], "bicep_peak")
        self.assertEqual(result["score"], 100.0)
        self.assertIn("recommendations", result)
        self.assertIn("exercises", result["recommendations"])

    def test_score_muscle_shape_invalid_template(self):
        """Verify error for unknown template name."""
        result = score_muscle_shape(np.array([]), "ghost_muscle")
        self.assertIn("error", result)
        self.assertIn("available", result)

    def test_score_to_grade_boundaries(self):
        """Verify grade mapping logic."""
        self.assertEqual(_score_to_grade(90), "S")
        self.assertEqual(_score_to_grade(89), "A")
        self.assertEqual(_score_to_grade(75), "A")
        self.assertEqual(_score_to_grade(74), "B")
        self.assertEqual(_score_to_grade(60), "B")
        self.assertEqual(_score_to_grade(59), "C")
        self.assertEqual(_score_to_grade(40), "C")
        self.assertEqual(_score_to_grade(39), "D")
        self.assertEqual(_score_to_grade(20), "D")
        self.assertEqual(_score_to_grade(19), "F")
        self.assertEqual(_score_to_grade(0), "F")

if __name__ == '__main__':
    unittest.main()
