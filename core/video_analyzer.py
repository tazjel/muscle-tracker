"""
Video scan analyzer — extracts keyframes, runs per-frame muscle analysis,
picks the best frame, and aggregates stats.
"""
import os
import logging
import cv2
import numpy as np

from core.keyframe_extractor import extract_keyframes, save_keyframes

logger = logging.getLogger(__name__)


def analyze_muscle_video(video_path, muscle_group=None, output_dir='video_output'):
    """
    Process a video of a muscle flex/rotation and extract analysis.

    1. Extract sharpest keyframes
    2. Analyze each keyframe with basic contour analysis
    3. Pick best frame (highest contour solidity)
    4. Aggregate stats across frames

    Returns:
        dict with keyframes, measurements, best_frame, summary
        Returns None if video cannot be opened.
    """
    if not video_path or not os.path.exists(video_path):
        return None

    os.makedirs(output_dir, exist_ok=True)

    # Extract keyframes
    frames = extract_keyframes(video_path, num_frames=5)
    if not frames:
        return {'error': 'No frames extracted from video', 'keyframes': [], 'summary': {}}

    # Save keyframes
    kf_paths = save_keyframes(frames, output_dir)

    # Analyze each frame
    measurements = []
    keyframe_info = []

    for i, (frame, path) in enumerate(zip(frames, kf_paths)):
        m = _analyze_frame(frame, muscle_group, i)
        measurements.append(m)
        keyframe_info.append({'frame_number': i, 'image_path': path, 'metrics': m})

    # Pick best frame — highest contour solidity (most "full" muscle flex)
    best_idx = 0
    best_solidity = -1.0
    for i, m in enumerate(measurements):
        s = m.get('solidity', 0.0)
        if s > best_solidity:
            best_solidity = s
            best_idx = i

    best_frame = {
        'frame_number': best_idx,
        'image_path': kf_paths[best_idx] if best_idx < len(kf_paths) else None,
        'metrics': measurements[best_idx],
    }

    # Aggregate summary
    areas = [m.get('area_px2', 0) for m in measurements if m.get('area_px2', 0) > 0]
    solidities = [m.get('solidity', 0) for m in measurements if m.get('solidity', 0) > 0]

    summary = {
        'frames_analyzed': len(frames),
        'frames_with_contour': len(areas),
        'muscle_group': muscle_group or 'unknown',
        'mean_area_px2': round(float(np.mean(areas)), 1) if areas else 0,
        'max_area_px2': round(float(np.max(areas)), 1) if areas else 0,
        'mean_solidity': round(float(np.mean(solidities)), 3) if solidities else 0,
        'best_frame_idx': best_idx,
    }

    return {
        'keyframes': keyframe_info,
        'measurements': measurements,
        'best_frame': best_frame,
        'summary': summary,
    }


def _analyze_frame(frame, muscle_group, frame_idx):
    """Run basic contour analysis on a single frame."""
    if frame is None:
        return {'frame': frame_idx, 'error': 'null frame'}

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {'frame': frame_idx, 'area_px2': 0, 'solidity': 0.0, 'contour_found': False}

    # Largest contour
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))

    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    solidity = area / hull_area if hull_area > 0 else 0.0

    x, y, w, h = cv2.boundingRect(contour)

    return {
        'frame': frame_idx,
        'area_px2': round(area, 1),
        'solidity': round(solidity, 3),
        'width_px': w,
        'height_px': h,
        'contour_found': True,
        'muscle_group': muscle_group or 'unknown',
    }
