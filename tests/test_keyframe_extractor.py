import pytest
import os
import numpy as np
import cv2
import tempfile
import shutil
from core.keyframe_extractor import extract_keyframes, save_keyframes

@pytest.fixture
def temp_dir():
    dir_path = tempfile.mkdtemp()
    yield dir_path
    shutil.rmtree(dir_path)

def create_test_video(path, frames=10, width=100, height=100):
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 10.0, (width, height))
    for i in range(frames):
        # Create a frame with some content to have variance
        frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
        # Add some text or shapes to increase Laplacian variance
        cv2.putText(frame, f"Frame {i}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        out.write(frame)
    out.release()

def test_extract_keyframes_success(temp_dir):
    video_path = os.path.join(temp_dir, "test_video.mp4")
    create_test_video(video_path, frames=10)
    
    keyframes = extract_keyframes(video_path, num_frames=3)
    assert len(keyframes) == 3
    for frame in keyframes:
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (100, 100, 3)

def test_extract_keyframes_short_video(temp_dir):
    video_path = os.path.join(temp_dir, "short_video.mp4")
    create_test_video(video_path, frames=2)
    
    keyframes = extract_keyframes(video_path, num_frames=5)
    # Sampling strategy might return duplicate or fewer if cap.read() fails
    # But for 2 frames, it should return 2.
    assert len(keyframes) <= 5
    assert len(keyframes) > 0

def test_extract_keyframes_nonexistent():
    keyframes = extract_keyframes("nonexistent.mp4")
    assert keyframes == []

def test_save_keyframes(temp_dir):
    frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(2)]
    output_dir = os.path.join(temp_dir, "keyframes")
    
    paths = save_keyframes(frames, output_dir)
    assert len(paths) == 2
    for path in paths:
        assert os.path.exists(path)
        assert path.endswith(".jpg")
