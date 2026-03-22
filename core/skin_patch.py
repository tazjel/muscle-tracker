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
                     has_top, has_left, n_candidates=50):
    """Find the best matching patch from sample using SSD in overlap region."""
    sh, sw = sample.shape[:2]
    best_ssd = float('inf')
    best_patch = None

    for _ in range(n_candidates):
        sy = np.random.randint(0, sh - patch_size)
        sx = np.random.randint(0, sw - patch_size)
        candidate = sample[sy:sy+patch_size, sx:sx+patch_size]

        ssd = 0.0
        # Left overlap
        if has_left:
            left_existing = canvas[y:y+patch_size, x:x+overlap].astype(np.float32)
            left_candidate = candidate[:, :overlap].astype(np.float32)
            ssd += np.sum((left_existing - left_candidate) ** 2)

        # Top overlap
        if has_top:
            top_existing = canvas[y:y+overlap, x:x+patch_size].astype(np.float32)
            top_candidate = candidate[:overlap, :].astype(np.float32)
            ssd += np.sum((top_existing - top_candidate) ** 2)

        if ssd < best_ssd:
            best_ssd = ssd
            best_patch = candidate.copy()

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
    """Dynamic programming min-cut through a vertical overlap region."""
    h, w = error_2d.shape
    dp = error_2d.copy()
    bt = np.zeros_like(dp, dtype=np.int32)

    for r in range(1, h):
        for c in range(w):
            candidates = [dp[r-1, c]]
            offsets = [0]
            if c > 0:
                candidates.append(dp[r-1, c-1])
                offsets.append(-1)
            if c < w - 1:
                candidates.append(dp[r-1, c+1])
                offsets.append(1)
            best = np.argmin(candidates)
            dp[r, c] += candidates[best]
            bt[r, c] = c + offsets[best]

    # Backtrace
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
    """Blend left↔right and top↔bottom edges for seamless tiling."""
    h, w = texture.shape[:2]
    result = texture.copy().astype(np.float32)

    # Horizontal wrap (left ↔ right)
    for i in range(blend_width):
        alpha = i / blend_width
        left_col = result[:, i].copy()
        right_col = result[:, w - blend_width + i].copy()
        result[:, i] = left_col * alpha + right_col * (1 - alpha)
        result[:, w - blend_width + i] = right_col * alpha + left_col * (1 - alpha)

    # Vertical wrap (top ↔ bottom)
    for i in range(blend_width):
        alpha = i / blend_width
        top_row = result[i, :].copy()
        bot_row = result[h - blend_width + i, :].copy()
        result[i, :] = top_row * alpha + bot_row * (1 - alpha)
        result[h - blend_width + i, :] = bot_row * alpha + top_row * (1 - alpha)

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
#  Region Compositor: tileable patches → full UV atlas
# ═══════════════════════════════════════════════════════════════════════

def composite_skin_atlas(uvs, part_ids, faces, region_textures,
                         atlas_size=2048, default_tone=(160, 140, 120)):
    """
    Composite per-region tileable skin textures into a full UV atlas.

    Args:
        uvs: (N, 2) float32 — per-vertex UV coordinates
        part_ids: (N,) int — SMPL part ID per vertex (0-23)
        faces: (F, 3) int — triangle indices
        region_textures: dict {region_name: (H,W,3) uint8 BGR tileable texture}
        atlas_size: output atlas size
        default_tone: BGR skin tone for uncovered regions

    Returns:
        (atlas_size, atlas_size, 3) uint8 BGR — composited UV atlas
    """
    # Start with default skin tone
    atlas = np.full((atlas_size, atlas_size, 3), default_tone, dtype=np.uint8)

    # Build per-region UV masks and fill with tileable textures
    region_layers = {}  # region_name → (atlas_size, atlas_size, 3) filled layer
    region_masks = {}   # region_name → (atlas_size, atlas_size) float32 mask

    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

    for region_name, tile_img in region_textures.items():
        if region_name not in CAPTURE_REGIONS:
            logger.warning("Unknown region: %s", region_name)
            continue

        smpl_parts = CAPTURE_REGIONS[region_name]

        # Create vertex mask for this region
        vert_mask = np.zeros(len(uvs), dtype=bool)
        for pid in smpl_parts:
            vert_mask |= (part_ids == pid)

        # Rasterize region mask into UV space using triangle fill
        region_mask = np.zeros((atlas_size, atlas_size), dtype=np.float32)
        for fi in range(len(faces)):
            f = faces[fi]
            # At least one vertex must be in this region
            if not (vert_mask[f[0]] or vert_mask[f[1]] or vert_mask[f[2]]):
                continue
            # Weight by how many vertices are in-region
            w = (float(vert_mask[f[0]]) + float(vert_mask[f[1]]) +
                 float(vert_mask[f[2]])) / 3.0

            pts = np.array([[u_px[f[0]], v_px[f[0]]],
                            [u_px[f[1]], v_px[f[1]]],
                            [u_px[f[2]], v_px[f[2]]]], dtype=np.int32)
            # Skip wrap-around triangles
            if (pts[:, 0].max() - pts[:, 0].min() > atlas_size // 2 or
                    pts[:, 1].max() - pts[:, 1].min() > atlas_size // 2):
                continue
            cv2.fillConvexPoly(region_mask, pts.reshape(-1, 1, 2), w)

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
