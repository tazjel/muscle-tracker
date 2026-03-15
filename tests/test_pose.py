import unittest
import numpy as np

# Mock mediapipe before importing pose_analyzer
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from unittest.mock import MagicMock, patch

class MockPoseLandmark:
    def __init__(self, y):
        self.y = y

class MockPoseResult:
    def __init__(self, ys):
        self.pose_landmarks = MagicMock()
        self.pose_landmarks.landmark = [MockPoseLandmark(y) for y in ys]

class MockPose:
    def process(self, img):
        # Let's say max y is 0.9, min y is 0.1
        return MockPoseResult([0.1, 0.5, 0.9])

mock_mp = MagicMock()
mock_mp.solutions.pose.Pose = MagicMock(return_value=MockPose())
sys.modules['mediapipe'] = mock_mp

# Now we can import the pose analyzer
import core.pose_analyzer as pose_analyzer
from core.pose_analyzer import get_px_to_mm_ratio_from_pose

class TestPoseAnalyzer(unittest.TestCase):
    @patch.object(pose_analyzer, 'pose_detector', MockPose())
    @patch.object(pose_analyzer, 'HAVE_MEDIAPIPE', True)
    def test_get_px_to_mm_ratio_from_pose(self):
        # Create a dummy image of height 1000px
        img = np.zeros((1000, 1000, 3), dtype=np.uint8)
        
        # In our mock, landmarks y are [0.1, 0.5, 0.9]
        # Bounding box in pixels: min_y = 100, max_y = 900 => diff = 800
        # Height is padded by 1.08: person_px_height = 800 * 1.08 = 864
        # If user_height_cm = 180, user_height_mm = 1800
        # Ratio = 1800 / 864 = 2.08333...
        
        ratio = get_px_to_mm_ratio_from_pose(img, 180.0)
        self.assertAlmostEqual(ratio, 1800 / 864, places=4)

if __name__ == '__main__':
    unittest.main()