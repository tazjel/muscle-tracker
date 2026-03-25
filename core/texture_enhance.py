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
    4x upscale texture atlas: try cloud GPU -> local GPU -> Lanczos fallback.

    Args:
        texture: (H, W, 3) uint8 BGR texture atlas
        target_size: max output dimension (default 4096)

    Returns:
        (H', W', 3) uint8 BGR upscaled texture, or original on failure
    """
    # Option 1: Cloud GPU (RunPod Real-ESRGAN)
    try:
        from core.cloud_gpu import is_configured, cloud_texture_upscale
        if is_configured():
            result = cloud_texture_upscale(texture, target_size=target_size)
            if result is not None:
                logger.info("Texture upscaled via cloud GPU: %s -> %s",
                           texture.shape[:2], result.shape[:2])
                return result
            logger.warning("Cloud upscale returned None, trying local...")
    except Exception as e:
        logger.warning("Cloud upscale unavailable: %s", e)

    # Option 2: Local Real-ESRGAN (existing code)
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


def depth_to_normal_map(depth_map, atlas_size=1024):
    """Convert depth map to tangent-space normal map using Sobel gradients."""
    h, w = depth_map.shape[:2]
    if len(depth_map.shape) == 3:
        depth_map = cv2.cvtColor(depth_map, cv2.COLOR_BGR2GRAY)
    depth_f = depth_map.astype(np.float32) / 255.0

    dx = cv2.Sobel(depth_f, cv2.CV_32F, 1, 0, ksize=3)
    dy = cv2.Sobel(depth_f, cv2.CV_32F, 0, 1, ksize=3)

    normals = np.dstack([-dx, -dy, np.ones_like(dx)])
    norm = np.linalg.norm(normals, axis=2, keepdims=True)
    normals = normals / (norm + 1e-8)

    # Encode tangent-space: [-1,1] -> [0,255]
    normal_img = ((normals * 0.5 + 0.5) * 255).astype(np.uint8)

    if normal_img.shape[:2] != (atlas_size, atlas_size):
        normal_img = cv2.resize(normal_img, (atlas_size, atlas_size),
                                interpolation=cv2.INTER_LINEAR)
    return normal_img


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



def generate_skin_normal_map(albedo_bgr, strength=10.0):
    """
    Generate a tangent-space normal map from skin albedo using frequency-separated
    Scharr gradients. Isolates pore-level detail from baked-in lighting.

    Args:
        albedo_bgr: (H, W, 3) uint8 BGR skin atlas
        strength: normal map intensity (higher = more pronounced pores)

    Returns:
        (H, W, 3) uint8 RGB tangent-space normal map
    """
    gray = cv2.cvtColor(albedo_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

    # High-pass: isolate pore micro-detail from low-freq lighting
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    high_freq = gray - blurred

    # Scharr gradients (more rotationally invariant than Sobel)
    dx = cv2.Scharr(high_freq, cv2.CV_32F, 1, 0)
    dy = cv2.Scharr(high_freq, cv2.CV_32F, 0, 1)
    z = np.ones_like(dx) / strength

    norm = np.sqrt(dx ** 2 + dy ** 2 + z ** 2)
    norm[norm == 0] = 1.0

    # Tangent-space normal: RGB = (X+1)/2, (Y+1)/2, Z mapped to [0,255]
    # OpenGL convention: R=X, G=Y, B=Z
    nx = (dx / norm + 1.0) * 127.5
    ny = (dy / norm + 1.0) * 127.5
    nz = (z / norm + 1.0) * 127.5

    normal_rgb = np.stack([nx, ny, nz], axis=-1).astype(np.uint8)
    return normal_rgb

def delight_texture(texture: np.ndarray, coverage_mask: np.ndarray = None,
                    sigma_ratio: float = 0.15) -> np.ndarray:
    """
    Remove low-frequency lighting from projected photo texture.
    """
    import cv2
    import numpy as np

    h, w = texture.shape[:2]
    sigma = int(max(h, w) * sigma_ratio) | 1  # Ensure odd

    # Work in float LAB space to preserve color
    lab = cv2.cvtColor(texture, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]

    # Log-space high-pass on luminance only (preserve chrominance)
    L_log = np.log1p(L)
    L_blur = cv2.GaussianBlur(L_log, (sigma, sigma), 0)
    L_highpass = L_log - L_blur

    # Rescale to target mean luminance (128 = middle grey in LAB)
    L_new = np.expm1(L_highpass)
    L_new = (L_new - L_new.min()) / (L_new.max() - L_new.min() + 1e-6) * 200 + 28

    # Blend: 70% delighted + 30% original (preserve some natural variation)
    lab[:, :, 0] = L_new * 0.7 + L * 0.3

    # Slight desaturation of extreme chrominance (removes colored light tints)
    ab_center = 128.0
    lab[:, :, 1] = (lab[:, :, 1] - ab_center) * 0.85 + ab_center
    lab[:, :, 2] = (lab[:, :, 2] - ab_center) * 0.85 + ab_center

    result = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)

    # Only apply to covered regions
    if coverage_mask is not None:
        mask = (coverage_mask > 0).astype(np.float32)
        if len(mask.shape) == 2:
            mask = mask[:, :, None]
        result = (result * mask + texture.astype(np.float32) * (1 - mask)).astype(np.uint8)

    return result

def enhance_texture_atlas(texture, coverage_mask=None, upscale=True, inpaint=True, 
                           delight=True, target_size=4096):
    """
    Full texture enhancement pipeline (Pro Edition).
    """
    result = texture.copy()

    # Step 0: Delight (Remove baked lighting gradients)
    if delight:
        try:
            result = delight_texture(result, coverage_mask=coverage_mask)
        except Exception:
            pass

    # Step 1: Inpaint gaps BEFORE upscaling
    if inpaint and coverage_mask is not None:
        result = inpaint_gaps(result, coverage_mask, method='opencv')

    # Step 2: Upscale
    if upscale:
        result = upscale_texture(result, target_size=target_size)

    # Step 3: High-Frequency Sharpening (Micro-Detail)
    blurred = cv2.GaussianBlur(result, (0, 0), 2.0)
    result = cv2.addWeighted(result, 1.4, blurred, -0.4, 0) # slightly stronger
    result = np.clip(result, 0, 255).astype(np.uint8)

    return result
