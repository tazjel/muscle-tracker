"""
skin_color_extract.py — Extract real skin colors from photos using DensePose.

Instead of trying to project photo pixels 1:1 onto the mesh (which fails due to
pose mismatch), this extracts average skin color per body region and creates a
smooth, natural-looking texture using the user's actual skin tone gradients.
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Body regions for color extraction (grouped from 24 DensePose parts)
BODY_REGIONS = {
    'face':       [23, 24],
    'torso':      [1, 2],
    'upper_arm':  [15, 16, 17, 18],
    'lower_arm':  [19, 20, 21, 22],
    'hand':       [3, 4],
    'upper_leg':  [7, 8, 9, 10],
    'lower_leg':  [11, 12, 13, 14],
    'foot':       [5, 6],
}


def extract_region_colors(photos, iuv_maps):
    """
    Extract average skin color per body region from all photos.

    Args:
        photos: dict {view_name: BGR image array}
        iuv_maps: dict {view_name: (H, W, 3) IUV map}

    Returns:
        dict {region_name: BGR color array} — average color per region
    """
    region_pixels = {r: [] for r in BODY_REGIONS}

    for view_name in photos:
        if view_name not in iuv_maps:
            continue

        img = photos[view_name]
        iuv = iuv_maps[view_name]

        for region_name, part_ids in BODY_REGIONS.items():
            for pid in part_ids:
                mask = iuv[:, :, 0] == pid
                if mask.any():
                    colors = img[mask]
                    region_pixels[region_name].append(colors)

    # Compute average color per region
    region_colors = {}
    all_colors = []

    for region_name, pixel_lists in region_pixels.items():
        if pixel_lists:
            all_pixels = np.vstack(pixel_lists)
            # Use median for robustness (avoids clothing/shadow outliers)
            color = np.median(all_pixels, axis=0).astype(np.uint8)
            region_colors[region_name] = color
            all_colors.append(color)
            logger.info(f"  {region_name}: BGR={color}, {len(all_pixels)} pixels")
        else:
            logger.info(f"  {region_name}: no data")

    # Fill missing regions with overall average
    if all_colors:
        avg_color = np.mean(all_colors, axis=0).astype(np.uint8)
    else:
        avg_color = np.array([100, 130, 170], dtype=np.uint8)

    for region_name in BODY_REGIONS:
        if region_name not in region_colors:
            region_colors[region_name] = avg_color

    return region_colors


def create_skin_texture(vertices, faces, uvs, region_colors, texture_size=1024):
    """
    Create a smooth skin texture using per-region colors.

    Maps mesh vertices to body regions based on 3D position,
    assigns regional colors, and rasterizes a smooth texture.

    Args:
        vertices: (V, 3) float32
        faces: (F, 3) uint32
        uvs: (V, 2) float32
        region_colors: dict from extract_region_colors()
        texture_size: output texture resolution

    Returns:
        texture: (texture_size, texture_size, 3) uint8 BGR
    """
    n = len(vertices)
    z = vertices[:, 2]  # height
    x = vertices[:, 0]  # left/right

    z_max = z.max()
    z_min = z.min()

    # Assign each vertex to a body region based on height + width
    vert_colors = np.zeros((n, 3), dtype=np.float64)

    # Height thresholds
    head_z = z_max - 200
    neck_z = z_max - 350
    shoulder_z = z_max - 400
    hip_z = z_max - 800
    knee_z = z_max - 1200
    ankle_z = z_max - 1550
    torso_width = 200

    for vi in range(n):
        vz = z[vi]
        vx = abs(x[vi])

        if vz > head_z:
            color = region_colors['face']
        elif vz > shoulder_z and vx > torso_width:
            color = region_colors['upper_arm']
        elif vz > hip_z and vx > torso_width:
            # Could be lower arm or hand depending on distance from center
            if vx > 400:
                color = region_colors['hand']
            else:
                color = region_colors['lower_arm']
        elif vz > hip_z:
            # Blend between face (top) and torso
            if vz > neck_z:
                t = (vz - neck_z) / max(head_z - neck_z, 1)
                color = (1 - t) * region_colors['torso'].astype(np.float64) + t * region_colors['face'].astype(np.float64)
            else:
                color = region_colors['torso']
        elif vz > knee_z:
            color = region_colors['upper_leg']
        elif vz > ankle_z:
            color = region_colors['lower_leg']
        else:
            color = region_colors['foot']

        vert_colors[vi] = np.array(color, dtype=np.float64)

    # Add subtle noise for natural look (±5 per channel)
    noise = np.random.RandomState(42).normal(0, 3, vert_colors.shape)
    vert_colors = np.clip(vert_colors + noise, 0, 255)

    # Smooth colors by averaging with neighbors (via face connectivity)
    smoothed = vert_colors.copy()
    neighbor_count = np.ones(n, dtype=np.float64)
    for fi in range(len(faces)):
        v0, v1, v2 = faces[fi]
        avg = (vert_colors[v0] + vert_colors[v1] + vert_colors[v2]) / 3
        smoothed[v0] += avg
        smoothed[v1] += avg
        smoothed[v2] += avg
        neighbor_count[v0] += 1
        neighbor_count[v1] += 1
        neighbor_count[v2] += 1
    smoothed /= neighbor_count[:, np.newaxis]

    # Rasterize into UV texture
    tex = np.zeros((texture_size, texture_size, 3), dtype=np.float64)
    weight = np.zeros((texture_size, texture_size), dtype=np.float64)

    for fi in range(len(faces)):
        v0, v1, v2 = faces[fi]

        c0 = smoothed[v0]
        c1 = smoothed[v1]
        c2 = smoothed[v2]

        uv0 = uvs[v0] * (texture_size - 1)
        uv1 = uvs[v1] * (texture_size - 1)
        uv2 = uvs[v2] * (texture_size - 1)

        umin = max(0, int(min(uv0[0], uv1[0], uv2[0])))
        umax = min(texture_size - 1, int(max(uv0[0], uv1[0], uv2[0])) + 1)
        vmin = max(0, int(min(uv0[1], uv1[1], uv2[1])))
        vmax = min(texture_size - 1, int(max(uv0[1], uv1[1], uv2[1])) + 1)

        if umax <= umin or vmax <= vmin:
            continue

        denom = ((uv1[1] - uv2[1]) * (uv0[0] - uv2[0]) +
                 (uv2[0] - uv1[0]) * (uv0[1] - uv2[1]))
        if abs(denom) < 1e-8:
            continue

        for ty in range(vmin, vmax + 1):
            for tx in range(umin, umax + 1):
                w0 = ((uv1[1] - uv2[1]) * (tx - uv2[0]) +
                       (uv2[0] - uv1[0]) * (ty - uv2[1])) / denom
                w1 = ((uv2[1] - uv0[1]) * (tx - uv2[0]) +
                       (uv0[0] - uv2[0]) * (ty - uv2[1])) / denom
                w2 = 1 - w0 - w1

                if w0 < -0.01 or w1 < -0.01 or w2 < -0.01:
                    continue

                color = w0 * c0 + w1 * c1 + w2 * c2
                tex_y = texture_size - 1 - ty
                if 0 <= tex_y < texture_size:
                    tex[tex_y, tx] = color
                    weight[tex_y, tx] = 1.0

    # Fill unfilled pixels with nearest
    from core.densepose_texture import inpaint_atlas
    result = inpaint_atlas(tex.astype(np.uint8), weight.astype(np.float32))

    coverage = (weight > 0).sum() / (texture_size * texture_size) * 100
    logger.info(f"Skin texture coverage: {coverage:.1f}%")

    return result
