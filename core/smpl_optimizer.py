"""
smpl_optimizer.py — Fit SMPL shape to photo silhouettes via parameter optimization.

Replaces free-form vertex displacement (silhouette_matcher.py) with
optimization over SMPL's 10 beta parameters.

  Old approach: 20,670 free parameters, no anatomical constraints
  This module: 10 parameters, always valid body shape, accurate measurements

Algorithm:
  1. SMPL forward: betas -> 6890 vertices via linear blend shapes
  2. Project mesh boundary to 2D for each camera view
  3. Bidirectional chamfer distance to photo silhouettes
  4. L-BFGS-B minimization (bounded +/-3 sigma, L2 regularized)
  5. Extract 15+ body measurements from optimized mesh cross-sections
"""

import numpy as np
import pickle
import os
import logging
from collections import defaultdict
from scipy.optimize import minimize
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

# Search paths for SMPL model
_SMPL_PATHS = [
    os.path.expanduser('~/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl'),
    os.path.join(os.path.dirname(__file__), '..', 'runpod', 'SMPL_NEUTRAL.pkl'),
    os.path.join(os.path.dirname(__file__), '..', 'meshes', 'SMPL_NEUTRAL.pkl'),
]

_smpl_cache = None


# -- SMPL model ----------------------------------------------------------------

def _find_smpl_pkl():
    for p in _SMPL_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        f"SMPL_NEUTRAL.pkl not found in any of: {_SMPL_PATHS}")


def _load_smpl():
    """Load and cache SMPL neutral model."""
    global _smpl_cache
    if _smpl_cache is not None:
        return _smpl_cache
    path = _find_smpl_pkl()
    with open(path, 'rb') as f:
        d = pickle.load(f, encoding='latin1')
    _smpl_cache = {
        'v_template': d['v_template'].astype(np.float64),        # (6890, 3)
        'shapedirs':  d['shapedirs'].astype(np.float64),         # (6890, 3, 10)
        'faces':      d['f'].astype(np.uint32),                  # (13776, 3)
        'J_regressor': np.asarray(
            d['J_regressor'].todense() if hasattr(d['J_regressor'], 'todense')
            else d['J_regressor'], dtype=np.float64),            # (24, 6890)
    }
    logger.info("SMPL loaded from %s", path)
    return _smpl_cache


def smpl_forward(betas):
    """
    SMPL shape-only forward pass (T-pose, no pose blend shapes).

    Args:
        betas: (10,) shape blend weights

    Returns:
        verts:  (6890, 3) float64, mm, Z-up, feet on floor, XY centered
        joints: (24, 3)   float64, mm, same frame
    """
    s = _load_smpl()
    b = np.asarray(betas, np.float64).ravel()
    if len(b) < 10:
        b = np.pad(b, (0, 10 - len(b)))
    else:
        b = b[:10]

    # Shape blend: v_template + sum_i(shapedirs[:,:,i] * betas[i])
    verts_y = s['v_template'] + np.einsum('vci,i->vc', s['shapedirs'], b)
    joints_y = s['J_regressor'] @ verts_y

    # SMPL Y-up -> pipeline Z-up, meters -> mm
    verts  = verts_y[:, [0, 2, 1]]  * 1000.0
    joints = joints_y[:, [0, 2, 1]] * 1000.0

    # Ground plane + center
    z0 = verts[:, 2].min()
    x0 = verts[:, 0].mean()
    y0 = verts[:, 1].mean()
    verts[:, 0]  -= x0; verts[:, 1]  -= y0; verts[:, 2]  -= z0
    joints[:, 0] -= x0; joints[:, 1] -= y0; joints[:, 2] -= z0

    return verts, joints


def get_faces():
    """Return SMPL face array (13776, 3) uint32."""
    return _load_smpl()['faces']


# -- Projection & boundary ----------------------------------------------------

def _project(verts, direction, dist_mm, cam_h_mm):
    """Pinhole perspective projection -> 2D (mm at reference distance)."""
    if direction in ('front', 'back'):
        s = 1.0 if direction == 'front' else -1.0
        dx    = verts[:, 0] * s
        depth = dist_mm + verts[:, 1] * s
    else:
        s = 1.0 if direction == 'right' else -1.0
        dx    = verts[:, 1] * s
        depth = dist_mm + verts[:, 0] * s
    dz   = cam_h_mm - verts[:, 2]
    safe = np.maximum(depth, 10.0)
    return np.stack([dx / safe * dist_mm, dz / safe * dist_mm], axis=1)


def _boundary(verts, faces, direction):
    """Vectorized silhouette-edge vertex detection (no Python face loop)."""
    fwd = {'front': [0, 1, 0], 'back': [0, -1, 0],
            'left': [-1, 0, 0], 'right': [1, 0, 0]}[direction]
    fwd = np.asarray(fwd, np.float64)

    dot = np.cross(verts[faces[:, 1]] - verts[faces[:, 0]],
                   verts[faces[:, 2]] - verts[faces[:, 0]]) @ fwd

    n = len(verts)
    fc = np.zeros(n, np.int32)
    bc = np.zeros(n, np.int32)
    np.add.at(fc, faces[dot > 0].ravel(), 1)
    np.add.at(bc, faces[dot < 0].ravel(), 1)
    return (fc > 0) & (bc > 0)


def render_silhouette(verts, faces, direction, dist_mm=2300.0, cam_h_mm=650.0):
    """
    Render mesh boundary as ordered 2D contour (mm).
    Useful for generating synthetic test silhouettes.

    Returns: (K, 2) float32 ordered contour points
    """
    proj = _project(verts, direction, dist_mm, cam_h_mm)
    mask = _boundary(verts, faces, direction)
    pts  = proj[mask]
    if len(pts) < 3:
        return pts.astype(np.float32)
    c = pts.mean(axis=0)
    order = np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))
    return pts[order].astype(np.float32)


# -- Optimizer -----------------------------------------------------------------

def optimize_betas(silhouette_views, initial_betas=None,
                   max_iter=80, reg_weight=0.005, verbose=False):
    """
    Optimize SMPL shape to match photo silhouettes.

    Args:
        silhouette_views: list of dicts, each with:
            'contour_mm':       (K, 2) float — silhouette points in mm
            'direction':        'front'|'back'|'left'|'right'
            'distance_mm':      float (default 2300)
            'camera_height_mm': float (default 650)
        initial_betas: (10,) starting point (default: zeros = average body)
        max_iter:   L-BFGS-B iteration limit
        reg_weight: L2 penalty on betas (keeps shape plausible)
        verbose:    print progress every 10 evaluations

    Returns:
        dict with keys:
            betas, vertices, joints, faces, measurements,
            loss_history, converged, n_evals
    """
    faces = _load_smpl()['faces']
    b0 = (np.zeros(10, np.float64) if initial_betas is None
          else np.asarray(initial_betas, np.float64).ravel()[:10])

    # Pre-build KD-trees for photo contours (they don't change)
    vdata = []
    for sv in silhouette_views:
        c = sv['contour_mm'].astype(np.float64)
        vdata.append({
            'contour': c,
            'tree':    cKDTree(c),
            'dir':     sv.get('direction', 'front'),
            'dist':    float(sv.get('distance_mm', 2300)),
            'camh':    float(sv.get('camera_height_mm', 650)),
        })

    hist = []

    def loss_fn(betas):
        v, _ = smpl_forward(betas)
        L = 0.0
        for vd in vdata:
            p = _project(v, vd['dir'], vd['dist'], vd['camh'])
            b = _boundary(v, faces, vd['dir'])
            rend = p[b]
            if len(rend) < 10:
                L += 1e6
                continue
            # Bidirectional chamfer distance
            d_fwd, _ = vd['tree'].query(rend)           # rendered -> photo
            d_rev, _ = cKDTree(rend).query(vd['contour'])  # photo -> rendered
            L += d_fwd.mean() + d_rev.mean()
        L += reg_weight * (betas ** 2).sum()
        hist.append(float(L))
        if verbose and len(hist) % 10 == 0:
            logger.info("  eval %d: loss=%.4f", len(hist), L)
        return L

    res = minimize(
        loss_fn, b0,
        method='L-BFGS-B',
        bounds=[(-3.0, 3.0)] * 10,
        options={'maxiter': max_iter, 'ftol': 1e-9},
    )

    opt_b = res.x.astype(np.float32)
    opt_v, opt_j = smpl_forward(opt_b)
    meas = extract_measurements(opt_v, opt_j, faces)

    logger.info("Optimizer done: %d evals, loss %.4f -> %.4f, converged=%s",
                res.nfev, hist[0] if hist else 0, hist[-1] if hist else 0,
                res.success)

    return {
        'betas':        opt_b,
        'vertices':     opt_v.astype(np.float32),
        'joints':       opt_j.astype(np.float32),
        'faces':        faces,
        'measurements': meas,
        'loss_history': hist,
        'converged':    res.success,
        'n_evals':      res.nfev,
    }


# -- Cross-section measurement -------------------------------------------------

# SMPL 24-joint index map
_J = dict(
    pelvis=0, l_hip=1, r_hip=2, spine1=3, l_knee=4, r_knee=5,
    spine2=6, l_ankle=7, r_ankle=8, spine3=9, l_foot=10, r_foot=11,
    neck=12, l_collar=13, r_collar=14, head=15,
    l_shoulder=16, r_shoulder=17, l_elbow=18, r_elbow=19,
    l_wrist=20, r_wrist=21,
)


def _circumference(verts, faces, plane_pt, plane_n):
    """
    Mesh cross-section perimeter of the largest loop (mm).

    Correctly handles multiple disconnected loops (e.g., torso + arms
    at the same height) by chaining face-edge crossings into loops
    and returning only the largest.
    """
    plane_pt = np.asarray(plane_pt, np.float64)
    plane_n  = np.asarray(plane_n,  np.float64)
    nlen = np.linalg.norm(plane_n)
    if nlen < 1e-10:
        return 0.0
    plane_n = plane_n / nlen

    # Signed distance of each vertex to the cutting plane
    sd = (verts - plane_pt) @ plane_n

    # Vectorized: find which of the 3 edges per face cross the plane
    d0, d1, d2 = sd[faces[:, 0]], sd[faces[:, 1]], sd[faces[:, 2]]
    cross = np.column_stack([d0 * d1 < 0, d1 * d2 < 0, d2 * d0 < 0])
    valid_fi = np.where(cross.sum(axis=1) == 2)[0]

    if len(valid_fi) == 0:
        return 0.0

    # For each valid face, compute the two edge crossing points
    _edge_pairs = [(0, 1), (1, 2), (2, 0)]
    edge_point = {}   # (vi, vj) -> 3D crossing point
    segments   = []   # list of (edge_key_a, edge_key_b)

    for fi in valid_fi:
        face = faces[fi]
        seg = []
        for ei in range(3):
            if cross[fi, ei]:
                a, b = _edge_pairs[ei]
                vi, vj = int(face[a]), int(face[b])
                ek = (min(vi, vj), max(vi, vj))
                if ek not in edge_point:
                    t = sd[vi] / (sd[vi] - sd[vj])
                    edge_point[ek] = verts[vi] + t * (verts[vj] - verts[vi])
                seg.append(ek)
        if len(seg) == 2:
            segments.append((seg[0], seg[1]))

    if not segments:
        return 0.0

    # Chain segments into closed loops via adjacency
    adj = defaultdict(list)
    for a, b in segments:
        adj[a].append(b)
        adj[b].append(a)

    visited = set()
    best_perim = 0.0

    for start in adj:
        if start in visited:
            continue
        loop = []
        cur, prev = start, None
        while cur not in visited:
            visited.add(cur)
            loop.append(edge_point[cur])
            nxt = [n for n in adj[cur] if n != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]

        if len(loop) >= 3:
            pts = np.array(loop)
            diffs = np.diff(np.vstack([pts, pts[:1]]), axis=0)
            perim = float(np.linalg.norm(diffs, axis=1).sum())
            best_perim = max(best_perim, perim)

    return best_perim


def _limb_circ(verts, faces, joint_top, joint_bot):
    """Circumference at bone midpoint, perpendicular to bone axis (mm)."""
    mid  = (joint_top + joint_bot) / 2.0
    bone = joint_bot - joint_top
    return _circumference(verts, faces, mid, bone)


def _avg_limb_circ_cm(verts, faces, joints, top_name, bot_name):
    """Average L+R limb circumference in cm."""
    c_l = _limb_circ(verts, faces,
                     joints[_J[f'l_{top_name}']], joints[_J[f'l_{bot_name}']])
    c_r = _limb_circ(verts, faces,
                     joints[_J[f'r_{top_name}']], joints[_J[f'r_{bot_name}']])
    return round((c_l + c_r) / 2.0 * 0.1, 1)


def extract_measurements(verts, joints, faces):
    """
    Extract body measurements from SMPL mesh + joint positions.

    Returns dict of measurements in cm, matching DEFAULT_PROFILE keys
    from smpl_fitting.py where possible.
    """
    j = joints
    Z_UP = np.array([0.0, 0.0, 1.0])
    mm2cm = 0.1
    m = {}

    # -- Height --
    m['height_cm'] = round(float(verts[:, 2].max()) * mm2cm, 1)

    # -- Torso circumferences (horizontal slices, largest loop) --
    chest_z = (j[_J['spine2'], 2] + j[_J['neck'], 2]) / 2.0
    m['chest_circumference_cm'] = round(
        _circumference(verts, faces, [0, 0, chest_z], Z_UP) * mm2cm, 1)
    m['waist_circumference_cm'] = round(
        _circumference(verts, faces, [0, 0, j[_J['spine1'], 2]], Z_UP) * mm2cm, 1)
    m['hip_circumference_cm'] = round(
        _circumference(verts, faces, [0, 0, j[_J['pelvis'], 2]], Z_UP) * mm2cm, 1)
    m['neck_circumference_cm'] = round(
        _circumference(verts, faces, [0, 0, j[_J['neck'], 2]], Z_UP) * mm2cm, 1)

    # -- Shoulder width --
    m['shoulder_width_cm'] = round(
        abs(j[_J['l_shoulder'], 0] - j[_J['r_shoulder'], 0]) * mm2cm, 1)

    # -- Segment lengths --
    m['torso_length_cm'] = round(
        (j[_J['neck'], 2] - j[_J['pelvis'], 2]) * mm2cm, 1)
    m['floor_to_knee_cm'] = round(
        (j[_J['l_knee'], 2] + j[_J['r_knee'], 2]) / 2.0 * mm2cm, 1)

    def _bone(a, b):
        return float(np.linalg.norm(j[_J[a]] - j[_J[b]]))

    arm_l = _bone('l_shoulder', 'l_elbow') + _bone('l_elbow', 'l_wrist')
    arm_r = _bone('r_shoulder', 'r_elbow') + _bone('r_elbow', 'r_wrist')
    m['arm_length_cm'] = round((arm_l + arm_r) / 2.0 * mm2cm, 1)

    upper_l = _bone('l_shoulder', 'l_elbow')
    upper_r = _bone('r_shoulder', 'r_elbow')
    m['upper_arm_length_cm'] = round((upper_l + upper_r) / 2.0 * mm2cm, 1)

    forearm_l = _bone('l_elbow', 'l_wrist')
    forearm_r = _bone('r_elbow', 'r_wrist')
    m['forearm_length_cm'] = round((forearm_l + forearm_r) / 2.0 * mm2cm, 1)

    # -- Limb circumferences (perpendicular to bone at midpoint, avg L+R) --
    m['thigh_circumference_cm']   = _avg_limb_circ_cm(verts, faces, j, 'hip', 'knee')
    m['calf_circumference_cm']    = _avg_limb_circ_cm(verts, faces, j, 'knee', 'ankle')
    m['bicep_circumference_cm']   = _avg_limb_circ_cm(verts, faces, j, 'shoulder', 'elbow')
    m['forearm_circumference_cm'] = _avg_limb_circ_cm(verts, faces, j, 'elbow', 'wrist')

    # -- Volume-derived weight + BMI --
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    vol_mm3 = abs(float(np.sum(
        v0[:, 0] * (v1[:, 1] * v2[:, 2] - v1[:, 2] * v2[:, 1]) +
        v0[:, 1] * (v1[:, 2] * v2[:, 0] - v1[:, 0] * v2[:, 2]) +
        v0[:, 2] * (v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])
    ) / 6.0))
    weight_kg = vol_mm3 / 1e9 * 985.0   # avg body density ~985 kg/m^3
    height_m  = verts[:, 2].max() / 1000.0
    m['weight_est_kg'] = round(weight_kg, 1)
    m['bmi_est']       = round(weight_kg / max(height_m ** 2, 0.01), 1)

    return m


# -- Profile-based optimization ------------------------------------------------

def optimize_from_profile(target_profile, initial_betas=None, max_iter=120):
    """
    Find SMPL betas that produce a body matching tape-measure inputs.

    Uses joint-based targets (fast) for optimization, then extracts
    full cross-section measurements at the end for display.

    Args:
        target_profile: dict with keys like height_cm, chest_circumference_cm, etc.
        initial_betas:  (10,) starting point (default zeros)
        max_iter:       optimizer iterations

    Returns:
        dict with betas, vertices, joints, faces, measurements,
              measurement_rings (for 3D viewer), loss_history
    """
    faces = _load_smpl()['faces']
    b0 = (np.zeros(10, np.float64) if initial_betas is None
          else np.asarray(initial_betas, np.float64))
    tp = target_profile

    # Build target vector (all in mm)
    targets = {}
    if 'height_cm' in tp:
        targets['height_mm'] = tp['height_cm'] * 10.0
    if 'shoulder_width_cm' in tp:
        targets['shoulder_w_mm'] = tp['shoulder_width_cm'] * 10.0
    if 'torso_length_cm' in tp:
        targets['torso_len_mm'] = tp['torso_length_cm'] * 10.0
    if 'floor_to_knee_cm' in tp:
        targets['knee_h_mm'] = tp['floor_to_knee_cm'] * 10.0
    if 'arm_length_cm' in tp:
        targets['arm_len_mm'] = tp['arm_length_cm'] * 10.0
    if 'chest_circumference_cm' in tp:
        targets['chest_circ_mm'] = tp['chest_circumference_cm'] * 10.0
    if 'waist_circumference_cm' in tp:
        targets['waist_circ_mm'] = tp['waist_circumference_cm'] * 10.0
    if 'hip_circumference_cm' in tp:
        targets['hip_circ_mm'] = tp['hip_circumference_cm'] * 10.0

    hist = []

    def loss_fn(betas):
        v, j = smpl_forward(betas)
        err = 0.0

        # Joint-based (instant)
        if 'height_mm' in targets:
            h = float(v[:, 2].max())
            err += ((h - targets['height_mm']) / targets['height_mm']) ** 2

        if 'shoulder_w_mm' in targets:
            sw = abs(j[_J['l_shoulder'], 0] - j[_J['r_shoulder'], 0])
            err += ((sw - targets['shoulder_w_mm']) / targets['shoulder_w_mm']) ** 2

        if 'torso_len_mm' in targets:
            tl = j[_J['neck'], 2] - j[_J['pelvis'], 2]
            err += ((tl - targets['torso_len_mm']) / targets['torso_len_mm']) ** 2

        if 'knee_h_mm' in targets:
            kh = (j[_J['l_knee'], 2] + j[_J['r_knee'], 2]) / 2.0
            err += ((kh - targets['knee_h_mm']) / targets['knee_h_mm']) ** 2

        if 'arm_len_mm' in targets:
            def bl(a, b): return float(np.linalg.norm(j[_J[a]] - j[_J[b]]))
            al = (bl('l_shoulder', 'l_elbow') + bl('l_elbow', 'l_wrist') +
                  bl('r_shoulder', 'r_elbow') + bl('r_elbow', 'r_wrist')) / 2.0
            err += ((al - targets['arm_len_mm']) / targets['arm_len_mm']) ** 2

        # Cross-section based (slower but critical for body shape)
        Z = np.array([0., 0., 1.])
        if 'chest_circ_mm' in targets:
            cz = (j[_J['spine2'], 2] + j[_J['neck'], 2]) / 2.0
            cc = _circumference(v, faces, [0, 0, cz], Z)
            err += ((cc - targets['chest_circ_mm']) / targets['chest_circ_mm']) ** 2

        if 'waist_circ_mm' in targets:
            wc = _circumference(v, faces, [0, 0, j[_J['spine1'], 2]], Z)
            err += ((wc - targets['waist_circ_mm']) / targets['waist_circ_mm']) ** 2

        if 'hip_circ_mm' in targets:
            hc = _circumference(v, faces, [0, 0, j[_J['pelvis'], 2]], Z)
            err += ((hc - targets['hip_circ_mm']) / targets['hip_circ_mm']) ** 2

        err += 0.002 * np.sum(betas ** 2)
        hist.append(float(err))
        return err

    res = minimize(loss_fn, b0, method='L-BFGS-B',
                   bounds=[(-3., 3.)] * 10,
                   options={'maxiter': max_iter, 'ftol': 1e-10})

    opt_b = res.x.astype(np.float32)
    opt_v, opt_j = smpl_forward(opt_b)
    meas = extract_measurements(opt_v, opt_j, faces)

    # Build ring data for 3D viewer (height_m + radius_m for each measurement)
    j = opt_j
    rings = []

    def _add_ring(name, z_mm, circ_cm, color):
        r = (circ_cm * 10.0) / (2 * np.pi) / 1000.0  # mm -> m radius
        rings.append({
            'name': name, 'y': z_mm / 1000.0,  # Z-up mm -> Y-up meters
            'radius': round(r, 4), 'value': f"{circ_cm} cm",
            'color': color,
        })

    chest_z = (j[_J['spine2'], 2] + j[_J['neck'], 2]) / 2.0
    _add_ring('Chest',  chest_z,              meas['chest_circumference_cm'], '#ff6b6b')
    _add_ring('Waist',  j[_J['spine1'], 2],   meas['waist_circumference_cm'], '#ffd93d')
    _add_ring('Hip',    j[_J['pelvis'], 2],    meas['hip_circumference_cm'],   '#6bcb77')
    _add_ring('Neck',   j[_J['neck'], 2],      meas['neck_circumference_cm'],  '#a78bfa')

    # Height marker
    rings.append({
        'name': 'Height', 'y': opt_v[:, 2].max() / 1000.0,
        'radius': 0, 'value': f"{meas['height_cm']} cm", 'color': '#ffffff',
    })

    return {
        'betas':        opt_b,
        'vertices':     opt_v.astype(np.float32),
        'joints':       opt_j.astype(np.float32),
        'faces':        faces,
        'measurements': meas,
        'rings':        rings,
        'loss_history': hist,
        'converged':    res.success,
        'n_evals':      res.nfev,
    }
