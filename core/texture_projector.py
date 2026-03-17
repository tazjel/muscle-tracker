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
        img = view['image']
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

        for fi in np.where(dots > 0)[0]:
            facing_w = float(dots[fi] / view_lens[fi])  # cosine weight

            for vi in faces[fi]:
                rel = vertices[vi] - cam_pos
                depth = float(np.dot(rel, cam_fwd))
                if depth < 10.0:
                    continue
                px = np.dot(rel, cam_right) / depth * focal_px + w_img / 2
                py = -np.dot(rel, cam_up)   / depth * focal_px + h_img / 2
                ix, iy = int(px), int(py)
                if not (0 <= ix < w_img and 0 <= iy < h_img):
                    continue

                color = img[iy, ix]
                u, v_coord = uvs[vi]
                tx = max(0, min(atlas_size - 1, int(u * (atlas_size - 1))))
                ty = max(0, min(atlas_size - 1, int((1.0 - v_coord) * (atlas_size - 1))))

                w_old = weight[ty, tx]
                w_new = w_old + facing_w
                texture[ty, tx] = (
                    (texture[ty, tx].astype(np.float32) * w_old +
                     color.astype(np.float32) * facing_w)
                    / (w_new + 1e-8)
                ).astype(np.uint8)
                weight[ty, tx] = w_new

    return texture, weight
