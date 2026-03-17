"""
uv_unwrap.py — Assign UV coordinates to parametric body mesh.

UV atlas layout (2048×2048 texture):
  Top half (v 0.5–1.0):
    Left quarter:   left arm  (part 2)
    Centre-left:    torso     (part 0)
    Centre-right:   (unused — torso back, same UV island)
    Right quarter:  right arm (part 1)
  Bottom half (v 0.0–0.5):
    Left quarter:   left leg  (part 4)
    Centre:         (spare)
    Right quarter:  right leg (part 3)

Each body segment uses cylindrical projection:
  u = angle / (2π)   → horizontal position around the ring
  v = z_normalized    → vertical position along the segment
"""
import numpy as np
import math


DEFAULT_ATLAS = {
    0: (0.25, 0.50, 0.75, 1.00),   # torso: centre top half
    1: (0.75, 0.50, 1.00, 1.00),   # right arm: right top quarter
    2: (0.00, 0.50, 0.25, 1.00),   # left arm: left top quarter
    3: (0.75, 0.00, 1.00, 0.50),   # right leg: right bottom quarter
    4: (0.00, 0.00, 0.25, 0.50),   # left leg: left bottom quarter
}


def compute_uvs(vertices: np.ndarray, body_part_ids: np.ndarray,
                atlas_layout: dict = None) -> np.ndarray:
    """
    Compute UV coordinates for each vertex using cylindrical projection
    per body part, mapped into the atlas layout regions.

    Args:
        vertices:      (N, 3) float32 array — vertex positions in mm
        body_part_ids: (N,)   int array     — body part per vertex
                          0=torso, 1=right_arm, 2=left_arm,
                          3=right_leg, 4=left_leg
        atlas_layout:  dict mapping part_id → (u_min, v_min, u_max, v_max)
                       Defaults to DEFAULT_ATLAS if None.

    Returns:
        uvs: (N, 2) float32 array — UV coordinates in [0, 1]
    """
    if atlas_layout is None:
        atlas_layout = DEFAULT_ATLAS

    uvs = np.zeros((len(vertices), 2), dtype=np.float32)

    for part_id, (u_min, v_min, u_max, v_max) in atlas_layout.items():
        mask = body_part_ids == part_id
        if not np.any(mask):
            continue
        part_verts = vertices[mask]

        # Cylindrical projection from the part's horizontal centre
        cx = part_verts[:, 0].mean()
        cy = part_verts[:, 1].mean()
        angles = np.arctan2(part_verts[:, 1] - cy, part_verts[:, 0] - cx)
        u_local = (angles + math.pi) / (2 * math.pi)  # 0..1

        z_min = part_verts[:, 2].min()
        z_max = part_verts[:, 2].max()
        if z_max > z_min:
            v_local = (part_verts[:, 2] - z_min) / (z_max - z_min)
        else:
            v_local = np.full(len(part_verts), 0.5, dtype=np.float32)

        uvs[mask, 0] = u_min + u_local * (u_max - u_min)
        uvs[mask, 1] = v_min + v_local * (v_max - v_min)

    return uvs
