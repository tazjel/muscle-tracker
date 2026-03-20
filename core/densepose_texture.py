"""
densepose_texture.py — Extract body-surface UV texture from photos using DensePose.

DensePose maps every human pixel in a photo to (I, U, V) coordinates:
  I = body part index (1-24, e.g. 1=torso, 2=right_hand, ...)
  U, V = position within that body part's surface patch [0, 1]

Pipeline:
  1. Run DensePose on photo → get IUV map (H, W, 3)
  2. For each skin pixel: read photo color, write to atlas at (I, U, V) position
  3. Merge front + back + side atlases with weighted blending
  4. Convert DensePose atlas (24 body parts) → SMPL UV texture
  5. Inpaint missing regions

This module handles steps 2-5. Step 1 (DensePose inference) is in densepose_infer.py.
"""
import cv2
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

# DensePose body part layout in the atlas texture.
# The atlas is a 4x6 grid of body parts, each part gets its own UV region.
# Part indices 1-24 map to specific grid cells.
# Reference: https://github.com/facebookresearch/DensePose/blob/main/DensePoseData/demo_data/texture_atlas_200.png

# Atlas grid: 4 columns × 6 rows = 24 parts
# Each cell is (atlas_size/4) × (atlas_size/6) pixels
ATLAS_COLS = 4
ATLAS_ROWS = 6
NUM_PARTS = 24

# DensePose body part names (1-indexed)
PART_NAMES = {
    1: 'torso_front',     2: 'torso_back',
    3: 'right_hand',      4: 'left_hand',
    5: 'left_foot',       6: 'right_foot',
    7: 'right_upper_leg_front',  8: 'left_upper_leg_front',
    9: 'right_upper_leg_back',  10: 'left_upper_leg_back',
    11: 'right_lower_leg_front', 12: 'left_lower_leg_front',
    13: 'right_lower_leg_back',  14: 'left_lower_leg_back',
    15: 'left_upper_arm_front',  16: 'right_upper_arm_front',
    17: 'left_upper_arm_back',   18: 'right_upper_arm_back',
    19: 'left_lower_arm_front',  20: 'right_lower_arm_front',
    21: 'left_lower_arm_back',   22: 'right_lower_arm_back',
    23: 'right_face',            24: 'left_face',
}

# Grid position for each part (col, row) — 0-indexed
# This maps DensePose part index → atlas grid cell
PART_GRID = {
    1:  (0, 0),  2:  (1, 0),  3:  (2, 0),  4:  (3, 0),
    5:  (0, 1),  6:  (1, 1),  7:  (2, 1),  8:  (3, 1),
    9:  (0, 2),  10: (1, 2),  11: (2, 2),  12: (3, 2),
    13: (0, 3),  14: (1, 3),  15: (2, 3),  16: (3, 3),
    17: (0, 4),  18: (1, 4),  19: (2, 4),  20: (3, 4),
    21: (0, 5),  22: (1, 5),  23: (2, 5),  24: (3, 5),
}


def iuv_to_atlas(image_bgr, iuv_map, atlas_size=1024):
    """
    Back-project photo pixels into a DensePose atlas texture using IUV map.

    Args:
        image_bgr: (H, W, 3) uint8 BGR — the source photo
        iuv_map:   (H, W, 3) uint8 — DensePose IUV prediction
                   channel 0 = body part index I (0=background, 1-24=body parts)
                   channel 1 = U coordinate (0-255, maps to 0-1)
                   channel 2 = V coordinate (0-255, maps to 0-1)
        atlas_size: output atlas resolution (should be divisible by 4 and 6)

    Returns:
        atlas:   (atlas_size, atlas_size, 3) uint8 BGR — the texture atlas
        weight:  (atlas_size, atlas_size) float32 — per-pixel confidence weight
    """
    h, w = image_bgr.shape[:2]
    # Start with skin-tone base (estimated from image foreground)
    # This ensures uncovered regions blend naturally instead of being black
    atlas = np.zeros((atlas_size, atlas_size, 3), dtype=np.uint8)
    weight = np.zeros((atlas_size, atlas_size), dtype=np.float32)

    cell_w = atlas_size // ATLAS_COLS
    cell_h = atlas_size // ATLAS_ROWS

    # Extract IUV channels
    part_ids = iuv_map[:, :, 0]   # body part index (0-24)
    u_coords = iuv_map[:, :, 1].astype(np.float32) / 255.0  # [0, 1]
    v_coords = iuv_map[:, :, 2].astype(np.float32) / 255.0  # [0, 1]

    # Process each body part
    for part_id in range(1, NUM_PARTS + 1):
        mask = part_ids == part_id
        if not np.any(mask):
            continue

        col, row = PART_GRID[part_id]

        # Get pixel coordinates and colors for this part
        ys, xs = np.where(mask)
        colors = image_bgr[ys, xs]  # (N, 3)

        # Map U, V to atlas pixel coordinates within this part's cell
        u = u_coords[ys, xs]
        v = v_coords[ys, xs]

        # Atlas pixel coordinates (float for sub-pixel accuracy)
        ax_f = col * cell_w + u * (cell_w - 1)
        ay_f = row * cell_h + (1 - v) * (cell_h - 1)

        ax = ax_f.astype(np.int32)
        ay = ay_f.astype(np.int32)

        # Clip to atlas bounds
        ax = np.clip(ax, 0, atlas_size - 1)
        ay = np.clip(ay, 0, atlas_size - 1)

        # Write to atlas with splat (fill center + 4 neighbors for better coverage)
        atlas[ay, ax] = colors
        weight[ay, ax] += 1.0

        # Splat to neighbors to fill gaps between samples
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ny = np.clip(ay + dy, 0, atlas_size - 1)
            nx = np.clip(ax + dx, 0, atlas_size - 1)
            # Only fill empty neighbors
            empty = weight[ny, nx] == 0
            atlas[ny[empty], nx[empty]] = colors[empty]
            weight[ny[empty], nx[empty]] += 0.5

    # Count coverage
    covered = (weight > 0).sum()
    total = atlas_size * atlas_size
    logger.info(f"Atlas coverage: {covered}/{total} ({100*covered/total:.1f}%)")

    return atlas, weight


def merge_atlases(atlases_and_weights):
    """
    Merge multiple atlas textures (from different views) with weighted blending.

    Args:
        atlases_and_weights: list of (atlas, weight) tuples

    Returns:
        merged_atlas: (H, W, 3) uint8 BGR
        merged_weight: (H, W) float32
    """
    if not atlases_and_weights:
        raise ValueError("No atlases to merge")

    h, w = atlases_and_weights[0][0].shape[:2]
    accum_color = np.zeros((h, w, 3), dtype=np.float64)
    accum_weight = np.zeros((h, w), dtype=np.float64)

    for atlas, wt in atlases_and_weights:
        mask = wt > 0
        wt_3ch = wt[:, :, np.newaxis]
        accum_color += atlas.astype(np.float64) * wt_3ch
        accum_weight += wt

    # Normalize
    safe_weight = np.maximum(accum_weight, 1e-8)[:, :, np.newaxis]
    merged = (accum_color / safe_weight).astype(np.uint8)

    # Zero out uncovered regions
    uncovered = accum_weight == 0
    merged[uncovered] = 0

    return merged, accum_weight.astype(np.float32)


def dilate_atlas(atlas, weight, iterations=5):
    """
    Dilate colored pixels to fill small gaps between DensePose samples.

    This spreads texture into nearby uncovered pixels without inpainting,
    giving a cleaner result for the subsequent inpainting step.
    """
    mask = (weight > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    result = atlas.copy()
    for _ in range(iterations):
        dilated_mask = cv2.dilate(mask, kernel)
        new_pixels = (dilated_mask > 0) & (mask == 0)

        if not np.any(new_pixels):
            break

        # For each new pixel, copy from nearest filled neighbor
        blurred = cv2.blur(result.astype(np.float32), (5, 5))
        blurred_weight = cv2.blur(mask.astype(np.float32), (5, 5))
        safe_w = np.maximum(blurred_weight, 1e-8)[:, :, np.newaxis]
        neighbor_avg = (blurred / safe_w).astype(np.uint8)

        result[new_pixels] = neighbor_avg[new_pixels]
        mask = dilated_mask

    return result, mask.astype(np.float32)


def _estimate_skin_color(atlas, weight):
    """Estimate the average skin color from covered atlas pixels."""
    mask = weight > 0
    if not mask.any():
        return np.array([160, 130, 110], dtype=np.uint8)  # Default warm skin BGR
    colors = atlas[mask].astype(np.float64)
    avg = colors.mean(axis=0).astype(np.uint8)
    return avg


def inpaint_atlas(atlas, weight, method='telea'):
    """
    Inpaint uncovered atlas regions using OpenCV.
    Fills remaining gaps with estimated skin color.
    """
    mask_unfilled = (weight == 0).astype(np.uint8) * 255

    if not np.any(mask_unfilled):
        return atlas

    # Estimate skin color for base fill
    skin_color = _estimate_skin_color(atlas, weight)
    logger.info(f"Estimated skin color (BGR): {skin_color}")

    # Dilate to fill gaps between DensePose samples (less aggressive to preserve detail)
    atlas_dilated, dilated_weight = dilate_atlas(atlas, weight, iterations=8)
    mask_unfilled = (dilated_weight == 0).astype(np.uint8) * 255

    if not np.any(mask_unfilled):
        return atlas_dilated

    # Fill remaining unfilled areas with skin base color before inpainting
    # This ensures inpainting blends from skin tone, not black
    base_filled = atlas_dilated.copy()
    still_empty = dilated_weight == 0
    base_filled[still_empty] = skin_color

    # Inpaint from the skin-tone base
    inpaint_radius = max(10, atlas.shape[0] // 64)
    flags = cv2.INPAINT_TELEA if method == 'telea' else cv2.INPAINT_NS
    result = cv2.inpaint(base_filled, mask_unfilled, inpaint_radius, flags)

    return result


def _split_atlas_to_parts(atlas_texture, part_size=200):
    """
    Split a single atlas grid image (4 cols × 6 rows) into 24 separate part textures.

    Args:
        atlas_texture: (H, W, 3) uint8 — the merged atlas grid
        part_size: output size for each part texture

    Returns:
        (24, part_size, part_size, 3) float64 — 24 part textures normalized to [0, 1]
    """
    h, w = atlas_texture.shape[:2]
    cell_w = w // ATLAS_COLS
    cell_h = h // ATLAS_ROWS

    parts = np.zeros((NUM_PARTS, part_size, part_size, 3), dtype=np.float64)

    for part_id in range(1, NUM_PARTS + 1):
        col, row = PART_GRID[part_id]
        x0 = col * cell_w
        y0 = row * cell_h
        cell = atlas_texture[y0:y0 + cell_h, x0:x0 + cell_w]

        if cell.shape[0] != part_size or cell.shape[1] != part_size:
            cell = cv2.resize(cell, (part_size, part_size), interpolation=cv2.INTER_LANCZOS4)

        parts[part_id - 1] = cell.astype(np.float64)

    return parts


def atlas_to_smpl_uv(atlas_texture, smpl_uv_map_path=None, atlas_size=1024, uv_size=1024):
    """
    Convert DensePose atlas format → SMPL UV texture map.

    DensePose uses a 24-part atlas layout. SMPL uses a different UV unwrapping.
    UVTextureConverter expects atlas_tex shape (24, part_h, part_w, 3) with
    pre-computed mapping for atlas_size=200, normal_size=512.

    Args:
        atlas_texture: (H, W, 3) uint8 — DensePose atlas (4×6 grid)
        smpl_uv_map_path: path to SMPL UV mapping data (optional)
        atlas_size: input atlas resolution (full grid size)
        uv_size: output UV map resolution

    Returns:
        (uv_size, uv_size, 3) uint8 — SMPL UV texture
    """
    try:
        converter_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'third_party', 'UVTextureConverter'
        )
        if os.path.exists(converter_path):
            import sys
            if converter_path not in sys.path:
                sys.path.insert(0, converter_path)
            from UVTextureConverter import Atlas2Normal

            # UVTextureConverter has pre-computed mapping for atlas_size=200, normal_size=512
            conv_atlas_size = 200
            conv_normal_size = 512
            converter = Atlas2Normal(atlas_size=conv_atlas_size, normal_size=conv_normal_size)

            # Split grid into 24 separate parts, each 200×200
            parts_4d = _split_atlas_to_parts(atlas_texture, part_size=conv_atlas_size)

            smpl_uv = converter.convert(parts_4d)
            logger.info(f"Converted atlas→SMPL UV via UVTextureConverter: {smpl_uv.shape}")

            # Convert from float [0,1] to uint8 and resize to requested size
            smpl_uv_uint8 = (np.clip(smpl_uv, 0, 1) * 255).astype(np.uint8)
            if smpl_uv_uint8.shape[0] != uv_size:
                smpl_uv_uint8 = cv2.resize(smpl_uv_uint8, (uv_size, uv_size),
                                            interpolation=cv2.INTER_LANCZOS4)
            return smpl_uv_uint8
    except Exception as e:
        logger.warning(f"UVTextureConverter failed: {e}")

    # Fallback: return atlas as-is
    logger.info("Using atlas directly (no SMPL UV conversion)")
    if atlas_texture.shape[0] != uv_size:
        return cv2.resize(atlas_texture, (uv_size, uv_size), interpolation=cv2.INTER_LANCZOS4)
    return atlas_texture


def photo_to_body_texture(image_paths, iuv_maps, atlas_size=1024, output_dir=None):
    """
    Full pipeline: multiple photos + IUV maps → merged, inpainted body texture atlas.

    Args:
        image_paths: list of image file paths
        iuv_maps:    list of (H, W, 3) uint8 IUV maps (one per image)
        atlas_size:  output atlas resolution
        output_dir:  optional directory to save intermediate results

    Returns:
        dict with:
            'atlas': (atlas_size, atlas_size, 3) uint8 BGR — the merged atlas
            'smpl_uv': (atlas_size, atlas_size, 3) uint8 BGR — SMPL UV format
            'coverage': float — percentage of atlas covered
    """
    atlases = []

    for i, (path, iuv) in enumerate(zip(image_paths, iuv_maps)):
        img = cv2.imread(path) if isinstance(path, str) else path
        if img is None:
            logger.warning(f"Could not read {path}, skipping")
            continue

        logger.info(f"Processing view {i+1}/{len(image_paths)}: {path if isinstance(path, str) else 'array'}")
        atlas, weight = iuv_to_atlas(img, iuv, atlas_size)
        atlases.append((atlas, weight))

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            name = os.path.basename(path) if isinstance(path, str) else f'view_{i}'
            cv2.imwrite(os.path.join(output_dir, f'atlas_{name}.png'), atlas)

    # Merge views
    merged, merged_weight = merge_atlases(atlases)
    coverage = (merged_weight > 0).sum() / (atlas_size * atlas_size) * 100

    # Inpaint gaps
    final_atlas = inpaint_atlas(merged, merged_weight)

    # Convert to SMPL UV
    smpl_uv = atlas_to_smpl_uv(final_atlas, atlas_size=atlas_size)

    # Inpaint the SMPL UV texture too — UVTextureConverter leaves unmapped areas black
    skin_color = _estimate_skin_color(merged, merged_weight)
    smpl_uv_mask = np.all(smpl_uv == 0, axis=-1)  # black pixels = unmapped
    if smpl_uv_mask.any():
        # Fill black areas with skin color, then inpaint for smooth blending
        smpl_uv_filled = smpl_uv.copy()
        smpl_uv_filled[smpl_uv_mask] = skin_color
        inpaint_mask = smpl_uv_mask.astype(np.uint8) * 255
        inpaint_r = max(15, smpl_uv.shape[0] // 32)
        smpl_uv = cv2.inpaint(smpl_uv_filled, inpaint_mask, inpaint_r, cv2.INPAINT_TELEA)
        logger.info(f"Inpainted SMPL UV: {smpl_uv_mask.sum()} black pixels filled")

    if output_dir:
        cv2.imwrite(os.path.join(output_dir, 'merged_atlas.png'), merged)
        cv2.imwrite(os.path.join(output_dir, 'final_atlas.png'), final_atlas)
        cv2.imwrite(os.path.join(output_dir, 'smpl_uv_texture.png'), smpl_uv)
        # Coverage heatmap
        coverage_vis = cv2.applyColorMap(
            np.clip(merged_weight * 50, 0, 255).astype(np.uint8),
            cv2.COLORMAP_JET
        )
        cv2.imwrite(os.path.join(output_dir, 'coverage_heatmap.png'), coverage_vis)

    logger.info(f"Final atlas coverage: {coverage:.1f}%")

    return {
        'atlas': final_atlas,
        'smpl_uv': smpl_uv,
        'coverage': coverage,
        'weight': merged_weight,
    }
