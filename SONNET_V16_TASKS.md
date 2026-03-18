# SONNET V16 — Anny Mesh Pipeline Polish

> **Theme:** Complete the Anny parametric body model integration — UVs, gender, API wiring, server restart.
> **Files:** `core/smpl_fitting.py` (547 lines), `core/mesh_reconstruction.py` (452 lines), `web_app/controllers.py` (grep only), `web_app/static/viewer3d/body_viewer.js` (3041 lines)
> **Server restart:** YES for T1-T4 (Python changes). T5-T6 are JS — refresh only.
> **Depends on:** Anny installed (`pip install anny`), PyTorch installed, port 8001 for Claude's server

---

## Context — What Opus Already Did

Opus installed the **Anny** parametric body model (NAVER, Apache 2.0) and integrated it as the primary mesh engine in `core/smpl_fitting.py`. The function `_build_anny_mesh(profile)` at **line 55** generates a 13,718-vertex anatomically correct human body from the user's measurements.

**Current state:**
- `build_body_mesh()` (line 175) tries Anny first, falls back to ellipsoids
- Gender is hardcoded to male (`'gender': 0.0` at line 99)
- UVs are NOT exported (Anny has 21,334 UVs but they need vertex expansion)
- Viewer skin material already upgraded (1024px textures, 7-light studio)
- The API endpoint `generate_body_model` (controllers.py line 2288) has NOT been tested with Anny yet

**Anny phenotype parameters:**
- `gender`: 0.0 = male, 1.0 = female
- `age`: 0.0 = baby, 0.5 = young adult, 1.0 = elderly
- `muscle`: 0.0–1.0 (derived from chest/waist ratio + bicep size)
- `weight`: 0.0–1.0 (derived from BMI)
- `height`: 0.0–1.0 (mapped from 150–200cm)
- `proportions`: 0.0 = ideal, 1.0 = uncommon

---

## T1 — Gender from Customer Profile

**File:** `core/smpl_fitting.py` (547 lines)

**Goal:** Read gender from profile dict instead of hardcoding male.

**Where to edit:** `_build_anny_mesh()` at line 99.

**Find** (exact):
```python
    phenotype = {
        'gender': 0.0,             # 0=male, 1=female
        'age': 0.5,               # young adult
```

**Replace with:**
```python
    # Map gender string to Anny parameter (0=male, 1=female)
    gender_str = str(profile.get('gender', 'male')).lower()
    gender_val = 1.0 if gender_str in ('female', 'f', '1') else 0.0

    phenotype = {
        'gender': gender_val,
        'age': 0.5,               # young adult
```

**Verification:**
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
from core.smpl_fitting import build_body_mesh
m = build_body_mesh({'gender': 'male'})
print('Male:', m['num_vertices'], 'verts')
m2 = build_body_mesh({'gender': 'female'})
print('Female:', m2['num_vertices'], 'verts')
# Both should be 13718 verts but different shapes
"
```

**Pitfalls:** The `customer` table in `models.py` has a `gender` field. The `generate_body_model` endpoint at controllers.py line 2288 already reads `customer.gender` and passes it in the profile dict (see line 1041: `gender = data.get('gender') or customer.gender or 'male'`). So this will work end-to-end.

**Server restart:** YES

---

## T2 — Export Anny UVs in GLB

**File:** `core/smpl_fitting.py` (547 lines)

**Goal:** Expand Anny's 13,718 geometry vertices to 21,334 UV-split vertices so texture projection and GLB export work with proper UVs.

**Background:** Anny has 21,334 UV coordinates but only 13,718 geometry vertices. At UV seams, one geometry vertex maps to multiple UV coords. To export GLB with correct UVs, we must expand: create one vertex per unique (position, UV) pair.

**Where to edit:** `_build_anny_mesh()` function, after `faces_tri` computation (~line 120). Replace the section from `# Export GLB without UVs` down to the `return` statement.

**Find** (exact):
```python
    # Triangulate quad faces
    fq = model.faces.numpy()
    faces_tri = np.vstack([fq[:, [0, 1, 2]], fq[:, [0, 2, 3]]]).astype(np.uint32)

    # Volume via trimesh
```

**Replace with:**
```python
    # Triangulate quad faces (geometry indices)
    fq = model.faces.numpy()
    geo_tri = np.vstack([fq[:, [0, 1, 2]], fq[:, [0, 2, 3]]]).astype(np.uint32)

    # Triangulate UV face indices (same split pattern)
    uv_fq = model.face_texture_coordinate_indices.numpy()
    uv_tri = np.vstack([uv_fq[:, [0, 1, 2]], uv_fq[:, [0, 2, 3]]]).astype(np.uint32)

    # Expand vertices to match UV count: one vertex per unique UV index
    all_uv_coords = model.texture_coordinates.numpy()  # (21334, 2)
    num_uv = all_uv_coords.shape[0]

    # Build expanded vertex array: UV index → geometry vertex position
    expanded_verts = np.zeros((num_uv, 3), dtype=np.float32)
    # Map UV face indices back to geometry positions
    for fi in range(len(geo_tri)):
        for vi in range(3):
            geo_idx = geo_tri[fi, vi]
            uv_idx = uv_tri[fi, vi]
            expanded_verts[uv_idx] = verts_mm[geo_idx]

    # Use UV-indexed faces as the final face array
    faces_tri = uv_tri
    uvs = all_uv_coords.astype(np.float32)

    # Update verts_mm to the expanded version
    verts_mm = expanded_verts

    # Volume via trimesh
```

**Verification:**
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
from core.smpl_fitting import build_body_mesh
m = build_body_mesh()
print(f'Vertices: {m[\"num_vertices\"]}')  # Should be 21334
print(f'Faces: {m[\"num_faces\"]}')        # Should be 27420
print(f'Has UVs: {\"uvs\" in m}')          # Should be True
"
```

**IMPORTANT:** Also update the return dict at the end of `_build_anny_mesh()` to include UVs:

**Find** (exact):
```python
    return {
        'vertices':      verts_mm,
        'faces':         faces_tri,
        'body_part_ids': np.zeros(len(verts_mm), dtype=np.int32),
        'volume_cm3':    vol_cm3,
        'num_vertices':  len(verts_mm),
        'num_faces':     len(faces_tri),
    }
```

**Replace with:**
```python
    return {
        'vertices':      verts_mm,
        'faces':         faces_tri,
        'uvs':           uvs,
        'body_part_ids': np.zeros(len(verts_mm), dtype=np.int32),
        'volume_cm3':    vol_cm3,
        'num_vertices':  len(verts_mm),
        'num_faces':     len(faces_tri),
    }
```

**Pitfalls:**
- The `expanded_verts` loop is O(faces * 3) — ~82K iterations, runs in <100ms.
- UV coords are in [0,1] range already (confirmed: u=[0.009, 0.994], v=[0.010, 0.992]).
- The ellipsoid fallback does NOT return `'uvs'`, so downstream code must check `mesh.get('uvs')`.

**Server restart:** YES

---

## T3 — Pass UVs Through to GLB Export

**File:** `web_app/controllers.py` (grep target: `generate_body_model` at line 2288)

**Goal:** When `build_body_mesh()` returns UVs (Anny path), pass them to `export_glb()`.

**Where to edit:** Inside `generate_body_model()`. Grep for `export_glb` within that function.

```bash
grep -n 'export_glb' web_app/controllers.py
```

**What to change:** Wherever `export_glb(mesh['vertices'], mesh['faces'], glb_path)` is called, add the `uvs` parameter:

```python
uvs = mesh.get('uvs')
export_glb(mesh['vertices'], mesh['faces'], glb_path, uvs=uvs)
```

This ensures that when Anny provides UVs, they get embedded in the GLB. When the ellipsoid fallback runs (no UVs), `uvs=None` is passed and `export_glb` handles it gracefully (already does — see mesh_reconstruction.py line 182).

**Verification:**
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
from core.smpl_fitting import build_body_mesh
from core.mesh_reconstruction import export_glb
m = build_body_mesh()
export_glb(m['vertices'], m['faces'], 'meshes/test_uvs.glb', uvs=m.get('uvs'))
import os; print(f'Size: {os.path.getsize(\"meshes/test_uvs.glb\")/1024:.0f} KB')
# Should be ~500-700 KB (larger than before due to UV data)
"
```

**Server restart:** YES

---

## T4 — Regenerate Demo GLB with UVs

**File:** None (CLI command only)

**Goal:** After T2+T3 are done, regenerate the demo mesh that the viewer loads.

**Command:**
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
cd C:/Users/MiEXCITE/Projects/gtd3d
$PY -c "
from core.smpl_fitting import build_body_mesh
from core.mesh_reconstruction import export_glb
m = build_body_mesh()
export_glb(m['vertices'], m['faces'], 'web_app/static/viewer3d/demo.glb', uvs=m.get('uvs'))
print(f'{m[\"num_vertices\"]} verts, {m[\"num_faces\"]} faces, UVs: {m.get(\"uvs\") is not None}')
"
```

**Server restart:** NO (static file)

---

## T5 — Viewer: Use Embedded UVs for Textured Mode

**File:** `web_app/static/viewer3d/body_viewer.js` (3041 lines)

**Goal:** When the GLB has embedded UVs + texture, the "Textured" view mode should show the embedded texture instead of the procedural skin. Currently `_applyDefaultMaterial()` at line 622 always overwrites with `SKIN_MATERIAL`. Fix it to preserve embedded texture maps.

**Where to edit:** `_applyDefaultMaterial()` at line 622.

**Find** (exact):
```js
function _applyDefaultMaterial(object) {
  object.traverse(child => {
    if (child.isMesh) {
      // Store original material for texture toggle
      _originalMaterials.set(child, child.material);
      origMaterials.push({ mesh: child, mat: child.material });
      // Upgrade all body meshes to the physical skin material for realism
      const hasTexture = child.material && child.material.map;
      if (hasTexture) {
        // Keep embedded texture but upgrade material properties
        const tex = child.material.map;
        const mat = SKIN_MATERIAL.clone();
        mat.map = tex;
        child.material = mat;
      } else {
        child.material = SKIN_MATERIAL.clone();
      }
      _originalMaterials.set(child, child.material);
      child.castShadow    = true;
      child.receiveShadow = true;
    }
  });
}
```

**Replace with:**
```js
function _applyDefaultMaterial(object) {
  object.traverse(child => {
    if (child.isMesh) {
      // Store the original loaded material (may have embedded texture)
      const loadedMat = child.material;
      const hasEmbeddedTexture = loadedMat && loadedMat.map;

      // Save original for "Textured" toggle
      origMaterials.push({ mesh: child, mat: loadedMat });

      if (hasEmbeddedTexture) {
        // Upgrade material properties but keep embedded texture
        const tex = loadedMat.map;
        const mat = SKIN_MATERIAL.clone();
        mat.map = tex;
        child.material = mat;
        // Store textured version as original (for toggle back)
        _originalMaterials.set(child, mat);
      } else {
        // No texture — use procedural skin
        child.material = SKIN_MATERIAL.clone();
        _originalMaterials.set(child, child.material);
      }
      child.castShadow    = true;
      child.receiveShadow = true;
    }
  });
}
```

**Verification:** Open `http://localhost:8001/web_app/static/viewer3d/index.html?model=/web_app/static/viewer3d/demo.glb`, click "Textured" button — should toggle between procedural and embedded texture (if GLB has one).

**Server restart:** NO (JS file, refresh browser)

---

## T6 — Viewer: IOR for Skin Material

**File:** `web_app/static/viewer3d/body_viewer.js` (3041 lines)

**Goal:** Add index of refraction to the skin material for more physically accurate rendering. Human skin has IOR ~1.4.

**Where to edit:** The `SKIN_MATERIAL` definition, around line 246.

**Find** (exact):
```js
  // Transmission for thin areas (ears, fingers) — subtle translucency
  transmission:     0.02,
  thickness:        5.0,
```

**Replace with:**
```js
  // Transmission for thin areas (ears, fingers) — subtle translucency
  transmission:     0.02,
  thickness:        5.0,
  ior:              1.4,
```

**Verification:** Refresh viewer — subtle visual improvement in specular highlights on skin.

**Server restart:** NO (JS file, refresh browser)

---

## Server Restart Procedure

After completing T1-T3, restart the server:

```bash
# Find the py4web PID on port 8001
PID=$(netstat -ano | grep ':8001.*LISTEN' | awk '{print $5}')
echo "Killing PID: $PID"
taskkill //F //PID $PID 2>/dev/null

# Wait then restart
sleep 2
cd C:/Users/MiEXCITE/Projects/gtd3d
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps \
  --host 0.0.0.0 --port 8001 > claude_server.log 2>&1 &

# Verify
sleep 5
curl -s http://localhost:8001/web_app/api/login -X POST \
  -H "Content-Type: application/json" -d '{"email":"demo@muscle.com"}' | head -c 50
```

**IMPORTANT:** Use port **8001** (not 8000). Port 8000 is Gemini's server. Kill by specific PID, never `taskkill /F /IM python.exe`.

---

## Execution Order

1. **T1** (gender) — simple find/replace, 5 lines
2. **T2** (UVs) — most complex, 30 lines added
3. **T3** (pass UVs to GLB) — 2-line change in controllers.py
4. **Restart server**
5. **T4** (regenerate demo) — one command
6. **T5** (viewer material fix) — find/replace in JS
7. **T6** (IOR) — one line add

**Total estimated changes:** ~50 lines across 3 files.
