"""
Smart Frame Selector — pick the best N frames from a video for 3D reconstruction.

Strategy: select frames evenly spaced by cumulative optical-flow displacement
(angular coverage), not by time, preferring sharp frames.
"""
import cv2
import numpy as np
import os


def compute_frame_sharpness(frame: np.ndarray) -> float:
    """Laplacian variance of grayscale frame. Higher = sharper."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def compute_displacement(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """Mean optical flow magnitude between two consecutive frames."""
    ga = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return float(np.mean(mag))


def select_best_frames(
    video_path: str,
    num_frames: int = 30,
    quality_report: dict = None,
    min_sharpness: float = 80.0,
    min_displacement_px: float = 10.0,
    max_displacement_px: float = 150.0,
) -> list:
    """
    Select optimal frames from a video for 3D reconstruction.

    Args:
        video_path: Path to the video file.
        num_frames: Target number of frames to return.
        quality_report: Optional output from quality_gate.check_video_quality().
        min_sharpness: Laplacian variance threshold — frames below this are blurry.
        min_displacement_px: Min optical-flow displacement from last selected frame.
        max_displacement_px: Max displacement — skip if camera jumped (likely jank).

    Returns:
        List of dicts sorted by timestamp:
        [{frame_idx, timestamp_ms, sharpness, displacement_from_prev,
          cumulative_displacement}]
    """
    if not os.path.isfile(video_path):
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Use recommended_frames hint from quality gate if available
    if quality_report and 'recommended_frames' in quality_report:
        num_frames = min(num_frames, quality_report['recommended_frames'] * 2)

    # ── Pass 1: read all frames, compute sharpness ────────────────────────────
    all_frames = []
    idx = 0
    prev_frame = None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        sharp = compute_frame_sharpness(frame)
        disp = compute_displacement(prev_frame, frame) if prev_frame is not None else 0.0
        all_frames.append({
            'frame_idx': idx,
            'timestamp_ms': round(idx / fps * 1000, 2),
            'sharpness': round(sharp, 2),
            'raw_displacement': round(disp, 3),
            '_frame': frame,
        })
        prev_frame = frame
        idx += 1
    cap.release()

    if not all_frames:
        return []

    # ── Pass 2: filter blurry + jank frames ──────────────────────────────────
    valid = [f for f in all_frames
             if f['sharpness'] >= min_sharpness
             and f['raw_displacement'] <= max_displacement_px]

    # Fallback: if too many rejected, lower sharpness threshold
    if len(valid) < num_frames * 2:
        min_sharpness_fallback = min_sharpness * 0.5
        valid = [f for f in all_frames
                 if f['sharpness'] >= min_sharpness_fallback
                 and f['raw_displacement'] <= max_displacement_px]

    if not valid:
        valid = all_frames  # last resort — use everything

    # ── Pass 3: compute cumulative displacement along valid frames ────────────
    cum = 0.0
    for f in valid:
        cum += f['raw_displacement']
        f['cumulative_displacement'] = round(cum, 2)

    total_displacement = valid[-1]['cumulative_displacement'] if valid else 0.0

    # ── Pass 4: greedy selection by displacement spacing ─────────────────────
    target_spacing = total_displacement / max(num_frames, 1)
    selected = []
    last_cum = -target_spacing  # force first frame to be selected

    for f in valid:
        gap = f['cumulative_displacement'] - last_cum
        if gap >= max(target_spacing, min_displacement_px):
            selected.append(f)
            last_cum = f['cumulative_displacement']
            if len(selected) >= num_frames:
                break

    # ── Pass 5: top-up if short — fill from sharpest remaining ───────────────
    if len(selected) < num_frames:
        selected_idxs = {f['frame_idx'] for f in selected}
        remaining = sorted(
            [f for f in valid if f['frame_idx'] not in selected_idxs],
            key=lambda f: f['sharpness'], reverse=True
        )
        for f in remaining:
            if len(selected) >= num_frames:
                break
            selected.append(f)
        selected.sort(key=lambda f: f['frame_idx'])

    # ── Clean output — drop internal _frame key ───────────────────────────────
    result = []
    prev_cum = 0.0
    for f in selected:
        result.append({
            'frame_idx':             f['frame_idx'],
            'timestamp_ms':          f['timestamp_ms'],
            'sharpness':             f['sharpness'],
            'displacement_from_prev': round(f['cumulative_displacement'] - prev_cum, 2),
            'cumulative_displacement': f['cumulative_displacement'],
        })
        prev_cum = f['cumulative_displacement']

    return result


def extract_selected_frames(video_path: str, frame_descriptors: list,
                             output_dir: str) -> list:
    """
    Save the selected frames to disk as JPEGs.

    Args:
        video_path: Source video.
        frame_descriptors: Output from select_best_frames().
        output_dir: Directory to save images.

    Returns:
        Same list with 'image_path' added to each entry.
    """
    os.makedirs(output_dir, exist_ok=True)
    target_idxs = {d['frame_idx']: d for d in frame_descriptors}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return frame_descriptors

    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx in target_idxs:
            path = os.path.join(output_dir, f'frame_{idx:06d}.jpg')
            cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            target_idxs[idx]['image_path'] = path
        idx += 1
    cap.release()

    return frame_descriptors
