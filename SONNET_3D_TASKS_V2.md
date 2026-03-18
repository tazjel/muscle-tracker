# Sonnet 3D Task Sheet v2 — Full Body Reconstruction

**Project**: Upgrade muscle_tracker from primitive ellipsoid-stack to realistic 3D human with skin texture and user feedback.
**Agent**: Claude Sonnet (sole owner — no Jules/Gemini boundaries)
**Date**: 2026-03-17

---

## RULES FOR SONNET

1. **DO NOT read** `companion_app/lib/main.dart` or `web_app/controllers.py` in full. Grep first, read +-30 lines.
2. After each task, run the verification command shown. Do NOT skip verification.
3. Commit after completing each task group.
4. ALL vertex coordinates are in **mm** (not cm). Heights, circumferences → multiply by 10.
5. Faces are 0-indexed uint32 triangles. Winding order: CCW = front face.
6. GLB export uses `pygltflib`. The pattern is in `core/mesh_reconstruction.py:102-175`.
7. The Three.js viewer loads GLB via URL param `?model=path.glb`. Test URL: `http://localhost:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/MESHID.glb`

## CRITICAL CONTEXT — Read These Before Starting

| What | Where | Why |
|------|-------|-----|
| Current body mesh builder | `core/smpl_fitting.py` (251 lines) | You will REWRITE `build_body_mesh()` starting at line 89 |
| GLB export function | `core/mesh_reconstruction.py:102-175` | You will ADD normals + UVs to this function |
| Three.js viewer | `web_app/static/viewer3d/body_viewer.js` (381 lines) | You will ADD region labels + texture toggle |
| Viewer HTML host | `web_app/static/viewer3d/index.html` (71 lines) | You will ADD feedback panel UI |
| Viewer CSS | `web_app/static/viewer3d/styles.css` | You will ADD adjustment panel styles |
| Measurement overlay | `web_app/static/viewer3d/measurement_overlay.js` (226 lines) | DO NOT BREAK — the wiring script on line 58-68 of index.html calls `MeasurementOverlay.init()` |
| User's body measurements | `core/smpl_fitting.py:35-57` — DEFAULT_PROFILE | These are ground-truth: height=168cm, chest=97cm, waist=90cm, etc. |

## USER'S ACTUAL MEASUREMENTS (mm — already in DEFAULT_PROFILE)

```
Height: 1680mm    Shoulder width: 370mm    Arm length: 800mm
Upper arm: 350mm  Forearm: 450mm           Torso: 500mm
Floor-to-knee: 520mm  Knee-to-belly: 400mm  Inseam: 920mm

Head circ: 560mm  Neck circ: 350mm  Chest circ: 970mm
Bicep circ: 320mm  Forearm circ: 290mm  Waist circ: 900mm
Hip circ: 920mm   Thigh circ: 530mm  Calf circ: 340mm
```

---

## TASK GROUP 1 — Anatomically Accurate Body Mesh

> Rewrite `build_body_mesh()` in `core/smpl_fitting.py`. Keep `_ellipse_ring()`, `_connect_rings()`, `fit_body_model()` — only replace the ring definitions and add limbs.

### T1.1 — High-Resolution Torso (50+ rings)

**File**: `core/smpl_fitting.py` — replace `rings_def` (lines 144-160) and the mesh-building loop (lines 162-188).

**Current**: 13 rings, 24 segments. ~338 vertices. Looks like a stack of coins.

**Target**: 35+ torso rings, 32 segments. Torso alone ~1,120 vertices. Smooth body column.

**How**: Instead of 13 hand-placed rings, generate rings by interpolating between known circumference levels. The known levels are:

```python
# Known circumference anchors (z_mm, circ_mm)
anchors = [
    (0,           calf_circ * 0.75),     # ankle
    (z_knee*0.3,  calf_circ),            # mid-calf
    (z_knee,      calf_circ * 0.95),     # knee (narrower)
    (z_mid_thigh, quad_circ),            # mid-thigh
    (z_hip,       hip_circ),             # hip/buttock
    (z_waist,     waist_circ),           # waist
    (z_chest_bot, (chest_circ+waist_circ)/2),  # lower chest
    (z_chest,     chest_circ),           # chest
    (z_shoulder,  shoulder_w * pi),      # shoulder (convert width to approx circ)
    (z_neck_base, neck_circ),            # neck base
    (z_neck_top,  neck_circ * 0.9),      # neck top
    (z_head,      head_circ),            # head widest
    (z_crown,     head_circ * 0.7),      # crown (tapers)
]
```

Then interpolate with `numpy.interp` to get 35 evenly-spaced rings:

```python
anchor_zs   = [a[0] for a in anchors]
anchor_circs = [a[1] for a in anchors]
z_levels = np.linspace(0, z_crown, 35)
circs    = np.interp(z_levels, anchor_zs, anchor_circs)
```

Each ring's radii: `a = circ / (2*pi)`, `b = a * aspect_ratio` where aspect_ratio varies by region:

```python
# Aspect ratios (front-back / left-right) by region
# Chest is flatter (wider than deep), waist is rounder, hips are wider
def aspect_at_z(z):
    if z < z_knee:       return 0.85   # legs: nearly round
    if z < z_waist:      return 0.70   # hips/thighs: wider than deep
    if z < z_chest:      return 0.65   # waist/chest: wider than deep
    if z < z_shoulder:   return 0.60   # chest: widest
    if z < z_neck_base:  return 0.95   # neck: round
    return 0.95                         # head: round
```

**Verification**:
```bash
cd C:/Users/MiEXCITE/Projects/muscle_tracker
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -c "
from core.smpl_fitting import build_body_mesh
m = build_body_mesh()
print(f'Vertices: {m[\"num_vertices\"]}')   # expect 1100-1200 (35 rings * 32 seg + 2 caps)
print(f'Faces:    {m[\"num_faces\"]}')       # expect 2100-2300
print(f'Volume:   {m[\"volume_cm3\"]} cm3')  # expect 50000-80000 (full body)
print(f'Height:   {m[\"vertices\"][:,2].max():.0f}mm')  # expect ~1680
print(f'Width:    {m[\"vertices\"][:,0].max() - m[\"vertices\"][:,0].min():.0f}mm')  # expect ~370 at shoulders
"
```

**Pitfalls**:
- Don't change `DEFAULT_PROFILE` keys — other code reads them.
- Keep `_ellipse_ring()` signature — it returns list of tuples. Convert to numpy AFTER building all rings.
- The caps (top/bottom fan) code at lines 174-188 must still work with the new ring count. The fan indexes `ring_starts[-1]` and `ring_starts[0]`.

---

### T1.2 — Add Arms and Legs as Separate Limbs

**File**: `core/smpl_fitting.py` — add after `build_body_mesh()`.

**Problem**: Current mesh is one continuous tube from ankle to head — no separate arms or legs.

**Goal**: Add left arm, right arm, left leg, right leg as separate tube meshes, stitched to the torso.

**Approach**: Build each limb as an independent ring-stack, then merge all vertices/faces into one mesh.

```python
def _build_limb(rings, segments=32):
    """Build a tube mesh from a list of (cx, cy, z, a, b) ring definitions.
    Returns (vertices_list, faces_list) with LOCAL indices starting at 0.
    """
    verts = []
    faces = []
    ring_starts = []
    for cx, cy, z, a, b in rings:
        ring_starts.append(len(verts))
        verts.extend(_ellipse_ring(cx, cy, z, a, b, segments))
    for i in range(len(rings) - 1):
        _connect_rings(verts, faces, ring_starts[i], ring_starts[i+1], segments)
    # Close end cap (top of limb = last ring)
    cap_idx = len(verts)
    verts.append((rings[-1][0], rings[-1][1], rings[-1][2]))
    rs = ring_starts[-1]
    for s in range(segments):
        faces.append([rs + s, cap_idx, rs + (s+1) % segments])
    # Close start cap (bottom of limb = first ring)
    cap_idx2 = len(verts)
    verts.append((rings[0][0], rings[0][1], rings[0][2]))
    rs0 = ring_starts[0]
    for s in range(segments):
        faces.append([rs0 + (s+1) % segments, cap_idx2, rs0 + s])
    return verts, faces


def _merge_meshes(parts):
    """Merge multiple (verts_list, faces_list) into one numpy mesh.
    Each part's face indices are offset by the cumulative vertex count.
    """
    all_verts = []
    all_faces = []
    offset = 0
    for verts, faces in parts:
        all_verts.extend(verts)
        for f in faces:
            all_faces.append([f[0]+offset, f[1]+offset, f[2]+offset])
        offset += len(verts)
    return all_verts, all_faces
```

**Arm rings** (8 per arm, from shoulder down):
```python
# Right arm — attach at (shoulder_x, 0, z_shoulder)
shoulder_x = shoulder_width_mm / 2
r_bicep  = bicep_circ / (2*pi)
r_forearm = forearm_circ / (2*pi)
r_wrist  = r_forearm * 0.6
r_hand   = hand_circ / (2*pi) if hand_circ else r_wrist * 1.1

right_arm_rings = [
    (shoulder_x,           0, z_shoulder,       r_bicep*1.1, r_bicep*0.9),  # shoulder cap
    (shoulder_x + 30,      0, z_shoulder - 50,  r_bicep, r_bicep*0.85),     # deltoid
    (shoulder_x + 50,      0, z_shoulder - 180, r_bicep, r_bicep*0.8),      # mid-bicep
    (shoulder_x + 50,      0, z_shoulder - 350, r_forearm*1.1, r_forearm),  # elbow
    (shoulder_x + 40,      0, z_shoulder - 400, r_forearm, r_forearm*0.9),  # upper forearm
    (shoulder_x + 30,      0, z_shoulder - 600, r_forearm*0.85, r_forearm*0.8), # mid forearm
    (shoulder_x + 20,      0, z_shoulder - 750, r_wrist, r_wrist),          # wrist
    (shoulder_x + 15,      0, z_shoulder - 800, r_hand, r_hand*0.5),       # hand
]
# Left arm: mirror x → -x
left_arm_rings = [(-cx, cy, z, a, b) for cx, cy, z, a, b in right_arm_rings]
```

**Leg rings** (8 per leg, from hip down):
```python
# Right leg — attach at (hip_offset, 0, z_hip)
hip_offset = hip_circ / (2*pi) * 0.45  # ~45% of hip radius
r_thigh_r = thigh_circ / (2*pi)
r_calf_r  = calf_circ / (2*pi)
r_ankle_r = r_calf_r * 0.7
r_foot    = r_ankle_r * 1.3

right_leg_rings = [
    (hip_offset, 0, z_hip,                  r_thigh_r, r_thigh_r*0.8),   # hip socket
    (hip_offset, 0, z_hip - 100,            r_thigh_r*1.05, r_thigh_r*0.8),  # upper thigh
    (hip_offset, 0, z_knee + 100,           r_thigh_r*0.9, r_thigh_r*0.7),   # above knee
    (hip_offset, 0, z_knee,                 r_calf_r*1.1, r_calf_r*0.9),     # knee
    (hip_offset, 0, z_knee - 100,           r_calf_r*1.05, r_calf_r*0.85),   # below knee
    (hip_offset, 0, z_knee * 0.4,           r_calf_r, r_calf_r*0.8),         # mid-calf
    (hip_offset, 0, 80,                     r_ankle_r, r_ankle_r),            # ankle
    (hip_offset, 20, 0,                     r_foot, r_foot*0.5),             # foot
]
# Left leg: mirror x → -x
left_leg_rings = [(-cx, cy, z, a, b) for cx, cy, z, a, b in right_leg_rings]
```

**Merge in `build_body_mesh()`**:
```python
    # After building torso rings...
    torso_verts, torso_faces = _build_limb(torso_rings, segments)
    r_arm_verts, r_arm_faces = _build_limb(right_arm_rings, segments)
    l_arm_verts, l_arm_faces = _build_limb(left_arm_rings, segments)
    r_leg_verts, r_leg_faces = _build_limb(right_leg_rings, segments)
    l_leg_verts, l_leg_faces = _build_limb(left_leg_rings, segments)

    all_verts, all_faces = _merge_meshes([
        (torso_verts, torso_faces),
        (r_arm_verts, r_arm_faces),
        (l_arm_verts, l_arm_faces),
        (r_leg_verts, r_leg_faces),
        (l_leg_verts, l_leg_faces),
    ])

    verts_np = np.array(all_verts, dtype=np.float32)
    faces_np = np.array(all_faces, dtype=np.uint32)
```

**Verification**:
```bash
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -c "
from core.smpl_fitting import build_body_mesh
m = build_body_mesh()
v = m['vertices']
print(f'Vertices: {m[\"num_vertices\"]}')  # expect 3000-5000
print(f'Faces:    {m[\"num_faces\"]}')
print(f'Height range: {v[:,2].min():.0f} to {v[:,2].max():.0f} mm')
print(f'X range: {v[:,0].min():.0f} to {v[:,0].max():.0f} mm')  # should be negative (left arm) to positive (right arm)
print(f'Arms visible: {v[:,0].max() > 250}')  # arms extend beyond shoulder
"
```

**Pitfalls**:
- Arms in A-pose: tips should hang DOWN (z decreases from shoulder). So arm ring z values DECREASE.
- Left arm mirrors right arm by negating x coordinate.
- Each leg starts at hip level and goes DOWN to floor. So z values also decrease.
- `_ellipse_ring()` takes (cx, cy, z, a, b) — the x/y center shifts per ring for arm curvature.

---

### T1.3 — Smooth Normals in GLB Export

**File**: `core/mesh_reconstruction.py` — modify `export_glb()` at line 102.

**Problem**: Current GLB has NO normals → Three.js auto-computes flat normals → visible facets.

**Goal**: Add per-vertex smooth normals via the NORMAL accessor in glTF.

**How**: After building vertices and faces, compute smooth normals:

```python
def _compute_smooth_normals(vertices, faces):
    """Average face normals at each vertex for smooth shading."""
    normals = np.zeros_like(vertices, dtype=np.float32)
    for f in faces:
        v0, v1, v2 = vertices[f[0]], vertices[f[1]], vertices[f[2]]
        n = np.cross(v1 - v0, v2 - v0)
        length = np.linalg.norm(n)
        if length > 0:
            n /= length
        normals[f[0]] += n
        normals[f[1]] += n
        normals[f[2]] += n
    # Normalize
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals /= lengths
    return normals.astype(np.float32)
```

Then add to `export_glb()`:
- Compute normals: `norms = _compute_smooth_normals(verts, tris)`
- Add `norms_binary = norms.tobytes()`
- Add accessor 2: NORMAL (VEC3, FLOAT, bufferView=2)
- Add bufferView 2: after positions
- Update `Attributes(POSITION=1, NORMAL=2)` in the Primitive
- Update buffer byteLength and binary blob: `tris_binary + verts_binary + norms_binary`

**Add `normals=True` parameter** to `export_glb()` so existing callers are not broken:
```python
def export_glb(vertices, faces, output_path, normals=True):
```

**Verification**:
```bash
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -c "
from core.smpl_fitting import fit_body_model
result = fit_body_model(output_dir='meshes', base_name='test_normals')
print(f'GLB: {result[\"glb_path\"]}')
print(f'Vertices: {result[\"num_vertices\"]}')
import os; print(f'File size: {os.path.getsize(result[\"glb_path\"])} bytes')
"
```
Then open `http://localhost:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/test_normals.glb` — mesh should be SMOOTH (no hard edges between segments).

**Pitfalls**:
- glTF bufferView byte offsets must be sequential: indices → positions → normals.
- Each bufferView's `byteOffset` = sum of all previous bufferViews' `byteLength`.
- `target` for NORMAL bufferView is `ARRAY_BUFFER` (same as positions).
- The normals accessor has `type=VEC3`, `componentType=FLOAT`, same count as positions accessor.

---

### T1.4 — A-Pose Default and Viewer Centering

**File**: `web_app/static/viewer3d/body_viewer.js` — modify `_centerAndScale()` at line 208.

**Problem**: Current auto-centering assumes a vertical mesh. With arms in A-pose, the bounding box is wider and centering needs adjustment.

**What to change**: After `_centerAndScale()`, set camera to view full body:

```javascript
// In _centerAndScale(), update the default camera position:
const box = new THREE.Box3().setFromObject(this._bodyMesh);
const size = box.getSize(new THREE.Vector3());
const maxDim = Math.max(size.x, size.y, size.z);
const fov = this._camera.fov * (Math.PI / 180);
const cameraZ = maxDim / (2 * Math.tan(fov / 2)) * 1.5;
this._camera.position.set(0, size.z * 0.45, cameraZ);
this._controls.target.set(0, size.z * 0.45, 0);
```

Also update `window.resetCamera()` at line 348 to match.

**Verification**: Load viewer → full body visible with arms, centered, no clipping.

---

## TASK GROUP 2 — Skin Texture from Camera

### T2.1 — UV Unwrapping

**File**: `core/uv_unwrap.py` (NEW file)

**Goal**: Assign (u, v) texture coordinates to every vertex in the body mesh.

**Approach**: Cylindrical projection per body part. Each body part maps to a region of the UV atlas.

```python
"""
uv_unwrap.py — Assign UV coordinates to parametric body mesh.

UV atlas layout (2048x2048 texture):
  Top half (v 0.5-1.0):
    Left quarter:  left arm
    Center-left:   torso front
    Center-right:  torso back
    Right quarter: right arm
  Bottom half (v 0.0-0.5):
    Left quarter:  left leg
    Center:        head
    Right quarter: right leg

Each body segment uses cylindrical projection:
  u = angle / (2*pi)     → horizontal position around the ring
  v = z_normalized        → vertical position along the segment
"""
import numpy as np
import math


def compute_uvs(vertices, body_part_ids, atlas_layout):
    """
    Compute UV coordinates for each vertex.

    Args:
        vertices: (N, 3) float32 array
        body_part_ids: (N,) int array — which body part each vertex belongs to
            0=torso, 1=right_arm, 2=left_arm, 3=right_leg, 4=left_leg
        atlas_layout: dict mapping part_id → (u_min, v_min, u_max, v_max)

    Returns:
        uvs: (N, 2) float32 array
    """
    uvs = np.zeros((len(vertices), 2), dtype=np.float32)
    for part_id, (u_min, v_min, u_max, v_max) in atlas_layout.items():
        mask = body_part_ids == part_id
        if not np.any(mask):
            continue
        part_verts = vertices[mask]
        # Cylindrical projection from part center
        cx = part_verts[:, 0].mean()
        cy = part_verts[:, 1].mean()
        angles = np.arctan2(part_verts[:, 1] - cy, part_verts[:, 0] - cx)
        u_local = (angles + np.pi) / (2 * np.pi)  # 0..1
        z_min, z_max = part_verts[:, 2].min(), part_verts[:, 2].max()
        if z_max > z_min:
            v_local = (part_verts[:, 2] - z_min) / (z_max - z_min)
        else:
            v_local = np.full(len(part_verts), 0.5)
        # Map to atlas region
        uvs[mask, 0] = u_min + u_local * (u_max - u_min)
        uvs[mask, 1] = v_min + v_local * (v_max - v_min)
    return uvs
```

**The body_part_ids array** must be generated in `build_body_mesh()` — assign each vertex to its body part based on which limb/torso it belongs to. Add `'body_part_ids': np.array(...)` to the return dict.

**Atlas layout** default:
```python
DEFAULT_ATLAS = {
    0: (0.25, 0.5,  0.75, 1.0),   # torso: center top half
    1: (0.75, 0.5,  1.0,  1.0),   # right arm: right top quarter
    2: (0.0,  0.5,  0.25, 1.0),   # left arm: left top quarter
    3: (0.75, 0.0,  1.0,  0.5),   # right leg: right bottom quarter
    4: (0.0,  0.0,  0.25, 0.5),   # left leg: left bottom quarter
}
```

**Verification**:
```bash
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -c "
from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
m = build_body_mesh()
uvs = compute_uvs(m['vertices'], m['body_part_ids'], DEFAULT_ATLAS)
print(f'UVs shape: {uvs.shape}')  # (N, 2)
print(f'UV range: u=[{uvs[:,0].min():.2f}, {uvs[:,0].max():.2f}]  v=[{uvs[:,1].min():.2f}, {uvs[:,1].max():.2f}]')
assert uvs.min() >= 0 and uvs.max() <= 1, 'UVs out of range!'
print('OK')
"
```

---

### T2.2 — Photo-to-Texture Projection

**File**: `core/texture_projector.py` (NEW file)

**Goal**: Project camera photos onto the UV texture atlas.

```python
"""
texture_projector.py — Project captured photos onto 3D mesh UV atlas.

Pipeline:
  1. Load body mesh + UVs
  2. For each camera view (front, back, left, right):
     a. Determine which mesh faces are visible from that camera
     b. For each visible vertex, project its 3D position to 2D image coordinates
     c. Sample the photo pixel at that 2D position
     d. Write the sampled color to the texture atlas at the vertex's UV position
  3. Blend overlapping regions (multiple views covering same UV area)
  4. Return 2048x2048 RGB texture image
"""
import cv2
import numpy as np
import math


def project_texture(vertices, faces, uvs, camera_views, atlas_size=2048):
    """
    Args:
        vertices: (N,3) float32 in mm
        faces: (M,3) uint32
        uvs: (N,2) float32 in [0,1]
        camera_views: list of dicts:
            {
                'image': np.ndarray (H,W,3) BGR,
                'direction': 'front'|'back'|'left'|'right',
                'distance_mm': float,
                'focal_mm': float,
                'sensor_width_mm': float,
            }
        atlas_size: texture resolution (default 2048)

    Returns:
        texture: (atlas_size, atlas_size, 3) uint8 BGR
        coverage: (atlas_size, atlas_size) float32 — how many views covered each pixel
    """
    texture = np.full((atlas_size, atlas_size, 3), 200, dtype=np.uint8)  # gray default
    weight  = np.zeros((atlas_size, atlas_size), dtype=np.float32)

    for view in camera_views:
        img = view['image']
        h_img, w_img = img.shape[:2]
        direction = view['direction']

        # Camera position based on direction
        dist = view['distance_mm']
        if direction == 'front':
            cam_pos = np.array([0, -dist, 800])  # in front, ~chest height
            cam_forward = np.array([0, 1, 0])
        elif direction == 'back':
            cam_pos = np.array([0, dist, 800])
            cam_forward = np.array([0, -1, 0])
        elif direction == 'left':
            cam_pos = np.array([-dist, 0, 800])
            cam_forward = np.array([1, 0, 0])
        elif direction == 'right':
            cam_pos = np.array([dist, 0, 800])
            cam_forward = np.array([-1, 0, 0])
        else:
            continue

        # Compute face normals for visibility check
        for fi in range(len(faces)):
            f = faces[fi]
            v0, v1, v2 = vertices[f[0]], vertices[f[1]], vertices[f[2]]
            face_center = (v0 + v1 + v2) / 3.0
            face_normal = np.cross(v1 - v0, v2 - v0)
            fn_len = np.linalg.norm(face_normal)
            if fn_len == 0:
                continue
            face_normal /= fn_len

            # Visibility: face normal must point toward camera
            view_dir = cam_pos - face_center
            if np.dot(face_normal, view_dir) < 0:
                continue  # back-facing

            # Project each vertex of this face to image coordinates
            # Simple pinhole projection
            focal_px = view['focal_mm'] / view['sensor_width_mm'] * w_img
            for vi in f:
                v = vertices[vi]
                rel = v - cam_pos
                # Project onto camera plane
                depth = np.dot(rel, cam_forward)
                if depth < 10:  # behind camera
                    continue
                # Image coordinates
                right = np.cross(cam_forward, np.array([0, 0, 1]))
                right /= (np.linalg.norm(right) + 1e-8)
                up = np.cross(right, cam_forward)
                px = np.dot(rel, right) / depth * focal_px + w_img / 2
                py = -np.dot(rel, up) / depth * focal_px + h_img / 2
                px, py = int(px), int(py)
                if 0 <= px < w_img and 0 <= py < h_img:
                    # Sample image color
                    color = img[py, px]
                    # Write to atlas at UV position
                    u, v_coord = uvs[vi]
                    tx = int(u * (atlas_size - 1))
                    ty = int((1 - v_coord) * (atlas_size - 1))  # flip V
                    tx = max(0, min(atlas_size-1, tx))
                    ty = max(0, min(atlas_size-1, ty))
                    w_old = weight[ty, tx]
                    # Weighted blend
                    facing_weight = max(0, np.dot(face_normal, view_dir / np.linalg.norm(view_dir)))
                    texture[ty, tx] = (
                        (texture[ty, tx].astype(float) * w_old + color.astype(float) * facing_weight)
                        / (w_old + facing_weight + 1e-8)
                    ).astype(np.uint8)
                    weight[ty, tx] += facing_weight

    return texture, weight
```

**Verification**:
```bash
# Generate a test mesh with UVs, create a dummy "front photo", project it
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -c "
import numpy as np, cv2
from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.texture_projector import project_texture

m = build_body_mesh()
uvs = compute_uvs(m['vertices'], m['body_part_ids'], DEFAULT_ATLAS)

# Dummy front photo (solid green)
front_img = np.full((2000, 1500, 3), (0, 180, 0), dtype=np.uint8)
views = [{'image': front_img, 'direction': 'front', 'distance_mm': 750, 'focal_mm': 4.0, 'sensor_width_mm': 6.4}]
tex, cov = project_texture(m['vertices'], m['faces'], uvs, views, atlas_size=512)
cv2.imwrite('meshes/test_texture.png', tex)
print(f'Texture shape: {tex.shape}, coverage: {(cov > 0).sum()} / {cov.size} pixels')
print('Wrote meshes/test_texture.png')
"
```

---

### T2.3 — Embed Texture in GLB

**File**: `core/mesh_reconstruction.py` — extend `export_glb()`.

**Goal**: Add optional `uvs` and `texture_image` parameters to `export_glb()`.

When texture is provided:
1. Add TEXCOORD_0 accessor (VEC2, FLOAT) for UV coordinates
2. Add the texture image as an embedded PNG in the binary buffer
3. Add a `baseColorTexture` to the PBR material (instead of flat `baseColorFactor`)
4. Add Image, Texture, Sampler glTF objects

```python
def export_glb(vertices, faces, output_path, normals=True,
               uvs=None, texture_image=None):
```

**glTF structure when texture is present**:
```python
# Existing: accessor 0 (indices), accessor 1 (positions), accessor 2 (normals)
# New:      accessor 3 (TEXCOORD_0) — if uvs provided
#           image 0 (embedded PNG)   — if texture_image provided
#           texture 0 (references image 0)
#           sampler 0 (linear filtering)
#           material 0 (pbrMetallicRoughness with baseColorTexture)

# Material with texture:
materials=[pygltflib.Material(
    pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
        baseColorTexture=pygltflib.TextureInfo(index=0) if texture_image is not None else None,
        baseColorFactor=[0.83, 0.65, 0.45, 1.0] if texture_image is None else None,
        roughnessFactor=0.65,
        metallicFactor=0.0,
    ),
    doubleSided=True,
)]
```

For embedding the PNG:
```python
import io
success, png_data = cv2.imencode('.png', texture_image)
png_bytes = png_data.tobytes()
# Add as a bufferView at the end of the binary blob
# Image references this bufferView
# image.mimeType = 'image/png'
# image.bufferView = <index of png bufferView>
```

**Verification**: Generate a GLB with texture → open in viewer → should show projected colors instead of flat skin tone.

**Pitfalls**:
- PNG bufferView does NOT have a `target` field (it's not vertex/index data).
- The bufferView for the PNG must be 4-byte aligned (pad with zeros if needed).
- When texture is NOT provided, fall back to the existing flat color material.
- The Primitive must reference the material: `material=0`.

---

### T2.4 — Viewer Texture Toggle

**File**: `web_app/static/viewer3d/body_viewer.js` — add to `setViewMode()` at line 316.

**Goal**: When a GLB has a texture, show it. Add a "Textured" view mode button.

The GLB loader already preserves materials from the file. When a textured GLB is loaded:
- The material will already have `map` (baseColorTexture) set by GLTFLoader.
- "Solid" mode should override with flat SKIN_MATERIAL.
- "Textured" mode should restore the original loaded material.
- Store original materials after load: `this._originalMaterials = new Map()`.

**Also update `index.html`**: Add a 4th view mode button "Textured" alongside Solid/Wire/Heat.

```html
<button class="view-mode-btn" onclick="setViewMode('textured')">Textured</button>
```

**Verification**: Load a textured GLB → toggle between Solid and Textured modes.

---

## TASK GROUP 3 — Interactive User Feedback

### T3.1 — Body Region Click Detection

**File**: `web_app/static/viewer3d/body_viewer.js` — extend `_getMeshIntersection()` at line 258.

**Goal**: Click on mesh → identify body region → highlight it.

**How**: The mesh vertices have `body_part_ids` baked in during generation. We need that info in the viewer.

**Approach**: Encode body_part_id per vertex as a custom vertex attribute, OR use a simpler method: map the hit vertex's Z-height to body region.

Simpler approach (no mesh changes needed):

```javascript
function getBodyRegion(point) {
    // point is THREE.Vector3 in model space (mm)
    const z = point.z;  // height from floor
    const x = Math.abs(point.x);  // lateral distance from center
    const meshHeight = bodyMesh ? new THREE.Box3().setFromObject(bodyMesh).getSize(new THREE.Vector3()).z : 1680;

    // Arm detection: if x > shoulder_width * 0.4 and z > hip level
    if (x > 150 && z > meshHeight * 0.55) return 'arm';
    if (x > 100 && z < meshHeight * 0.35) return 'leg';

    // Height-based regions
    const ratio = z / meshHeight;
    if (ratio > 0.90) return 'head';
    if (ratio > 0.82) return 'neck';
    if (ratio > 0.70) return 'shoulder';
    if (ratio > 0.58) return 'chest';
    if (ratio > 0.50) return 'waist';
    if (ratio > 0.40) return 'hip';
    if (ratio > 0.30) return 'thigh';
    if (ratio > 0.18) return 'knee';
    if (ratio > 0.08) return 'calf';
    return 'ankle';
}
```

On click:
1. Raycast → get hit point
2. `getBodyRegion(point)` → region name
3. Show region name in floating label
4. Highlight vertices in that region (change color)

---

### T3.2 — Adjustment Sliders Panel

**File**: `web_app/static/viewer3d/index.html` + `styles.css`

**Goal**: When a body region is selected, show a panel with sliders for Width, Depth, Length.

Add HTML after the existing card panel:

```html
<div id="adjust-panel" class="card" style="display:none;">
    <h3 id="adjust-region">Region</h3>
    <label>Width <input type="range" id="adj-width" min="-30" max="30" value="0">
        <span id="adj-width-val">0</span>mm</label>
    <label>Depth <input type="range" id="adj-depth" min="-30" max="30" value="0">
        <span id="adj-depth-val">0</span>mm</label>
    <label>Length <input type="range" id="adj-length" min="-30" max="30" value="0">
        <span id="adj-length-val">0</span>mm</label>
    <button onclick="applyAdjustment()">Apply</button>
    <button onclick="resetAdjustment()">Reset</button>
    <button onclick="saveAdjustments()">Save to Profile</button>
</div>
```

**In `body_viewer.js`**: When sliders change, modify vertex positions in real-time:

```javascript
function applySliderToRegion(region, widthDelta, depthDelta, lengthDelta) {
    // Find vertices in this region (by Z range)
    const geometry = bodyMesh.geometry || bodyMesh.children[0].geometry;
    const pos = geometry.attributes.position;
    const zRange = getRegionZRange(region);

    for (let i = 0; i < pos.count; i++) {
        const z = pos.getZ(i);
        if (z >= zRange[0] && z <= zRange[1]) {
            // Scale x (width) and y (depth) from center
            const x = pos.getX(i);
            const y = pos.getY(i);
            const dist = Math.sqrt(x*x + y*y);
            if (dist > 0) {
                const scaleX = 1 + widthDelta / (dist + 1);
                const scaleY = 1 + depthDelta / (dist + 1);
                pos.setX(i, x * scaleX);
                pos.setY(i, y * scaleY);
            }
            // Shift z for length
            pos.setZ(i, z + lengthDelta * (z - zRange[0]) / (zRange[1] - zRange[0]));
        }
    }
    pos.needsUpdate = true;
    geometry.computeBoundingBox();
}
```

---

### T3.3 — Save Adjustments to Server

**File**: `web_app/static/viewer3d/body_viewer.js` + `web_app/controllers.py`

**Goal**: "Save to Profile" button converts vertex adjustments back to measurement changes and POSTs to the body_profile API.

```javascript
async function saveAdjustments() {
    // Collect all adjustments
    const adjustments = {};
    for (const [region, deltas] of Object.entries(regionAdjustments)) {
        // Convert width/depth deltas to circumference changes
        // delta_circ = 2 * pi * delta_radius (mm → cm)
        if (deltas.width !== 0) {
            const field = regionToCircumferenceField(region);
            if (field) {
                adjustments[field] = (deltas.width * 2 * Math.PI / 10);  // mm→cm
            }
        }
    }
    // POST to server
    const resp = await fetch(`/web_app/api/customer/1/body_profile`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(adjustments),
    });
    const result = await resp.json();
    if (result.status === 'success') {
        alert('Profile updated. Regenerating mesh...');
        // Trigger mesh regeneration
        const meshResp = await fetch(`/web_app/api/customer/1/body_model`, {method: 'POST'});
        const meshResult = await meshResp.json();
        if (meshResult.glb_url) {
            window.location.href = `?model=${meshResult.glb_url}`;
        }
    }
}
```

**Mapping** region → measurement field:
```javascript
const REGION_TO_FIELD = {
    'chest':    'chest_circumference_cm',
    'waist':    'waist_circumference_cm',
    'hip':      'hip_circumference_cm',
    'thigh':    'thigh_circumference_cm',
    'calf':     'calf_circumference_cm',
    'arm':      'bicep_circumference_cm',
    'neck':     'neck_circumference_cm',
    'head':     'head_circumference_cm',
    'shoulder': 'shoulder_width_cm',
};
```

---

## TASK GROUP 4 — Silhouette Refinement

### T4.1 — Extract Clean Silhouettes from Scan Images

**File**: `core/silhouette_extractor.py` (NEW file)

**Goal**: From each captured photo, extract the body outline as an ordered 2D point array in mm.

```python
def extract_silhouette(image_path, camera_distance_cm):
    """
    Returns:
        contour_mm: (K, 2) float32 array — body outline in mm coordinates
        mask: (H, W) uint8 — binary body mask
    """
    from core.body_segmentation import segment_body
    from core.calibration import get_px_to_mm_ratio
    from core.vision_medical import _auto_orient

    img = _auto_orient(image_path)
    mask = segment_body(img)
    if mask is None:
        return None, None

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None

    main = max(contours, key=cv2.contourArea)
    ratio = get_px_to_mm_ratio(image_path, camera_distance_cm=camera_distance_cm) or 1.0
    contour_mm = main.squeeze().astype(np.float32) * ratio
    return contour_mm, mask
```

---

### T4.2 — Deform Mesh to Match Silhouettes

**File**: `core/silhouette_matcher.py` (NEW file)

**Goal**: Given 3D mesh + 2D silhouettes from front/back/side, push vertices to match.

**Algorithm**:
1. Project mesh vertices to 2D from the camera viewpoint
2. Find boundary vertices (those on the mesh's projected outline)
3. For each boundary vertex, find nearest point on the photo silhouette contour
4. Move vertex by 30% of the distance toward that contour point
5. Repeat for 15 iterations, alternating between views
6. Apply Laplacian smoothing after each iteration to prevent spikes

This is computationally simple (no neural nets, no optimization library) — just iterative vertex displacement with damping.

---

## EXECUTION ORDER

```
T1.1 (high-res torso rings)      — 1 hour — makes mesh smoother
T1.2 (arms + legs)               — 1 hour — makes mesh look human
T1.3 (smooth normals in GLB)     — 30 min — smooth shading
T1.4 (viewer centering for A-pose) — 15 min — viewer shows full body
  ↓
T3.1 (click body region)         — 30 min — user can interact
T3.2 (adjustment sliders)        — 45 min — user can adjust
T3.3 (save to profile)           — 30 min — adjustments persist
  ↓
T2.1 (UV unwrapping)             — 45 min — texture coordinate system
T2.2 (photo projection)          — 1 hour — camera → texture
T2.3 (texture in GLB)            — 45 min — embedded in model file
T2.4 (viewer texture toggle)     — 15 min — show/hide texture
  ↓
T4.1 (silhouette extraction)     — 30 min — reuse existing code
T4.2 (mesh deformation)          — 1 hour — silhouette → shape refinement
```

**Total: ~8 hours of Sonnet work across 12 tasks.**

---

## TOKEN-SAVING TIPS FOR SONNET

1. **DO NOT read `main.dart`** — you don't need it for any of these tasks.
2. **DO NOT read `controllers.py` in full** — grep for `body_model` or `reconstruct_3d` to find the 10 lines you need.
3. **`core/smpl_fitting.py` is 251 lines** — read it ONCE at the start, then edit directly.
4. **`core/mesh_reconstruction.py` is 187 lines** — only the `export_glb()` function (lines 102-175) matters.
5. **`body_viewer.js` is 381 lines** — read once, edit the specific functions named in each task.
6. **Test after each task** using the verification commands above. Don't batch multiple tasks then debug.
7. **The numpy vertex format is always `(N, 3) float32` in mm**. The face format is always `(M, 3) uint32`.
8. **When stuck on GLB export**: the pattern in `mesh_reconstruction.py:125-174` is your template. Just add more accessors + bufferViews following the same pattern.

## KEY COMMANDS

```bash
# Python with correct path
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe

# Test mesh generation
$PY -c "from core.smpl_fitting import build_body_mesh; m = build_body_mesh(); print(m['num_vertices'], m['num_faces'])"

# Generate and export GLB
$PY -c "from core.smpl_fitting import fit_body_model; print(fit_body_model(output_dir='meshes', base_name='test'))"

# Start server (must restart after code changes!)
ps aux | grep py4web | grep -v grep | awk '{print $1}' | xargs kill 2>/dev/null
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps --host 0.0.0.0 --port 8000 >> server.log 2>&1 &

# View in browser
# http://localhost:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/test.glb
```
