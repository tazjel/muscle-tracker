import numpy as np
import pytest
import os
import tempfile
import cv2
from core.video_analyzer import analyze_muscle_video


class TestAnalyzeMuscleVideo:
    def test_analyzes_synthetic_video(self):
        """Create a minimal video, analyze it."""
        with tempfile.NamedTemporaryFile(suffix='.avi', delete=False) as f:
            video_path = f.name

        # Write a 10-frame synthetic video
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        out = cv2.VideoWriter(video_path, fourcc, 10.0, (300, 300))
        for i in range(10):
            frame = np.zeros((300, 300, 3), dtype=np.uint8)
            # Draw a "muscle" blob that changes size
            cv2.ellipse(frame, (150, 150), (50 + i*3, 80 + i*2), 0, 0, 360, (180, 180, 180), -1)
            out.write(frame)
        out.release()

        out_dir = tempfile.mkdtemp()
        try:
            result = analyze_muscle_video(video_path, muscle_group='bicep', output_dir=out_dir)
            assert 'keyframes' in result
            assert 'best_frame' in result
            assert 'summary' in result
            assert len(result['keyframes']) > 0
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)

    def test_invalid_video_path(self):
        result = analyze_muscle_video('/nonexistent/video.mp4')
        assert result is None or result == {} or 'error' in result
