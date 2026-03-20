"""
texture_bake.py — Bake photo skin texture onto Anny mesh UV space.

V3: Spatial projection — projects vertices onto photos using body-region
bounding box alignment. No DensePose UV matching needed — uses pure geometric
correspondence within regions. DensePose is used only as a body mask.
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

# ── Region definitions ────────────────────────────────────────────────────
REGION_PARTS = {
    'head':        [23, 24],
    'torso':       [1, 2],
    'upper_arm_r': [16, 18],
    'upper_arm_l': [15, 17],
    'lower_arm_r': [20, 22],
    'lower_arm_l': [19, 21],
    'hand_r':      [3],
    'hand_l':      [4],
    'upper_leg_r': [7, 9],
    'upper_leg_l': [8, 10],
    'lower_leg_r': [11, 13],
    'lower_leg_l': [12, 14],
    'foot_r':      [6],
    'foot_l':      [5],
}

PART_TO_REGION = {}
for _region, _parts in REGION_PARTS.items():
    for _p in _parts:
        PART_TO_REGION[_p] = _region

# View preference for each region (best → fallback)
VIEW_PREF = {
    'head':        ['front', 'left', 'right', 'back'],
    'torso':       ['front', 'back'],  # left/right cause seam artifacts on torso
    'upper_arm_r': ['right', 'front', 'back'],
    'upper_arm_l': ['left', 'front', 'back'],
    'lower_arm_r': ['right', 'front', 'back'],
    'lower_arm_l': ['left', 'front', 'back'],
    'hand_r':      ['right', 'front', 'back'],
    'hand_l':      ['left', 'front', 'back'],
    'upper_leg_r': ['front', 'right', 'back'],
    'upper_leg_l': ['front', 'left', 'back'],
    'lower_leg_r': ['front', 'right', 'back'],
    'lower_leg_l': ['front', 'left', 'back'],
    'foot_r':      ['front', 'right'],
    'foot_l':      ['front', 'left'],
}

# Arm regions need special projection (length along X in T-pose)
ARM_REGIONS = {'upper_arm_r', 'upper_arm_l', 'lower_arm_r', 'lower_arm_l',
               'hand_r', 'hand_l'}


def _segment_vertices(vertices):
    """
    Assign body region labels to Anny mesh vertices based on 3D position.
    T-pose aware: arms segmented by X distance from center, not Z height.

    Returns:
        region_ids: (N,) string array — region name for each vertex
    """
    n = len(vertices)
    x = vertices[:, 0]
    y = vertices[:, 1]
    z = vertices[:, 2]

    region_ids = np.full(n, '', dtype='U20')

    z_max = z.max()
    abs_x = np.abs(x)

    z_head = z_max - 200
    z_neck = z_max - 350
    z_hip = z_max - 800
    z_knee = z_max - 1200
    z_ankle = z_max - 1550

    torso_width = 220
    arm_max_x = abs_x.max()
    arm_range = max(arm_max_x - torso_width, 1)
    upper_arm_end = torso_width + arm_range * 0.40
    lower_arm_end = torso_width + arm_range * 0.80

    is_right = x > 0
    is_left = ~is_right

    # Head
    region_ids[z > z_head] = 'head'

    # Neck → torso
    neck = (z > z_neck) & (z <= z_head) & (abs_x < torso_width)
    region_ids[neck] = 'torso'

    # Arms (T-pose: X distance)
    arm_zone = (abs_x > torso_width) & (z >= z_hip) & (z <= z_head)
    upper_arm = arm_zone & (abs_x <= upper_arm_end)
    region_ids[upper_arm & is_right] = 'upper_arm_r'
    region_ids[upper_arm & is_left] = 'upper_arm_l'

    lower_arm = arm_zone & (abs_x > upper_arm_end) & (abs_x <= lower_arm_end)
    region_ids[lower_arm & is_right] = 'lower_arm_r'
    region_ids[lower_arm & is_left] = 'lower_arm_l'

    hand = arm_zone & (abs_x > lower_arm_end)
    region_ids[hand & is_right] = 'hand_r'
    region_ids[hand & is_left] = 'hand_l'

    # Catch arm vertices that fall outside arm_zone height range
    arm_overflow = (abs_x > torso_width) & (z < z_hip) & (z >= z_knee) & (region_ids == '')
    region_ids[arm_overflow & is_right] = 'hand_r'
    region_ids[arm_overflow & is_left] = 'hand_l'

    # Torso
    torso = (z >= z_hip) & (z <= z_neck) & (abs_x <= torso_width) & (region_ids == '')
    region_ids[torso] = 'torso'

    # Upper legs
    upper_leg = (z >= z_knee) & (z < z_hip) & (region_ids == '')
    region_ids[upper_leg & is_right] = 'upper_leg_r'
    region_ids[upper_leg & is_left] = 'upper_leg_l'

    # Lower legs
    lower_leg = (z >= z_ankle) & (z < z_knee) & (region_ids == '')
    region_ids[lower_leg & is_right] = 'lower_leg_r'
    region_ids[lower_leg & is_left] = 'lower_leg_l'

    # Feet
    feet = (z < z_ankle) & (region_ids == '')
    region_ids[feet & is_right] = 'foot_r'
    region_ids[feet & is_left] = 'foot_l'

    # Unassigned → torso
    region_ids[region_ids == ''] = 'torso'

    for region in REGION_PARTS:
        count = (region_ids == region).sum()
        if count > 0:
            logger.info(f"  {region}: {count} vertices")

    return region_ids


def _project_vertices(mesh_verts, region, view):
    """
    Compute normalized 2D projection [0,1] of mesh vertices for a given region+view.

    For arms in T-pose, projects arm length (|X|) → vertical, Y → horizontal.
    For other regions, projects XZ (front/back) or YZ (left/right).

    Returns:
        norm_x, norm_y: arrays in [0,1] mapping to photo (x, y) normalized coords
    """
    x = mesh_verts[:, 0]
    y = mesh_verts[:, 1]
    z = mesh_verts[:, 2]

    if region in ARM_REGIONS:
        # Arms: |X| = arm length (shoulder→hand), Y = circumference (front→back)
        # In photo: arm hangs vertically, so arm length → photo Y, circumference → photo X
        arm_len = np.abs(x)
        arm_circ = y.copy()

        al_min, al_max = arm_len.min(), arm_len.max()
        ac_min, ac_max = arm_circ.min(), arm_circ.max()

        # shoulder (small |X|) → top (norm_y=0), hand (large |X|) → bottom (norm_y=1)
        norm_y = (arm_len - al_min) / max(al_max - al_min, 1e-3)
        norm_x = (arm_circ - ac_min) / max(ac_max - ac_min, 1e-3)
    else:
        if view in ('front', 'back'):
            px = x.copy()
            if view == 'back':
                px = -px
            pz = z.copy()
        else:  # left, right
            px = y.copy()
            if view == 'right':
                px = -px
            pz = z.copy()

        px_min, px_max = px.min(), px.max()
        pz_min, pz_max = pz.min(), pz.max()

        norm_x = (px - px_min) / max(px_max - px_min, 1e-3)
        norm_y = (pz_max - pz) / max(pz_max - pz_min, 1e-3)  # inverted: top=0

    return norm_x, norm_y


def bake_from_photos_nn(vertices, faces, uvs, photo_dict, iuv_dict,
                        texture_size=1024):
    """
    Bake texture by spatially projecting vertices onto photos per body region.

    For each region, finds the DensePose-labeled area in each photo, computes
    bounding box alignment, and samples photo color at projected vertex positions.
    Uses DensePose only as a body mask — no UV coordinate matching.

    Args:
        vertices, faces, uvs: mesh data
        photo_dict: {view_name: BGR image}
        iuv_dict: {view_name: (H,W,3) IUV map}
        texture_size: output resolution

    Returns:
        texture: (size, size, 3) uint8 BGR
        weight: (size, size) float32
    """
    from scipy.spatial import KDTree

    n_verts = len(vertices)
    vert_colors = np.zeros((n_verts, 3), dtype=np.float64)
    vert_weights = np.zeros(n_verts, dtype=np.float64)

    region_ids = _segment_vertices(vertices)

    # Process each region
    for region in REGION_PARTS:
        v_mask = region_ids == region
        if not v_mask.any():
            continue

        vi_indices = np.where(v_mask)[0]
        mesh_verts = vertices[v_mask]
        parts = REGION_PARTS[region]

        for view in VIEW_PREF.get(region, list(photo_dict.keys())):
            if view not in photo_dict:
                continue

            img = photo_dict[view]
            iuv = iuv_dict[view]
            h, w = img.shape[:2]

            # Find DensePose pixels for this region in this view
            photo_mask = np.zeros((h, w), dtype=bool)
            for pid in parts:
                photo_mask |= (iuv[:, :, 0] == pid)

            if photo_mask.sum() < 50:
                continue

            ys, xs = np.where(photo_mask)
            pb_x0, pb_x1 = xs.min(), xs.max()
            pb_y0, pb_y1 = ys.min(), ys.max()
            pb_w = max(pb_x1 - pb_x0, 1)
            pb_h = max(pb_y1 - pb_y0, 1)

            # Project vertices → normalized [0,1] coords
            norm_x, norm_y = _project_vertices(mesh_verts, region, view)

            # Map to photo pixel coordinates within the region's bbox
            photo_x = (norm_x * pb_w + pb_x0).astype(np.int32)
            photo_y = (norm_y * pb_h + pb_y0).astype(np.int32)
            photo_x = np.clip(photo_x, 0, w - 1)
            photo_y = np.clip(photo_y, 0, h - 1)

            # Filter: only process vertices not yet fully colored
            need_color = np.array([vert_weights[vi] < 4 for vi in vi_indices])
            if not need_color.any():
                break  # all vertices in this region are done

            sub_vi = vi_indices[need_color]
            sub_px = photo_x[need_color]
            sub_py = photo_y[need_color]
            sub_verts = mesh_verts[need_color]

            # Batch sample: check which projected positions hit body pixels
            hit_body = iuv[sub_py, sub_px, 0] > 0
            hit_colors = img[sub_py, sub_px].astype(np.float64)

            # 2D angular view weighting: compute how much each vertex faces the camera
            # using atan2(Y, X) around the body's vertical axis.
            # Winner-take-all: only use this view if it's the BEST view for each vertex
            if region not in ARM_REGIONS:
                x_vals = sub_verts[:, 0]
                y_vals = sub_verts[:, 1]
                x_c = x_vals - x_vals.mean()
                y_c = y_vals - y_vals.mean()
                vert_angle = np.arctan2(y_c, x_c)  # -π to π

                cam_angles = {
                    'front': np.pi / 2,
                    'back': -np.pi / 2,
                    'left': np.pi,
                    'right': 0.0,
                }

                # Compute this view's score
                cam_angle = cam_angles.get(view, 0.0)
                angle_diff = vert_angle - cam_angle
                angle_diff = (angle_diff + np.pi) % (2 * np.pi) - np.pi
                this_score = np.cos(angle_diff)

                # Check if any OTHER available view would score higher
                is_best = np.ones(len(sub_verts), dtype=bool)
                for other_view in photo_dict:
                    if other_view == view or other_view not in cam_angles:
                        continue
                    other_angle = cam_angles[other_view]
                    other_diff = vert_angle - other_angle
                    other_diff = (other_diff + np.pi) % (2 * np.pi) - np.pi
                    other_score = np.cos(other_diff)
                    is_best &= (this_score >= other_score)

                # Only process vertices where this is the best view
                hit_body = hit_body & is_best
                view_weights = np.clip(this_score, 0.1, 1.0)
            else:
                view_weights = np.ones(len(sub_verts))

            # Apply hits — each vertex gets colored by its single best view
            hit_vi = sub_vi[hit_body]
            hit_w = view_weights[hit_body]
            vert_colors[hit_vi] += hit_colors[hit_body] * hit_w[:, np.newaxis]
            vert_weights[hit_vi] += hit_w

            n_hit = hit_body.sum()
            n_need = need_color.sum()
            logger.info(f"  {region} via {view}: {n_hit}/{n_need} vertices hit "
                         f"(bbox {pb_w}x{pb_h} px)")

            # For misses, search nearby body pixels (vectorized with small radius)
            miss_mask = ~hit_body
            miss_vi = sub_vi[miss_mask]
            miss_px = sub_px[miss_mask]
            miss_py = sub_py[miss_mask]

            if len(miss_vi) > 0:
                n_found = 0
                for r in [5, 15, 30]:
                    still_need = vert_weights[miss_vi] < 1
                    if not still_need.any():
                        break
                    for i in np.where(still_need)[0]:
                        vi = miss_vi[i]
                        cx, cy = miss_px[i], miss_py[i]
                        y0 = max(0, cy - r)
                        y1 = min(h - 1, cy + r)
                        x0 = max(0, cx - r)
                        x1 = min(w - 1, cx + r)
                        patch_body = iuv[y0:y1+1, x0:x1+1, 0] > 0
                        if patch_body.any():
                            patch_colors = img[y0:y1+1, x0:x1+1][patch_body]
                            vert_colors[vi] += patch_colors.mean(axis=0)
                            vert_weights[vi] += 0.5
                            n_found += 1
                if n_found > 0:
                    logger.info(f"    nearby search: {n_found} more vertices")

    # Average accumulated colors
    has_color = vert_weights > 0
    vert_colors[has_color] /= vert_weights[has_color, np.newaxis]

    n_colored = has_color.sum()
    logger.info(f"Total colored: {n_colored}/{n_verts} ({100*n_colored/n_verts:.1f}%)")

    # Fill uncolored vertices from nearest colored neighbor (spatial proximity)
    if not has_color.all() and n_colored > 10:
        colored_tree = KDTree(vertices[has_color])
        uncolored_mask = ~has_color
        _, fill_idx = colored_tree.query(vertices[uncolored_mask], k=3)
        colored_colors = vert_colors[has_color]
        fill_colors = colored_colors[fill_idx].mean(axis=1)
        vert_colors[uncolored_mask] = fill_colors
        logger.info(f"  Filled {uncolored_mask.sum()} vertices from nearest neighbors")
    elif not has_color.all():
        vert_colors[~has_color] = np.array([100, 130, 170], dtype=np.float64)

    # Light smoothing: ONLY on filled/low-confidence vertices (preserve photo detail)
    # Vertices colored directly from photos (weight >= 1) keep their original color
    filled_mask = (vert_weights < 1) & (vert_weights > 0)  # partial hits + KDTree fills
    if filled_mask.any():
        smoothed = vert_colors.copy()
        neighbor_sum = np.zeros_like(vert_colors)
        neighbor_count = np.zeros(n_verts, dtype=np.float64)
        for fi in range(len(faces)):
            v0, v1, v2 = faces[fi]
            avg = (vert_colors[v0] + vert_colors[v1] + vert_colors[v2]) / 3
            neighbor_sum[v0] += avg
            neighbor_sum[v1] += avg
            neighbor_sum[v2] += avg
            neighbor_count[v0] += 1
            neighbor_count[v1] += 1
            neighbor_count[v2] += 1
        has_neighbors = neighbor_count > 0
        blend_mask = filled_mask & has_neighbors
        # 50/50 blend with neighbors for low-confidence vertices only
        smoothed[blend_mask] = (
            0.5 * vert_colors[blend_mask] +
            0.5 * neighbor_sum[blend_mask] / neighbor_count[blend_mask, np.newaxis]
        )
        vert_colors = smoothed

    # Rasterize into UV texture space
    tex = np.zeros((texture_size, texture_size, 3), dtype=np.float64)
    weight = np.zeros((texture_size, texture_size), dtype=np.float64)

    for fi in range(len(faces)):
        v0, v1, v2 = faces[fi]
        c0, c1, c2 = vert_colors[v0], vert_colors[v1], vert_colors[v2]

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

    coverage = (weight > 0).sum() / (texture_size * texture_size) * 100
    logger.info(f"UV texture coverage: {coverage:.1f}%")

    return tex.astype(np.uint8), weight.astype(np.float32)


def build_seam_mask(vertices, faces, uvs, texture_size=1024):
    """
    Build UV-space seam masks for both front/back (Y-axis) and left/right (X-axis).

    Rasterizes vertex positions into UV space, then marks transition zones
    where the coordinate ≈ midpoint as seam regions.

    Returns:
        seam_mask: (size, size) float32 in [0,1] — combined seam intensity
    """
    y_vals = vertices[:, 1]
    x_vals = vertices[:, 0]
    y_mid = (y_vals.min() + y_vals.max()) / 2
    x_mid = (x_vals.min() + x_vals.max()) / 2
    y_range = max(y_vals.max() - y_vals.min(), 1e-3)
    x_range = max(x_vals.max() - x_vals.min(), 1e-3)

    # Rasterize both Y-depth and X-lateral into UV space
    y_depth_map = np.zeros((texture_size, texture_size), dtype=np.float64)
    x_depth_map = np.zeros((texture_size, texture_size), dtype=np.float64)
    filled = np.zeros((texture_size, texture_size), dtype=bool)

    for fi in range(len(faces)):
        v0, v1, v2 = faces[fi]
        yd0 = (y_vals[v0] - y_mid) / (y_range * 0.5)
        yd1 = (y_vals[v1] - y_mid) / (y_range * 0.5)
        yd2 = (y_vals[v2] - y_mid) / (y_range * 0.5)
        xd0 = (x_vals[v0] - x_mid) / (x_range * 0.5)
        xd1 = (x_vals[v1] - x_mid) / (x_range * 0.5)
        xd2 = (x_vals[v2] - x_mid) / (x_range * 0.5)

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

                tex_y = texture_size - 1 - ty
                if 0 <= tex_y < texture_size:
                    y_depth_map[tex_y, tx] = w0 * yd0 + w1 * yd1 + w2 * yd2
                    x_depth_map[tex_y, tx] = w0 * xd0 + w1 * xd1 + w2 * xd2
                    filled[tex_y, tx] = True

    # Front/back seam: Y ≈ 0 (midpoint depth)
    y_seam_width = 0.35
    y_seam = np.zeros_like(y_depth_map)
    y_seam[filled] = np.exp(-0.5 * (y_depth_map[filled] / y_seam_width) ** 2)

    # Left/right seam: X ≈ 0 (center lateral)
    x_seam_width = 0.35
    x_seam = np.zeros_like(x_depth_map)
    x_seam[filled] = np.exp(-0.5 * (x_depth_map[filled] / x_seam_width) ** 2)

    # Combined: max of both seam masks (union of seam zones)
    seam_mask = np.maximum(y_seam, x_seam)

    logger.info(f"Seam mask: Y-seam {(y_seam > 0.5).sum()} px, "
                f"X-seam {(x_seam > 0.5).sum()} px, "
                f"combined {(seam_mask > 0.1).sum()} px")

    return seam_mask.astype(np.float32)


def smooth_seam(texture, seam_mask, blur_radius=15):
    """
    Smooth view-boundary seams in UV space using two-pass selective Gaussian blur.

    Pass 1: Wide blur (blur_radius) blended by seam_mask — smooths color transitions.
    Pass 2: Narrow blur (blur_radius//2) at strong seam zones — kills hard edges.

    Args:
        texture: (H, W, 3) uint8 BGR texture
        seam_mask: (H, W) float32 in [0,1] — 1.0 at seam
        blur_radius: Gaussian kernel radius (must be odd)

    Returns:
        smoothed: (H, W, 3) uint8 BGR texture with seam smoothed
    """
    if blur_radius % 2 == 0:
        blur_radius += 1

    # Pass 1: wide Gaussian blur for overall color transition
    blurred_wide = cv2.GaussianBlur(texture, (blur_radius, blur_radius), 0)
    mask_3ch = seam_mask[:, :, np.newaxis]
    result = (mask_3ch * blurred_wide.astype(np.float32) +
              (1 - mask_3ch) * texture.astype(np.float32))
    result = np.clip(result, 0, 255).astype(np.uint8)

    # Pass 2: narrower bilateral filter on strong seam zones (preserves some detail)
    strong_mask = (seam_mask > 0.6).astype(np.float32)
    if strong_mask.sum() > 0:
        bilateral = cv2.bilateralFilter(result, d=11, sigmaColor=40, sigmaSpace=11)
        strong_3ch = strong_mask[:, :, np.newaxis]
        result = (strong_3ch * bilateral.astype(np.float32) +
                  (1 - strong_3ch) * result.astype(np.float32))
        result = np.clip(result, 0, 255).astype(np.uint8)

    smoothed_pixels = (seam_mask > 0.1).sum()
    logger.info(f"Seam smoothing: {smoothed_pixels} pixels affected "
                f"(blur={blur_radius}, bilateral on {int(strong_mask.sum())} strong px)")

    return result
