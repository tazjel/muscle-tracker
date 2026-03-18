# SONNET V15 — New Perspectives: Silhouette Profile + Posture Axis + Volume Zones

> **Theme:** Structural understanding — three new windows into the body that no previous version shows: a real-time silhouette profile panel, a 3D posture axis revealing alignment, and zone-by-zone volume distribution.
> **Files:** `body_viewer.js`, `index.html` (2 files, ~185 lines added)
> **Server restart:** NO — pure JS/HTML, refresh browser
> **Depends on:** V11 (`_meshCrossSection`, `_richCrossSection`, `_ANALYSIS_LANDMARKS`), V12 (`_sortedCrossSection`), V14 globals

---

## The Creative Vision

V11-V14 showed measurements and changes. V15 asks a deeper question: **what is the body's structure in space?**

**Silhouette Profile (P):** A 150×300px canvas overlay at top-right. Shows the body's front silhouette (width at every height) and side silhouette (depth at every height) — derived from actual 3D mesh data, not scan photos. Ghost overlay in green. Landmark ticks. This is the "honest before/after" from 3D geometry: no misleading camera angles, no lighting tricks.

**Posture Axis (Q):** A colored 3D line through the body's centroid column. Green = aligned, red = deviated. Small spheres mark each centroid. With ghost: a second line shows how the alignment changed. Immediately reveals lean, tilt, and shoulder drop.

**Volume Zones:** Added to the analysis panel — uses the 5 `currRich` cross-section areas (already computed) to estimate volume of 6 body zones via the trapezoid rule. Shows zone percentages and ghost deltas. Answers: "where is the body's mass concentrated, and did it shift?"

---

## T1 — Globals

**Find** (exact):
```js
let _sliceGroup  = null;

// ── Auth ──────────────────────────────────────────────────────────────────────
```

**Replace with:**
```js
let _sliceGroup  = null;

// ── V15 globals ──────────────────────────────────────────────────────────────
let _axisGroup      = null;
let _axisVisible    = false;
let _profileVisible = false;

// ── Auth ──────────────────────────────────────────────────────────────────────
```

---

## T2 — Fast Mesh Helpers (vertex-bucketing, O(vertices))

Both profile and axis need per-height data. These helpers iterate vertices ONCE — no cross-section overhead.

**Find** (exact):
```js
// ── V11: Scan Analysis ───────────────────────────────────────────────────────
```

**Insert BEFORE that line:**
```js
// ── V15: Fast mesh helpers ────────────────────────────────────────────────────
function _computeProfileFast(mesh, numBuckets) {
  if (!mesh) return null;
  const box = new THREE.Box3().setFromObject(mesh);
  const minY = box.min.y, rangeY = box.max.y - box.min.y;
  if (rangeY < 1) return null;
  const buckets = Array.from({ length: numBuckets }, () =>
    ({ minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity }));
  const v = new THREE.Vector3();
  mesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(child.matrixWorld);
      const bin = Math.min(numBuckets - 1, Math.floor((v.y - minY) / rangeY * numBuckets));
      if (bin >= 0) {
        buckets[bin].minX = Math.min(buckets[bin].minX, v.x);
        buckets[bin].maxX = Math.max(buckets[bin].maxX, v.x);
        buckets[bin].minZ = Math.min(buckets[bin].minZ, v.z);
        buckets[bin].maxZ = Math.max(buckets[bin].maxZ, v.z);
      }
    }
  });
  // Fill empty buckets by borrowing from neighbors
  for (let i = 1; i < numBuckets; i++) {
    if (!isFinite(buckets[i].maxX)) buckets[i] = { ...buckets[i - 1] };
  }
  return { buckets, box };
}

function _computeCentroidAxis(mesh, numLevels) {
  if (!mesh) return null;
  const box = new THREE.Box3().setFromObject(mesh);
  const minY = box.min.y, rangeY = box.max.y - box.min.y;
  if (rangeY < 1) return null;
  const bins = Array.from({ length: numLevels }, () => ({ sumX: 0, sumZ: 0, count: 0 }));
  const v = new THREE.Vector3();
  mesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(child.matrixWorld);
      const bin = Math.min(numLevels - 1, Math.floor((v.y - minY) / rangeY * numLevels));
      if (bin >= 0) { bins[bin].sumX += v.x; bins[bin].sumZ += v.z; bins[bin].count++; }
    }
  });
  const sceneToMm = rangeY > 0 ? 1680 / rangeY : 1;
  return bins.map((b, i) => ({
    y: minY + (i + 0.5) * rangeY / numLevels,
    cx: b.count > 0 ? b.sumX / b.count : 0,
    cz: b.count > 0 ? b.sumZ / b.count : 0,
    devMm: b.count > 0 ? Math.sqrt((b.sumX / b.count) ** 2 + (b.sumZ / b.count) ** 2) * sceneToMm : 0,
  }));
}

```

### Verify T2
No visible change. No console errors.

---

## T3 — Silhouette Profile Panel

**Find** (exact):
```js
// ── V12: Measurement rings ──────────────────────────────────────────────────
```

**Insert BEFORE that line:**
```js
// ── V15: Silhouette profile panel ────────────────────────────────────────────
function _drawSilhouetteProfile(canvas, currData, ghostData) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(22,33,62,0.92)';
  ctx.fillRect(0, 0, W, H);

  const N = currData.buckets.length;
  const plotTop = 18, plotH = H - 24, labelW = 26;
  const colW = (W - labelW - 4) / 2;
  const frontCx = labelW + colW / 2;
  const sideCx  = labelW + colW + 4 + colW / 2;

  // Headers
  ctx.font = 'bold 8px sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = '#4a9eff';
  ctx.fillText('FRONT', frontCx, 10);
  ctx.fillText('SIDE', sideCx, 10);
  ctx.strokeStyle = 'rgba(74,158,255,0.2)'; ctx.lineWidth = 0.5;
  ctx.beginPath(); ctx.moveTo(labelW + colW + 2, 12); ctx.lineTo(labelW + colW + 2, H - 4); ctx.stroke();

  // Find max extents for normalization
  const maxHalfW = Math.max(...currData.buckets.map(b => Math.max(Math.abs(b.maxX), Math.abs(b.minX))), 1);
  const maxHalfD = Math.max(...currData.buckets.map(b => Math.max(Math.abs(b.maxZ), Math.abs(b.minZ))), 1);

  function drawOutline(data, cx, getRight, getLeft, isGhost) {
    const buckets = data.buckets;
    const N2 = buckets.length;
    const scale = cx === frontCx ? colW * 0.46 / maxHalfW : colW * 0.46 / maxHalfD;
    ctx.beginPath();
    // Right edge top→bottom
    for (let i = N2 - 1; i >= 0; i--) {
      const y = plotTop + (1 - i / (N2 - 1)) * plotH;
      ctx.lineTo(cx + getRight(buckets[i]) * scale, y);
    }
    // Left edge bottom→top
    for (let i = 0; i < N2; i++) {
      const y = plotTop + (1 - i / (N2 - 1)) * plotH;
      ctx.lineTo(cx + getLeft(buckets[i]) * scale, y);
    }
    ctx.closePath();
    ctx.fillStyle = isGhost ? 'rgba(68,255,136,0.08)' : 'rgba(74,158,255,0.12)';
    ctx.fill();
    ctx.strokeStyle = isGhost ? 'rgba(68,255,136,0.7)' : '#4a9eff';
    ctx.lineWidth = isGhost ? 0.8 : 1.2;
    ctx.stroke();
  }

  if (ghostData) {
    drawOutline(ghostData, frontCx, b => b.maxX, b => b.minX, true);
    drawOutline(ghostData, sideCx, b => b.maxZ, b => b.minZ, true);
  }
  drawOutline(currData, frontCx, b => b.maxX, b => b.minX, false);
  drawOutline(currData, sideCx, b => b.maxZ, b => b.minZ, false);

  // Landmark height markers
  const NAMES = Object.keys(_ANALYSIS_LANDMARKS);
  const RATIOS = Object.values(_ANALYSIS_LANDMARKS);
  ctx.font = '7px sans-serif'; ctx.textAlign = 'right'; ctx.lineWidth = 0.4;
  for (let li = 0; li < NAMES.length; li++) {
    const y = plotTop + (1 - RATIOS[li]) * plotH;
    ctx.fillStyle = '#555'; ctx.strokeStyle = 'rgba(74,158,255,0.2)';
    ctx.beginPath(); ctx.moveTo(labelW, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(NAMES[li].slice(0, 3), labelW - 1, y + 3);
  }
}

window.toggleProfile = function() {
  _profileVisible = !_profileVisible;
  let canvas = document.getElementById('profile-canvas');
  if (!canvas) return;
  canvas.style.display = _profileVisible ? 'block' : 'none';
  const btn = document.getElementById('btn-profile');
  if (btn) btn.classList.toggle('active', _profileVisible);
  if (_profileVisible) _refreshProfile();
};

function _refreshProfile() {
  if (!_profileVisible || !bodyMesh) return;
  const canvas = document.getElementById('profile-canvas');
  if (!canvas) return;
  const curr  = _computeProfileFast(bodyMesh, 120);
  const ghost = _ghostMesh ? _computeProfileFast(_ghostMesh, 120) : null;
  if (curr) _drawSilhouetteProfile(canvas, curr, ghost);
}

```

---

## T4 — Posture Axis

**Find** (exact — immediately after T3 code, still before V12 rings):
```js
// ── V12: Measurement rings ──────────────────────────────────────────────────
```

**Insert BEFORE that line:**
```js
// ── V15: Posture axis ────────────────────────────────────────────────────────
function _buildPostureAxis() {
  if (_axisGroup) { scene.remove(_axisGroup); _axisGroup = null; }
  if (!bodyMesh) return;

  _axisGroup = new THREE.Group();
  const NUM = 20;
  const centroids = _computeCentroidAxis(bodyMesh, NUM);
  if (!centroids) return;

  const points = centroids.map(c => new THREE.Vector3(c.cx, c.y, c.cz));
  const colorArr = new Float32Array(NUM * 3);
  centroids.forEach((c, i) => {
    const t = Math.min(1, c.devMm / 20);  // 0=straight, 1=20mm+ deviation
    colorArr[i * 3]     = 0.3 + 0.7 * t;  // R: low→high
    colorArr[i * 3 + 1] = 0.9 - 0.7 * t;  // G: high→low
    colorArr[i * 3 + 2] = 0.3 * (1 - t);  // B: fades
  });
  const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
  lineGeo.setAttribute('color', new THREE.Float32BufferAttribute(colorArr, 3));
  _axisGroup.add(new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ vertexColors: true })));

  // Sphere at each centroid (colored same as line)
  centroids.forEach((c, i) => {
    const t = Math.min(1, c.devMm / 20);
    const color = new THREE.Color(0.3 + 0.7 * t, 0.9 - 0.7 * t, 0.3 * (1 - t));
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(2, 6, 4),
      new THREE.MeshBasicMaterial({ color })
    );
    sphere.position.set(c.cx, c.y, c.cz);
    _axisGroup.add(sphere);
  });

  // Ghost axis if loaded
  if (_ghostMesh) {
    const gCentroids = _computeCentroidAxis(_ghostMesh, NUM);
    if (gCentroids) {
      const gPoints = gCentroids.map(c => new THREE.Vector3(c.cx, c.y, c.cz));
      const gGeo = new THREE.BufferGeometry().setFromPoints(gPoints);
      _axisGroup.add(new THREE.Line(gGeo, new THREE.LineBasicMaterial({ color: 0x44ff88, transparent: true, opacity: 0.5 })));
    }
  }

  _axisGroup.visible = _axisVisible;
  scene.add(_axisGroup);
}

window.togglePostureAxis = function() {
  _axisVisible = !_axisVisible;
  if (_axisVisible && !_axisGroup) _buildPostureAxis();
  if (_axisGroup) _axisGroup.visible = _axisVisible;
  const btn = document.getElementById('btn-axis');
  if (btn) btn.classList.toggle('active', _axisVisible);
};

```

---

## T5 — Volume Zones in Analysis Panel

### 5a — New helper

**Find** (exact):
```js
function _computeRatiosHtml(measurements) {
```

**Insert BEFORE that line:**
```js
function _computeVolumeZonesHtml(richMap, ghostRichMap) {
  if (!richMap || !richMap.Shoulder) return '';
  const H_CM = 168;  // body height in cm
  // Define zones: [name, bottom_ratio, top_ratio, area_landmarks...]
  const zones = [
    { name: 'Legs',    h: 0.34, area: richMap.Thigh?.areaCm2 || 0 },
    { name: 'Thighs',  h: 0.11, area: ((richMap.Thigh?.areaCm2||0) + (richMap.Hip?.areaCm2||0)) / 2 },
    { name: 'Pelvis',  h: 0.09, area: ((richMap.Hip?.areaCm2||0) + (richMap.Waist?.areaCm2||0)) / 2 },
    { name: 'Torso',   h: 0.10, area: ((richMap.Waist?.areaCm2||0) + (richMap.Chest?.areaCm2||0)) / 2 },
    { name: 'Chest',   h: 0.12, area: ((richMap.Chest?.areaCm2||0) + (richMap.Shoulder?.areaCm2||0)) / 2 },
    { name: 'Upper',   h: 0.24, area: richMap.Shoulder?.areaCm2 || 0 },
  ];
  zones.forEach(z => { z.vol = z.area * z.h * H_CM; });
  const totalVol = zones.reduce((s, z) => s + z.vol, 0);
  if (totalVol < 1) return '';

  // Ghost volumes
  if (ghostRichMap && ghostRichMap.Shoulder) {
    const gz = [
      { area: ghostRichMap.Thigh?.areaCm2 || 0 },
      { area: ((ghostRichMap.Thigh?.areaCm2||0) + (ghostRichMap.Hip?.areaCm2||0)) / 2 },
      { area: ((ghostRichMap.Hip?.areaCm2||0) + (ghostRichMap.Waist?.areaCm2||0)) / 2 },
      { area: ((ghostRichMap.Waist?.areaCm2||0) + (ghostRichMap.Chest?.areaCm2||0)) / 2 },
      { area: ((ghostRichMap.Chest?.areaCm2||0) + (ghostRichMap.Shoulder?.areaCm2||0)) / 2 },
      { area: ghostRichMap.Shoulder?.areaCm2 || 0 },
    ];
    zones.forEach((z, i) => { z.ghostVol = gz[i].area * z.h * H_CM; });
  }

  let html = '<div style="margin-top:6px;color:#4a9eff;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Volume Zones</div>';
  for (const z of zones) {
    const pct = (z.vol / totalVol * 100).toFixed(0);
    let delta = '';
    if (z.ghostVol != null) {
      const d = z.vol - z.ghostVol;
      const c = d > 50 ? '#22c55e' : d < -50 ? '#ef4444' : '#94a3b8';
      delta = ` <span style="color:${c};font-size:9px;">${d > 0 ? '+' : ''}${(d / 1000).toFixed(2)}L</span>`;
    }
    html += `<div style="display:flex;justify-content:space-between;align-items:center;">`;
    html += `<span style="color:#94a3b8;">${z.name}</span>`;
    html += `<span style="color:#e0e0e0;font-size:10px;">${pct}%${delta}</span>`;
    html += `</div>`;
  }
  return html;
}

```

### 5b — Wire into `_computeAnalysis`

**Find** (exact):
```js
  // Extensible sections
  html += _computeWidthDepthHtml(currRich);
  html += _computeSymmetryHtml();
  html += _computeRatiosHtml(curr);
```

**Replace with:**
```js
  // Extensible sections
  html += _computeWidthDepthHtml(currRich);
  html += _computeVolumeZonesHtml(currRich, Object.keys(ghostCurr).length > 0 ? _ghostRich : null);
  html += _computeSymmetryHtml();
  html += _computeRatiosHtml(curr);
```

### 5c — Collect `_ghostRich` alongside `ghostCurr`

The `_computeVolumeZonesHtml` needs ghost `areaCm2` values. We must collect a ghost rich map. Add a module-level variable and populate it during analysis.

**Find** (exact):
```js
  const curr      = {};
  const currRich  = {};
  const ghostCurr = {};
```

**Replace with:**
```js
  const curr      = {};
  const currRich  = {};
  const ghostCurr = {};
  _ghostRich      = {};
```

**Find** (exact):
```js
      const prev = _meshCrossSection(_ghostMesh, ratio);
      const prevCm = prev ? prev.circumferenceCm : null;
      ghostCurr[name] = prevCm;
```

**Replace with:**
```js
      const prev = _richCrossSection(_ghostMesh, ratio);
      const prevCm = prev ? prev.circumferenceCm : null;
      ghostCurr[name] = prevCm;
      _ghostRich[name] = prev;
```

**Add `_ghostRich` as a module-level variable** — it must exist outside `_computeAnalysis` since `_computeVolumeZonesHtml` reads it. Add it to T1 globals:

**Find** (from T1, already done):
```js
let _profileVisible = false;

// ── Auth ──────────────────────────────────────────────────────────────────────
```

**Replace with:**
```js
let _profileVisible = false;
let _ghostRich      = {};

// ── Auth ──────────────────────────────────────────────────────────────────────
```

---

## T6 — Wire-ups

### 6a — Add profile + axis to `_resetVisModes`

**Find** (exact):
```js
function _resetVisModes() {
  if (_growthMode) {
```

**Replace with:**
```js
function _resetVisModes() {
  if (_axisVisible) {
    _axisVisible = false;
    if (_axisGroup) { scene.remove(_axisGroup); _axisGroup = null; }
    document.getElementById('btn-axis')?.classList.remove('active');
  }
  if (_profileVisible) {
    _profileVisible = false;
    const pc = document.getElementById('profile-canvas'); if (pc) pc.style.display = 'none';
    document.getElementById('btn-profile')?.classList.remove('active');
  }
  if (_growthMode) {
```

### 6b — Refresh profile + axis on ghost load/clear

**Find** (exact):
```js
    if (_growthMode) _applyGrowthColors();
    if (_sliceMode) _buildSliceView();
  });
};
```

**Replace with:**
```js
    if (_growthMode) _applyGrowthColors();
    if (_sliceMode) _buildSliceView();
    if (_axisVisible) _buildPostureAxis();
    _refreshProfile();
  });
};
```

**Find** (exact, in clearGhost):
```js
  if (_sliceMode) _buildSliceView();  // rebuild without ghost outlines
};
```

**Replace with:**
```js
  if (_sliceMode) _buildSliceView();  // rebuild without ghost outlines
  if (_axisVisible) _buildPostureAxis();
  _ghostRich = {};
  _refreshProfile();
};
```

### 6c — Rebuild axis and profile on mesh load

**Find** (exact, in `_loadGLB` callback):
```js
      _resetVisModes();
      _hideProgress();
```

**Replace with:**
```js
      _resetVisModes();
      _ghostRich = {};
      _hideProgress();
```

---

## T7 — Keyboard Shortcuts

**Find** (exact):
```js
      case 'g': case 'G': window.toggleGrowthMap(); break;
      case 'x': case 'X': window.toggleSliceView(); break;
```

**Replace with:**
```js
      case 'g': case 'G': window.toggleGrowthMap();    break;
      case 'x': case 'X': window.toggleSliceView();    break;
      case 'p': case 'P': window.toggleProfile();      break;
      case 'q': case 'Q': window.togglePostureAxis();  break;
```

---

## T8 — HTML

### 8a — Buttons (add to V14 row)

**Find** (exact, in `index.html`):
```html
      <!-- V14: Visualization modes -->
      <div class="view-modes" style="margin-top:4px;">
        <button class="view-mode-btn" id="btn-growth"
                onclick="toggleGrowthMap()">Growth</button>
        <button class="view-mode-btn" id="btn-slices"
                onclick="toggleSliceView()">Slices</button>
      </div>
```

**Replace with:**
```html
      <!-- V14/V15: Visualization modes -->
      <div class="view-modes" style="margin-top:4px;">
        <button class="view-mode-btn" id="btn-growth"
                onclick="toggleGrowthMap()">Growth</button>
        <button class="view-mode-btn" id="btn-slices"
                onclick="toggleSliceView()">Slices</button>
        <button class="view-mode-btn" id="btn-profile"
                onclick="toggleProfile()">Profile</button>
        <button class="view-mode-btn" id="btn-axis"
                onclick="togglePostureAxis()">Axis</button>
      </div>
```

### 8b — Profile canvas (fixed overlay)

**Find** (exact, in `index.html`):
```html
  <!-- Growth legend (shown only in growth mode) -->
```

**Insert BEFORE that line:**
```html
  <!-- Profile silhouette panel (shown when profile mode on) -->
  <canvas id="profile-canvas" width="150" height="300"
          style="position:fixed;top:20px;right:20px;z-index:10;display:none;border-radius:8px;border:1px solid rgba(74,158,255,0.5);"></canvas>

```

### 8c — Key hints

**Find** (exact, in `index.html`):
```
        G growth · X slices
```

**Replace with:**
```
        G growth · X slices · P profile · Q axis
```

---

## T9 — Final Verification

1. Refresh browser (no server restart)
2. **Profile (P):** Press P → a 150×300px canvas appears at top-right. Body outline visible as blue filled silhouette, front column on left, side column on right. Landmark ticks (Sho/Che/Wai/Hip/Thi) on left side. Load ghost → green ghost outline overlays blue current outline at every height. Press P → canvas hides.
3. **Posture Axis (Q):** Press Q → a colored line appears through the body from feet to head. Green = body centered at that height, red = deviated. Small spheres mark each centroid level. Load ghost → faint green line shows ghost axis. If body is standing straight, the entire line should be green/near-center.
4. **Volume Zones:** Open Analysis panel → "Volume Zones" section shows 6 zones (Legs, Thighs, Pelvis, Torso, Chest, Upper) with percentages. With ghost loaded → volume delta per zone in ±L (liters).
5. **Combinations:** Growth + Profile → profile updates to show growth-colored body outline. Axis + Slices → axis visible through semi-transparent body.
6. **Wire-ups:** Switch mesh → axis rebuilds, profile hides. Load ghost → axis rebuilds with ghost line, profile refreshes with ghost outline. Clear ghost → ghost line + outline removed.
7. No console errors.

---

## Pitfalls

1. **`_ghostRich = {}` is a module-level variable** — it must be declared in T1 (globals), NOT inside `_computeAnalysis`. The `_computeVolumeZonesHtml` function reads it after `_computeAnalysis` has populated it. If it's declared with `const` inside `_computeAnalysis`, the outer function can't access it.

2. **T5b uses `_ghostRich` directly** — this is the module-level variable from T1. Sonnet: do NOT declare it locally in `_computeAnalysis`. The `let _ghostRich = {}` goes in T1's globals, and `_ghostRich = {}` (no `let`) inside `_computeAnalysis` is a reassignment.

3. **Switching `_meshCrossSection` to `_richCrossSection` for ghost (T5c)** — the ghost cross-section call is changed from `_meshCrossSection` to `_richCrossSection` so we get `areaCm2`. This is slightly more expensive (calls `_sortedCrossSection` internally) but still fine for 5 calls.

4. **Profile canvas bucketing** — we use 120 height buckets. Empty buckets (where no vertex falls) are filled by borrowing from the bucket below (in `_computeProfileFast`). Without this, gaps at neck or ankle would break the silhouette outline.

5. **Posture axis devMm threshold** — 20mm deviation maps to fully red. A perfectly straight body has 0mm (fully green). Real bodies have 2-8mm natural deviation. This gives a meaningful spectrum.

6. **Volume zone `h` values must sum to 1.0** — they sum to 0.34+0.11+0.09+0.10+0.12+0.24 = 1.00 ✓. If you change them, ensure they still sum to 1.0.

7. **Volume deltas in liters** — `z.vol - z.ghostVol` is in cm³ (area cm² × height cm). We display `/ 1000` to convert to liters. A 50cm³ threshold for coloring ≈ 0.05L ≈ a small change.

8. **Profile canvas top-right vs profile legend bottom-right** — the profile canvas goes top-right (`top:20px; right:20px`). The growth and heatmap legends are bottom-right (`bottom:20px; right:20px`). They don't overlap.

9. **T6a inserts BEFORE `if (_growthMode)`** — the axis/profile reset must come BEFORE the growth reset so all modes are clean. The exact find string is the opening of `_resetVisModes`.

---

## File Change Summary

| File | Task | Lines |
|------|------|-------|
| `body_viewer.js` | T1 | 3 globals + 1 `_ghostRich` (~5 lines) |
| `body_viewer.js` | T2 | `_computeProfileFast`, `_computeCentroidAxis` (~45 lines) |
| `body_viewer.js` | T3 | `_drawSilhouetteProfile`, `toggleProfile`, `_refreshProfile` (~70 lines) |
| `body_viewer.js` | T4 | `_buildPostureAxis`, `togglePostureAxis` (~45 lines) |
| `body_viewer.js` | T5 | `_computeVolumeZonesHtml` + `_computeAnalysis` mods (~35 lines) |
| `body_viewer.js` | T6 | Wire-ups in `_resetVisModes`, ghost callbacks (~15 lines net) |
| `body_viewer.js` | T7 | Keyboard P, Q (~2 lines) |
| `index.html` | T8 | Profile+Axis buttons, canvas element, key hints (~10 lines) |
