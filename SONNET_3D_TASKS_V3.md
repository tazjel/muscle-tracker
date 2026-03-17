# Sonnet 3D Task Sheet v3 — Validation, Performance & Integration

**Project**: Complete the 3D pipeline: test with real photos, fix performance, add remaining integrations.
**Agent**: Claude Sonnet
**Date**: 2026-03-17
**Prerequisite**: V2 tasks all complete. Read `handoff_next_agent.md` first.

---

## RULES

1. **DO NOT read** `main.dart` or `controllers.py` in full. Grep first, read ±40 lines.
2. Run verification after each task. Do not batch tasks then debug.
3. Commit after each task group.
4. `texture_projector.py` Python loops are intentionally slow — see P2.1 for the fix.
5. `silhouette_matcher.py` uses orthographic projection — acceptable at 100cm, see P4.1 for upgrade.

---

## PRIORITY 1 — Validate the pipeline end-to-end

### P1.1 — Test body_model endpoint (measurement-only)

No code needed. Just run:

```bash
cd C:/Users/MiEXCITE/Projects/muscle_tracker

# Start server
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps \
  --host 0.0.0.0 --port 8000 > server.log 2>&1 &

# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/web_app/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@muscle.com","password":"demo123"}' \
  | /c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe \
    -c "import sys,json; print(json.load(sys.stdin).get('token',''))")

# Generate body model
curl -s -X POST http://localhost:8000/web_app/api/customer/1/body_model \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool
```

**Expected**: `{"status":"success","glb_url":"/api/mesh/N.glb",...}`

Open in browser: `http://localhost:8000/web_app/static/viewer3d/index.html?model=/api/mesh/N.glb`

**Expected visual**: Standing A-pose human, arms extended, smooth shading, skin-tone colour.
Click on chest/thigh/arm → region label appears → slider panel opens.

**If GLB is blank/invisible**: The Z-up → Y-up rotation in body_viewer.js may need adjustment.
Check `_centerAndScale()` in `body_viewer.js` — it does `object.rotation.x = -Math.PI / 2`.

---

### P1.2 — Test with real scan photos

Pull the latest scan images captured during the dual scan session:

```bash
# Pull front image (A24)
adb -s R58W41RF6ZK exec-out \
  run-as com.example.companion_app cat cache/muscle_dual/front_0.jpg > scripts/real_front.jpg

# Pull back image (MatePad)
adb connect 192.168.100.33:5555
adb -s 192.168.100.33:5555 exec-out \
  run-as com.example.companion_app cat cache/muscle_dual/front_0.jpg > scripts/real_back.jpg

# Submit to body_model endpoint with images
curl -s -X POST http://localhost:8000/web_app/api/customer/1/body_model \
  -H "Authorization: Bearer $TOKEN" \
  -F "front_image=@scripts/real_front.jpg" \
  -F "back_image=@scripts/real_back.jpg" \
  -F "camera_distance_cm=100" | python -m json.tool
```

**Expected**: `"silhouette_views_used": 1` or 2 (if MediaPipe runs successfully).
**If silhouette_views_used is 0**: MediaPipe segmentation likely unavailable.
→ Check server.log for "MediaPipe unavailable" warnings.
→ GrabCut fallback may fail on cluttered backgrounds — acceptable for now.

---

## PRIORITY 2 — Performance

### P2.1 — Vectorize texture_projector.py

**Problem**: `project_texture()` in `core/texture_projector.py` loops over every face in Python:
```python
for fi in np.where(dots > 0)[0]:   # up to 4288 iterations
    for vi in faces[fi]:            # × 3 vertices
```
For 4288 faces × 4 views this runs ~51K Python iterations — takes 30–60 seconds.

**Fix**: The face-visibility check (`dots > 0`) is already vectorized. The remaining bottleneck
is the per-vertex sampling. Vectorize the vertex projection for all visible faces at once:

**File**: `core/texture_projector.py` — replace the inner `for fi / for vi` loop with:

```python
# Get all visible vertex indices (may have duplicates — that's fine)
visible_face_idxs = np.where(dots > 0)[0]
if len(visible_face_idxs) == 0:
    continue
vis_vert_idxs = faces[visible_face_idxs].ravel()  # shape (K*3,)
facing_weights = np.repeat(
    np.clip(dots[visible_face_idxs] / view_lens[visible_face_idxs], 0, 1),
    3
)  # shape (K*3,)

# Vectorized projection
rel_verts = vertices[vis_vert_idxs] - cam_pos          # (K*3, 3)
depth     = rel_verts @ cam_fwd                         # (K*3,)
valid     = depth > 10.0
rel_verts = rel_verts[valid]
depth     = depth[valid]
fw        = facing_weights[valid]
vi_valid  = vis_vert_idxs[valid]

px_all = (rel_verts @ cam_right) / depth * focal_px + w_img / 2
py_all = -(rel_verts @ cam_up)  / depth * focal_px + h_img / 2
ix_all = px_all.astype(int)
iy_all = py_all.astype(int)

in_frame = (ix_all >= 0) & (ix_all < w_img) & (iy_all >= 0) & (iy_all < h_img)
ix_all = ix_all[in_frame]
iy_all = iy_all[in_frame]
fw     = fw[in_frame]
vi_valid = vi_valid[in_frame]

# Sample colours
colors_all = img[iy_all, ix_all]  # (N, 3)

# Map to atlas
uv_all = uvs[vi_valid]
tx_all = np.clip((uv_all[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
ty_all = np.clip(((1 - uv_all[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

# Weighted accumulation (loop only over unique atlas pixels, not all vertices)
for i in range(len(tx_all)):
    tx, ty = tx_all[i], ty_all[i]
    w_old = weight[ty, tx]
    w_new = w_old + fw[i]
    texture[ty, tx] = (
        (texture[ty, tx].astype(np.float32) * w_old + colors_all[i].astype(np.float32) * fw[i])
        / (w_new + 1e-8)
    ).astype(np.uint8)
    weight[ty, tx] = w_new
```

**Verification**:
```bash
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -c "
import time, numpy as np, cv2
from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.texture_projector import project_texture

m = build_body_mesh()
uvs = compute_uvs(m['vertices'], m['body_part_ids'], DEFAULT_ATLAS)
img = np.full((2000,1500,3), (0,180,0), dtype=np.uint8)
views = [{'image':img,'direction':'front','distance_mm':1000,'focal_mm':4.0,'sensor_width_mm':6.4}]
t0 = time.time()
tex, cov = project_texture(m['vertices'], m['faces'], uvs, views, atlas_size=512)
print(f'Time: {time.time()-t0:.2f}s  Coverage: {(cov>0).sum()}/{cov.size}')
# Expect: < 5 seconds (was 30–60s)
"
```

---

### P2.2 — Add `body3d` command to GTDdebug

**File**: `scripts/gtddebug.py`

**Goal**: One command that captures front+back photos and generates the body model.

Grep for the existing `full` command:
```bash
grep -n "def cmd_full\|subparsers.add_parser" scripts/gtddebug.py | head -20
```

Add new subcommand `body3d`:
```python
# In the argument parser section:
p_body = subparsers.add_parser('body3d', help='Capture + generate 3D body model')
p_body.add_argument('--distance', type=float, default=100.0)
p_body.add_argument('--open', action='store_true', help='Open viewer URL in browser')

# New command handler:
def cmd_body3d(args):
    """Capture front+back, generate body model, print viewer URL."""
    print('[body3d] Setting up dual capture...')
    cmd_setup(args)                             # reconnect ADB, set roles

    print('[body3d] Triggering capture on both devices...')
    cmd_capture(args)                           # ADB tap / auto-trigger

    print('[body3d] Pulling images...')
    front_path = pull_image(PHONE_SERIAL, 'front')    # returns local path
    back_path  = pull_image(MATEPAD_SERIAL, 'back')

    print('[body3d] Logging in...')
    token = get_token()

    print('[body3d] Generating body model...')
    import requests
    with open(front_path, 'rb') as fh, open(back_path, 'rb') as bh:
        resp = requests.post(
            f'{SERVER_URL}/api/customer/1/body_model',
            headers={'Authorization': f'Bearer {token}'},
            files={'front_image': fh, 'back_image': bh},
            data={'camera_distance_cm': str(args.distance)},
        )
    r = resp.json()
    if r.get('status') == 'success':
        glb_url = r.get('glb_url', '')
        viewer  = f'http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model={glb_url}'
        print(f'[body3d] ✓ mesh_id={r["mesh_id"]} verts={r["num_vertices"]}')
        print(f'[body3d] silhouette_views_used={r.get("silhouette_views_used",0)}')
        print(f'[body3d] Viewer: {viewer}')
        if args.open:
            import webbrowser; webbrowser.open(viewer)
    else:
        print(f'[body3d] FAILED: {r}')
```

**Verification**: `python scripts/gtddebug.py body3d --distance 100 --open`

---

## PRIORITY 3 — Pipeline completeness

### P3.1 — Wire texture projection into generate_body_model

**File**: `web_app/controllers.py` — grep for `generate_body_model`, find the export block.

After `fit_mesh_to_silhouettes()` runs (and images are available), also generate a texture:

```python
# After verts are refined, if we have silhouette images + UVs:
if silhouette_views:
    try:
        from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
        from core.texture_projector import project_texture
        from core.smpl_fitting import build_body_mesh  # need body_part_ids

        mesh_full = build_body_mesh(profile)
        uvs = compute_uvs(mesh_full['vertices'], mesh_full['body_part_ids'], DEFAULT_ATLAS)

        # Rebuild camera_views list from the saved tmp images
        cam_views = []
        for sv in silhouette_views:
            img = cv2.imread(sv['_tmp_path'])  # store path in silhouette_views dict
            if img is not None:
                cam_views.append({
                    'image': img,
                    'direction': sv['direction'],
                    'distance_mm': sv['distance_mm'],
                    'focal_mm': 4.0,
                    'sensor_width_mm': 6.4,
                })

        if cam_views:
            tex, _ = project_texture(verts, faces, uvs, cam_views, atlas_size=1024)
            export_glb(verts, faces, glb_path, uvs=uvs, texture_image=tex)
    except Exception:
        logger.warning('Texture projection failed — exporting untextured GLB')
        export_glb(verts, faces, glb_path)
else:
    export_glb(verts, faces, glb_path)
```

**Note**: Store `'_tmp_path'` in each `silhouette_views` entry when saving the uploaded image.
This requires a small addition to the image-saving loop above it in the same function.

**Verification**: Submit with front_image → open GLB in viewer → switch to Textured mode → see projected photo colour on mesh.

---

### P3.2 — Segmentation quality check

**Problem**: When MediaPipe is unavailable, GrabCut fallback runs but may extract garbage contours
on cluttered backgrounds (chairs, walls visible in frame).

**File**: `core/silhouette_extractor.py` — add a confidence check after contour extraction:

```python
# After extracting main contour, check aspect ratio (body should be tall)
x, y, w, h = cv2.boundingRect(main)
aspect = h / (w + 1)
if aspect < 1.2:   # contour is wider than tall — probably not a person
    logger.warning('Silhouette aspect ratio %.2f < 1.2 — likely a bad segmentation', aspect)
    return None, mask, ratio

# Check contour fills reasonable fraction of image height
img_h = mask.shape[0]
if h < img_h * 0.3:
    logger.warning('Silhouette height %dpx < 30%% of image — likely a bad segmentation', h)
    return None, mask, ratio
```

**Verification**: Run on a blank wall photo → should return None (not garbage contour).

---

## PRIORITY 4 — Quality improvements

### P4.1 — Perspective projection in silhouette_matcher

**File**: `core/silhouette_matcher.py` — replace `_project_vertices()` and `_unproject_delta()`.

Current: orthographic projection (no depth-based scaling).
Target: simple pinhole perspective projection.

```python
def _project_vertices_perspective(verts, direction, dist_mm, cam_h_mm,
                                   focal_mm=4.0, sensor_w_mm=6.4, img_w_px=1080):
    """Pinhole camera projection."""
    focal_px = focal_mm / sensor_w_mm * img_w_px

    if direction in ('front', 'back'):
        sign = 1.0 if direction == 'front' else -1.0
        # Camera at (0, -dist_mm, cam_h_mm), looking at origin
        dx = verts[:, 0] * sign
        dy_depth = dist_mm - verts[:, 1] * sign   # depth (distance from camera plane)
        dz = cam_h_mm - verts[:, 2]
    else:
        sign = 1.0 if direction == 'right' else -1.0
        dx = verts[:, 1] * sign
        dy_depth = dist_mm - verts[:, 0] * sign
        dz = cam_h_mm - verts[:, 2]

    safe_depth = np.where(dy_depth > 10, dy_depth, 10)
    x_img = dx / safe_depth * focal_px
    y_img = dz / safe_depth * focal_px
    return np.stack([x_img, y_img], axis=1)
```

Replace the call in `fit_mesh_to_silhouettes()`:
```python
proj2d = _project_vertices_perspective(verts, direction, dist_mm, cam_h_mm)
```

**Verification**: Re-run the P4.1 verification from T4.2, compare max displacement — should be similar but more accurate at large field-of-view.

---

### P4.2 — CLAUDE.md project documentation

Create `CLAUDE.md` at the project root. This helps any future agent orient in one read without burning tokens on SONNET_3D_TASKS files.

Contents:
- Project purpose (muscle tracker app)
- Architecture overview (py4web server, Flutter app, core/ vision pipeline, 3D mesh)
- Key files and what they do
- Quick-start commands
- Known gotchas (server restart, ADB path mangling, Inkscape Python, etc.)

---

## EXECUTION ORDER

```
P1.1 (test measurement-only body model)  — no code, 10 min
P1.2 (test with real scan photos)        — no code, 10 min
  ↓
P2.1 (vectorize texture_projector)       — 30 min, improves speed 10×
P2.2 (gtddebug body3d command)           — 30 min, makes testing one-command
  ↓
P3.1 (texture in body_model endpoint)    — 30 min, needs P2.1 first
P3.2 (silhouette quality check)          — 15 min, prevents bad mesh deformation
  ↓
P4.1 (perspective projection)            — 20 min, improves accuracy
P4.2 (CLAUDE.md)                         — 15 min
```

---

## KNOWN LIMITATIONS TO NOT OVER-ENGINEER

- **UV seams**: cylindrical projection wraps at angle=0/2π — visible seam on rendered texture.
  Acceptable for now (fixing requires seam-aware UV unwrapping with vertex duplication).
- **Arm mesh caps**: each arm/leg is a closed tube with flat end-caps at shoulder/wrist.
  This is visible as a flat disc but acceptable for body proportion tracking.
- **Single texture per GLB**: texture_projector blends multiple views into one atlas.
  This is correct — don't change to per-view materials.

---

## TOKEN-SAVING TIPS

1. `controllers.py` is 2200+ lines. Grep for `generate_body_model` then read ±60 lines.
2. `gtddebug.py` grep for `subparsers.add_parser` to see command structure before reading.
3. `silhouette_matcher.py` and `texture_projector.py` are new, small (<200 lines) — read in full.
4. Test mesh generation without starting the server: use `$PY -c "from core.smpl_fitting import ..."`.
5. Viewer changes don't need server restart — static files are served directly.
