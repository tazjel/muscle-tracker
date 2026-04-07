"""Tests for G12: Pose Correction Engine (core/pose_analyzer.py)"""
import unittest
import math
import numpy as np
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock mediapipe before importing pose_analyzer (it does module-level init)
mock_mp = MagicMock()
mock_mp.solutions.pose.Pose.return_value = MagicMock()
sys.modules['mediapipe'] = mock_mp

from core.pose_analyzer import (
    _angle_between, _correction_instruction, POSE_RULES, _LM, analyze_pose
)
import core.pose_analyzer as pa
pa.HAVE_MEDIAPIPE = True


class TestAngleBetween(unittest.TestCase):
    """Test the angle calculation geometry."""

    def test_right_angle(self):
        a = (0, 1)
        b = (0, 0)
        c = (1, 0)
        self.assertAlmostEqual(_angle_between(a, b, c), 90.0, places=1)

    def test_straight_line(self):
        a = (-1, 0)
        b = (0, 0)
        c = (1, 0)
        self.assertAlmostEqual(_angle_between(a, b, c), 180.0, places=1)

    def test_acute_angle(self):
        a = (1, 0)
        b = (0, 0)
        c = (0.5, math.sqrt(3) / 2)
        self.assertAlmostEqual(_angle_between(a, b, c), 60.0, places=1)

    def test_obtuse_angle(self):
        a = (1, 0)
        b = (0, 0)
        c = (-0.5, math.sqrt(3) / 2)
        self.assertAlmostEqual(_angle_between(a, b, c), 120.0, places=1)

    def test_zero_angle(self):
        a = (1, 0)
        b = (0, 0)
        c = (2, 0)
        self.assertAlmostEqual(_angle_between(a, b, c), 0.0, places=1)


class TestCorrectionInstruction(unittest.TestCase):
    """Test instruction generation logic."""

    def test_within_tolerance_returns_none(self):
        result = _correction_instruction("elbow flexion", 88.0, 90.0, 15.0)
        self.assertIsNone(result)

    def test_outside_tolerance_returns_instruction(self):
        result = _correction_instruction("elbow flexion", 120.0, 90.0, 15.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["axis"], "elbow flexion")
        self.assertAlmostEqual(result["deviation"], 30.0, places=1)
        self.assertIn("Bend elbow more", result["instruction"])

    def test_elbow_needs_extension(self):
        result = _correction_instruction("elbow flexion", 60.0, 90.0, 15.0)
        self.assertIn("Extend elbow more", result["instruction"])

    def test_shoulder_too_high(self):
        result = _correction_instruction("shoulder abduction", 80.0, 45.0, 20.0)
        self.assertIn("Lower arm", result["instruction"])

    def test_shoulder_too_low(self):
        result = _correction_instruction("shoulder abduction", 10.0, 45.0, 20.0)
        self.assertIn("Raise arm", result["instruction"])

    def test_knee_needs_straightening(self):
        result = _correction_instruction("knee extension", 150.0, 175.0, 10.0)
        self.assertIn("Straighten leg", result["instruction"])

    def test_hip_alignment(self):
        result = _correction_instruction("hip alignment", 150.0, 175.0, 15.0)
        self.assertIn("Stand more upright", result["instruction"])


class TestPoseRules(unittest.TestCase):
    """Test that pose rules are well-formed."""

    def test_all_groups_have_rules(self):
        # Including new multi-view rules and aliases
        expected = {"bicep", "bicep_front", "bicep_side", "tricep", "quad", "calf", "delt", "lat", "lat_front", "lat_back"}
        self.assertEqual(set(POSE_RULES.keys()), expected)

    def test_rules_have_valid_structure(self):
        for group, rules in POSE_RULES.items():
            self.assertGreater(len(rules), 0, f"{group} has no rules")
            for (ja, jb, jc, ideal, tol, label) in rules:
                self.assertIn(ja, _LM, f"{group}: unknown landmark {ja}")
                self.assertIn(jb, _LM, f"{group}: unknown landmark {jb}")
                self.assertIn(jc, _LM, f"{group}: unknown landmark {jc}")
                self.assertGreater(ideal, 0)
                self.assertGreater(tol, 0)
                self.assertIsInstance(label, str)


class TestAnalyzePoseMocked(unittest.TestCase):
    """Test analyze_pose with mocked MediaPipe landmarks."""

    def _make_landmarks(self, angle_at_elbow=90):
        """Create mock landmarks where the right arm forms a given elbow angle."""
        class LM:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        landmarks = [LM(0.5, 0.5) for _ in range(33)]

        # right_hip(24), right_shoulder(12), right_elbow(14), right_wrist(16)
        landmarks[24] = LM(0.5, 0.7)
        landmarks[12] = LM(0.4, 0.3)
        landmarks[14] = LM(0.3, 0.45)

        # Position wrist to create the desired elbow angle
        ux, uy = -0.1, 0.15  # upper arm direction
        length = 0.12
        arm_angle = math.atan2(uy, ux)
        wrist_angle = arm_angle + math.radians(180 - angle_at_elbow)
        wx = landmarks[14].x + length * math.cos(wrist_angle)
        wy = landmarks[14].y + length * math.sin(wrist_angle)
        landmarks[16] = LM(wx, wy)

        return landmarks

    @patch('core.pose_analyzer._detect_pose')
    def test_analyze_pose_returns_scores(self, mock_detect):
        """Test that analyze_pose returns angles and scores for bicep."""
        import core.pose_analyzer as pa
        mock_detect.return_value = (self._make_landmarks(90), (1000, 1000))

        img = np.zeros((1000, 1000, 3), dtype=np.uint8)
        result = pa.analyze_pose(img, "bicep")
        self.assertIn(result["status"], ("ok", "corrections_needed"))
        self.assertIn("pose_score", result)
        self.assertIn("angles", result)
        self.assertGreater(result["pose_score"], 0)

    @patch('core.pose_analyzer._detect_pose')
    def test_bad_angle_generates_correction(self, mock_detect):
        """Test that a very wrong elbow angle produces corrections."""
        import core.pose_analyzer as pa
        # 170° elbow = nearly straight arm, bad for bicep peak (ideal=90°)
        mock_detect.return_value = (self._make_landmarks(170), (1000, 1000))

        img = np.zeros((1000, 1000, 3), dtype=np.uint8)
        result = pa.analyze_pose(img, "bicep")
        self.assertEqual(result["status"], "corrections_needed")
        self.assertGreater(result["num_corrections"], 0)
        # Should have an elbow correction
        axes = [c["axis"] for c in result["corrections"]]
        self.assertIn("elbow flexion", axes)

    def test_no_mediapipe_returns_error(self):
        import core.pose_analyzer as pa
        original = pa.HAVE_MEDIAPIPE
        pa.HAVE_MEDIAPIPE = False
        try:
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            result = pa.analyze_pose(img, "bicep")
            self.assertEqual(result["status"], "error")
        finally:
            pa.HAVE_MEDIAPIPE = original

    def test_unknown_group_returns_error(self):
        import core.pose_analyzer as pa
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result = pa.analyze_pose(img, "nonexistent_muscle")
        self.assertEqual(result["status"], "error")
        self.assertIn("available_groups", result)

    @patch('core.pose_analyzer._detect_pose')
    def test_group_name_aliases(self, mock_detect):
        """Test that aliases like 'biceps', 'shoulder' map correctly."""
        import core.pose_analyzer as pa
        mock_detect.return_value = (self._make_landmarks(90), (1000, 1000))

        img = np.zeros((1000, 1000, 3), dtype=np.uint8)
        for alias in ("biceps", "Bicep", "shoulder", "lats"):
            result = pa.analyze_pose(img, alias)
            self.assertNotEqual(result["status"], "error",
                                f"Alias '{alias}' should be recognized")


if __name__ == '__main__':
    unittest.main()
