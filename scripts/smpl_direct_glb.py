"""
Direct SMPL mesh → GLB with photo texture.
Skips Anny entirely — uses HMR2.0 predicted SMPL mesh (6890 verts).
Uses UV-space triangle rasterization for dense texture coverage.
Adds body segmentation to avoid projecting room background onto mesh.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib', '4D-Humans'))

import numpy as np
import cv2
import logging

logging.basicConfig(level=logging.INFO, format='%(name)s %(levelname)s: %(message)s')
logger = logging.getLogger('smpl_direct')


def segment_body(img_bgr):
    """
    Create a binary body mask using rembg (U2-Net).
    Returns (H, W) uint8 mask: 255=body, 0=background.
    """
    try:
        from rembg import remove, new_session
        from PIL import Image
        import io

        # Convert BGR to RGB PIL Image
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        # Get alpha mask only (much faster than full removal)
        result = remove(pil_img, only_mask=True)
        mask = np.array(result)

        # Threshold and dilate to include body edges
        mask = (mask > 128).astype(np.uint8) * 255
        kernel = np.ones((21, 21), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)
        return mask
    except Exception as e:
        logger.warning(f"rembg segmentation failed: {e}, using full image")
        return np.ones(img_bgr.shape[:2], dtype=np.uint8) * 255

# ── 1. Load photos ──────────────────────────────────────────────────────────
photo_dir = os.path.join(os.path.dirname(__file__), 'dual_captures', 'matepad_360')

photo_map = {
    'front': 'img2.jpg',
    'back':  'img3.jpg',
    'right': 'img4.jpg',
    'left':  'img5.jpg',
}

images = []
directions = []
photo_data = {}
body_masks = {}

for direction, fname in photo_map.items():
    path = os.path.join(photo_dir, fname)
    img = cv2.imread(path)
    if img is None:
        logger.error(f"Cannot load {path}")
        sys.exit(1)
    images.append(img)
    directions.append(direction)
    photo_data[direction] = img
    logger.info(f"Loaded {direction}: {fname} → {img.shape}")

# Segment bodies in all photos
logger.info("Segmenting bodies from backgrounds...")
for direction in photo_map:
    mask = segment_body(photo_data[direction])
    body_masks[direction] = mask
    coverage = (mask > 0).sum() / mask.size * 100
    logger.info(f"  {direction}: {coverage:.1f}% body pixels")

# ── 2. Predict SMPL shape ──────────────────────────────────────────────────
from core.hmr_shape import predict_shape

logger.info("Running HMR2.0 shape prediction...")
result = predict_shape(images, directions)
if result is None or result['vertices'] is None:
    logger.error("Shape prediction failed!")
    sys.exit(1)

verts = result['vertices']
logger.info(f"SMPL: {verts.shape}, height={verts[:,2].max()-verts[:,2].min():.0f}mm, backend={result['backend']}")

# ── 3. Get SMPL faces ───────────────────────────────────────────────────────
import pickle
smpl_pkl = os.path.expanduser('~/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl')
with open(smpl_pkl, 'rb') as f:
    smpl_data = pickle.load(f, encoding='latin1')
faces = smpl_data['f'].astype(np.uint32)

# ── 4. Center body ─────────────────────────────────────────────────────────
verts[:, 2] -= verts[:, 2].min()
verts[:, 0] -= verts[:, 0].mean()
verts[:, 1] -= verts[:, 1].mean()
height_mm = verts[:, 2].max()
logger.info(f"Centered: height={height_mm:.0f}mm, X=[{verts[:,0].min():.0f},{verts[:,0].max():.0f}], "
            f"Y=[{verts[:,1].min():.0f},{verts[:,1].max():.0f}]")

# ── 5. Compute UVs — single full-body cylindrical projection ───────────────
# No body-part splitting — uses the full atlas area for better texel density
import math

cx = verts[:, 0].mean()
cy = verts[:, 1].mean()
angles = np.arctan2(verts[:, 1] - cy, verts[:, 0] - cx)
u = (angles + math.pi) / (2 * math.pi)  # 0..1

z_min = verts[:, 2].min()
z_max = verts[:, 2].max()
v = (verts[:, 2] - z_min) / (z_max - z_min + 1e-6)

uvs = np.stack([u, v], axis=1).astype(np.float32)
logger.info(f"UVs (full cylindrical): u=[{u.min():.3f},{u.max():.3f}], v=[{v.min():.3f},{v.max():.3f}]")

# ── 7. Camera setup ────────────────────────────────────────────────────────
DIST_MM = 2300.0
CAM_HEIGHT_MM = 650.0
FOCAL_MM = 4.0
SENSOR_W_MM = 6.4

ATLAS_SIZE = 2048


def get_camera(direction):
    """Return (cam_pos, cam_fwd, cam_right, cam_up) for a direction."""
    cam_defs = {
        'front': (np.array([0.0, -DIST_MM, CAM_HEIGHT_MM]), np.array([0.0,  1.0, 0.0])),
        'back':  (np.array([0.0,  DIST_MM, CAM_HEIGHT_MM]), np.array([0.0, -1.0, 0.0])),
        'left':  (np.array([-DIST_MM, 0.0, CAM_HEIGHT_MM]), np.array([1.0,  0.0, 0.0])),
        'right': (np.array([ DIST_MM, 0.0, CAM_HEIGHT_MM]), np.array([-1.0, 0.0, 0.0])),
    }
    cam_pos, cam_fwd = cam_defs[direction]
    up_world = np.array([0.0, 0.0, 1.0])
    cam_right = np.cross(cam_fwd, up_world)
    cam_right /= np.linalg.norm(cam_right)
    cam_up = np.cross(cam_right, cam_fwd)
    return cam_pos, cam_fwd, cam_right, cam_up


def project_point(pt3d, cam_pos, cam_fwd, cam_right, cam_up, focal_px, w_img, h_img):
    """Project a 3D point to 2D image coords. Returns (px, py, depth)."""
    rel = pt3d - cam_pos
    depth = rel @ cam_fwd
    if depth < 10.0:
        return None, None, None
    px = (rel @ cam_right) / depth * focal_px + w_img / 2
    py = -(rel @ cam_up) / depth * focal_px + h_img / 2
    return px, py, depth


# ── 8. UV-space triangle rasterization ──────────────────────────────────────
logger.info("\n=== UV-SPACE RASTERIZATION ===")

# Default fill: warm skin tone (BGR) so inpainted gaps blend naturally
texture = np.full((ATLAS_SIZE, ATLAS_SIZE, 3), [140, 160, 190], dtype=np.uint8)
weight = np.zeros((ATLAS_SIZE, ATLAS_SIZE), dtype=np.float32)

# Precompute face normals
v0 = verts[faces[:, 0]]
v1 = verts[faces[:, 1]]
v2 = verts[faces[:, 2]]
face_normals = np.cross(v1 - v0, v2 - v0)
fn_lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
fn_lens[fn_lens < 1e-10] = 1.0
face_normals /= fn_lens

total_texels = 0

for direction in ['front', 'back', 'left', 'right']:
    img_raw = photo_data[direction]
    mask = body_masks[direction]
    # Gentle light normalize — preserve skin color, just even out brightness
    lab = cv2.cvtColor(img_raw, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(16, 16))
    l = clahe.apply(l)
    # Skip grey-world white balance — it desaturates skin tones
    img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

    h_img, w_img = img.shape[:2]
    cam_pos, cam_fwd, cam_right, cam_up = get_camera(direction)
    focal_px = FOCAL_MM / SENSOR_W_MM * w_img

    # Determine visible faces (back-face culling)
    face_centers = (v0 + v1 + v2) / 3.0
    view_vecs = cam_pos - face_centers
    dots = (face_normals * view_vecs).sum(axis=1)
    view_lens = np.linalg.norm(view_vecs, axis=1) + 1e-8
    visible_mask = dots > 0
    facing_strength = np.clip(dots / view_lens, 0, 1)

    n_visible = visible_mask.sum()
    dir_texels = 0

    for fi in np.where(visible_mask)[0]:
        f = faces[fi]
        fw = facing_strength[fi]

        # Get UV coords of this triangle's 3 vertices in atlas pixel space
        uv0 = uvs[f[0]]
        uv1 = uvs[f[1]]
        uv2 = uvs[f[2]]
        tx0 = uv0[0] * (ATLAS_SIZE - 1)
        ty0 = (1 - uv0[1]) * (ATLAS_SIZE - 1)
        tx1 = uv1[0] * (ATLAS_SIZE - 1)
        ty1 = (1 - uv1[1]) * (ATLAS_SIZE - 1)
        tx2 = uv2[0] * (ATLAS_SIZE - 1)
        ty2 = (1 - uv2[1]) * (ATLAS_SIZE - 1)

        # Bounding box in UV space
        min_tx = max(0, int(min(tx0, tx1, tx2)))
        max_tx = min(ATLAS_SIZE - 1, int(max(tx0, tx1, tx2)) + 1)
        min_ty = max(0, int(min(ty0, ty1, ty2)))
        max_ty = min(ATLAS_SIZE - 1, int(max(ty0, ty1, ty2)) + 1)

        if max_tx - min_tx > ATLAS_SIZE // 2 or max_ty - min_ty > ATLAS_SIZE // 2:
            continue  # Skip degenerate UV triangles that wrap around

        # Get 3D positions of this triangle's vertices
        p0 = verts[f[0]]
        p1 = verts[f[1]]
        p2 = verts[f[2]]

        # Rasterize: for each texel in bbox, check if inside UV triangle
        # Use barycentric coordinates
        denom = (ty1 - ty2) * (tx0 - tx2) + (tx2 - tx1) * (ty0 - ty2)
        if abs(denom) < 1e-6:
            continue

        for ty in range(min_ty, max_ty + 1):
            for tx in range(min_tx, max_tx + 1):
                # Barycentric coords
                w0 = ((ty1 - ty2) * (tx - tx2) + (tx2 - tx1) * (ty - ty2)) / denom
                w1 = ((ty2 - ty0) * (tx - tx2) + (tx0 - tx2) * (ty - ty2)) / denom
                w2 = 1.0 - w0 - w1

                if w0 < -0.01 or w1 < -0.01 or w2 < -0.01:
                    continue  # Outside triangle

                # Interpolate 3D position
                pt3d = w0 * p0 + w1 * p1 + w2 * p2

                # Project to image
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
    logger.info(f"{direction}: {n_visible} visible faces, {dir_texels} texels filled")

logger.info(f"\nTotal texels filled: {total_texels}")
coverage = (weight > 0).sum() / (ATLAS_SIZE * ATLAS_SIZE) * 100
logger.info(f"Atlas coverage: {coverage:.1f}%")

# ── 9. Delight texture (remove baked room lighting) ────────────────────────
logger.info("Delighting texture (removing baked room lighting)...")
covered = weight > 0
if covered.any():
    lab = cv2.cvtColor(texture, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]

    # Homomorphic high-pass: removes smooth lighting gradients, keeps albedo
    sigma = ATLAS_SIZE // 4 | 1  # larger sigma = only remove very broad gradients
    L_log = np.log1p(L)
    L_blur = cv2.GaussianBlur(L_log, (sigma, sigma), 0)
    L_highpass = L_log - L_blur

    # Rescale to preserve original brightness range (not squash to grey)
    L_new = np.expm1(L_highpass)
    L_min, L_max = L[covered].min(), L[covered].max()
    L_new_norm = (L_new - L_new.min()) / (L_new.max() - L_new.min() + 1e-6)
    L_new = L_new_norm * (L_max - L_min) + L_min

    # 35% delighted + 65% original — gentle correction, preserve natural skin tones
    lab[:, :, 0] = np.where(covered, L_new * 0.35 + L * 0.65, L)

    # Very slight desaturation of colored light tints (keep skin warm)
    ab_center = 128.0
    for ch in [1, 2]:
        lab[:, :, ch] = np.where(
            covered,
            (lab[:, :, ch] - ab_center) * 0.95 + ab_center,
            lab[:, :, ch]
        )

    texture = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
    logger.info("Delighting applied")

# ── 10. Gap inpainting ─────────────────────────────────────────────────────
mask_unfilled = (weight == 0).astype(np.uint8) * 255
if mask_unfilled.any():
    texture = cv2.inpaint(texture, mask_unfilled, inpaintRadius=8, flags=cv2.INPAINT_TELEA)

# ── 11. Export GLB ──────────────────────────────────────────────────────────
from core.mesh_reconstruction import export_glb

out_path = os.path.join(os.path.dirname(__file__), '..', 'meshes', 'smpl_direct.glb')
os.makedirs(os.path.dirname(out_path), exist_ok=True)

verts_m = verts / 1000.0
export_glb(verts_m, faces, out_path, uvs=uvs, texture_image=texture)
logger.info(f"\nGLB saved: {out_path}")
logger.info(f"Verts: {len(verts)}, Faces: {len(faces)}, Texture: {ATLAS_SIZE}x{ATLAS_SIZE}")

# Copy to viewer
import shutil
viewer_path = os.path.join(os.path.dirname(__file__), '..', 'web_app', 'static', 'viewer3d', 'smpl_direct.glb')
shutil.copy2(out_path, viewer_path)
logger.info(f"Copied to viewer: {viewer_path}")

# Save texture for inspection
tex_path = os.path.join(os.path.dirname(out_path), 'smpl_texture_debug.png')
cv2.imwrite(tex_path, texture)
logger.info(f"Texture saved: {tex_path}")
