"""
skin_patch.py — Per-region skin texture pipeline.

Converts close-up skin photos into seamless tileable textures using
Image Quilting (Efros & Freeman 2001), then composites them into a
full-body UV atlas with Laplacian pyramid blending at region boundaries.

Usage:
    from core.skin_patch import make_tileable, composite_skin_atlas

    patch = make_tileable(cv2.imread("arm_closeup.jpg"), out_size=512)
    atlas = composite_skin_atlas(uvs, part_ids, faces,
                                 {"forearm": patch, "chest": chest_patch})
"""
import numpy as np
import cv2
import logging

logger = logging.getLogger(__name__)

# ── Region mapping: capture region name → SMPL part IDs ──────────────
# Matches _SMPL_PART_MAP in texture_factory.py
CAPTURE_REGIONS = {
    'forearm':    [18, 19],         # L/R elbow (forearm)
    'abdomen':    [0, 3],           # pelvis, spine1
    'chest':      [6, 9],           # spine2, spine3
    'thigh':      [1, 2],           # L/R upper leg
    'calf':       [4, 5],           # L/R knee (lower leg)
    'upper_arm':  [16, 17],         # L/R shoulder (upper arm)
    'face':       [15],             # head
    'neck':       [12],             # neck
    'shoulders':  [13, 14],         # L/R collar
    'hands':      [20, 21, 22, 23], # wrists + hands
    'feet':       [7, 8, 10, 11],   # ankles + feet
    'back':       [6, 9, 3],        # spine (shared with chest/abdomen)
}

# MPFB2 muscle group mapping (same region keys, muscle group name lists)
MPFB2_CAPTURE_REGIONS = {
    'forearm':    ['forearms_l', 'forearms_r'],
    'abdomen':    ['abs', 'obliques'],
    'chest':      ['pectorals'],
    'thigh':      ['quads_l', 'quads_r'],
    'calf':       ['calves_l', 'calves_r'],
    'upper_arm':  ['biceps_l', 'biceps_r'],
    'shoulders':  ['deltoids_l', 'deltoids_r'],
    'back':       ['traps'],
    'neck':       [],
    'hands':      [],
    'feet':       [],
    'face':       [],
}

# Minimum 5 regions for 90%+ perceptual coverage (Gemini G-T3)
MINIMUM_REGIONS = ['forearm', 'abdomen', 'chest', 'thigh', 'calf']


# ═══════════════════════════════════════════════════════════════════════
#  G-T1: Image Quilting — tileable texture from close-up photo
# ═══════════════════════════════════════════════════════════════════════

def make_tileable(sample_bgr, out_size=512, patch_size=64, overlap=16):
    """
    Convert a close-up skin photo into a seamlessly tileable texture
    using Image Quilting (Efros & Freeman 2001).

    Args:
        sample_bgr: BGR image of skin close-up (any size, will be used as source)
        out_size: output texture size (square)
        patch_size: quilting patch size in pixels
        overlap: overlap region between patches

    Returns:
        (out_size, out_size, 3) uint8 BGR tileable texture
    """
    if sample_bgr is None:
        return None

    sample = sample_bgr.copy()
    h, w = sample.shape[:2]

    # Crop to square center region for uniform sampling
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    sample = sample[y0:y0+side, x0:x0+side]

    # Resize sample if too small for patch extraction
    if side < patch_size * 3:
        sample = cv2.resize(sample, (patch_size * 4, patch_size * 4))

    step = patch_size - overlap
    n_patches = (out_size - overlap) // step + 1
    canvas_size = n_patches * step + overlap
    canvas = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)

    sh, sw = sample.shape[:2]

    for row in range(n_patches):
        for col in range(n_patches):
            y = row * step
            x = col * step

            if row == 0 and col == 0:
                # First patch: random
                sy = np.random.randint(0, sh - patch_size)
                sx = np.random.randint(0, sw - patch_size)
                canvas[y:y+patch_size, x:x+patch_size] = \
                    sample[sy:sy+patch_size, sx:sx+patch_size]
                continue

            # Find best matching patch from sample
            best_patch, best_mask = _find_best_patch(
                canvas, sample, y, x, patch_size, overlap,
                row > 0, col > 0
            )

            # Blend using minimum error boundary cut
            _paste_with_cut(canvas, best_patch, best_mask, y, x, patch_size)

    # Crop to exact output size
    canvas = canvas[:out_size, :out_size]

    # Make edges tileable: blend left↔right and top↔bottom edges
    canvas = _make_edges_seamless(canvas, overlap)

    return canvas


def _find_best_patch(canvas, sample, y, x, patch_size, overlap,
                     has_top, has_left, n_candidates=None):
    """
    Find best matching patch using vectorized Global SSD via cv2.matchTemplate.
    Finds the mathematical global optimum across the entire sample image.
    """
    sh, sw = sample.shape[:2]
    
    # Extract overlap reference regions from canvas
    left_ref = canvas[y:y+patch_size, x:x+overlap] if has_left else None
    top_ref = canvas[y:y+overlap, x:x+patch_size] if has_top else None
    
    # Compute total SSD map across the sample image for each rotation
    best_ssd = float('inf')
    best_patch = None
    
    # We test 4 rotations to maximize texture variety
    for k in (0, 1, 2, 3):
        rot_sample = np.rot90(sample, k)
        rh, rw = rot_sample.shape[:2]
        if rh < patch_size or rw < patch_size: continue
        
        # Total SSD = SSD(left_overlap) + SSD(top_overlap)
        total_ssd = np.zeros((rh - patch_size + 1, rw - patch_size + 1), dtype=np.float32)
        
        if has_left:
            # Match only the left vertical strip of the patch
            res_left = cv2.matchTemplate(rot_sample, left_ref, cv2.TM_SQDIFF)
            # res_left size is (rh - patch_size + 1, rw - overlap + 1)
            # Align res_left to the start position of a full patch_size window
            total_ssd += res_left[:, :rw - patch_size + 1]
            
        if has_top:
            # Match only the top horizontal strip of the patch
            res_top = cv2.matchTemplate(rot_sample, top_ref, cv2.TM_SQDIFF)
            # res_top size is (rh - overlap + 1, rw - patch_size + 1)
            total_ssd += res_top[:rh - patch_size + 1, :]
            
        min_val, _, min_loc, _ = cv2.minMaxLoc(total_ssd)
        
        if min_val < best_ssd:
            best_ssd = min_val
            sx, sy = min_loc
            best_patch = rot_sample[sy:sy+patch_size, sx:sx+patch_size].copy()

    if best_patch is None:
        # Fallback to random if something went wrong
        sy = np.random.randint(0, sh - patch_size)
        sx = np.random.randint(0, sw - patch_size)
        best_patch = sample[sy:sy+patch_size, sx:sx+patch_size].copy()

    # Compute minimum error boundary cut mask

    # Compute minimum error boundary cut mask
    mask = np.ones((patch_size, patch_size), dtype=np.float32)

    if has_left:
        left_err = np.sum(
            (canvas[y:y+patch_size, x:x+overlap].astype(np.float32) -
             best_patch[:, :overlap].astype(np.float32)) ** 2, axis=2
        )
        cut = _min_cut_vertical(left_err)
        for r in range(patch_size):
            mask[r, :cut[r]] = 0.0

    if has_top:
        top_err = np.sum(
            (canvas[y:y+overlap, x:x+patch_size].astype(np.float32) -
             best_patch[:overlap, :].astype(np.float32)) ** 2, axis=2
        )
        cut = _min_cut_horizontal(top_err)
        for c in range(patch_size):
            mask[:cut[c], c] = 0.0

    return best_patch, mask


def _min_cut_vertical(error_2d):
    """Vectorized DP min-cut through a vertical overlap region."""
    h, w = error_2d.shape
    dp = error_2d.copy().astype(np.float32)
    bt = np.zeros_like(dp, dtype=np.int32)

    # Padding to handle boundaries gracefully in vectorized min()
    INF = 1e10

    for r in range(1, h):
        prev = dp[r-1]
        # Shifted versions for left, center, right neighbors
        left = np.hstack(([INF], prev[:-1]))
        center = prev
        right = np.hstack((prev[1:], [INF]))
        
        # Stack and find min over the 3-neighbor window
        stacked = np.stack([left, center, right], axis=0)
        dp[r] += np.min(stacked, axis=0)
        
        # Relative offset: 0=-1 (left), 1=0 (center), 2=+1 (right)
        offsets = np.argmin(stacked, axis=0) - 1
        bt[r] = np.arange(w, dtype=np.int32) + offsets

    # Backtrace remains sequential but is O(H) instead of O(H*W)
    cut = np.zeros(h, dtype=np.int32)
    cut[-1] = np.argmin(dp[-1])
    for r in range(h - 2, -1, -1):
        cut[r] = bt[r + 1, cut[r + 1]]

    return cut


def _min_cut_horizontal(error_2d):
    """Min-cut through a horizontal overlap region."""
    return _min_cut_vertical(error_2d.T)


def _paste_with_cut(canvas, patch, mask, y, x, patch_size):
    """Paste patch onto canvas using the cut mask."""
    mask3 = mask[:, :, np.newaxis]
    region = canvas[y:y+patch_size, x:x+patch_size].astype(np.float32)
    blended = region * (1 - mask3) + patch.astype(np.float32) * mask3
    canvas[y:y+patch_size, x:x+patch_size] = blended.astype(np.uint8)


def _make_edges_seamless(texture, blend_width=32):
    """Vectorized blending of left↔right and top↔bottom edges for seamless tiling."""
    h, w = texture.shape[:2]
    result = texture.copy().astype(np.float32)
    alpha = np.linspace(0, 1, blend_width).reshape(1, -1, 1)

    # Horizontal wrap (left ↔ right)
    left_strip = result[:, :blend_width]
    right_strip = result[:, w - blend_width:]
    result[:, :blend_width] = left_strip * alpha + right_strip * (1 - alpha)
    result[:, w - blend_width:] = right_strip * alpha + left_strip * (1 - alpha)

    # Vertical wrap (top ↔ bottom)
    alpha_v = alpha.transpose(1, 0, 2)
    top_strip = result[:blend_width, :]
    bot_strip = result[h - blend_width:, :]
    result[:blend_width, :] = top_strip * alpha_v + bot_strip * (1 - alpha_v)
    result[h - blend_width:, :] = bot_row_strip = bot_strip * alpha_v + top_strip * (1 - alpha_v)

    return result.astype(np.uint8)


# ═══════════════════════════════════════════════════════════════════════
#  G-T2: Laplacian Pyramid Blending for region boundaries
# ═══════════════════════════════════════════════════════════════════════

def _build_laplacian_pyramid(img, levels=5):
    """Build a Laplacian pyramid from an image."""
    gaussian = [img.astype(np.float32)]
    for _ in range(levels):
        down = cv2.pyrDown(gaussian[-1])
        gaussian.append(down)

    laplacian = []
    for i in range(levels):
        up = cv2.pyrUp(gaussian[i + 1],
                       dstsize=(gaussian[i].shape[1], gaussian[i].shape[0]))
        lap = gaussian[i] - up
        laplacian.append(lap)
    laplacian.append(gaussian[-1])  # lowest frequency residual
    return laplacian


def _reconstruct_from_pyramid(pyramid):
    """Reconstruct image from Laplacian pyramid."""
    img = pyramid[-1]
    for i in range(len(pyramid) - 2, -1, -1):
        up = cv2.pyrUp(img, dstsize=(pyramid[i].shape[1], pyramid[i].shape[0]))
        img = up + pyramid[i]
    return img


def _blend_laplacian(img_a, img_b, mask, levels=5):
    """
    Blend two images using Laplacian pyramid blending.
    mask: float32 [0,1] — 0=use img_a, 1=use img_b
    """
    if img_a.shape != img_b.shape:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))

    mask3 = mask if mask.ndim == 3 else mask[:, :, np.newaxis]
    if mask3.shape[2] == 1 and img_a.ndim == 3:
        mask3 = np.repeat(mask3, 3, axis=2)

    pyr_a = _build_laplacian_pyramid(img_a, levels)
    pyr_b = _build_laplacian_pyramid(img_b, levels)

    # Build Gaussian pyramid of the mask
    mask_pyr = [mask3]
    for _ in range(levels):
        mask_pyr.append(cv2.pyrDown(mask_pyr[-1]))

    # Blend each level
    blended_pyr = []
    for la, lb, m in zip(pyr_a, pyr_b, mask_pyr):
        if m.shape[:2] != la.shape[:2]:
            m = cv2.resize(m, (la.shape[1], la.shape[0]))
        if m.ndim == 2 and la.ndim == 3:
            m = m[:, :, np.newaxis]
        blended_pyr.append(la * (1 - m) + lb * m)

    return np.clip(_reconstruct_from_pyramid(blended_pyr), 0, 255).astype(np.uint8)


# ═══════════════════════════════════════════════════════════════════════
#  S-N3: Skin Tone Extraction (LAB-space + k-means)
# ═══════════════════════════════════════════════════════════════════════

def extract_skin_tone(img_bgr, k=3):
    """
    Extract dominant skin tone from a close-up photo using LAB color space.

    Segments skin pixels via LAB a/b channel thresholds, then uses k-means
    to find the dominant cluster. Handles dark/light skin, shadows, and hair.

    Args:
        img_bgr: BGR image (close-up skin photo or face photo)
        k: number of k-means clusters (3 works well for skin+shadow+highlight)

    Returns:
        (3,) uint8 BGR skin tone color, or (160, 140, 120) if extraction fails
    """
    FALLBACK = np.array([160, 140, 120], dtype=np.uint8)
    if img_bgr is None or img_bgr.size == 0:
        return FALLBACK

    # Resize for speed (k-means on full res is slow)
    h, w = img_bgr.shape[:2]
    scale = min(1.0, 256.0 / max(h, w))
    if scale < 1.0:
        img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))

    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

    # Skin detection in LAB: a channel ~125-160, b channel ~115-155
    # Wide range to handle dark to light skin under varying illumination
    a_ch = lab[:, :, 1].astype(np.float32)
    b_ch = lab[:, :, 2].astype(np.float32)
    l_ch = lab[:, :, 0].astype(np.float32)

    skin_mask = (
        (a_ch >= 115) & (a_ch <= 165) &
        (b_ch >= 110) & (b_ch <= 160) &
        (l_ch >= 30) & (l_ch <= 230)  # exclude very dark shadows & blown highlights
    )

    # Morphological cleanup: remove hair strands, fill gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    skin_mask_u8 = skin_mask.astype(np.uint8) * 255
    skin_mask_u8 = cv2.morphologyEx(skin_mask_u8, cv2.MORPH_OPEN, kernel)
    skin_mask_u8 = cv2.morphologyEx(skin_mask_u8, cv2.MORPH_CLOSE, kernel)

    skin_pixels = img_bgr[skin_mask_u8 > 0]
    if len(skin_pixels) < 50:
        # Not enough skin pixels — fall back to center crop median
        ch, cw = img_bgr.shape[0] // 4, img_bgr.shape[1] // 4
        center = img_bgr[ch:ch*3, cw:cw*3]
        if center.size > 0:
            return np.median(center.reshape(-1, 3), axis=0).astype(np.uint8)
        return FALLBACK

    # K-means clustering on skin pixels (LAB space for perceptual uniformity)
    skin_lab = cv2.cvtColor(skin_pixels.reshape(1, -1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(skin_lab, min(k, len(skin_lab)), None,
                                     criteria, 3, cv2.KMEANS_PP_CENTERS)

    # Pick the cluster with the most pixels (dominant skin tone)
    counts = np.bincount(labels.flatten(), minlength=len(centers))
    dominant_idx = np.argmax(counts)
    dominant_lab = centers[dominant_idx].reshape(1, 1, 3).astype(np.uint8)
    dominant_bgr = cv2.cvtColor(dominant_lab, cv2.COLOR_LAB2BGR).flatten()

    logger.info("Extracted skin tone: BGR(%d,%d,%d) from %d skin pixels, %d clusters",
                dominant_bgr[0], dominant_bgr[1], dominant_bgr[2],
                len(skin_pixels), len(centers))
    return dominant_bgr


# ═══════════════════════════════════════════════════════════════════════
#  S-N1: PBR Maps from Skin Albedo (Scharr normal + anatomical roughness)
# ═══════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════
#  Region Compositor: tileable patches → full UV atlas
# ═══════════════════════════════════════════════════════════════════════

def composite_skin_atlas(uvs, part_ids, faces, region_textures,
                         atlas_size=2048, default_tone=None, seg_dict=None):
    """
    Composite per-region tileable skin textures into a full UV atlas.

    Args:
        uvs: (N, 2) float32 — per-vertex UV coordinates
        part_ids: (N,) int — SMPL part ID per vertex (0-23)
        faces: (F, 3) int — triangle indices
        region_textures: dict {region_name: (H,W,3) uint8 BGR tileable texture}
        atlas_size: output atlas size
        default_tone: BGR skin tone for uncovered regions (auto-extracted if None)
        seg_dict: optional dict {group_name: [vertex indices]} for MPFB2 mesh.
                  When provided, uses MPFB2_CAPTURE_REGIONS instead of SMPL part IDs.

    Returns:
        (atlas_size, atlas_size, 3) uint8 BGR — composited UV atlas
    """
    # Auto-extract skin tone from the first available region texture
    if default_tone is None and region_textures:
        first_tex = next(iter(region_textures.values()))
        default_tone = extract_skin_tone(first_tex)
        logger.info("Auto skin tone: BGR(%d,%d,%d)", *default_tone)
    elif default_tone is None:
        default_tone = (160, 140, 120)

    # Start with default skin tone
    atlas = np.full((atlas_size, atlas_size, 3), default_tone, dtype=np.uint8)

    # Build per-region UV masks and fill with tileable textures
    region_layers = {}  # region_name → (atlas_size, atlas_size, 3) filled layer
    region_masks = {}   # region_name → (atlas_size, atlas_size) float32 mask

    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

    for region_name, tile_img in region_textures.items():
        # Create vertex mask for this region
        vert_mask = np.zeros(len(uvs), dtype=bool)

        if seg_dict is not None and region_name in MPFB2_CAPTURE_REGIONS:
            # MPFB2 path: use muscle group vertex indices directly
            for grp in MPFB2_CAPTURE_REGIONS[region_name]:
                if grp in seg_dict:
                    idx = np.array(seg_dict[grp], dtype=np.int32)
                    vert_mask[idx] = True
        elif region_name in CAPTURE_REGIONS:
            # SMPL path: use part ID integer matching
            for pid in CAPTURE_REGIONS[region_name]:
                vert_mask |= (part_ids == pid)
        else:
            logger.warning("Unknown region: %s", region_name)
            continue

        # Rasterize region mask into UV space using batch triangle fill
        region_mask = np.zeros((atlas_size, atlas_size), dtype=np.float32)
        
        # Identify faces that have at least one vertex in this region
        face_in_region = vert_mask[faces].any(axis=1)
        relevant_faces = faces[face_in_region]
        
        # Calculate weight per face (1/3, 2/3, or 1.0)
        face_weights = vert_mask[relevant_faces].sum(axis=1) / 3.0
        
        # Skip wrap-around triangles (UV coordinates that cross the 0/1 seam)
        # These are rare but can cause long horizontal streaks across the atlas
        f_u = u_px[relevant_faces]
        f_v = v_px[relevant_faces]
        is_wrap = (np.ptp(f_u, axis=1) > atlas_size // 2) | (np.ptp(f_v, axis=1) > atlas_size // 2)
        
        # Batch fill by weight group
        for weight_val in [1/3.0, 2/3.0, 1.0]:
            mask_w = (face_weights == weight_val) & (~is_wrap)
            if not mask_w.any():
                continue
                
            # Prepare points for cv2.fillPoly: (N, 3, 2)
            pts_w = np.stack([f_u[mask_w], f_v[mask_w]], axis=-1)
            cv2.fillPoly(region_mask, pts_w, weight_val)

        # Tile the texture across the entire atlas
        th, tw = tile_img.shape[:2]
        tiled = np.tile(tile_img, (atlas_size // th + 1, atlas_size // tw + 1, 1))
        tiled = tiled[:atlas_size, :atlas_size]

        region_layers[region_name] = tiled
        region_masks[region_name] = region_mask

    # Composite regions onto atlas using Laplacian blending at boundaries
    if not region_layers:
        return atlas

    # Sort by area (largest regions first as base)
    sorted_regions = sorted(region_masks.keys(),
                            key=lambda r: region_masks[r].sum(), reverse=True)

    # Start compositing
    result = atlas.copy()
    for region_name in sorted_regions:
        layer = region_layers[region_name]
        mask = region_masks[region_name]

        # Feather the mask edges for smooth blending (32px at 2048)
        feather = max(8, atlas_size // 64)
        mask_smooth = cv2.GaussianBlur(mask, (feather * 2 + 1, feather * 2 + 1), 0)
        mask_smooth = np.clip(mask_smooth, 0, 1)

        # Apply Laplacian pyramid blending for high-quality transitions
        if mask_smooth.max() > 0.01:
            result = _blend_laplacian(result, layer, mask_smooth, levels=4)

    return result
