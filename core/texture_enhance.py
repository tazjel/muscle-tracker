"""
texture_enhance.py — AI-powered texture atlas enhancement.

1. Real-ESRGAN 4x upscale (1024→4096 or 2048→8192, capped at 4096)
2. Seam inpainting via diffusion or OpenCV
3. Color correction + seamless blending
"""
import numpy as np
import cv2
import logging
import os

logger = logging.getLogger(__name__)

_esrgan_model = None


def _load_esrgan():
    global _esrgan_model
    if _esrgan_model is not None:
        return _esrgan_model

    try:
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet
        import torch

        device = 'cuda' if torch.cuda.is_available() else 'cpu'

        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                        num_block=23, num_grow_ch=32, scale=4)

        upsampler = RealESRGANer(
            scale=4,
            model_path=None,  # auto-download
            model=model,
            tile=512,
            tile_pad=10,
            pre_pad=0,
            half=True if device == 'cuda' else False,
            device=device,
        )

        _esrgan_model = upsampler
        logger.info(f"Real-ESRGAN loaded on {device}")
        return _esrgan_model

    except Exception as e:
        logger.warning(f"Real-ESRGAN unavailable: {e}")
        return None


def upscale_texture(texture, target_size=4096):
    """
    4x upscale texture atlas using Real-ESRGAN.

    Args:
        texture: (H, W, 3) uint8 BGR texture atlas
        target_size: max output dimension (default 4096)

    Returns:
        (H', W', 3) uint8 BGR upscaled texture, or original on failure
    """
    model = _load_esrgan()

    if model is None:
        # Fallback: Lanczos upscale
        logger.info("Real-ESRGAN unavailable — falling back to Lanczos 4x upscale")
        h, w = texture.shape[:2]
        scale = min(target_size / h, target_size / w, 4.0)
        new_h, new_w = int(h * scale), int(w * scale)
        return cv2.resize(texture, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    try:
        output, _ = model.enhance(texture, outscale=4)

        # Cap at target_size
        h, w = output.shape[:2]
        if max(h, w) > target_size:
            scale = target_size / max(h, w)
            new_h, new_w = int(h * scale), int(w * scale)
            output = cv2.resize(output, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        logger.info(f"Texture upscaled: {texture.shape[:2]} → {output.shape[:2]}")
        return output

    except Exception as e:
        logger.warning(f"Real-ESRGAN upscale failed: {e}")
        return texture


def inpaint_gaps(texture, coverage_mask, method='opencv'):
    """
    Fill uncovered regions in texture atlas.

    Args:
        texture: (H, W, 3) uint8 BGR
        coverage_mask: (H, W) float32 or uint8 — >0 where texture exists
        method: 'opencv' (fast) or 'diffusion' (quality, needs diffusers)

    Returns:
        (H, W, 3) uint8 BGR inpainted texture
    """
    if coverage_mask.dtype == np.float32:
        gap_mask = (coverage_mask < 0.01).astype(np.uint8) * 255
    else:
        gap_mask = (coverage_mask == 0).astype(np.uint8) * 255

    gap_ratio = gap_mask.sum() / (gap_mask.size * 255)
    if gap_ratio < 0.01:
        logger.info("Texture coverage >99%, skipping inpainting")
        return texture

    logger.info(f"Inpainting {gap_ratio*100:.1f}% of texture atlas ({method})")

    if method == 'diffusion':
        return _inpaint_diffusion(texture, gap_mask)
    else:
        return _inpaint_opencv(texture, gap_mask)


def _inpaint_opencv(texture, gap_mask):
    """Fast OpenCV inpainting (Telea algorithm)."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    gap_mask_dilated = cv2.dilate(gap_mask, kernel, iterations=1)
    return cv2.inpaint(texture, gap_mask_dilated, inpaintRadius=10,
                       flags=cv2.INPAINT_TELEA)


def _inpaint_diffusion(texture, gap_mask):
    """Diffusion-based inpainting for higher quality gap filling."""
    try:
        from diffusers import StableDiffusionInpaintPipeline
        import torch
        from PIL import Image

        device = 'cuda' if torch.cuda.is_available() else 'cpu'

        pipe = StableDiffusionInpaintPipeline.from_pretrained(
            "stabilityai/stable-diffusion-2-inpainting",
            torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
        ).to(device)

        rgb = cv2.cvtColor(texture, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb).resize((512, 512))
        pil_mask = Image.fromarray(gap_mask).resize((512, 512))

        result = pipe(
            prompt="human skin texture, natural, seamless",
            image=pil_image,
            mask_image=pil_mask,
            num_inference_steps=20,
            guidance_scale=7.5,
        ).images[0]

        result_np = np.array(result)
        result_bgr = cv2.cvtColor(result_np, cv2.COLOR_RGB2BGR)
        h, w = texture.shape[:2]
        result_bgr = cv2.resize(result_bgr, (w, h), interpolation=cv2.INTER_LANCZOS4)

        mask_3ch = np.stack([gap_mask / 255.0] * 3, axis=-1)
        blended = (texture * (1 - mask_3ch) + result_bgr * mask_3ch).astype(np.uint8)
        return blended

    except Exception as e:
        logger.warning(f"Diffusion inpainting failed, falling back to OpenCV: {e}")
        return _inpaint_opencv(texture, gap_mask)


def enhance_texture_atlas(texture, coverage_mask=None, upscale=True, inpaint=True, target_size=4096):
    """
    Full texture enhancement pipeline.

    Args:
        texture: (H, W, 3) uint8 BGR
        coverage_mask: (H, W) float32 coverage weights (from project_texture)
        upscale: bool — apply Real-ESRGAN 4x upscale
        inpaint: bool — fill gaps
        target_size: max output size

    Returns:
        (H', W', 3) uint8 BGR enhanced texture
    """
    result = texture.copy()

    # Step 1: Inpaint gaps BEFORE upscaling (faster at low res)
    if inpaint and coverage_mask is not None:
        result = inpaint_gaps(result, coverage_mask, method='opencv')

    # Step 2: Upscale
    if upscale:
        result = upscale_texture(result, target_size=target_size)

    # Step 3: Mild unsharp mask sharpening
    blurred = cv2.GaussianBlur(result, (0, 0), 2.0)
    result = cv2.addWeighted(result, 1.3, blurred, -0.3, 0)
    result = np.clip(result, 0, 255).astype(np.uint8)

    return result
