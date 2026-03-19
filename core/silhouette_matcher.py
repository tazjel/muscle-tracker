"""
silhouette_matcher.py — Deform 3D body mesh to match 2D photo silhouettes.

Algorithm (iterative boundary-vertex projection):
  1. Project mesh vertices to 2D from the camera viewpoint
  2. Find boundary vertices (those on the mesh's projected outline)
  3. For each boundary vertex, find the nearest point on the photo silhouette
  4. Move vertex 30% of the distance toward that contour point (damped)
  5. Apply Laplacian smoothing to prevent spikes
  6. Repeat for N iterations, alternating between views

No neural nets, no optimisation library — just iterative vertex displacement.

All units: mm.
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


# ── Depth displacement ────────────────────────────────────────────────────────

def _displace_from_depth(vertices, boundary_mask, depth_map, direction,
                         distance_mm, cam_height_mm, depth_weight=0.15):
    """
    Displace boundary vertices along the view depth axis to match depth map.

    For front/back views: adjusts Y axis (depth into scene).
    For left/right views: adjusts X axis (depth into scene).
    Only applies when depth_map is metric.
    """
    if depth_map is None or not depth_map.get('is_metric'):
        return vertices

    depth = depth_map['depth']
    h, w = depth.shape

    # Project current vertices to 2D
    proj_2d = _project_vertices(vertices, direction, distance_mm, cam_height_mm)

    # Map projected coordinates to depth map pixel space
    x_min, x_max = proj_2d[:, 0].min(), proj_2d[:, 0].max()
    y_min, y_max = proj_2d[:, 1].min(), proj_2d[:, 1].max()

    x_range = max(x_max - x_min, 1.0)
    y_range = max(y_max - y_min, 1.0)

    x_px = np.clip(((proj_2d[:, 0] - x_min) / x_range * (w - 1)).astype(int), 0, w - 1)
    y_px = np.clip(((proj_2d[:, 1] - y_min) / y_range * (h - 1)).astype(int), 0, h - 1)

    sampled_depth = depth[y_px, x_px]

    # Depth axis: Y for front/back views, X for left/right views
    if direction in ('front', 'back'):
        depth_axis = 1  # Y
    else:
        depth_axis = 0  # X

    boundary_idxs = np.where(boundary_mask)[0]
    for i in boundary_idxs:
        target_depth = sampled_depth[i]
        current_depth = abs(vertices[i, depth_axis])
        delta = (target_depth - current_depth) * depth_weight

        if direction in ('front', 'left'):
            vertices[i, depth_axis] -= delta
        else:
            vertices[i, depth_axis] += delta

    return vertices


# ── Public entry point ────────────────────────────────────────────────────────

def fit_mesh_to_silhouettes(vertices: np.ndarray, faces: np.ndarray,
                            silhouette_views: list,
                            iterations: int = 15,
                            step: float = 0.30,
                            depth_maps: list = None) -> np.ndarray:
    """
    Deform mesh vertices to match 2D silhouettes from one or more views.

    Args:
        vertices:        (N, 3) float32 — initial vertex positions in mm.
        faces:           (M, 3) uint32  — triangle indices.
        silhouette_views: list of dicts, each with:
            'contour_mm'   (K, 2) float32 — ordered silhouette points in mm
                            (image-space: x=right, y=down)
            'direction'    'front'|'back'|'left'|'right'
            'distance_mm'  float — camera distance in mm
            'camera_height_mm' float — camera height from floor in mm
        iterations:      number of deformation iterations (default 15).
        step:            fraction to move vertex per iteration (default 0.30).
        depth_maps:      optional list of dicts with 'depth', 'is_metric', 'direction'
                         from depth_estimator.estimate_depth().

    Returns:
        deformed: (N, 3) float32 — updated vertex positions in mm.
    """
    verts = vertices.copy().astype(np.float64)
    # Build adjacency list once for Laplacian smoothing
    adj = _build_adjacency(len(verts), faces)

    for it in range(iterations):
        for view in silhouette_views:
            contour_mm = view.get('contour_mm')
            if contour_mm is None or len(contour_mm) < 4:
                continue
            direction  = view.get('direction', 'front')
            dist_mm    = float(view.get('distance_mm', 1000.0))
            cam_h_mm   = float(view.get('camera_height_mm', 650.0))

            # Project vertices to 2D image space for this view
            proj2d = _project_vertices(verts, direction, dist_mm, cam_h_mm)

            # Find boundary vertices in the projected image
            boundary_mask = _find_boundary_vertices(verts, faces, direction)

            # Displace boundary vertices toward silhouette
            verts = _displace_to_silhouette(
                verts, proj2d, boundary_mask, contour_mm,
                direction, dist_mm, cam_h_mm, step,
            )

            # Depth-based displacement (if depth maps provided)
            if depth_maps:
                matching_depth = None
                for dm in depth_maps:
                    if dm.get('direction') == direction:
                        matching_depth = dm
                        break
                if matching_depth:
                    verts = _displace_from_depth(
                        verts, boundary_mask, matching_depth,
                        direction, dist_mm, cam_h_mm,
                        depth_weight=step * 0.5,
                    )

        # Laplacian smoothing (light — preserve large-scale shape)
        verts = _laplacian_smooth(verts, adj, alpha=0.05)

    logger.info("silhouette_matcher: %d iterations complete", iterations)
    return verts.astype(np.float32)


# ── Projection ────────────────────────────────────────────────────────────────

def _project_vertices(verts: np.ndarray, direction: str,
                      dist_mm: float, cam_h_mm: float) -> np.ndarray:
    """
    Pinhole perspective projection of 3D vertices to 2D image space.

    Output is scaled by dist_mm so units match contour_mm (mm at reference dist).
    Image axes: x_img = right, y_img = down (matching OpenCV/camera convention).

    Returns:
        proj: (N, 2) float64 — projected (x_img, y_img) in mm
    """
    if direction in ('front', 'back'):
        sign = 1.0 if direction == 'front' else -1.0
        dx = verts[:, 0] * sign
        # Depth: camera is at Y = -dist_mm*sign; vertex depth = dist_mm + Y*sign
        depth = dist_mm + verts[:, 1] * sign
        dz = cam_h_mm - verts[:, 2]
    else:  # left / right
        sign = 1.0 if direction == 'right' else -1.0
        dx = verts[:, 1] * sign
        depth = dist_mm + verts[:, 0] * sign
        dz = cam_h_mm - verts[:, 2]

    safe_depth = np.maximum(depth, 10.0)
    # Scale by dist_mm so output is in mm at reference distance (compatible with contour_mm)
    x_img = dx / safe_depth * dist_mm
    y_img = dz / safe_depth * dist_mm
    return np.stack([x_img, y_img], axis=1)


def _unproject_delta(dx_img: float, dy_img: float, direction: str) -> np.ndarray:
    """
    Convert a 2D image-space delta (mm) back to a 3D world-space delta (mm).
    Only the two visible axes are modified; depth (toward camera) is unchanged.
    """
    if direction in ('front', 'back'):
        sign = 1.0 if direction == 'front' else -1.0
        return np.array([dx_img * sign, 0.0, -dy_img])
    else:
        sign = 1.0 if direction == 'right' else -1.0
        return np.array([0.0, dx_img * sign, -dy_img])


# ── Boundary detection ────────────────────────────────────────────────────────

def _find_boundary_vertices(verts: np.ndarray, faces: np.ndarray,
                            direction: str) -> np.ndarray:
    """
    Identify which vertices sit on the silhouette boundary when viewed
    from `direction`.

    A vertex is a boundary vertex if it belongs to at least one front-facing
    face AND at least one back-facing face (when projected orthographically).

    Returns:
        mask: (N,) bool
    """
    # Camera forward vector for back-face determination
    fwd_map = {
        'front': np.array([0.0,  1.0, 0.0]),
        'back':  np.array([0.0, -1.0, 0.0]),
        'left':  np.array([-1.0, 0.0, 0.0]),
        'right': np.array([1.0,  0.0, 0.0]),
    }
    fwd = fwd_map.get(direction, np.array([0.0, 1.0, 0.0]))

    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    normals = np.cross(v1 - v0, v2 - v0)
    dot = (normals * fwd).sum(axis=1)

    front_facing = dot > 0
    back_facing  = dot < 0

    # Vertices touching at least one front-facing face
    front_verts = np.zeros(len(verts), dtype=bool)
    back_verts  = np.zeros(len(verts), dtype=bool)
    for fi in np.where(front_facing)[0]:
        front_verts[faces[fi]] = True
    for fi in np.where(back_facing)[0]:
        back_verts[faces[fi]] = True

    return front_verts & back_verts


# ── Displacement ──────────────────────────────────────────────────────────────

def _displace_to_silhouette(verts: np.ndarray, proj2d: np.ndarray,
                             boundary_mask: np.ndarray, contour_mm: np.ndarray,
                             direction: str, dist_mm: float, cam_h_mm: float,
                             step: float) -> np.ndarray:
    """
    Move each boundary vertex toward the nearest silhouette point.

    Args:
        verts:         (N, 3) float64 — current vertex positions
        proj2d:        (N, 2) float64 — projected 2D positions
        boundary_mask: (N,)   bool    — which vertices are boundary
        contour_mm:    (K, 2) float32 — silhouette contour points
        step:          damping factor (0 < step ≤ 1)
    """
    boundary_idxs = np.where(boundary_mask)[0]
    if len(boundary_idxs) == 0:
        return verts

    contour = contour_mm.astype(np.float64)

    for vi in boundary_idxs:
        px, py = proj2d[vi]
        # Nearest silhouette point (brute-force: K is typically < 2000)
        diffs = contour - np.array([px, py])
        dists = (diffs[:, 0] ** 2 + diffs[:, 1] ** 2)
        nearest_idx = int(np.argmin(dists))
        nearest = contour[nearest_idx]

        dx_img = (nearest[0] - px) * step
        dy_img = (nearest[1] - py) * step

        delta3d = _unproject_delta(dx_img, dy_img, direction)
        verts[vi] += delta3d

    return verts


# ── Laplacian smoothing ───────────────────────────────────────────────────────

def _build_adjacency(num_verts: int, faces: np.ndarray) -> list:
    """Build a list of neighbour index sets for each vertex."""
    adj = [set() for _ in range(num_verts)]
    for f in faces:
        adj[f[0]].add(f[1]); adj[f[0]].add(f[2])
        adj[f[1]].add(f[0]); adj[f[1]].add(f[2])
        adj[f[2]].add(f[0]); adj[f[2]].add(f[1])
    return adj


def _laplacian_smooth(verts: np.ndarray, adj: list, alpha: float = 0.05) -> np.ndarray:
    """
    One step of Laplacian smoothing.
    Each vertex moves alpha × (average_of_neighbours − self).
    alpha=0.05 is light — preserves shape while removing spikes.
    """
    new_verts = verts.copy()
    for i, neighbours in enumerate(adj):
        if not neighbours:
            continue
        nbr = np.array(list(neighbours))
        mean_pos = verts[nbr].mean(axis=0)
        new_verts[i] += alpha * (mean_pos - verts[i])
    return new_verts
