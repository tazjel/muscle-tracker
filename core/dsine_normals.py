"""
DSINE normal map estimation from photos.
Projects per-pixel surface normals onto UV atlas for realistic body detail.
"""
import numpy as np
import cv2
import logging
import os

logger = logging.getLogger('dsine_normals')

_dsine_model = None


def _get_model():
    """Lazy-load DSINE model (278MB, cached after first load)."""
    global _dsine_model
    if _dsine_model is not None:
        return _dsine_model
    try:
        import torch
        _dsine_model = torch.hub.load('hugoycj/DSINE-hub', 'DSINE', trust_repo=True)
        logger.info("DSINE model loaded (CUDA=%s)", torch.cuda.is_available())
        return _dsine_model
    except Exception as e:
        logger.warning("Failed to load DSINE: %s", e)
        return None


def estimate_normals(img_bgr):
    """
    Estimate surface normals from a BGR image.

    Returns:
        (H, W, 3) float32 array in [-1, 1] (RGB normal map),
        or None on failure.
    """
    model = _get_model()
    if model is None:
        return None
    try:
        result = model.infer_cv2(img_bgr)  # [1, 3, H, W] tensor in [-1, 1]
        normal = result[0].permute(1, 2, 0).cpu().numpy()  # (H, W, 3)
        return normal.astype(np.float32)
    except Exception as e:
        logger.warning("DSINE inference failed: %s", e)
        return None


def project_normals_to_atlas(verts, faces, uvs, photo_normals, body_masks,
                              dist_mm, cam_h_mm, focal_mm, sensor_w_mm,
                              atlas_size=2048):
    """
    Project DSINE normal maps from multiple views onto UV atlas.

    Args:
        verts: (N, 3) float — SMPL vertices in mm, Z-up
        faces: (F, 3) uint32
        uvs: (N, 2) float32 — per-vertex UVs
        photo_normals: dict {direction: (H,W,3) float32 in [-1,1]}
        body_masks: dict {direction: (H,W) uint8 mask}
        dist_mm, cam_h_mm, focal_mm, sensor_w_mm: camera params

    Returns:
        (atlas_size, atlas_size, 3) uint8 — tangent-space normal map [0,255]
    """
    from core.smpl_direct import get_camera

    # Default: flat normal (pointing up in tangent space)
    atlas = np.full((atlas_size, atlas_size, 3), [128, 128, 255], dtype=np.float32)
    weight = np.zeros((atlas_size, atlas_size), dtype=np.float32)

    # Precompute face geometry
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    fn_lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
    fn_lens[fn_lens < 1e-10] = 1.0
    face_normals /= fn_lens

    for direction in ['front', 'back', 'left', 'right']:
        if direction not in photo_normals:
            continue

        normals_img = photo_normals[direction]  # (H, W, 3) in [-1, 1]
        mask = body_masks.get(direction,
                              np.ones(normals_img.shape[:2], dtype=np.uint8) * 255)
        h_img, w_img = normals_img.shape[:2]

        cam_pos, cam_fwd, cam_right, cam_up = get_camera(direction, dist_mm, cam_h_mm)
        focal_px = focal_mm / sensor_w_mm * w_img

        # Back-face culling
        face_centers = (v0 + v1 + v2) / 3.0
        view_vecs = cam_pos - face_centers
        dots = (face_normals * view_vecs).sum(axis=1)
        view_lens = np.linalg.norm(view_vecs, axis=1) + 1e-8
        visible_mask = dots > 0
        facing_strength = np.clip(dots / view_lens, 0, 1)

        dir_texels = 0
        for fi in np.where(visible_mask)[0]:
            f = faces[fi]
            fw = facing_strength[fi]

            uv0, uv1, uv2 = uvs[f[0]], uvs[f[1]], uvs[f[2]]
            tx0, ty0 = uv0[0] * (atlas_size - 1), (1 - uv0[1]) * (atlas_size - 1)
            tx1, ty1 = uv1[0] * (atlas_size - 1), (1 - uv1[1]) * (atlas_size - 1)
            tx2, ty2 = uv2[0] * (atlas_size - 1), (1 - uv2[1]) * (atlas_size - 1)

            min_tx = max(0, int(min(tx0, tx1, tx2)))
            max_tx = min(atlas_size - 1, int(max(tx0, tx1, tx2)) + 1)
            min_ty = max(0, int(min(ty0, ty1, ty2)))
            max_ty = min(atlas_size - 1, int(max(ty0, ty1, ty2)) + 1)

            if max_tx - min_tx > atlas_size // 2 or max_ty - min_ty > atlas_size // 2:
                continue

            p0, p1, p2 = verts[f[0]], verts[f[1]], verts[f[2]]
            denom = (ty1 - ty2) * (tx0 - tx2) + (tx2 - tx1) * (ty0 - ty2)
            if abs(denom) < 1e-6:
                continue

            for ty in range(min_ty, max_ty + 1):
                for tx in range(min_tx, max_tx + 1):
                    w0 = ((ty1 - ty2) * (tx - tx2) + (tx2 - tx1) * (ty - ty2)) / denom
                    w1 = ((ty2 - ty0) * (tx - tx2) + (tx0 - tx2) * (ty - ty2)) / denom
                    w2 = 1.0 - w0 - w1
                    if w0 < -0.01 or w1 < -0.01 or w2 < -0.01:
                        continue

                    pt3d = w0 * p0 + w1 * p1 + w2 * p2
                    rel = pt3d - cam_pos
                    depth = rel @ cam_fwd
                    if depth < 10.0:
                        continue
                    px = int((rel @ cam_right) / depth * focal_px + w_img / 2)
                    py = int(-(rel @ cam_up) / depth * focal_px + h_img / 2)

                    if 0 <= px < w_img and 0 <= py < h_img and mask[py, px] > 0:
                        # Sample normal from DSINE output, convert to [0, 255] range
                        n = normals_img[py, px]  # [-1, 1]
                        n_encoded = n * 0.5 + 0.5  # [0, 1]
                        n_color = n_encoded * 255.0  # [0, 255]

                        w_old = weight[ty, tx]
                        w_new = w_old + fw
                        atlas[ty, tx] = (
                            (atlas[ty, tx] * w_old + n_color * fw) / (w_new + 1e-8)
                        )
                        weight[ty, tx] = w_new
                        dir_texels += 1

        logger.info("%s: %d normal texels projected", direction, dir_texels)

    # Fill gaps
    mask_unfilled = (weight == 0).astype(np.uint8) * 255
    result = np.clip(atlas, 0, 255).astype(np.uint8)
    if mask_unfilled.any():
        result = cv2.inpaint(result, mask_unfilled, inpaintRadius=8,
                             flags=cv2.INPAINT_TELEA)

    return result
