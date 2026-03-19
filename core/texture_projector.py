"""
texture_projector.py — Project captured photos onto 3D mesh UV atlas.

Pipeline:
  1. For each camera view (front, back, left, right):
     a. For each mesh face, check if it faces toward the camera
     b. For each visible vertex, project its 3D position to 2D image coords
     c. Sample the photo pixel at that 2D position
     d. Write the sampled colour to the texture atlas at the vertex's UV position
  2. Blend overlapping regions (multiple views covering same UV area)
  3. Return (atlas_size × atlas_size) RGB texture image
"""
import cv2
import numpy as np
import math


def _normalize_lighting(img):
    """White-balance + CLAHE on each camera view for consistent skin tone."""
    # Convert to LAB for perceptual uniformity
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # CLAHE on luminance only — preserves color, evens brightness
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)

    # Simple grey-world white balance on a/b channels
    a = cv2.add(a, int(128 - a.mean()))
    b = cv2.add(b, int(128 - b.mean()))

    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def project_texture(vertices: np.ndarray, faces: np.ndarray, uvs: np.ndarray,
                    camera_views: list, atlas_size: int = 2048):
    """
    Project camera photos onto a UV texture atlas.

    Args:
        vertices:     (N, 3) float32 — vertex positions in mm
        faces:        (M, 3) uint32  — triangle indices
        uvs:          (N, 2) float32 — UV coords in [0, 1]
        camera_views: list of dicts, each with keys:
            'image'            np.ndarray (H, W, 3) BGR
            'direction'        'front'|'back'|'left'|'right'
            'distance_mm'      float — camera distance from subject
            'focal_mm'         float — focal length in mm
            'sensor_width_mm'  float — sensor width in mm
        atlas_size:   output texture resolution (default 2048)

    Returns:
        texture:  (atlas_size, atlas_size, 3) uint8 BGR
        coverage: (atlas_size, atlas_size) float32 — accumulated weight
    """
    texture = np.full((atlas_size, atlas_size, 3), 200, dtype=np.uint8)  # grey default
    weight  = np.zeros((atlas_size, atlas_size), dtype=np.float32)

    for view in camera_views:
        img = _normalize_lighting(view['image'])
        h_img, w_img = img.shape[:2]
        direction = view['direction']
        dist      = float(view['distance_mm'])
        focal_mm  = float(view['focal_mm'])
        sensor_w  = float(view['sensor_width_mm'])

        # Camera position and forward vector by direction
        cam_defs = {
            'front': (np.array([0.0, -dist, 800.0]), np.array([0.0,  1.0, 0.0])),
            'back':  (np.array([0.0,  dist, 800.0]), np.array([0.0, -1.0, 0.0])),
            'left':  (np.array([-dist, 0.0, 800.0]), np.array([1.0,  0.0, 0.0])),
            'right': (np.array([ dist, 0.0, 800.0]), np.array([-1.0, 0.0, 0.0])),
        }
        if direction not in cam_defs:
            continue
        cam_pos, cam_fwd = cam_defs[direction]
        focal_px = focal_mm / sensor_w * w_img

        # Precompute camera axes
        up_world = np.array([0.0, 0.0, 1.0])
        cam_right = np.cross(cam_fwd, up_world)
        cr_len = np.linalg.norm(cam_right)
        if cr_len < 1e-8:
            continue
        cam_right /= cr_len
        cam_up = np.cross(cam_right, cam_fwd)

        # Precompute face normals for back-face culling
        v0 = vertices[faces[:, 0]]
        v1 = vertices[faces[:, 1]]
        v2 = vertices[faces[:, 2]]
        face_normals = np.cross(v1 - v0, v2 - v0)
        fn_lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
        fn_lens[fn_lens < 1e-10] = 1.0
        face_normals /= fn_lens

        face_centers = (v0 + v1 + v2) / 3.0
        view_vecs = cam_pos - face_centers
        dots = (face_normals * view_vecs).sum(axis=1)
        view_lens = np.linalg.norm(view_vecs, axis=1) + 1e-8

        visible_face_idxs = np.where(dots > 0)[0]
        if len(visible_face_idxs) == 0:
            continue
        vis_vert_idxs = faces[visible_face_idxs].ravel()  # (K*3,)
        facing_weights = np.repeat(
            np.clip(dots[visible_face_idxs] / view_lens[visible_face_idxs], 0, 1), 3
        )  # (K*3,)

        # Vectorized projection
        rel_verts = vertices[vis_vert_idxs] - cam_pos   # (K*3, 3)
        depth     = rel_verts @ cam_fwd                  # (K*3,)
        valid     = depth > 10.0
        rel_verts = rel_verts[valid]
        depth     = depth[valid]
        fw        = facing_weights[valid]
        vi_valid  = vis_vert_idxs[valid]

        px_all = (rel_verts @ cam_right) / depth * focal_px + w_img / 2
        py_all = -(rel_verts @ cam_up)   / depth * focal_px + h_img / 2
        ix_all = px_all.astype(int)
        iy_all = py_all.astype(int)

        in_frame = (ix_all >= 0) & (ix_all < w_img) & (iy_all >= 0) & (iy_all < h_img)
        ix_all   = ix_all[in_frame]
        iy_all   = iy_all[in_frame]
        fw       = fw[in_frame]
        vi_valid = vi_valid[in_frame]

        colors_all = img[iy_all, ix_all]  # (N, 3)

        uv_all = uvs[vi_valid]
        tx_all = np.clip((uv_all[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
        ty_all = np.clip(((1 - uv_all[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

        for i in range(len(tx_all)):
            tx, ty = tx_all[i], ty_all[i]
            w_old = weight[ty, tx]
            w_new = w_old + fw[i]
            texture[ty, tx] = (
                (texture[ty, tx].astype(np.float32) * w_old +
                 colors_all[i].astype(np.float32) * fw[i])
                / (w_new + 1e-8)
            ).astype(np.uint8)
            weight[ty, tx] = w_new

    # ── Seam blending: smooth overlap zones between views ─────────────────────
    overlap_mask = (weight > 1.0).astype(np.uint8) * 255
    if overlap_mask.any():
        kernel = np.ones((5, 5), np.uint8)
        seam_region = cv2.dilate(overlap_mask, kernel, iterations=2)
        blurred = cv2.GaussianBlur(texture, (7, 7), 0)
        alpha = seam_region.astype(np.float32) / 255.0
        for c in range(3):
            texture[:, :, c] = (
                texture[:, :, c].astype(np.float32) * (1.0 - alpha) +
                blurred[:, :, c].astype(np.float32) * alpha
            ).astype(np.uint8)

    # ── Gap inpainting: fill uncovered pixels with surrounding colors ──────────
    mask_unfilled = (weight == 0).astype(np.uint8) * 255
    if mask_unfilled.any():
        inpaint_r = max(5, atlas_size // 256)  # scale radius with atlas resolution
        texture = cv2.inpaint(texture, mask_unfilled, inpaintRadius=inpaint_r, flags=cv2.INPAINT_TELEA)

    # Return (texture, coverage_map) — weight is (H,W) float32, >0 where texture exists
    return texture, weight


def generate_ai_texture(prompt="photorealistic human skin UV texture map, seamless, "
                                "natural skin tone, subtle pores and veins, plain white background",
                        output_path=None, atlas_size=2048):
    """
    Generate an AI skin texture via the game-asset-gen MCP server (Gemini).

    This is a convenience wrapper — the actual MCP call must be made by the
    orchestrating agent (Claude). This function prepares the prompt and
    post-processes the result into a UV-ready BGR texture.

    Args:
        prompt:      text prompt for the AI image generator
        output_path: where to save the generated PNG (if None, uses temp file)
        atlas_size:  resize output to this resolution

    Returns:
        texture: (atlas_size, atlas_size, 3) uint8 BGR image, or None if file not found
    """
    import os, tempfile

    if output_path is None:
        output_path = os.path.join(tempfile.gettempdir(), 'ai_skin_texture.png')

    # The MCP tool call happens externally — this function reads the result
    if not os.path.exists(output_path):
        return None

    img = cv2.imread(output_path)
    if img is None:
        return None

    # Resize to atlas dimensions
    if img.shape[0] != atlas_size or img.shape[1] != atlas_size:
        img = cv2.resize(img, (atlas_size, atlas_size), interpolation=cv2.INTER_LANCZOS4)

    return img
