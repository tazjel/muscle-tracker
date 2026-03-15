import sys
import os
import unittest
import math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.volumetrics import estimate_muscle_volume, compare_volumes, _elliptical_cylinder, _prismatoid

class TestVolumetrics(unittest.TestCase):
    def test_elliptical_cylinder_math(self):
        # A simple case where height is 100, front width is 50, side width is 40
        # h_front = area_front / width_front => area_front = 100 * 50 = 5000
        # h_side = area_side / width_side => area_side = 100 * 40 = 4000
        result = _elliptical_cylinder(5000, 4000, 50, 40)
        
        # Expected:
        # a = 25, b = 20
        # h = 100
        # volume_mm3 = pi * 25 * 20 * 100 = 50000 * pi ~ 157079.63
        # volume_cm3 = volume_mm3 / 1000 = 157.08
        
        self.assertAlmostEqual(result["volume_cm3"], round(math.pi * 25 * 20 * 100 / 1000, 2))
        self.assertAlmostEqual(result["semi_axis_a_mm"], 25)
        self.assertAlmostEqual(result["semi_axis_b_mm"], 20)
        self.assertAlmostEqual(result["height_mm"], 100)

    def test_prismatoid_math(self):
        # h = 100, front width = 50, side width = 40
        # area_front = 5000, area_side = 4000
        result = _prismatoid(5000, 4000, 50, 40)
        
        # a = 25, b = 20
        # A_mid = pi * 25 * 20 = 500 * pi ~ 1570.80
        # A_end = pi * (25 * 0.6) * (20 * 0.6) = 180 * pi ~ 565.49
        # volume_mm3 = (100 / 6) * (A_end + 4 * A_mid + A_end)
        # = (100 / 6) * (180*pi + 2000*pi + 180*pi) = (100 / 6) * 2360 * pi ~ 123569.31
        # volume_cm3 = volume_mm3 / 1000 = 123.57
        
        expected_v_mm3 = (100 / 6.0) * (180 * math.pi + 4 * 500 * math.pi + 180 * math.pi)
        self.assertAlmostEqual(result["volume_cm3"], round(expected_v_mm3 / 1000, 2))

    def test_invalid_inputs(self):
        # width zero
        result = estimate_muscle_volume(5000, 4000, 0, 40)
        self.assertEqual(result["volume_cm3"], 0.0)
        self.assertTrue("error" in result)
        
        # negative area
        result = estimate_muscle_volume(-5000, 4000, 50, 40)
        self.assertEqual(result["volume_cm3"], 0.0)
        self.assertTrue("error" in result)

    def test_compare_volumes(self):
        res = compare_volumes({"volume_cm3": 100.0}, {"volume_cm3": 110.0})
        self.assertEqual(res["delta_cm3"], 10.0)
        self.assertEqual(res["gain_pct"], 10.0)
        self.assertEqual(res["verdict"], "Significant Gain")

if __name__ == '__main__':
    unittest.main()