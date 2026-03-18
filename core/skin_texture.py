"""
skin_texture.py — Process camera skin photos into tileable PBR texture maps.

Input: Raw camera photo of skin (any distance: 10cm, 30cm, 50cm, 1m)
Output: albedo.png, normal.png, roughness.png (all square, tileable)
"""
import cv2
import numpy as np
import os


def process_skin_photo(image_path: str, output_dir: str, size: int = 1024) -> dict:
    """
    Process a skin photo into tileable PBR maps.

    Args:
        image_path: Path to raw skin photo
        output_dir: Where to save processed textures
        size: Output texture size (square, power of 2)

    Returns:
        dict with paths: {albedo, normal, roughness}
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f'Could not read image: {image_path}')

    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Center-crop to square
    h, w = img.shape[:2]
    s = min(h, w)
    y0, x0 = (h - s) // 2, (w - s) // 2
    crop = img[y0:y0+s, x0:x0+s]

    # Step 2: Resize to target size
    crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_LANCZOS4)

    # Step 3: Flatten lighting gradient (high-pass filter)
    albedo = _flatten_lighting(crop, size)

    # Step 4: Make seamless (cross-blend edges)
    albedo = _make_seamless(albedo)

    # Step 5: Generate normal map from detail
    normal = _generate_normal_map(albedo, strength=1.5)

    # Step 6: Generate roughness map
    roughness = _generate_roughness_map(albedo)

    # Save
    paths = {}
    for name, tex in [('albedo', albedo), ('normal', normal), ('roughness', roughness)]:
        p = os.path.join(output_dir, f'skin_{name}.png')
        cv2.imwrite(p, tex)
        paths[name] = p

    return paths


def _flatten_lighting(img, size):
    """Remove directional lighting gradient using high-pass filter."""
    blur = cv2.GaussianBlur(img, (0, 0), size // 8)
    mean_color = img.mean(axis=(0, 1))
    flat = np.clip(img.astype(np.float32) - blur.astype(np.float32) + mean_color, 0, 255)
    return flat.astype(np.uint8)


def _make_seamless(img):
    """Cross-blend edges to create a seamless tileable texture."""
    h, w = img.shape[:2]
    result = img.copy().astype(np.float32)

    blend = max(h // 10, 16)

    for i in range(blend):
        alpha = i / blend  # 0 at edge → 1 at interior

        result[:, i] = img[:, i] * alpha + img[:, w - blend + i] * (1 - alpha)
        result[:, w - blend + i] = img[:, w - blend + i] * alpha + img[:, i] * (1 - alpha)

        result[i, :] = img[i, :] * alpha + img[h - blend + i, :] * (1 - alpha)
        result[h - blend + i, :] = img[h - blend + i, :] * alpha + img[i, :] * (1 - alpha)

    return np.clip(result, 0, 255).astype(np.uint8)


def _generate_normal_map(img, strength=1.5):
    """Generate a tangent-space normal map from skin photo detail."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

    fine = cv2.GaussianBlur(gray, (3, 3), 0.5)
    medium = cv2.GaussianBlur(gray, (7, 7), 1.5)
    detail = (fine * 0.7 + (gray - medium + 0.5) * 0.3)

    dx = cv2.Sobel(detail, cv2.CV_32F, 1, 0, ksize=3) * strength
    dy = cv2.Sobel(detail, cv2.CV_32F, 0, 1, ksize=3) * strength

    h, w = gray.shape
    normal = np.zeros((h, w, 3), dtype=np.float32)
    normal[:, :, 2] = 1.0
    normal[:, :, 0] = dx
    normal[:, :, 1] = -dy  # flip for OpenGL convention

    lengths = np.sqrt(np.sum(normal ** 2, axis=2, keepdims=True))
    lengths[lengths == 0] = 1
    normal = normal / lengths

    normal_img = ((normal + 1.0) * 0.5 * 255).astype(np.uint8)
    # R=X, G=Y, B=Z → swap R and B for correct OpenCV storage
    normal_img = cv2.cvtColor(normal_img, cv2.COLOR_RGB2BGR)

    return normal_img


def _generate_roughness_map(img):
    """Generate a roughness map from skin texture detail."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (15, 15), 5)
    detail = cv2.absdiff(gray, blur)

    # Base roughness ~155 (0.6), detail adds variation
    roughness = np.full_like(gray, 155, dtype=np.uint8)
    roughness = cv2.add(roughness, (detail * 0.5).astype(np.uint8))

    roughness = cv2.GaussianBlur(roughness, (5, 5), 1)

    return roughness
