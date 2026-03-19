"""
Direct SMPL mesh pipeline: HMR2.0 → rembg segmentation → canonical UV →
UV-space triangle rasterization → DSINE normals → delighting → GLB export.

Skips Anny entirely — preserves HMR2.0's full shape detail (6890 verts).
"""
import numpy as np
import cv2
import math
import pickle
import os
import logging

logger = logging.getLogger('smpl_direct')

# Camera defaults matching the dual-capture rig
DEFAULT_DIST_MM = 2300.0
DEFAULT_CAM_HEIGHT_MM = 650.0
DEFAULT_FOCAL_MM = 4.0
DEFAULT_SENSOR_W_MM = 6.4
ATLAS_SIZE = 2048

SMPL_PKL = os.path.expanduser('~/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl')

# Canonical SMPL UV data (from Meshcapade, mapped to base 6890 verts)
_CANONICAL_UV_PATH = os.path.join(os.path.dirname(__file__), '..', 'meshes',
                                   'smpl_canonical_vert_uvs.npy')

def _load_canonical_uvs():
    """Load canonical SMPL UVs, fall back to cylindrical if unavailable."""
    if os.path.exists(_CANONICAL_UV_PATH):
        uvs = np.load(_CANONICAL_UV_PATH)
        logger.info("Loaded canonical SMPL UVs (%d verts)", len(uvs))
        return uvs
    return None


def segment_body(img_bgr):
    """Binary body mask using rembg (U2-Net). Returns (H, W) uint8: 255=body."""
    try:
        from rembg import remove
        from PIL import Image

        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        result = remove(pil_img, only_mask=True)
        mask = np.array(result)
        mask = (mask > 128).astype(np.uint8) * 255
        kernel = np.ones((21, 21), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)
        return mask
    except Exception as e:
        logger.warning("rembg segmentation failed: %s, using full image", e)
        return np.ones(img_bgr.shape[:2], dtype=np.uint8) * 255


def cylindrical_uvs(verts):
    """Full-body cylindrical UV mapping. Returns (N, 2) float32."""
    cx = verts[:, 0].mean()
    cy = verts[:, 1].mean()
    angles = np.arctan2(verts[:, 1] - cy, verts[:, 0] - cx)
    u = (angles + math.pi) / (2 * math.pi)

    z_min = verts[:, 2].min()
    z_max = verts[:, 2].max()
    v = (verts[:, 2] - z_min) / (z_max - z_min + 1e-6)

    return np.stack([u, v], axis=1).astype(np.float32)


def get_camera(direction, dist_mm=DEFAULT_DIST_MM, cam_h_mm=DEFAULT_CAM_HEIGHT_MM):
    """Return (cam_pos, cam_fwd, cam_right, cam_up) for a direction."""
    cam_defs = {
        'front': (np.array([0.0, -dist_mm, cam_h_mm]), np.array([0.0,  1.0, 0.0])),
        'back':  (np.array([0.0,  dist_mm, cam_h_mm]), np.array([0.0, -1.0, 0.0])),
        'left':  (np.array([-dist_mm, 0.0, cam_h_mm]), np.array([1.0,  0.0, 0.0])),
        'right': (np.array([ dist_mm, 0.0, cam_h_mm]), np.array([-1.0, 0.0, 0.0])),
    }
    cam_pos, cam_fwd = cam_defs[direction]
    up_world = np.array([0.0, 0.0, 1.0])
    cam_right = np.cross(cam_fwd, up_world)
    cam_right /= np.linalg.norm(cam_right)
    cam_up = np.cross(cam_right, cam_fwd)
    return cam_pos, cam_fwd, cam_right, cam_up


def rasterize_texture(verts, faces, uvs, photo_data, body_masks,
                      dist_mm=DEFAULT_DIST_MM, cam_h_mm=DEFAULT_CAM_HEIGHT_MM,
                      focal_mm=DEFAULT_FOCAL_MM, sensor_w_mm=DEFAULT_SENSOR_W_MM,
                      atlas_size=ATLAS_SIZE):
    """
    UV-space triangle rasterization: project photos onto texture atlas.

    Args:
        verts: (N, 3) float — SMPL vertices in mm, Z-up
        faces: (F, 3) uint32 — triangle indices
        uvs: (N, 2) float32 — per-vertex UVs
        photo_data: dict {direction: BGR image}
        body_masks: dict {direction: uint8 mask}
        dist_mm, cam_h_mm, focal_mm, sensor_w_mm: camera params

    Returns:
        texture: (atlas_size, atlas_size, 3) uint8 BGR
        weight: (atlas_size, atlas_size) float32 — accumulated blend weight
    """
    # Default fill: warm skin tone (BGR)
    texture = np.full((atlas_size, atlas_size, 3), [140, 160, 190], dtype=np.uint8)
    weight = np.zeros((atlas_size, atlas_size), dtype=np.float32)

    # Precompute face geometry
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    fn_lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
    fn_lens[fn_lens < 1e-10] = 1.0
    face_normals /= fn_lens

    total_texels = 0

    for direction in ['front', 'back', 'left', 'right']:
        if direction not in photo_data:
            continue

        img_raw = photo_data[direction]
        mask = body_masks.get(direction,
                              np.ones(img_raw.shape[:2], dtype=np.uint8) * 255)

        # Gentle CLAHE — preserve skin color, even out brightness
        lab = cv2.cvtColor(img_raw, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(16, 16))
        l = clahe.apply(l)
        img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

        h_img, w_img = img.shape[:2]
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

            # UV coords in atlas pixel space
            uv0, uv1, uv2 = uvs[f[0]], uvs[f[1]], uvs[f[2]]
            tx0, ty0 = uv0[0] * (atlas_size - 1), (1 - uv0[1]) * (atlas_size - 1)
            tx1, ty1 = uv1[0] * (atlas_size - 1), (1 - uv1[1]) * (atlas_size - 1)
            tx2, ty2 = uv2[0] * (atlas_size - 1), (1 - uv2[1]) * (atlas_size - 1)

            min_tx = max(0, int(min(tx0, tx1, tx2)))
            max_tx = min(atlas_size - 1, int(max(tx0, tx1, tx2)) + 1)
            min_ty = max(0, int(min(ty0, ty1, ty2)))
            max_ty = min(atlas_size - 1, int(max(ty0, ty1, ty2)) + 1)

            if max_tx - min_tx > atlas_size // 2 or max_ty - min_ty > atlas_size // 2:
                continue  # Skip degenerate UV triangles that wrap

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
                        color = img[py, px]
                        w_old = weight[ty, tx]
                        w_new = w_old + fw
                        texture[ty, tx] = (
                            (texture[ty, tx].astype(np.float32) * w_old +
                             color.astype(np.float32) * fw) / (w_new + 1e-8)
                        ).astype(np.uint8)
                        weight[ty, tx] = w_new
                        dir_texels += 1

        total_texels += dir_texels
        logger.info("%s: %d texels filled", direction, dir_texels)

    logger.info("Total texels: %d, coverage: %.1f%%",
                total_texels, (weight > 0).sum() / (atlas_size ** 2) * 100)
    return texture, weight


def delight_texture(texture, weight):
    """Homomorphic delighting — remove baked room lighting, preserve skin tones."""
    covered = weight > 0
    if not covered.any():
        return texture

    atlas_size = texture.shape[0]
    lab = cv2.cvtColor(texture, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]

    sigma = atlas_size // 4 | 1
    L_log = np.log1p(L)
    L_blur = cv2.GaussianBlur(L_log, (sigma, sigma), 0)
    L_highpass = L_log - L_blur

    L_new = np.expm1(L_highpass)
    L_min, L_max = L[covered].min(), L[covered].max()
    L_new_norm = (L_new - L_new.min()) / (L_new.max() - L_new.min() + 1e-6)
    L_new = L_new_norm * (L_max - L_min) + L_min

    # 35% delighted + 65% original — gentle correction
    lab[:, :, 0] = np.where(covered, L_new * 0.35 + L * 0.65, L)

    # Slight desaturation of colored light tints
    ab_center = 128.0
    for ch in [1, 2]:
        lab[:, :, ch] = np.where(
            covered,
            (lab[:, :, ch] - ab_center) * 0.95 + ab_center,
            lab[:, :, ch],
        )

    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def generate_direct_smpl(images_dict, profile=None,
                         dist_mm=None, cam_h_mm=None,
                         focal_mm=DEFAULT_FOCAL_MM,
                         sensor_w_mm=DEFAULT_SENSOR_W_MM):
    """
    Full direct SMPL pipeline from photos to textured mesh data.

    Args:
        images_dict: dict {direction: BGR ndarray} — at least 1 photo
        profile: optional dict with camera_distance_cm, camera_height_from_ground_cm
        dist_mm: override camera distance in mm
        cam_h_mm: override camera height in mm

    Returns:
        dict with keys: vertices, faces, uvs, texture_image, height_mm,
                        num_vertices, num_faces, volume_cm3, hmr_backend,
                        hmr_confidence
        or None on failure.
    """
    profile = profile or {}

    # Camera params from profile or defaults
    if dist_mm is None:
        dist_mm = float(profile.get('camera_distance_cm', 230)) * 10.0
    if cam_h_mm is None:
        cam_h_mm = float(profile.get('camera_height_from_ground_cm', 65)) * 10.0

    # ── 1. HMR2.0 shape prediction ──────────────────────────────────────────
    from core.hmr_shape import predict_shape

    images = list(images_dict.values())
    directions = list(images_dict.keys())

    logger.info("Running HMR2.0 on %d images...", len(images))
    result = predict_shape(images, directions)
    if result is None or result['vertices'] is None:
        logger.error("HMR2.0 shape prediction failed")
        return None

    verts = result['vertices']  # (6890, 3) mm, Z-up
    logger.info("SMPL: %s, height=%.0fmm, backend=%s",
                verts.shape, verts[:, 2].max() - verts[:, 2].min(), result['backend'])

    # ── 2. SMPL faces ────────────────────────────────────────────────────────
    if not os.path.exists(SMPL_PKL):
        logger.error("SMPL_NEUTRAL.pkl not found at %s", SMPL_PKL)
        return None

    with open(SMPL_PKL, 'rb') as f:
        smpl_data = pickle.load(f, encoding='latin1')
    faces = smpl_data['f'].astype(np.uint32)

    # ── 3. Center body ───────────────────────────────────────────────────────
    verts[:, 2] -= verts[:, 2].min()
    verts[:, 0] -= verts[:, 0].mean()
    verts[:, 1] -= verts[:, 1].mean()
    height_mm = float(verts[:, 2].max())

    # ── 4. Body segmentation ─────────────────────────────────────────────────
    logger.info("Segmenting bodies...")
    body_masks = {}
    for direction, img in images_dict.items():
        body_masks[direction] = segment_body(img)
        coverage = (body_masks[direction] > 0).sum() / body_masks[direction].size * 100
        logger.info("  %s: %.1f%% body pixels", direction, coverage)

    # ── 5. UVs — canonical SMPL if available, else cylindrical fallback ─────
    canonical = _load_canonical_uvs()
    if canonical is not None and len(canonical) == len(verts):
        uvs = canonical.astype(np.float32)
        logger.info("Using canonical SMPL UVs")
    else:
        uvs = cylindrical_uvs(verts)
        logger.info("Using cylindrical UVs (canonical not available)")

    # ── 6. UV-space rasterization ────────────────────────────────────────────
    logger.info("Rasterizing texture...")
    texture, weight = rasterize_texture(
        verts, faces, uvs, images_dict, body_masks,
        dist_mm=dist_mm, cam_h_mm=cam_h_mm,
        focal_mm=focal_mm, sensor_w_mm=sensor_w_mm,
    )

    # ── 7. Delight ───────────────────────────────────────────────────────────
    logger.info("Delighting texture...")
    texture = delight_texture(texture, weight)

    # ── 8. Gap inpainting ────────────────────────────────────────────────────
    mask_unfilled = (weight == 0).astype(np.uint8) * 255
    if mask_unfilled.any():
        texture = cv2.inpaint(texture, mask_unfilled, inpaintRadius=8,
                              flags=cv2.INPAINT_TELEA)

    # ── 9. DSINE normal map from photos ──────────────────────────────────────
    normal_map = None
    try:
        from core.dsine_normals import estimate_normals, project_normals_to_atlas
        photo_normals = {}
        for direction, img in images_dict.items():
            n = estimate_normals(img)
            if n is not None:
                photo_normals[direction] = n
                logger.info("DSINE normals estimated for %s", direction)
        if photo_normals:
            normal_map = project_normals_to_atlas(
                verts, faces, uvs, photo_normals, body_masks,
                dist_mm=dist_mm, cam_h_mm=cam_h_mm,
                focal_mm=focal_mm, sensor_w_mm=sensor_w_mm,
                atlas_size=ATLAS_SIZE,
            )
            logger.info("Normal map projected from %d views", len(photo_normals))
    except Exception as e:
        logger.warning("DSINE normal estimation skipped: %s", e)
        normal_map = None

    # ── 10. Convert to meters for GLB ────────────────────────────────────────
    verts_m = verts / 1000.0

    # Rough volume estimate (sum of signed tetrahedra)
    v0 = verts_m[faces[:, 0]]
    v1 = verts_m[faces[:, 1]]
    v2 = verts_m[faces[:, 2]]
    volume_m3 = abs(np.sum(v0[:, 0] * (v1[:, 1] * v2[:, 2] - v1[:, 2] * v2[:, 1]) +
                           v0[:, 1] * (v1[:, 2] * v2[:, 0] - v1[:, 0] * v2[:, 2]) +
                           v0[:, 2] * (v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])) / 6.0)
    volume_cm3 = volume_m3 * 1e6

    return {
        'vertices': verts_m,
        'faces': faces,
        'uvs': uvs,
        'texture_image': texture,
        'normal_map': normal_map,
        'height_mm': height_mm,
        'num_vertices': len(verts),
        'num_faces': len(faces),
        'volume_cm3': round(volume_cm3, 1),
        'hmr_backend': result.get('backend'),
        'hmr_confidence': result.get('confidence'),
    }
