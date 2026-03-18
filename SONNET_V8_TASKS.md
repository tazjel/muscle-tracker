# V8 Task Sheet — Body Progress & Viewer Polish

> **For Sonnet execution only.** All code provided — paste and verify.
> Static files (JS/CSS/HTML) do NOT need server restart.
> No Python changes in V8. Zero server restarts.

---

## How to Use This Sheet

1. Work top-to-bottom — P1 before P2 (P2 depends on P1's `_centerOnly` helper)
2. Each task = exact code + exact location + verification
3. Do NOT read files unless a verification fails
4. Do NOT refactor, add features, or "improve" anything

---

## P1 — Scan Timeline Slider

**Goal**: Slider to flip between scan dates without reloading the page.

### P1.1 — Add globals

**File**: `web_app/static/viewer3d/body_viewer.js`

**Where**: After `let _roomLightObjs   = [];` (line 69), add:

```javascript

// ── V8 globals ───────────────────────────────────────────────────────────────
let _meshList    = [];
let _ghostMesh   = null;
let _autoRotate  = false;
let _gridHelper  = null;
```

### P1.2 — Add `_centerOnly` helper

**File**: `body_viewer.js`

**Where**: After `_centerAndScale()` function closing brace (line 464), add:

```javascript

function _centerOnly(object) {
  // Same as _centerAndScale but does NOT move the camera
  object.rotation.x = -Math.PI / 2;
  const box = new THREE.Box3().setFromObject(object);
  const size = new THREE.Vector3();
  box.getSize(size);
  const targetH = 300;
  const scale = size.y > 0 ? targetH / size.y : 1;
  object.scale.setScalar(scale);
  const box2 = new THREE.Box3().setFromObject(object);
  const ctr2 = new THREE.Vector3();
  box2.getCenter(ctr2);
  object.position.sub(ctr2);
  object.position.y += targetH / 2;
}
```

### P1.3 — Store mesh list + populate timeline slider

**File**: `body_viewer.js`

**Where**: Inside `_loadMeshList()`, right after the line `if (data.status !== 'success') return;` (line 987), add:

```javascript
    _meshList = data.meshes;
    // Populate timeline slider
    const slider = document.getElementById('timeline-slider');
    const dateEl = document.getElementById('timeline-date');
    if (slider && _meshList.length > 0) {
      slider.max = _meshList.length - 1;
      slider.value = 0;
      if (dateEl) dateEl.textContent = _meshList[0].created_on;
    }
```

### P1.4 — Add `switchMesh` function

**File**: `body_viewer.js`

**Where**: After `_loadMeshList()` function closing brace (the `}` at line 1000), add:

```javascript

window.switchMesh = function(idx) {
  idx = parseInt(idx);
  if (idx < 0 || idx >= _meshList.length) return;
  const m = _meshList[idx];
  if (bodyMesh) { scene.remove(bodyMesh); bodyMesh = null; }
  if (_ghostMesh) { scene.remove(_ghostMesh); _ghostMesh = null; }
  origMaterials = [];
  _originalMaterials.clear();
  _setStatus('Loading scan #' + m.id + '…');
  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/');
  loader.setDRACOLoader(draco);
  loader.load(`/web_app/api/mesh/${m.id}.glb`, (gltf) => {
    bodyMesh = gltf.scene;
    _applyDefaultMaterial(bodyMesh);
    _centerOnly(bodyMesh);
    scene.add(bodyMesh);
    _updateStats(bodyMesh);
    _setStatus('Scan #' + m.id + ' — ' + m.created_on);
    _createRegionLabels();
  });
  const dateEl = document.getElementById('timeline-date');
  if (dateEl) dateEl.textContent = m.created_on;
};
```

### P1.5 — Add timeline HTML

**File**: `web_app/static/viewer3d/index.html`

**Where**: Right before `<!-- Cross-section tool -->` (line 75), add:

```html
      <!-- Scan timeline -->
      <div id="timeline-panel" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Scan Timeline</h3>
        <label style="font-size:11px;display:block;">
          <input type="range" id="timeline-slider" min="0" max="0" value="0" style="width:140px;"
                 oninput="switchMesh(this.value)">
        </label>
        <div id="timeline-date" style="font-size:11px;color:#94a3b8;margin-top:2px;"></div>
      </div>
```

### P1 — Verify

- Open viewer → timeline slider appears in sidebar
- If 4+ meshes exist, slider has 4 stops
- Slide right → model changes to older scan, date label updates
- Camera stays in the same position (doesn't jump)
- View mode (solid/wire/etc) is preserved

**Needs restart**: NO

---

## P2 — Ghost Overlay

**Goal**: Show previous body mesh as semi-transparent green wireframe over current body. "Before vs After" visualization.

### P2.1 — Add ghost functions

**File**: `body_viewer.js`

**Where**: After the `switchMesh` function you just added (after its closing `};`), add:

```javascript

window.loadGhost = function() {
  const sel = document.getElementById('compare-old');
  const meshId = sel?.value;
  if (!meshId) { _setStatus('Select a "Before" mesh first'); return; }
  if (_ghostMesh) { scene.remove(_ghostMesh); _ghostMesh = null; }
  _setStatus('Loading ghost…');
  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/');
  loader.setDRACOLoader(draco);
  loader.load(`/web_app/api/mesh/${meshId}.glb`, (gltf) => {
    _ghostMesh = gltf.scene;
    _ghostMesh.traverse(c => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({
          color: 0x44ff88, wireframe: true, transparent: true, opacity: 0.3,
        });
        c.castShadow = false;
        c.receiveShadow = false;
      }
    });
    _centerOnly(_ghostMesh);
    scene.add(_ghostMesh);
    _setStatus('Ghost: scan #' + meshId);
  });
};

window.clearGhost = function() {
  if (_ghostMesh) { scene.remove(_ghostMesh); _ghostMesh = null; }
  _setStatus('');
};
```

### P2.2 — Add Ghost buttons to compare panel

**File**: `index.html`

**Where**: Find the compare panel buttons line (line 70-71):
```html
        <button onclick="runComparison()" style="font-size:11px;margin-right:4px;">Compare</button>
        <button onclick="clearComparison()" style="font-size:11px;">Clear</button>
```

**Replace with**:
```html
        <button onclick="runComparison()" style="font-size:11px;margin-right:4px;">Compare</button>
        <button onclick="loadGhost()" style="font-size:11px;margin-right:4px;">Ghost</button>
        <button onclick="clearComparison(); clearGhost()" style="font-size:11px;">Clear</button>
```

### P2 — Verify

- Select a "Before" mesh in the dropdown
- Click "Ghost" → green transparent wireframe appears overlaid on current body
- Rotate camera → ghost stays aligned with body
- Click "Clear" → ghost disappears

**Needs restart**: NO

---

## P3 — Body Stats Panel

**Goal**: Show real body measurements from profile API directly in the viewer sidebar.

### P3.1 — Add stats fetch function

**File**: `body_viewer.js`

**Where**: After the `clearGhost` function you just added, add:

```javascript

let _statsVisible = false;
async function _loadBodyStats() {
  if (!_viewerToken) return;
  try {
    const cid = _customerId();
    const resp = await fetch(`/web_app/api/customer/${cid}/body_profile`, {
      headers: _authHeaders(),
    });
    const data = await resp.json();
    if (data.status !== 'success' || !data.profile) return;
    const p = data.profile;
    const el = document.getElementById('body-stats-content');
    if (!el) return;
    const stats = [
      ['Height', p.height_cm, 'cm'],
      ['Weight', p.weight_kg, 'kg'],
      ['Chest', p.chest_circumference_cm, 'cm'],
      ['Waist', p.waist_circumference_cm, 'cm'],
      ['Hip', p.hip_circumference_cm, 'cm'],
      ['Thigh', p.thigh_circumference_cm, 'cm'],
      ['Bicep', p.bicep_circumference_cm, 'cm'],
      ['Calf', p.calf_circumference_cm, 'cm'],
      ['Neck', p.neck_circumference_cm, 'cm'],
      ['Shoulder', p.shoulder_width_cm, 'cm'],
    ];
    el.innerHTML = stats
      .filter(([, v]) => v != null)
      .map(([name, val, unit]) =>
        `<div style="display:flex;justify-content:space-between;"><span style="color:#94a3b8;">${name}</span><strong>${val}</strong><span style="color:#666;">${unit}</span></div>`
      ).join('');
  } catch (e) { console.warn('Stats load failed:', e); }
}

window.toggleBodyStats = function() {
  _statsVisible = !_statsVisible;
  const panel = document.getElementById('body-stats-panel');
  if (panel) panel.style.display = _statsVisible ? 'block' : 'none';
  document.getElementById('btn-stats')?.classList.toggle('active', _statsVisible);
};
```

### P3.2 — Wire stats loading into init

**File**: `body_viewer.js`

**Where**: Find the line (around line 188):
```javascript
  _autoLogin().then(() => { _loadMeshList(); _loadRoomTextures(); });
```

**Replace with**:
```javascript
  _autoLogin().then(() => { _loadMeshList(); _loadRoomTextures(); _loadBodyStats(); });
```

### P3.3 — Add stats panel HTML

**File**: `index.html`

**Where**: Right before `<div class="controls">` (line 85), add:

```html
      <!-- Body stats -->
      <div id="body-stats-panel" style="display:none;margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Body Measurements</h3>
        <div id="body-stats-content" style="font-size:11px;line-height:1.8;"></div>
      </div>
```

### P3.4 — Add Stats button

**File**: `index.html`

**Where**: In the V7 button row (line 30), add a 5th button after Props:

Find:
```html
        <button class="view-mode-btn" id="btn-props"
                onclick="toggleProps()">Props</button>
```

After it, add:
```html
        <button class="view-mode-btn" id="btn-stats"
                onclick="toggleBodyStats()">Stats</button>
```

### P3.5 — Add keyboard shortcut `9`

**File**: `body_viewer.js`

**Where**: In the keydown switch, after the `case '8':` line, add:

```javascript
      case '9': window.toggleBodyStats();          break;
```

### P3 — Verify

- Open viewer → click "Stats" button (or press 9) → panel shows real measurements
- Height: 168cm, Chest: 97cm, Waist: 90cm, etc (matches demo user profile)
- Click again → panel hides
- Panel values match what `curl .../body_profile` returns

**Needs restart**: NO

---

## P4 — Auto-Rotate Presentation Mode

**Goal**: Body slowly rotates for screenshots and recordings. Uses built-in OrbitControls.autoRotate.

### P4.1 — Add auto-rotate toggle

**File**: `body_viewer.js`

**Where**: After the `toggleBodyStats` function you just added, add:

```javascript

window.toggleAutoRotate = function() {
  _autoRotate = !_autoRotate;
  controls.autoRotate = _autoRotate;
  controls.autoRotateSpeed = 2.0;
  document.getElementById('btn-spin')?.classList.toggle('active', _autoRotate);
};
```

### P4.2 — Add Spin button

**File**: `index.html`

**Where**: In the V7 button row, after the Stats button you just added, add:

```html
        <button class="view-mode-btn" id="btn-spin"
                onclick="toggleAutoRotate()">Spin</button>
```

### P4.3 — Add keyboard shortcut `0`

**File**: `body_viewer.js`

**Where**: In the keydown switch, after the `case '9':` line you just added, add:

```javascript
      case '0': window.toggleAutoRotate();          break;
```

### P4.4 — Update keyboard hint

**File**: `index.html`

**Where**: Find the key hints div (line 92-94). Replace with:

```html
      <div style="font-size:9px;color:#555;margin-top:6px;">
        Keys: 1-4 views · 5 walk · 6 room · 7 mirror · 8 props<br>
        9 stats · 0 spin · L labels · M measure · R reset · S shot
      </div>
```

### P4 — Verify

- Press `0` → body starts rotating slowly
- Press `0` → rotation stops
- Drag to orbit while spinning → orbit works, spinning resumes when you let go
- Walk mode (5) still works independently

**Needs restart**: NO

---

## P5 — Ground Grid

**Goal**: Subtle measurement grid on the floor when room is on. Helps judge body scale.

### P5.1 — Add grid to room

**File**: `body_viewer.js`

**Where**: Inside `_buildRoom()`, right before the line `scene.add(_roomGroup);` (line 1162), add:

```javascript

  // Floor measurement grid (10cm intervals ≈ 17.86 scene units, 20 divisions across 4m)
  _gridHelper = new THREE.GridHelper(_ROOM_W, 20, 0x777777, 0x555555);
  _gridHelper.position.y = 0.5;
  _roomGroup.add(_gridHelper);
```

### P5 — Verify

- Press `6` (room on) → subtle grid visible on floor
- Grid has ~20 divisions across the room width (4m / 20 = 20cm per cell)
- Grid disappears when room is toggled off (it's a child of roomGroup)
- Grid doesn't interfere with body shadow

**Needs restart**: NO

---

## Execution Order

| Order | Task | Depends On | Time Est |
|-------|------|-----------|----------|
| 1 | P1 (Timeline) | — | 5 min |
| 2 | P2 (Ghost) | P1 (`_centerOnly`) | 3 min |
| 3 | P3 (Stats) | — | 4 min |
| 4 | P4 (Spin) | — | 2 min |
| 5 | P5 (Grid) | — | 1 min |

**Total: ~15 min, zero server restarts.**

---

## Pitfalls

- **P1**: When switching meshes, clear `origMaterials` array and `_originalMaterials` map — otherwise heatmap toggle breaks on the new mesh (stale references to removed mesh children)
- **P2**: Ghost must use `_centerOnly` NOT `_centerAndScale` — otherwise camera jumps to ghost position
- **P2**: Ghost `castShadow = false` — otherwise the green wireframe casts a shadow blob that conflicts with the body's shadow
- **P3**: Filter out `null` values — some measurements may be empty (e.g., `inseam_cm: null`)
- **P4**: Auto-rotate only works when `controls.update()` is called in the render loop — it already is (line 1403), but NOT when `_walkMode` is true. That's correct: walk mode disables orbit, so spin should stop.
- **P5**: Grid `position.y = 0.5` keeps it just above the floor plane (Y=0) to prevent z-fighting flicker

## Files Modified by V8

| File | Changes |
|------|---------|
| `body_viewer.js` | +~90 lines: globals, _centerOnly, switchMesh, ghost, stats, spin, grid |
| `index.html` | +~20 lines: timeline slider, ghost button, stats panel, spin button, key hints |

## Keyboard Map After V8
| Key | Action |
|-----|--------|
| 1-4 | View modes |
| 5 | Walk mode |
| 6 | Room toggle |
| 7 | Mirror cycle |
| 8 | Props toggle |
| 9 | Body stats toggle |
| 0 | Auto-rotate toggle |
| L | Labels |
| M | Measure |
| R | Reset camera |
| S | Screenshot (or backward in walk) |
| WASD | Move (walk mode) |
| Esc | Exit walk / exit measure |
