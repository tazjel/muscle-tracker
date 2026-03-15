import cv2
import os
import numpy as np

def extract_keyframes(video_path, num_frames=3):
    """
    Extracts the sharpest num_frames from a video file.
    Sample frames evenly and score by Laplacian variance.
    """
    if not os.path.exists(video_path):
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0:
        cap.release()
        return []

    # Sampling strategy: sample up to 30 frames evenly to find the sharpest ones
    sample_size = min(total_frames, 30)
    indices = np.linspace(0, total_frames - 1, sample_size, dtype=int)

    candidates = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if not ret:
            continue
        
        # Calculate Laplacian variance (sharpness score)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = cv2.Laplacian(gray, cv2.CV_64F).var()
        candidates.append((score, frame))

    cap.release()

    # Sort by score descending and take top num_frames
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    # Return only the frames, up to num_frames
    return [c[1] for c in candidates[:num_frames]]

def save_keyframes(frames, output_dir):
    """
    Saves a list of frames as JPEG images in output_dir.
    Returns the list of paths to the saved images.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    saved_paths = []
    for i, frame in enumerate(frames):
        path = os.path.join(output_dir, f"keyframe_{i}.jpg")
        cv2.imwrite(path, frame)
        saved_paths.append(path)
    
    return saved_paths
