"""
video_capture.py — PTS-accurate frame extraction using PyAV.

OpenCV's CAP_PROP_POS_MSEC skips to the nearest keyframe, giving
incorrect timestamps on H.264/HEVC video. PyAV decodes every frame
in display order and reports the real PTS so the timestamp is exact.

Public API:
    extract_frames_by_index(video_path, frame_indices, output_dir) → list
    extract_frames_by_time(video_path, timestamps_ms, output_dir)  → list
    get_video_info(video_path)                                       → dict
"""

import os

try:
    import av
    _AV_AVAILABLE = True
except ImportError:
    _AV_AVAILABLE = False

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


# ── Video metadata ─────────────────────────────────────────────────────────────

def get_video_info(video_path: str) -> dict:
    """
    Return basic metadata without decoding all frames.

    Returns:
        dict with keys: width, height, fps, duration_s, total_frames,
                        codec, has_audio, backend ('av' | 'cv2' | 'error').
    """
    if not os.path.isfile(video_path):
        return {'error': f'File not found: {video_path}', 'backend': 'error'}

    if _AV_AVAILABLE:
        try:
            with av.open(video_path) as container:
                vs = next((s for s in container.streams if s.type == 'video'), None)
                if vs is None:
                    return {'error': 'No video stream', 'backend': 'av'}
                fps = float(vs.average_rate) if vs.average_rate else 0.0
                dur = float(container.duration / av.time_base) if container.duration else 0.0
                return {
                    'width':        vs.width,
                    'height':       vs.height,
                    'fps':          round(fps, 3),
                    'duration_s':   round(dur, 3),
                    'total_frames': vs.frames or int(dur * fps),
                    'codec':        vs.codec_context.name,
                    'has_audio':    any(s.type == 'audio' for s in container.streams),
                    'backend':      'av',
                }
        except Exception as e:
            pass  # fall through to cv2

    if _CV2_AVAILABLE:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {'error': 'Cannot open video', 'backend': 'error'}
        fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return {
            'width': w, 'height': h,
            'fps':   round(fps, 3),
            'duration_s': round(frames / fps, 3) if fps > 0 else 0.0,
            'total_frames': frames,
            'codec': 'unknown', 'has_audio': False,
            'backend': 'cv2',
        }

    return {'error': 'Neither PyAV nor OpenCV available', 'backend': 'error'}


# ── PyAV extraction helpers ────────────────────────────────────────────────────

def _extract_av(video_path: str, target_indices: set, output_dir: str,
                jpeg_quality: int = 95) -> list:
    """
    Decode video with PyAV, save frames whose display_index is in target_indices.

    Returns list of dicts: {frame_idx, timestamp_ms, image_path}.
    """
    results = {}
    with av.open(video_path) as container:
        vs = next((s for s in container.streams if s.type == 'video'), None)
        if vs is None:
            return []
        vs.thread_type = 'AUTO'

        display_idx = 0
        for packet in container.demux(vs):
            for frame in packet.decode():
                if display_idx in target_indices:
                    pts_s = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
                    img = frame.to_ndarray(format='bgr24')

                    import cv2 as _cv2
                    path = os.path.join(output_dir, f'frame_{display_idx:06d}.jpg')
                    _cv2.imwrite(path, img, [_cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                    results[display_idx] = {
                        'frame_idx':    display_idx,
                        'timestamp_ms': round(pts_s * 1000, 2),
                        'image_path':   path,
                    }
                    if len(results) == len(target_indices):
                        return list(results[i] for i in sorted(results))
                display_idx += 1

    return list(results[i] for i in sorted(results))


def _extract_cv2(video_path: str, target_indices: set, output_dir: str,
                 jpeg_quality: int = 95) -> list:
    """OpenCV fallback — less accurate timestamps but no PyAV dependency."""
    import cv2 as _cv2
    results = {}
    cap = _cv2.VideoCapture(video_path)
    fps = cap.get(_cv2.CAP_PROP_FPS) or 30.0
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx in target_indices:
            path = os.path.join(output_dir, f'frame_{idx:06d}.jpg')
            _cv2.imwrite(path, frame, [_cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            results[idx] = {
                'frame_idx':    idx,
                'timestamp_ms': round(idx / fps * 1000, 2),
                'image_path':   path,
            }
        idx += 1
    cap.release()
    return list(results[i] for i in sorted(results))


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_frames_by_index(video_path: str, frame_indices: list,
                             output_dir: str, jpeg_quality: int = 95) -> list:
    """
    Extract specific frames by their display index (0-based).

    Uses PyAV if available (PTS-accurate), falls back to OpenCV.

    Args:
        video_path:    source video file.
        frame_indices: list of integer frame indices to extract.
        output_dir:    directory to write JPEG files.
        jpeg_quality:  JPEG compression quality (1–100).

    Returns:
        List of dicts: [{frame_idx, timestamp_ms, image_path}],
        sorted by frame_idx. Missing indices are silently omitted.
    """
    if not os.path.isfile(video_path):
        return []
    os.makedirs(output_dir, exist_ok=True)
    target = set(frame_indices)

    if _AV_AVAILABLE:
        try:
            return _extract_av(video_path, target, output_dir, jpeg_quality)
        except Exception:
            pass  # fall through

    if _CV2_AVAILABLE:
        return _extract_cv2(video_path, target, output_dir, jpeg_quality)

    raise RuntimeError('Neither PyAV nor OpenCV is available for frame extraction')


def extract_frames_by_time(video_path: str, timestamps_ms: list,
                            output_dir: str, jpeg_quality: int = 95) -> list:
    """
    Extract the closest frame to each requested timestamp (ms).

    First calls get_video_info() to determine FPS, then converts timestamps
    to frame indices and calls extract_frames_by_index().

    Args:
        video_path:     source video file.
        timestamps_ms:  list of target times in milliseconds.
        output_dir:     directory to write JPEG files.
        jpeg_quality:   JPEG compression quality (1–100).

    Returns:
        Same format as extract_frames_by_index().
    """
    info = get_video_info(video_path)
    fps  = info.get('fps') or 30.0
    indices = [max(0, round(t_ms / 1000.0 * fps)) for t_ms in timestamps_ms]
    return extract_frames_by_index(video_path, indices, output_dir, jpeg_quality)
