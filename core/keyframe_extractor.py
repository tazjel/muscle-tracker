import cv2
import os
import numpy as np
import logging

logger = logging.getLogger(__name__)

class PoseKeyframeExtractor:
    """
    G13: Auto Keyframe Extraction for 3DGS and High-Fidelity Reconstruction.
    Selects frames based on sharpness, displacement (angular coverage), and pose stability.
    """
    def __init__(self, min_sharpness=100.0, min_displacement=15.0):
        self.min_sharpness = min_sharpness
        self.min_displacement = min_displacement

    def extract_3dgs_keyframes(self, video_path, num_frames=24, output_dir=None):
        """
        Extract the best frames for 3D Gaussian Splatting training.
        Ensures diverse angles and sharp details.
        """
        if not os.path.exists(video_path):
            logger.error(f"Video not found: {video_path}")
            return []

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        
        frames_data = []
        prev_gray = None
        cum_displacement = 0.0
        
        logger.info(f"Analyzing {total_frames} frames from {video_path}...")

        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 1. Sharpness check
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            # 2. Displacement check (Optical Flow)
            displacement = 0.0
            if prev_gray is not None:
                # Use a fast optical flow for displacement estimation
                flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                displacement = np.mean(np.sqrt(flow[..., 0]**2 + flow[..., 1]**2))
            
            cum_displacement += displacement
            
            frames_data.append({
                "idx": idx,
                "frame": frame,
                "sharpness": sharpness,
                "cum_disp": cum_displacement,
                "timestamp": idx / fps
            })
            
            prev_gray = gray
            idx += 1
            
        cap.release()

        # 3. Greedy selection based on displacement spacing
        if not frames_data:
            return []

        total_disp = frames_data[-1]["cum_disp"]
        target_spacing = total_disp / max(num_frames - 1, 1)
        
        selected = []
        last_selected_disp = -target_spacing
        
        # Sort by sharpness within windows to pick the best frame in each segment
        for f in frames_data:
            if (f["cum_disp"] - last_selected_disp) >= target_spacing:
                # Look ahead a few frames to find the sharpest one in this "segment"
                segment_end_disp = f["cum_disp"] + (target_spacing * 0.2)
                best_in_segment = f
                
                # Check next few frames for better sharpness
                for look_idx in range(f["idx"], min(f["idx"] + 10, len(frames_data))):
                    candidate = frames_data[look_idx]
                    if candidate["cum_disp"] > segment_end_disp:
                        break
                    if candidate["sharpness"] > best_in_segment["sharpness"]:
                        best_in_segment = candidate
                
                selected.append(best_in_segment)
                last_selected_disp = best_in_segment["cum_disp"]
                
                if len(selected) >= num_frames:
                    break

        logger.info(f"Selected {len(selected)} keyframes for 3DGS.")

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            saved_paths = []
            for i, item in enumerate(selected):
                path = os.path.join(output_dir, f"kf_{i:03d}_frame_{item['idx']:05d}.jpg")
                cv2.imwrite(path, item["frame"], [cv2.IMWRITE_JPEG_QUALITY, 95])
                saved_paths.append(path)
            return saved_paths

        return [s["frame"] for s in selected]

def extract_keyframes(video_path, num_frames=3):
    """Legacy wrapper for simple extraction."""
    extractor = PoseKeyframeExtractor()
    return extractor.extract_3dgs_keyframes(video_path, num_frames=num_frames)

def save_keyframes(frames, output_dir):
    """Legacy wrapper for saving frames."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    saved_paths = []
    for i, frame in enumerate(frames):
        path = os.path.join(output_dir, f"keyframe_{i}.jpg")
        cv2.imwrite(path, frame)
        saved_paths.append(path)
    
    return saved_paths
