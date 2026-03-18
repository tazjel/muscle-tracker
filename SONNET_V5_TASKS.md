# Sonnet V5 Task Sheet — Comparison, Measurement & Polish

**Project**: Muscle Tracker 3D viewer & dashboard upgrades
**Agent**: Claude Sonnet (sole owner)
**Date**: 2026-03-18
**Prereq commit**: `7e502f8` (V4 complete)

---

## RULES FOR SONNET

1. **DO NOT read** `companion_app/lib/main.dart` or `web_app/controllers.py` in full. Grep first, read +-30 lines.
2. After each task, run the verification command. Do NOT skip.
3. Commit after completing each task group.
4. Static files (JS/CSS/HTML) do NOT require server restart. Python changes DO.
5. `body_viewer.js` is 795 lines. Read once fully at the start — it's the main work target.
6. `index.html` is 94 lines. Read fully.
7. `app.js` (personal dashboard) is 357 lines. Read fully.

---

## CRITICAL CONTEXT — Read Before Starting

| What | Where | Lines | Why |
|------|-------|-------|-----|
| 3D viewer | `web_app/static/viewer3d/body_viewer.js` | 795 | MAIN WORK TARGET for P1-P3 |
| Viewer HTML | `web_app/static/viewer3d/index.html` | 94 | Add comparison dropdown + measurement UI |
| Viewer CSS | `web_app/static/viewer3d/styles.css` | 257 | Style new UI elements |
| Dashboard JS | `web_app/static/personal/app.js` | 357 | Add comparison feature |
| Dashboard HTML | `web_app/static/personal/index.html` | ~140 | Add comparison UI |

### Existing heatmap comparison code (already works but no UI):
- `body_viewer.js:182-184` reads `?compare_old=ID&compare_new=ID` from URL params
- `body_viewer.js:192-193` calls `_applyCompareHeatmap(oldId, newId)` after GLB loads
- `body_viewer.js:204-220` fetches `/web_app/api/customer/1/compare_meshes` POST with `{mesh_id_old, mesh_id_new}`
- `controllers.py:1326-1400` is the `compare_meshes_heatmap` endpoint — returns `heatmap_values[]`, `max_displacement_mm`, `mean_displacement_mm`
- Heatmap legend is at `index.html:63-70`, toggled via `.visible` CSS class

### Existing viewer features:
- 4 view modes: Solid, Wire, Heat, Textured (+ Labels toggle)
- Region click → adjustment panel (width/depth/length sliders) → Save to Profile
- `_autoLogin()` handles auth → stores `_viewerToken`
- `window.setViewMode(mode)` at line 705
- `resetCamera()`, `takeScreenshot()`, `clearMeasurements()` exposed on window

---

## TASK GROUP 1 — Mesh Comparison UI (P1)

> Currently heatmap comparison only works via manual URL params. Add a dropdown to compare any two meshes.

### P1.1 — Mesh List Dropdown in Viewer

**Files**: `index.html`, `body_viewer.js`

**Goal**: Add a "Compare" section in the viewer card that lists available meshes and lets user pick old/new.

**In `index.html`** — add after the adjust-panel div (line 47), before `<div class="controls">`:

```html
<!-- Mesh comparison -->
<div id="compare-panel" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
  <h3 style="margin:0 0 6px;font-size:13px;">Compare Growth</h3>
  <label style="font-size:11px;display:block;margin-bottom:4px;">
    Before: <select id="compare-old" style="width:120px;font-size:11px;"></select>
  </label>
  <label style="font-size:11px;display:block;margin-bottom:6px;">
    After: <select id="compare-new" style="width:120px;font-size:11px;"></select>
  </label>
  <button onclick="runComparison()" style="font-size:11px;margin-right:4px;">Compare</button>
  <button onclick="clearComparison()" style="font-size:11px;">Clear</button>
  <div id="compare-stats" style="font-size:11px;margin-top:4px;display:none;"></div>
</div>
```

**In `body_viewer.js`** — add two functions:

1. **`_loadMeshList()`** — fetch mesh list and populate dropdowns:
```javascript
async function _loadMeshList() {
  // The viewer already auto-logs in and stores _viewerToken
  // Fetch mesh models for customer 1
  try {
    const resp = await fetch('/web_app/api/customer/1/meshes', {
      headers: { 'Authorization': `Bearer ${_viewerToken}` }
    });
    const data = await resp.json();
    if (data.status !== 'success') return;
    const oldSel = document.getElementById('compare-old');
    const newSel = document.getElementById('compare-new');
    if (!oldSel || !newSel) return;
    oldSel.innerHTML = '<option value="">— none —</option>';
    newSel.innerHTML = '<option value="">— none —</option>';
    for (const m of data.meshes) {
      const label = `#${m.id} ${m.created_on || ''} (${m.muscle_group || 'body'})`;
      oldSel.innerHTML += `<option value="${m.id}">${label}</option>`;
      newSel.innerHTML += `<option value="${m.id}">${label}</option>`;
    }
  } catch (e) { console.warn('Failed to load mesh list:', e); }
}
```

Call `_loadMeshList()` at the end of `init()` (after `_loadModel()` is called).

2. **`window.runComparison()`** and **`window.clearComparison()`**:
```javascript
window.runComparison = async function() {
  const oldId = document.getElementById('compare-old')?.value;
  const newId = document.getElementById('compare-new')?.value;
  if (!oldId || !newId) { alert('Select both meshes'); return; }
  await _applyCompareHeatmap(parseInt(oldId), parseInt(newId));
  // _applyCompareHeatmap already shows stats in status bar, but also show in panel:
  const statsEl = document.getElementById('compare-stats');
  if (statsEl) statsEl.style.display = 'block';
};

window.clearComparison = function() {
  window.setViewMode('solid');
  const statsEl = document.getElementById('compare-stats');
  if (statsEl) { statsEl.style.display = 'none'; statsEl.textContent = ''; }
};
```

3. **Update `_applyCompareHeatmap()`** (line ~204) to also write stats into `#compare-stats`:
```javascript
// After the existing _setStatus line, add:
const statsEl = document.getElementById('compare-stats');
if (statsEl) {
  statsEl.textContent = `Max Δ: ${data.max_displacement_mm}mm | Mean Δ: ${data.mean_displacement_mm}mm`;
  statsEl.style.display = 'block';
}
```

### P1.2 — Mesh List API Endpoint

**File**: `web_app/controllers.py`

**Goal**: Add `GET /api/customer/<id>/meshes` to return list of mesh models.

**Grep** `controllers.py` for `mesh_model` to find the table name, then add:

```python
@action('api/customer/<customer_id:int>/meshes', method=['GET'])
@action.uses(db, cors)
def list_meshes(customer_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Auth required')
    rows = db(db.mesh_model.customer_id == customer_id).select(
        db.mesh_model.id,
        db.mesh_model.muscle_group,
        db.mesh_model.volume_cm3,
        db.mesh_model.created_on,
        orderby=~db.mesh_model.id
    )
    return dict(
        status='success',
        meshes=[dict(id=r.id, muscle_group=r.muscle_group or 'body',
                     volume_cm3=r.volume_cm3,
                     created_on=str(r.created_on) if r.created_on else '')
                for r in rows]
    )
```

**Where to add**: Search for `def compare_meshes_heatmap` (~line 1326). Add the new endpoint BEFORE it.

**Verification**:
```bash
# Restart server first (new Python code)
ps aux | grep py4web | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
cd C:/Users/MiEXCITE/Projects/muscle_tracker
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps --host 0.0.0.0 --port 8000 >> server.log 2>&1 &
sleep 3

# Get token
TOKEN=$(curl -s http://localhost:8000/web_app/api/login -X POST \
  -H "Content-Type: application/json" -d '{"email":"demo@muscle.com"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")

# Test mesh list
curl -s http://localhost:8000/web_app/api/customer/1/meshes \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Then open viewer in browser — dropdown should be populated
```

**Pitfalls**:
- The `mesh_model` table might use `customer` not `customer_id` as the reference field — grep for `Field('customer'` or `Field('customer_id'` in `models.py` to confirm.
- The `created_on` field might be `datetime` — wrap in `str()`.
- Server MUST be restarted for the new endpoint. Static files (JS/HTML) do NOT need restart.

---

## TASK GROUP 2 — Measurement Tools (P2)

> Add click-to-measure distance and cross-section analysis.

### P2.1 — Distance Measurement Mode

**File**: `body_viewer.js`

**Goal**: Toggle a "Measure" mode. In measure mode, clicking two points on the mesh draws a line and shows distance in mm.

**Implementation**:

Add state variables near the top (after line 24):
```javascript
let _measureMode = false;
let _measurePoints = [];     // [{point: THREE.Vector3, marker: THREE.Mesh}]
let _measureLines = [];      // THREE.Line objects in scene
```

Add `window.toggleMeasure()`:
```javascript
window.toggleMeasure = function() {
  _measureMode = !_measureMode;
  const btn = document.getElementById('btn-measure');
  if (btn) btn.classList.toggle('active', _measureMode);
  if (!_measureMode) return;
  // Clear previous incomplete pair
  if (_measurePoints.length === 1) {
    scene.remove(_measurePoints[0].marker);
    _measurePoints = [];
  }
};
```

Modify the existing click handler (find the `addEventListener('click'` or `mousedown` in the file). In measure mode, instead of showing region info, collect points:

```javascript
// Inside the click handler, before the existing region detection:
if (_measureMode && intersection) {
  const pt = intersection.point.clone();
  // Create small sphere marker
  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(3, 8, 8),
    new THREE.MeshBasicMaterial({ color: 0xff4444 })
  );
  marker.position.copy(pt);
  scene.add(marker);
  _measurePoints.push({ point: pt, marker });

  if (_measurePoints.length === 2) {
    // Draw line
    const geom = new THREE.BufferGeometry().setFromPoints(
      [_measurePoints[0].point, _measurePoints[1].point]
    );
    const line = new THREE.Line(geom, new THREE.LineBasicMaterial({ color: 0xff4444, linewidth: 2 }));
    scene.add(line);
    _measureLines.push(line);

    // Calculate distance
    const dist = _measurePoints[0].point.distanceTo(_measurePoints[1].point);
    _setStatus(`Distance: ${dist.toFixed(1)} mm`);

    // Show label at midpoint
    _showMeasureLabel(_measurePoints[0].point, _measurePoints[1].point, dist);

    _measurePoints = [];  // Reset for next pair
  }
  return;  // Don't trigger region selection
}
```

Add `_showMeasureLabel()`:
```javascript
function _showMeasureLabel(p1, p2, dist) {
  const mid = p1.clone().add(p2).multiplyScalar(0.5);
  // Create a CSS2D label or use a simple div overlay
  const div = document.createElement('div');
  div.className = 'measure-label';
  div.textContent = `${dist.toFixed(1)} mm`;
  div.style.cssText = 'position:absolute;background:rgba(255,68,68,0.85);color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;pointer-events:none;';
  document.getElementById('canvas-container').appendChild(div);

  // Update position each frame
  function updatePos() {
    if (!div.parentElement) return;
    const projected = mid.clone().project(camera);
    const x = (projected.x * 0.5 + 0.5) * renderer.domElement.clientWidth;
    const y = (-projected.y * 0.5 + 0.5) * renderer.domElement.clientHeight;
    div.style.left = x + 'px';
    div.style.top = y + 'px';
    requestAnimationFrame(updatePos);
  }
  updatePos();

  // Store ref for cleanup
  if (!window._measureLabels) window._measureLabels = [];
  window._measureLabels.push(div);
}
```

Update `clearMeasurements()` (find existing function) to also remove measure lines and labels:
```javascript
// Add inside existing clearMeasurements():
_measureLines.forEach(l => scene.remove(l));
_measureLines = [];
_measurePoints.forEach(p => scene.remove(p.marker));
_measurePoints = [];
(window._measureLabels || []).forEach(l => l.remove());
window._measureLabels = [];
```

**In `index.html`** — add Measure button to the controls div (line 49-53):
```html
<button id="btn-measure" onclick="toggleMeasure()">Measure</button>
```

**Verification**: Load viewer → click Measure → click two points on body → see red line + distance label. Click Clear Pins → all removed.

### P2.2 — Cross-Section Display

**File**: `body_viewer.js`

**Goal**: Add a horizontal slice plane. Dragging a slider shows the cross-section outline at that height, plus area and perimeter.

**In `index.html`** — add after compare-panel:
```html
<!-- Cross-section tool -->
<div id="section-panel" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
  <h3 style="margin:0 0 6px;font-size:13px;">Cross Section</h3>
  <label style="font-size:11px;display:block;">
    Height: <input type="range" id="section-height" min="0" max="100" value="50" style="width:110px;">
    <span id="section-height-val">50</span>%
  </label>
  <div id="section-stats" style="font-size:11px;margin-top:4px;"></div>
</div>
```

**In `body_viewer.js`** — add cross-section logic:

```javascript
let _sectionPlane = null;  // THREE.Mesh (semi-transparent disc)
let _sectionOutline = null; // THREE.Line

window.addEventListener('load', () => {
  const slider = document.getElementById('section-height');
  if (slider) {
    slider.addEventListener('input', (e) => {
      const pct = parseInt(e.target.value);
      document.getElementById('section-height-val').textContent = pct;
      _updateCrossSection(pct / 100);
    });
  }
});

function _updateCrossSection(ratio) {
  if (!bodyMesh) return;
  const box = new THREE.Box3().setFromObject(bodyMesh);
  const minY = box.min.y;
  const maxY = box.max.y;
  const sliceY = minY + (maxY - minY) * ratio;

  // Remove old
  if (_sectionPlane) scene.remove(_sectionPlane);
  if (_sectionOutline) scene.remove(_sectionOutline);

  // Add translucent plane
  const planeSize = Math.max(box.max.x - box.min.x, box.max.z - box.min.z) * 1.5;
  const planeGeom = new THREE.PlaneGeometry(planeSize, planeSize);
  const planeMat = new THREE.MeshBasicMaterial({
    color: 0x4a9eff, transparent: true, opacity: 0.15, side: THREE.DoubleSide
  });
  _sectionPlane = new THREE.Mesh(planeGeom, planeMat);
  _sectionPlane.rotation.x = -Math.PI / 2;
  _sectionPlane.position.y = sliceY;
  scene.add(_sectionPlane);

  // Compute cross-section: find edges that cross sliceY
  // Get geometry from mesh
  let geometry = null;
  bodyMesh.traverse(c => { if (c.isMesh && !geometry) geometry = c.geometry; });
  if (!geometry) return;

  const pos = geometry.attributes.position;
  const idx = geometry.index;
  const crossPoints = [];

  const getVert = (i) => new THREE.Vector3(pos.getX(i), pos.getY(i), pos.getZ(i));

  const triCount = idx ? idx.count / 3 : pos.count / 3;
  for (let t = 0; t < triCount; t++) {
    const i0 = idx ? idx.getX(t * 3) : t * 3;
    const i1 = idx ? idx.getX(t * 3 + 1) : t * 3 + 1;
    const i2 = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
    const v0 = getVert(i0), v1 = getVert(i1), v2 = getVert(i2);
    const edges = [[v0, v1], [v1, v2], [v2, v0]];

    const pts = [];
    for (const [a, b] of edges) {
      if ((a.y - sliceY) * (b.y - sliceY) < 0) {
        const t = (sliceY - a.y) / (b.y - a.y);
        pts.push(new THREE.Vector3(
          a.x + t * (b.x - a.x),
          sliceY,
          a.z + t * (b.z - a.z)
        ));
      }
    }
    if (pts.length === 2) crossPoints.push(pts[0], pts[1]);
  }

  if (crossPoints.length > 0) {
    // Draw outline segments
    const lineGeom = new THREE.BufferGeometry().setFromPoints(crossPoints);
    const lineMat = new THREE.LineBasicMaterial({ color: 0x4a9eff, linewidth: 2 });
    _sectionOutline = new THREE.LineSegments(lineGeom, lineMat);
    scene.add(_sectionOutline);

    // Estimate perimeter and area (sum of segment lengths for perimeter)
    let perimeter = 0;
    for (let i = 0; i < crossPoints.length; i += 2) {
      perimeter += crossPoints[i].distanceTo(crossPoints[i + 1]);
    }
    // Rough circumference (perimeter of all cross-section segments)
    const statsEl = document.getElementById('section-stats');
    if (statsEl) {
      statsEl.textContent = `Height: ${sliceY.toFixed(0)}mm | Perimeter: ${perimeter.toFixed(0)}mm (${(perimeter / 10).toFixed(1)}cm)`;
    }
  }
}
```

**Note on coordinate system**: The mesh from `smpl_fitting.py` uses Z as up, but Three.js GLB loader may remap to Y-up. Check by logging `box.min, box.max` after load. If Y is up (typical for GLB), the code above is correct. If Z is up, swap Y↔Z in the slice logic.

**Verification**: Load viewer → drag the Height slider → see blue translucent plane move up/down the body → perimeter updates in real time.

**Pitfalls**:
- The cross-section computation iterates ALL triangles each frame. For ~32k faces this is fine (< 5ms). If it lags, debounce the slider.
- `THREE.LineSegments` draws pairs of points (not a connected loop). This is correct for cross-section segments.
- The Y-up vs Z-up issue: GLB files exported by `mesh_reconstruction.py` — check if it flips axes. Grep for `y_up` or coordinate swap in `mesh_reconstruction.py`.

---

## TASK GROUP 3 — Dashboard Scan Comparison (P3)

> Let users select 2 scans on the personal dashboard and open the 3D comparison viewer.

### P3.1 — Compare Button on Scan Cards

**File**: `web_app/static/personal/app.js`

**Goal**: Add checkboxes on scan cards. When 2 are checked, show a "Compare in 3D" button.

Find the function that renders scan cards (grep for `scan-card` or `renderScans`). Each card should get a checkbox:

```javascript
// Inside the scan card rendering loop, add:
<input type="checkbox" class="compare-check" data-mesh-id="${scan.mesh_model_id || ''}"
       onchange="updateCompareButton()" style="position:absolute;top:5px;right:5px;">
```

Add compare logic:
```javascript
function updateCompareButton() {
  const checked = document.querySelectorAll('.compare-check:checked');
  let btn = document.getElementById('btn-compare-3d');
  if (!btn) {
    btn = document.createElement('button');
    btn.id = 'btn-compare-3d';
    btn.textContent = 'Compare in 3D';
    btn.style.cssText = 'position:fixed;bottom:20px;right:20px;padding:10px 20px;background:#4a9eff;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;z-index:100;display:none;';
    btn.onclick = openComparison;
    document.body.appendChild(btn);
  }
  btn.style.display = checked.length === 2 ? 'block' : 'none';
}

function openComparison() {
  const checked = document.querySelectorAll('.compare-check:checked');
  if (checked.length !== 2) return;
  const ids = Array.from(checked).map(c => c.dataset.meshId).filter(Boolean);
  if (ids.length !== 2) { alert('Selected scans have no 3D mesh'); return; }
  // Sort: older first
  const [oldId, newId] = ids[0] < ids[1] ? ids : [ids[1], ids[0]];
  // Open viewer with comparison params
  window.open(`/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/${newId}.glb&compare_old=${oldId}&compare_new=${newId}`, '_blank');
}
```

**Also**: The scan data must include `mesh_model_id`. Grep `controllers.py` for the scans endpoint to check if it returns this field. If not, add it.

**Verification**: Open personal dashboard → check 2 scan cards → "Compare in 3D" button appears → click → viewer opens with heatmap.

**Pitfalls**:
- Not all scans have a mesh model (only body scans do). The checkbox should be hidden or disabled for scans without `mesh_model_id`.
- Scan card styling: the checkbox must not overlap existing content. Use `position:relative` on the card container.

---

## TASK GROUP 4 — Quality of Life Polish (P4)

### P4.1 — Keyboard Shortcuts

**File**: `body_viewer.js`

**Goal**: Add keyboard shortcuts for common actions.

Add at the end of `init()`:
```javascript
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  switch (e.key) {
    case '1': window.setViewMode('solid'); break;
    case '2': window.setViewMode('wireframe'); break;
    case '3': window.setViewMode('heatmap'); break;
    case '4': window.setViewMode('textured'); break;
    case 'l': case 'L': window.toggleLabels(); break;
    case 'm': case 'M': window.toggleMeasure(); break;
    case 'r': case 'R': window.resetCamera(); break;
    case 's': case 'S': if (!e.ctrlKey) window.takeScreenshot(); break;
    case 'Escape':
      _measureMode = false;
      document.getElementById('btn-measure')?.classList.remove('active');
      break;
  }
});
```

**In `index.html`** — add a small help hint at the bottom of the card:
```html
<div style="font-size:9px;color:#666;margin-top:6px;">
  Keys: 1-4 views · L labels · M measure · R reset · S screenshot
</div>
```

**Verification**: Load viewer → press 1/2/3/4 → view modes change. Press M → measure mode activates. Press Escape → exits.

### P4.2 — Loading Progress Indicator

**File**: `body_viewer.js`, `styles.css`

**Goal**: Show a progress bar while GLB is loading (GLTFLoader supports `onProgress`).

Find `_loadGLB()` in `body_viewer.js`. The GLTFLoader.load() call has 3 callbacks: `onLoad`, `onProgress`, `onError`. Add the progress callback:

```javascript
// In _loadGLB, the loader.load call:
loader.load(url, (gltf) => {
  // ... existing onLoad code ...
  _hideProgress();
}, (xhr) => {
  // onProgress
  if (xhr.total > 0) {
    const pct = Math.round(xhr.loaded / xhr.total * 100);
    _showProgress(pct);
  }
}, (err) => {
  // ... existing onError code ...
  _hideProgress();
});
```

Add progress bar functions:
```javascript
function _showProgress(pct) {
  let bar = document.getElementById('load-progress');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'load-progress';
    bar.style.cssText = 'position:fixed;top:0;left:0;height:3px;background:#4a9eff;transition:width 0.2s;z-index:9999;';
    document.body.appendChild(bar);
  }
  bar.style.width = pct + '%';
}

function _hideProgress() {
  const bar = document.getElementById('load-progress');
  if (bar) { bar.style.width = '100%'; setTimeout(() => bar.remove(), 300); }
}
```

**Verification**: Load a GLB model → see blue progress bar at top of screen → disappears when loaded.

### P4.3 — High-DPI Screenshot

**File**: `body_viewer.js`

**Goal**: Upgrade `takeScreenshot()` to render at 2x resolution for sharper exports.

Find `takeScreenshot()` (grep for it). Replace with:

```javascript
window.takeScreenshot = function() {
  const w = renderer.domElement.width;
  const h = renderer.domElement.height;
  // Render at 2x
  renderer.setSize(w * 2, h * 2, false);
  renderer.render(scene, camera);
  const dataUrl = renderer.domElement.toDataURL('image/png');
  // Restore
  renderer.setSize(w, h, false);
  renderer.render(scene, camera);
  // Download
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = `muscle_tracker_3d_${Date.now()}.png`;
  a.click();
};
```

**Verification**: Load viewer → press S → downloads a 2x resolution PNG.

---

## TASK GROUP 5 — Texture Quality (P5)

### P5.1 — Gap Inpainting for Texture Atlas

**File**: `core/texture_projector.py` (130 lines)

**Goal**: After projection, fill gaps (gray pixels where no camera view reached) using OpenCV inpainting.

At the end of `project_texture()`, before the return:

```python
    # Inpaint uncovered regions
    mask_unfilled = (weight == 0).astype(np.uint8) * 255
    if mask_unfilled.any():
        texture = cv2.inpaint(texture, mask_unfilled, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
```

**Verification**:
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
import numpy as np, cv2
from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.texture_projector import project_texture

m = build_body_mesh()
uvs = compute_uvs(m['vertices'], m['body_part_ids'], DEFAULT_ATLAS)
front = np.full((2000, 1500, 3), (0, 180, 0), dtype=np.uint8)
views = [{'image': front, 'direction': 'front', 'distance_mm': 750, 'focal_mm': 4.0, 'sensor_width_mm': 6.4}]
tex, cov = project_texture(m['vertices'], m['faces'], uvs, views, atlas_size=512)
unfilled = (cov == 0).sum()
print(f'Unfilled pixels: {unfilled}/{cov.size} ({unfilled/cov.size*100:.1f}%)')
# Should be 0 after inpainting fills gaps with surrounding colors
cv2.imwrite('meshes/test_texture_inpainted.png', tex)
print('Wrote meshes/test_texture_inpainted.png — verify no gray patches')
"
```

**Pitfalls**:
- `cv2.inpaint` expects uint8 image and uint8 mask.
- After inpainting, `weight` array still has 0 for those pixels — that's fine, it's just for blending during projection.
- If `inpaintRadius` is too small, large gaps won't fill. 5 is a good default; increase to 10 for atlas_size > 1024.

### P5.2 — Seam Blending Between Views

**File**: `core/texture_projector.py`

**Goal**: Where two camera views overlap, the current code uses weighted average. Add Gaussian blur along seam boundaries for smoother transitions.

After the main projection loop and before inpainting, add seam smoothing:

```python
    # Smooth seam boundaries where multiple views overlap
    overlap_mask = (weight > 1.0).astype(np.uint8) * 255
    if overlap_mask.any():
        # Dilate overlap region slightly
        kernel = np.ones((5, 5), np.uint8)
        seam_region = cv2.dilate(overlap_mask, kernel, iterations=2)
        # Blur only the seam region
        blurred = cv2.GaussianBlur(texture, (7, 7), 0)
        seam_float = seam_region.astype(np.float32) / 255.0
        for c in range(3):
            texture[:, :, c] = (
                texture[:, :, c].astype(np.float32) * (1 - seam_float) +
                blurred[:, :, c].astype(np.float32) * seam_float
            ).astype(np.uint8)
```

**Verification**: Same test as P5.1 but with 2 views (front + right). Check that the transition zone is smooth, not a hard line.

---

## EXECUTION ORDER

```
P1.2 (mesh list endpoint)       — 10 min — needs server restart
P1.1 (comparison dropdown UI)   — 20 min — static files, no restart
  → commit "feat(v5): mesh comparison UI with dropdown + stats"

P2.1 (distance measurement)     — 25 min — viewer JS only
P2.2 (cross-section display)    — 30 min — viewer JS + HTML
  → commit "feat(v5): measurement tools — distance + cross-section"

P3.1 (dashboard compare)        — 15 min — dashboard JS only
  → commit "feat(v5): dashboard scan comparison with 3D viewer link"

P4.1 (keyboard shortcuts)       — 5 min  — viewer JS + HTML
P4.2 (loading progress)         — 5 min  — viewer JS only
P4.3 (hi-dpi screenshot)        — 5 min  — viewer JS only
  → commit "feat(v5): keyboard shortcuts, progress bar, hi-dpi screenshots"

P5.1 (gap inpainting)           — 10 min — Python, needs server restart
P5.2 (seam blending)            — 10 min — Python, same file
  → commit "feat(v5): texture inpainting + seam blending"
```

**Total: ~2.5 hours Sonnet work across 10 tasks, 5 commits.**

---

## TOKEN-SAVING TIPS

1. Read `body_viewer.js` (795 lines) ONCE at the start. Reference by line number after.
2. Read `index.html` (94 lines) ONCE.
3. Read `app.js` (357 lines) ONCE for P3.
4. DO NOT read `controllers.py` in full. Grep for: `mesh_model`, `compare_meshes`, `body_profile`.
5. DO NOT read `main.dart` at all — no Flutter work in V5.
6. Static file changes (JS/CSS/HTML) need NO server restart. Only restart for P1.2 and P5.
7. Test each task individually before moving to the next.

## KEY COMMANDS

```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe

# Start/restart server
ps aux | grep py4web | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
cd C:/Users/MiEXCITE/Projects/muscle_tracker
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps \
  --host 0.0.0.0 --port 8000 >> server.log 2>&1 &

# Get auth token
curl -s http://localhost:8000/web_app/api/login -X POST \
  -H "Content-Type: application/json" -d '{"email":"demo@muscle.com"}'

# Viewer URL
# http://localhost:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/1.glb

# Dashboard URL
# http://localhost:8000/web_app/static/personal/index.html
```
