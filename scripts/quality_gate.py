"""
Video Quality Gate — pre-filter before expensive 3D reconstruction.
Usage: python scripts/quality_gate.py video.mp4 [--tracking-json poses.json] [--strict]
Exit 0 = pass, exit 1 = fail.
"""
import cv2
import numpy as np
import json
import sys
import argparse
import os


def _frame_sharpness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _optical_flow_displacement(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    ga = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return float(np.mean(mag))


def _has_person(frame: np.ndarray) -> bool:
    """Simple skin-colour HSV heuristic — fast, no heavy ML."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Broad skin range works for most skin tones including light-brown
    lower = np.array([0, 20, 70], dtype=np.uint8)
    upper = np.array([25, 180, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    skin_ratio = np.count_nonzero(mask) / max(mask.size, 1)
    return skin_ratio > 0.04   # at least 4 % of frame is skin-coloured


def check_video_quality(video_path: str, tracking_json_path: str = None,
                        strict: bool = False) -> dict:
    """
    Analyse a capture video for 3D reconstruction readiness.

    Returns dict with 'passed', 'score' (0-100), 'checks', 'rejection_reasons'.
    """
    if not os.path.isfile(video_path):
        return {'passed': False, 'score': 0,
                'rejection_reasons': [f'File not found: {video_path}'], 'checks': {}}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {'passed': False, 'score': 0,
                'rejection_reasons': ['Cannot open video file'], 'checks': {}}

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    duration_s = total_frames / fps if fps > 0 else 0

    # ── 1. Frame rate check ───────────────────────────────────────────────────
    fps_pass = fps >= 15.0
    fps_check = {'passed': fps_pass, 'actual_fps': round(fps, 2), 'min_required_fps': 15}

    # ── Sample every 5th frame ────────────────────────────────────────────────
    sample_step = max(1, total_frames // min(60, total_frames))
    sampled_frames = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % sample_step == 0:
            sampled_frames.append((idx, frame.copy()))
        idx += 1
    cap.release()

    if not sampled_frames:
        return {'passed': False, 'score': 0,
                'rejection_reasons': ['No frames could be decoded'], 'checks': {}}

    # ── 2. Motion blur check ──────────────────────────────────────────────────
    sharpness_scores = [_frame_sharpness(f) for _, f in sampled_frames]
    blurry = sum(1 for s in sharpness_scores if s < 100)
    blur_ratio = blurry / max(len(sharpness_scores), 1)
    blur_pass = blur_ratio < 0.20
    blur_check = {
        'passed': blur_pass,
        'score': round(float(np.mean(sharpness_scores)), 1),
        'blurry_frames': blurry,
        'total_frames': len(sampled_frames),
        'blur_ratio': round(blur_ratio, 3),
    }

    # ── 3. Person-presence check ──────────────────────────────────────────────
    person_count = sum(1 for _, f in sampled_frames if _has_person(f))
    person_ratio = person_count / max(len(sampled_frames), 1)
    person_pass = person_ratio > 0.60
    person_check = {
        'passed': person_pass,
        'frames_with_person': person_count,
        'total_frames': len(sampled_frames),
        'person_ratio': round(person_ratio, 3),
    }

    # ── 4. Frame coverage via optical flow ────────────────────────────────────
    total_displacement = 0.0
    displacements = []
    for i in range(1, len(sampled_frames)):
        d = _optical_flow_displacement(sampled_frames[i - 1][1], sampled_frames[i][1])
        displacements.append(d)
        total_displacement += d

    # Rough arc estimate: assume 30px mean displacement ≈ 1 degree of rotation
    # (heuristic — actual value depends on resolution and distance)
    px_per_degree = 30.0
    estimated_arc = total_displacement / px_per_degree
    min_arc = 270.0 if strict else 90.0
    coverage_pass = estimated_arc >= min_arc
    coverage_check = {
        'passed': coverage_pass,
        'estimated_arc_degrees': round(estimated_arc, 1),
        'total_displacement_px': round(total_displacement, 1),
        'min_required_degrees': min_arc,
    }

    # ── 5. Jank / dropped frames ─────────────────────────────────────────────
    dropped = 0
    if len(displacements) > 3:
        median_d = float(np.median(displacements))
        dropped = sum(1 for d in displacements if d > median_d * 4)
    jank_pass = dropped <= max(1, len(displacements) // 10)
    jank_check = {'passed': jank_pass, 'dropped_frames': dropped,
                  'total_intervals': len(displacements)}

    # ── 6. Tracking JSON check (optional) ────────────────────────────────────
    tracking_check = None
    if tracking_json_path and os.path.isfile(tracking_json_path):
        try:
            with open(tracking_json_path) as f:
                tj = json.load(f)
            poses = tj.get('poses') or tj.get('frames') or []
            tracking_check = {'passed': len(poses) > 0, 'pose_count': len(poses)}
        except Exception as e:
            tracking_check = {'passed': False, 'error': str(e)}

    # ── Overall score ─────────────────────────────────────────────────────────
    weights = {
        'fps':      (fps_pass,      15),
        'blur':     (blur_pass,     30),
        'person':   (person_pass,   25),
        'coverage': (coverage_pass, 20),
        'jank':     (jank_pass,     10),
    }
    score = sum(w for passed, w in weights.values() if passed)

    rejection_reasons = []
    if not fps_pass:
        rejection_reasons.append(f'Frame rate too low ({fps:.1f} fps, need ≥15)')
    if not blur_pass:
        rejection_reasons.append(f'{blurry}/{len(sampled_frames)} frames are blurry')
    if not person_pass:
        rejection_reasons.append(f'Person visible in only {person_ratio*100:.0f}% of frames')
    if not coverage_pass:
        rejection_reasons.append(
            f'Camera arc ~{estimated_arc:.0f}° — need {"270" if strict else "90"}°+')
    if not jank_pass:
        rejection_reasons.append(f'{dropped} jank/dropped frame intervals detected')

    checks = {
        'frame_rate':    fps_check,
        'motion_blur':   blur_check,
        'person_present': person_check,
        'frame_coverage': coverage_check,
        'jank':          jank_check,
    }
    if tracking_check:
        checks['tracking_json'] = tracking_check

    recommended_frames = max(10, min(60, int(total_frames * 0.15)))
    passed = score >= 60 and person_pass   # must have a person

    return {
        'passed': passed,
        'score': score,
        'duration_s': round(duration_s, 2),
        'total_frames': total_frames,
        'fps': round(fps, 2),
        'checks': checks,
        'recommended_frames': recommended_frames,
        'rejection_reasons': rejection_reasons,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Video quality gate for 3D reconstruction')
    parser.add_argument('video', help='Path to capture video')
    parser.add_argument('--tracking-json', dest='tracking_json', default=None,
                        help='Optional IMU/pose JSON file')
    parser.add_argument('--strict', action='store_true',
                        help='Require near-full orbit (270+ deg) instead of 90 deg')
    args = parser.parse_args()

    result = check_video_quality(args.video, args.tracking_json, args.strict)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['passed'] else 1)
