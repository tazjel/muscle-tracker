# V9 Task Sheet — UI Polish & Interaction Refinements

> **For Sonnet execution only.** All code provided — paste and verify.
> Static files only. Zero server restarts. Zero Python changes.

---

## How to Use This Sheet

1. Work top-to-bottom — P1 through P5
2. Each task uses **unique string anchors** for Edit tool — match the `old_string` exactly
3. Do NOT read files unless a verification fails
4. Do NOT refactor, add features, or "improve" anything

---

## P1 — Hover Info Tooltip

**Goal**: Mouseover body shows region name + actual measurement from profile (e.g., "Chest: 97cm").

### P1.1 — Store profile data for hover lookup

**File**: `web_app/static/viewer3d/body_viewer.js`

**Find** (unique anchor):
```javascript
let _statsVisible = false;
async function _loadBodyStats() {
```

**Replace with**:
```javascript
let _statsVisible = false;
let _bodyProfile  = null;
async function _loadBodyStats() {
```

Then **find**:
```javascript
    if (data.status !== 'success' || !data.profile) return;
    const p = data.profile;
    const el = document.getElementById('body-stats-content');
```

**Replace with**:
```javascript
    if (data.status !== 'success' || !data.profile) return;
    const p = data.profile;
    _bodyProfile = p;
    const el = document.getElementById('body-stats-content');
```

### P1.2 — Add hover tooltip functions

**File**: `body_viewer.js`

**Find** (after auto-rotate, before runComparison):
```javascript
window.toggleAutoRotate = function() {
  _autoRotate = !_autoRotate;
  controls.autoRotate = _autoRotate;
  controls.autoRotateSpeed = 2.0;
  document.getElementById('btn-spin')?.classList.toggle('active', _autoRotate);
};

window.runComparison = async function() {
```

**Replace with**:
```javascript
window.toggleAutoRotate = function() {
  _autoRotate = !_autoRotate;
  controls.autoRotate = _autoRotate;
  controls.autoRotateSpeed = 2.0;
  document.getElementById('btn-spin')?.classList.toggle('active', _autoRotate);
};

// ── Hover info tooltip (V9) ─────────────────────────────────────────────────
const _REGION_FIELDS = {
  chest: ['chest_circumference_cm', 'cm'], waist: ['waist_circumference_cm', 'cm'],
  hip: ['hip_circumference_cm', 'cm'], thigh: ['thigh_circumference_cm', 'cm'],
  calf: ['calf_circumference_cm', 'cm'], arm: ['bicep_circumference_cm', 'cm'],
  neck: ['neck_circumference_cm', 'cm'], shoulder: ['shoulder_width_cm', 'cm'],
  head: ['head_circumference_cm', 'cm'], knee: ['thigh_circumference_cm', 'cm'],
};

function _onMeshHover(event) {
  if (_measureMode || _walkMode) return;
  const tooltip = document.getElementById('hover-tooltip');
  if (!tooltip) return;
  const hit = _getMeshIntersection(event);
  if (!hit) { tooltip.style.display = 'none'; return; }
  const region = getBodyRegion(hit.point);
  const label = region.charAt(0).toUpperCase() + region.slice(1);
  let text = label;
  if (_bodyProfile) {
    const entry = _REGION_FIELDS[region];
    if (entry) {
      const val = _bodyProfile[entry[0]];
      if (val != null) text += ': ' + val + entry[1];
    }
  }
  tooltip.textContent = text;
  tooltip.style.display = 'block';
  tooltip.style.left = (event.clientX + 15) + 'px';
  tooltip.style.top = (event.clientY - 10) + 'px';
}

window.runComparison = async function() {
```

### P1.3 — Wire hover listener in init

**File**: `body_viewer.js`

**Find**:
```javascript
  // Click-to-select body region
  renderer.domElement.addEventListener('click', _onMeshClick);
```

**Replace with**:
```javascript
  // Click-to-select body region
  renderer.domElement.addEventListener('click', _onMeshClick);
  renderer.domElement.addEventListener('mousemove', _onMeshHover);
```

### P1.4 — Add tooltip HTML

**File**: `web_app/static/viewer3d/index.html`

**Find**:
```html
  <!-- Canvas -->
  <div id="canvas-container"></div>
```

**Replace with**:
```html
  <!-- Hover tooltip -->
  <div id="hover-tooltip" style="position:fixed;display:none;background:rgba(0,0,0,0.8);color:#e0e0e0;padding:4px 10px;border-radius:4px;font-size:12px;pointer-events:none;z-index:100;border:1px solid #4a9eff;white-space:nowrap;"></div>

  <!-- Canvas -->
  <div id="canvas-container"></div>
```

### P1 — Verify

- Move mouse over body → tooltip follows cursor showing "Chest: 97cm", "Waist: 90cm", etc.
- Move off body → tooltip disappears
- Tooltip doesn't appear during Measure mode or Walk mode
- "Head", "Ankle" show just the name (no measurement mapped or null)

**Needs restart**: NO

---

## P2 — Fullscreen Toggle

**Goal**: Key `F` hides sidebar and enters browser fullscreen for clean presentation.

### P2.1 — Add fullscreen function

**File**: `body_viewer.js`

**Find** (the hover tooltip section you just added has `window.runComparison` after it — add fullscreen BEFORE the hover section):

Actually, add it right after `toggleAutoRotate`. **Find**:
```javascript
  document.getElementById('btn-spin')?.classList.toggle('active', _autoRotate);
};

// ── Hover info tooltip (V9)
```

**Replace with**:
```javascript
  document.getElementById('btn-spin')?.classList.toggle('active', _autoRotate);
};

window.toggleFullscreen = function() {
  const overlay = document.getElementById('ui-overlay');
  const legend = document.querySelector('.heatmap-legend');
  if (!document.fullscreenElement) {
    document.body.requestFullscreen().catch(() => {});
    if (overlay) overlay.style.display = 'none';
    if (legend) legend.style.display = 'none';
  } else {
    document.exitFullscreen();
    if (overlay) overlay.style.display = '';
    if (legend) legend.style.display = '';
  }
};

// ── Hover info tooltip (V9)
```

### P2.2 — Add key `F` to keyboard handler

**File**: `body_viewer.js`

**Find**:
```javascript
      case 'l': case 'L': window.toggleLabels();  break;
```

**Replace with**:
```javascript
      case 'f': case 'F': window.toggleFullscreen(); break;
      case 'l': case 'L': window.toggleLabels();  break;
```

### P2.3 — Restore sidebar on fullscreen exit (Escape)

**File**: `body_viewer.js`

**Find** (in init, after the resize listener):
```javascript
  // Resize
  window.addEventListener('resize', _onResize);
```

**Replace with**:
```javascript
  // Resize
  window.addEventListener('resize', _onResize);

  // Restore sidebar when exiting fullscreen via Escape
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) {
      const overlay = document.getElementById('ui-overlay');
      if (overlay) overlay.style.display = '';
    }
  });
```

### P2.4 — Update keyboard hints

**File**: `index.html`

**Find**:
```html
        9 stats · 0 spin · L labels · M measure · R reset · S shot
```

**Replace with**:
```html
        9 stats · 0 spin · F full · L labels · M measure · R reset
```

### P2 — Verify

- Press `F` → sidebar disappears, browser enters fullscreen, just the 3D body visible
- Press `Escape` → exits fullscreen, sidebar returns
- Press `F` again → works repeatedly

**Needs restart**: NO

---

## P3 — Collapsible Sidebar Panels

**Goal**: Click section header (h3) to collapse/expand. Keeps sidebar manageable. Compare, Timeline, and Cross-Section start collapsed.

### P3.1 — Add CSS

**File**: `web_app/static/viewer3d/styles.css`

**Find** (at the very end of the file):
```css
  #compare-panel select {
    width: 100px !important;
  }
}
```

**After it, add**:
```css

/* ── Collapsible panels (V9) ────────────────────────────── */
.collapsible > h3 {
  cursor: pointer;
  user-select: none;
}
.collapsible > h3::after {
  content: ' \25BE';
  font-size: 9px;
  color: #666;
}
.collapsible.collapsed > h3::after {
  content: ' \25B8';
}
.collapsible.collapsed > *:not(h3) {
  display: none !important;
}
```

### P3.2 — Add collapsible class to panels

**File**: `index.html`

Make these 3 replacements (each is unique):

**Replace 1** — Compare panel:
```html
      <div id="compare-panel" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Compare Growth</h3>
```
→
```html
      <div id="compare-panel" class="collapsible collapsed" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Compare Growth</h3>
```

**Replace 2** — Timeline panel:
```html
      <div id="timeline-panel" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Scan Timeline</h3>
```
→
```html
      <div id="timeline-panel" class="collapsible collapsed" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Scan Timeline</h3>
```

**Replace 3** — Cross-section panel:
```html
      <div id="section-panel" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Cross Section</h3>
```
→
```html
      <div id="section-panel" class="collapsible collapsed" style="margin-top:10px;border-top:1px solid #444;padding-top:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">Cross Section</h3>
```

### P3.3 — Add click handler in init

**File**: `body_viewer.js`

**Find**:
```javascript
  // Authenticate for save/regenerate calls then load mesh list + room textures
  _autoLogin().then(() => { _loadMeshList(); _loadRoomTextures(); _loadBodyStats(); });
```

**Replace with**:
```javascript
  // Collapsible panels — click h3 to toggle
  document.querySelectorAll('.collapsible > h3').forEach(h3 => {
    h3.addEventListener('click', () => h3.parentElement.classList.toggle('collapsed'));
  });

  // Authenticate for save/regenerate calls then load mesh list + room textures
  _autoLogin().then(() => { _loadMeshList(); _loadRoomTextures(); _loadBodyStats(); });
```

### P3 — Verify

- Open viewer → Compare, Timeline, Cross Section panels show only their header (collapsed, with ▸ arrow)
- Click "Compare Growth" header → panel expands (▾ arrow), dropdowns visible
- Click again → collapses
- Body stats panel (toggle via Stats button) still works independently — it uses display:none/block, not the collapsible class

**Needs restart**: NO

---

## P4 — Smooth Camera Transitions

**Goal**: `resetCamera` and view switching animate smoothly instead of instant snap. ~400ms ease-out.

### P4.1 — Add transition global

**File**: `body_viewer.js`

**Find**:
```javascript
// ── V8 globals ───────────────────────────────────────────────────────────────
```

**Replace with**:
```javascript
// ── V8 globals ───────────────────────────────────────────────────────────────
let _camTransition = null;  // {startPos, endPos, startTarget, endTarget, startTime, duration}
```

### P4.2 — Replace resetCamera with animated version

**File**: `body_viewer.js`

**Find**:
```javascript
window.resetCamera = function() {
  if (bodyMesh) {
    const box = new THREE.Box3().setFromObject(bodyMesh);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    const camZ = maxDim / (2 * Math.tan(fov / 2)) * 1.6;
    const midY = size.y * 0.45;
    camera.position.set(0, midY, camZ);
    controls.target.set(0, midY, 0);
  } else {
    camera.position.set(0, 150, 400);
    controls.target.set(0, 80, 0);
  }
  controls.update();
};
```

**Replace with**:
```javascript
window.resetCamera = function() {
  let endPos, endTarget;
  if (bodyMesh) {
    const box = new THREE.Box3().setFromObject(bodyMesh);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    const camZ = maxDim / (2 * Math.tan(fov / 2)) * 1.6;
    const midY = size.y * 0.45;
    endPos = new THREE.Vector3(0, midY, camZ);
    endTarget = new THREE.Vector3(0, midY, 0);
  } else {
    endPos = new THREE.Vector3(0, 150, 400);
    endTarget = new THREE.Vector3(0, 80, 0);
  }
  _camTransition = {
    startPos: camera.position.clone(),
    endPos,
    startTarget: controls.target.clone(),
    endTarget,
    startTime: performance.now(),
    duration: 400,
  };
};
```

### P4.3 — Add transition update in render loop

**File**: `body_viewer.js`

**Find**:
```javascript
function _animate() {
  requestAnimationFrame(_animate);
  _updateFirstPerson();
  if (!_walkMode) controls.update();
```

**Replace with**:
```javascript
function _animate() {
  requestAnimationFrame(_animate);
  _updateFirstPerson();
  // Smooth camera transition
  if (_camTransition) {
    const t = Math.min(1, (performance.now() - _camTransition.startTime) / _camTransition.duration);
    const e = t * (2 - t);  // ease-out quad
    camera.position.lerpVectors(_camTransition.startPos, _camTransition.endPos, e);
    controls.target.lerpVectors(_camTransition.startTarget, _camTransition.endTarget, e);
    if (t >= 1) _camTransition = null;
  }
  if (!_walkMode) controls.update();
```

### P4 — Verify

- Orbit camera to a weird angle → press `R` → camera smoothly glides back to default position (~0.4s)
- No instant snap
- Walk mode (5) still works (transition is ignored when walking)
- Double-tap on mobile still triggers smooth reset

**Needs restart**: NO

---

## P5 — Loading Pulse Animation

**Goal**: Status text pulses while loading a mesh. Subtle visual feedback.

### P5.1 — Add CSS

**File**: `styles.css`

**Find** (at the end, after the collapsible CSS you added in P3):
```css
.collapsible.collapsed > *:not(h3) {
  display: none !important;
}
```

**After it, add**:
```css

/* ── Loading pulse (V9) ─────────────────────────────────── */
#mesh-info.loading {
  animation: info-pulse 1.5s ease-in-out infinite;
  color: #4a9eff;
}
@keyframes info-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
```

### P5.2 — Add/remove loading class in status helper

**File**: `body_viewer.js`

**Find**:
```javascript
function _setStatus(msg) {
  const el = document.getElementById('mesh-info');
  if (el) el.textContent = msg;
}
```

**Replace with**:
```javascript
function _setStatus(msg) {
  const el = document.getElementById('mesh-info');
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('loading', msg.includes('Loading') || msg.includes('loading'));
}
```

### P5 — Verify

- Reload the page → "Loading model…" text pulses blue while mesh loads
- After mesh loads → text stops pulsing, shows normal color
- Switch mesh via timeline slider → "Loading scan #X…" text pulses
- Ghost loading → "Loading ghost…" pulses

**Needs restart**: NO

---

## Execution Order

| Order | Task | Depends On | Time Est |
|-------|------|-----------|----------|
| 1 | P1 (Hover tooltip) | — | 4 min |
| 2 | P2 (Fullscreen) | — | 3 min |
| 3 | P3 (Collapsible) | — | 3 min |
| 4 | P4 (Smooth camera) | — | 3 min |
| 5 | P5 (Loading pulse) | P3 CSS (append after it) | 2 min |

**Total: ~15 min, zero server restarts.**

---

## Pitfalls

- **P1**: `_getMeshIntersection` raycasts against `bodyMesh` — on mousemove it fires every frame. This is cheap (single raycast) but don't add any heavy computation inside `_onMeshHover`.
- **P1**: Must check `_measureMode` and `_walkMode` — tooltip should NOT appear when measuring or walking.
- **P2**: `document.body.requestFullscreen()` can fail silently — use `.catch(() => {})`. Some browsers need `webkitRequestFullscreen`.
- **P2**: Must restore sidebar on `fullscreenchange` event (user can exit via Escape without triggering our handler).
- **P3**: `.collapsed > *:not(h3)` uses `!important` to override inline `display:block` styles on child elements.
- **P3**: Do NOT add `collapsible` to `adjust-panel` or `body-stats-panel` — they use their own show/hide logic (display:none by default).
- **P4**: `lerpVectors` is a THREE.Vector3 method — it's called on camera.position which IS a Vector3. No allocation needed.
- **P4**: Transition should be skipped in walk mode — the `_updateFirstPerson` runs before transition code, and `controls.update()` only runs when `!_walkMode`. This is safe because transitions only happen from `resetCamera`, which is only useful in orbit mode.
- **P5**: The `includes('Loading')` check is case-sensitive — matches "Loading model…", "Loading scan #X…", "Loading ghost…" but not "Comparison error" or "Saved".

## Files Modified by V9

| File | Changes |
|------|---------|
| `body_viewer.js` | +~50 lines: hover tooltip, fullscreen, smooth camera, loading class |
| `index.html` | +3 lines: tooltip div, collapsible classes, key hint update |
| `styles.css` | +20 lines: collapsible panel CSS, loading pulse animation |

## Keyboard Map After V9
| Key | Action |
|-----|--------|
| 1-4 | View modes |
| 5 | Walk mode |
| 6 | Room toggle |
| 7 | Mirror cycle |
| 8 | Props toggle |
| 9 | Body stats toggle |
| 0 | Auto-rotate toggle |
| F | Fullscreen toggle |
| L | Labels |
| M | Measure |
| R | Smooth reset camera |
| S | Screenshot (or backward in walk) |
| WASD | Move (walk mode) |
| Esc | Exit walk / exit measure / exit fullscreen |
