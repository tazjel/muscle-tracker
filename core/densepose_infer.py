"""
densepose_infer.py — Run DensePose inference to get IUV maps from photos.

Supports multiple backends:
  1. DensePose-TorchScript (lightweight, no detectron2 dependency)
  2. Detectron2 DensePose (full, needs detectron2)
  3. Cloud GPU via RunPod (offload to GPU server)

Each backend produces the same output: an IUV map (H, W, 3) uint8 where:
  channel 0 = body part index I (0=background, 1-24=body parts)
  channel 1 = U coordinate (0-255)
  channel 2 = V coordinate (0-255)
"""
import cv2
import numpy as np
import os
import logging
import sys

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_MODELS_DIR = os.path.join(_PROJECT_ROOT, 'models', 'densepose')


def _ensure_models_dir():
    os.makedirs(_MODELS_DIR, exist_ok=True)
    return _MODELS_DIR


def detect_backend():
    """Detect which DensePose backend is available. Local-first, cloud only if explicit."""
    # Try TorchScript first (lightweight)
    ts_path = os.path.join(_PROJECT_ROOT, 'third_party', 'DensePose-TorchScript')
    if os.path.exists(ts_path):
        try:
            import torch
            return 'torchscript'
        except ImportError:
            pass

    # Try Detectron2
    try:
        import detectron2
        return 'detectron2'
    except ImportError:
        pass

    # Cloud GPU — ONLY if explicitly enabled via USE_CLOUD_GPU=true
    if os.environ.get('USE_CLOUD_GPU', '').lower() == 'true':
        try:
            from core.cloud_gpu import is_configured
            if is_configured():
                return 'cloud'
        except Exception:
            pass

    return None


def predict_iuv(image_path, backend=None):
    """
    Run DensePose on an image, return IUV map.

    Args:
        image_path: path to image file, or (H, W, 3) uint8 BGR array
        backend:    'torchscript', 'detectron2', or 'cloud' (auto-detected if None)

    Returns:
        iuv_map: (H, W, 3) uint8 — IUV prediction
                 channel 0 = part index (0=bg, 1-24=body)
                 channel 1 = U (0-255)
                 channel 2 = V (0-255)
        or None if inference fails
    """
    if backend is None:
        backend = detect_backend()
        if backend is None:
            logger.error("No DensePose backend available. Install one of:\n"
                         "  1. DensePose-TorchScript: git clone https://github.com/dajes/DensePose-TorchScript third_party/DensePose-TorchScript\n"
                         "  2. Detectron2: pip install detectron2\n"
                         "  3. Set RUNPOD_API_KEY for cloud inference")
            return None

    logger.info(f"Using DensePose backend: {backend}")

    if backend == 'torchscript':
        return _predict_torchscript(image_path)
    elif backend == 'detectron2':
        return _predict_detectron2(image_path)
    elif backend == 'cloud':
        return _predict_cloud(image_path)
    else:
        logger.error(f"Unknown backend: {backend}")
        return None


def _load_image(image_path):
    """Load image from path or return array as-is."""
    if isinstance(image_path, np.ndarray):
        return image_path
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    return img


_cached_model = None


def _get_torchscript_model():
    """Load and cache the DensePose TorchScript model."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model

    import torch
    import torchvision  # noqa: F401 — required for torchvision::nms op

    # Find exported model
    model_path = os.path.join(
        _PROJECT_ROOT, 'third_party', 'DensePose-TorchScript',
        'exported', 'densepose_rcnn_R_50_FPN_s1x_legacy_fp16.pt'
    )
    if not os.path.exists(model_path):
        # Check alternative locations
        alt = os.path.join(_MODELS_DIR, 'densepose_torchscript.pt')
        if os.path.exists(alt):
            model_path = alt
        else:
            raise FileNotFoundError(
                f"DensePose model not found. Export it first:\n"
                f"  cd third_party/DensePose-TorchScript && python export.py "
                f"configs/densepose_rcnn_R_50_FPN_s1x_legacy.yaml "
                f"https://dl.fbaipublicfiles.com/densepose/densepose_rcnn_R_50_FPN_s1x_legacy/164832157/model_final_d366fa.pkl --fp16"
            )

    logger.info(f"Loading DensePose model: {model_path}")
    model = torch.jit.load(model_path)
    model.eval().float()
    _cached_model = model
    return model


def _predict_torchscript(image_path):
    """Run DensePose via DensePose-TorchScript (lightweight, no detectron2).

    Model output format (dict):
      pred_boxes: (N, 4) float32 — bounding boxes [x1, y1, x2, y2]
      pred_densepose_coarse_segm: (N, 15, 56, 56) float32
      pred_densepose_fine_segm:   (N, 25, 56, 56) float32 — body part logits
      pred_densepose_u:           (N, 25, 56, 56) float32 — U coordinates per part
      pred_densepose_v:           (N, 25, 56, 56) float32 — V coordinates per part

    Uses the same extraction logic as visualizer.py's DensePoseResultExtractor:
      1. Resample fine_segm to bounding box size → argmax → part labels
      2. For each part, pick the corresponding U/V channel
    """
    import torch
    from torch.nn import functional as F

    ts_path = os.path.join(_PROJECT_ROOT, 'third_party', 'DensePose-TorchScript')
    if ts_path not in sys.path:
        sys.path.insert(0, ts_path)

    img = _load_image(image_path)
    h, w = img.shape[:2]

    model = _get_torchscript_model()

    # Model expects raw BGR numpy image as tensor (no preprocessing needed)
    tensor = torch.from_numpy(img)

    with torch.no_grad():
        outputs = model(tensor)

    if not isinstance(outputs, dict) or 'pred_boxes' not in outputs:
        logger.error(f"Unexpected model output: {type(outputs)}")
        return None

    n_detections = outputs['pred_boxes'].shape[0]
    if n_detections == 0:
        logger.warning("No person detected in image")
        return np.zeros((h, w, 3), dtype=np.uint8)

    logger.info(f"Detected {n_detections} person(s)")

    # Build full-image IUV map
    iuv = np.zeros((h, w, 3), dtype=np.uint8)

    # Process each detected person (typically just 1)
    for det_idx in range(n_detections):
        # Bounding box: x1, y1, x2, y2
        box = outputs['pred_boxes'][det_idx].cpu()
        x1, y1, x2, y2 = box.long().tolist()
        bw = max(x2 - x1, 1)
        bh = max(y2 - y1, 1)

        # Extract DensePose predictions for this detection
        coarse_segm = outputs['pred_densepose_coarse_segm'][det_idx].unsqueeze(0)  # (1, 15, 56, 56)
        fine_segm = outputs['pred_densepose_fine_segm'][det_idx].unsqueeze(0)      # (1, 25, 56, 56)
        u_tensor = outputs['pred_densepose_u'][det_idx].unsqueeze(0)               # (1, 25, 56, 56)
        v_tensor = outputs['pred_densepose_v'][det_idx].unsqueeze(0)               # (1, 25, 56, 56)

        # Resample to bounding box size (same logic as visualizer.py resample_fine)
        coarse_bbox = F.interpolate(coarse_segm, (bh, bw), mode="bilinear", align_corners=False).argmax(dim=1)
        body_mask = (coarse_bbox > 0).long()
        labels = F.interpolate(fine_segm, (bh, bw), mode="bilinear", align_corners=False).argmax(dim=1) * body_mask
        labels = labels.squeeze(0)  # (bh, bw)

        # Resample U, V to bounding box size and select per-part values
        u_bbox = F.interpolate(u_tensor, (bh, bw), mode="bilinear", align_corners=False).squeeze(0)  # (25, bh, bw)
        v_bbox = F.interpolate(v_tensor, (bh, bw), mode="bilinear", align_corners=False).squeeze(0)  # (25, bh, bw)

        u_map = torch.zeros((bh, bw), dtype=torch.float32)
        v_map = torch.zeros((bh, bw), dtype=torch.float32)

        for part_id in range(1, min(u_bbox.shape[0], 25)):
            part_mask = labels == part_id
            if part_mask.any():
                u_map[part_mask] = u_bbox[part_id][part_mask]
                v_map[part_mask] = v_bbox[part_id][part_mask]

        # Convert to numpy uint8
        labels_np = labels.cpu().numpy().astype(np.uint8)
        u_np = (u_map.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        v_np = (v_map.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)

        # Clip bounding box to image bounds
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(w, x1 + bw), min(h, y1 + bh)
        sx, sy = x1c - x1, y1c - y1
        ex, ey = x2c - x1, y2c - y1

        # Place into full-image IUV
        iuv[y1c:y2c, x1c:x2c, 0] = labels_np[sy:ey, sx:ex]
        iuv[y1c:y2c, x1c:x2c, 1] = u_np[sy:ey, sx:ex]
        iuv[y1c:y2c, x1c:x2c, 2] = v_np[sy:ey, sx:ex]

    body_pixels = (iuv[:, :, 0] > 0).sum()
    logger.info(f"Body pixels: {body_pixels}/{h*w} ({100*body_pixels/(h*w):.1f}%)")

    return iuv


def _predict_detectron2(image_path):
    """Run DensePose via full Detectron2 installation."""
    from detectron2.config import get_cfg
    from detectron2.engine import DefaultPredictor
    from densepose import add_densepose_config
    from densepose.structures import DensePoseChartPredictorOutput

    img = _load_image(image_path)
    h, w = img.shape[:2]

    # Config
    cfg = get_cfg()
    add_densepose_config(cfg)
    cfg.MODEL.WEIGHTS = _get_detectron2_weights()
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.5

    predictor = DefaultPredictor(cfg)
    outputs = predictor(img)

    # Extract IUV for the largest detected person
    instances = outputs["instances"]
    if len(instances) == 0:
        logger.warning("No person detected in image")
        return np.zeros((h, w, 3), dtype=np.uint8)

    # Get the largest detection by area
    areas = (instances.pred_boxes.tensor[:, 2] - instances.pred_boxes.tensor[:, 0]) * \
            (instances.pred_boxes.tensor[:, 3] - instances.pred_boxes.tensor[:, 1])
    largest_idx = areas.argmax().item()

    # Extract DensePose prediction
    dp = instances.pred_densepose
    if isinstance(dp, DensePoseChartPredictorOutput):
        # Fine segmentation (25 channels: bg + 24 parts)
        fine_segm = dp.fine_segm[largest_idx].cpu().numpy()
        u = dp.u[largest_idx].cpu().numpy()
        v = dp.v[largest_idx].cpu().numpy()

        # Bounding box for this detection
        box = instances.pred_boxes.tensor[largest_idx].cpu().numpy().astype(int)
        x1, y1, x2, y2 = box

        # Build full-image IUV
        iuv = np.zeros((h, w, 3), dtype=np.uint8)

        # Part segmentation
        part_idx = fine_segm.argmax(axis=0)  # (roi_h, roi_w)
        # Resize to bounding box size
        roi_h, roi_w = y2 - y1, x2 - x1
        part_resized = cv2.resize(part_idx.astype(np.float32),
                                   (roi_w, roi_h),
                                   interpolation=cv2.INTER_NEAREST).astype(np.uint8)

        # U, V maps
        u_map = np.zeros((roi_h, roi_w), dtype=np.uint8)
        v_map = np.zeros((roi_h, roi_w), dtype=np.uint8)

        for p in range(1, 25):
            mask_p = part_resized == p
            if not mask_p.any():
                continue
            u_ch = cv2.resize(u[p], (roi_w, roi_h))
            v_ch = cv2.resize(v[p], (roi_w, roi_h))
            u_map[mask_p] = (u_ch[mask_p] * 255).clip(0, 255).astype(np.uint8)
            v_map[mask_p] = (v_ch[mask_p] * 255).clip(0, 255).astype(np.uint8)

        # Place in full image
        iuv[y1:y2, x1:x2, 0] = part_resized
        iuv[y1:y2, x1:x2, 1] = u_map
        iuv[y1:y2, x1:x2, 2] = v_map

        return iuv

    logger.error("Unsupported DensePose prediction format")
    return None


def _predict_cloud(image_path):
    """Run DensePose via RunPod cloud GPU."""
    import base64
    from core.cloud_gpu import cloud_inference

    img = _load_image(image_path)

    # Encode image
    _, enc = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    img_b64 = base64.b64encode(enc.tobytes()).decode('utf-8')

    # Send to cloud
    result = cloud_inference(
        images_dict={'body_photo': img_b64},
        tasks=['densepose']
    )

    if result is None or 'densepose' not in result:
        logger.error("Cloud DensePose inference failed")
        return None

    # Decode IUV map from result
    iuv_b64 = result['densepose'].get('iuv_b64')
    if iuv_b64:
        iuv_bytes = base64.b64decode(iuv_b64)
        iuv_arr = np.frombuffer(iuv_bytes, dtype=np.uint8)
        iuv = cv2.imdecode(iuv_arr, cv2.IMREAD_COLOR)
        if iuv is not None:
            return iuv

    logger.error("Could not decode cloud DensePose result")
    return None


def _get_detectron2_weights():
    """Get or download DensePose model weights for Detectron2."""
    models_dir = _ensure_models_dir()
    weights_path = os.path.join(models_dir, 'model_final_162be9.pkl')

    if not os.path.exists(weights_path):
        url = ("https://dl.fbaipublicfiles.com/densepose/"
               "densepose_rcnn_R_50_FPN_s1x/165712039/model_final_162be9.pkl")
        logger.info(f"Downloading DensePose weights from {url}...")
        import urllib.request
        urllib.request.urlretrieve(url, weights_path)
        logger.info(f"Saved to {weights_path}")

    return weights_path
