"""
depth_estimator.py — Monocular depth estimation using Depth Anything V2.

Input: BGR image + optional camera distance for metric scaling
Output: (H, W) float32 depth map in mm (or relative if no distance)
"""
import numpy as np
import cv2
import logging

logger = logging.getLogger(__name__)

_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model

    try:
        import torch
        from depth_anything_v2.dpt import DepthAnythingV2
        device = 'cuda' if torch.cuda.is_available() else 'cpu'

        model = DepthAnythingV2.from_pretrained('depth-anything/Depth-Anything-V2-Small-hf')
        model = model.to(device).eval()
        _model = (model, device)
        logger.info(f"Depth Anything V2 loaded on {device}")
        return _model
    except ImportError:
        logger.warning("Depth Anything V2 not installed — depth estimation unavailable")
        return None
    except Exception as e:
        logger.warning(f"Depth model load failed: {e}")
        return None


def estimate_depth(image, camera_distance_mm=None, body_mask=None):
    """
    Estimate depth map from single image.

    Args:
        image: (H, W, 3) uint8 BGR
        camera_distance_mm: float, if known → output is metric (mm)
        body_mask: (H, W) uint8, 255=body — used for metric scaling

    Returns:
        dict with:
            'depth': (H, W) float32 depth map
            'is_metric': bool — True if depth is in mm
            'depth_range_mm': (min, max) if metric
        or None on failure
    """
    loaded = _load_model()
    if loaded is None:
        return None

    model, device = loaded

    try:
        import torch

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        input_size = 518  # Depth Anything V2 default
        rgb_resized = cv2.resize(rgb, (input_size, input_size))

        tensor = torch.from_numpy(rgb_resized).float().permute(2, 0, 1) / 255.0
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        tensor = (tensor - mean) / std
        tensor = tensor.unsqueeze(0).to(device)

        with torch.no_grad():
            depth = model(tensor)

        depth = depth.squeeze().cpu().numpy()
        depth = cv2.resize(depth, (w, h))

        is_metric = False
        depth_range = None

        if camera_distance_mm and body_mask is not None:
            body_pixels = depth[body_mask > 127]
            if len(body_pixels) > 100:
                median_depth = np.median(body_pixels)
                scale = camera_distance_mm / max(median_depth, 0.001)
                depth = depth * scale
                is_metric = True
                body_depths = depth[body_mask > 127]
                depth_range = (float(body_depths.min()), float(body_depths.max()))

        return {
            'depth': depth.astype(np.float32),
            'is_metric': is_metric,
            'depth_range_mm': depth_range,
        }

    except Exception as e:
        logger.warning(f"Depth estimation failed: {e}")
        return None
