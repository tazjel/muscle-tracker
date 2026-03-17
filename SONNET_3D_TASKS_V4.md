# Sonnet 3D Task Sheet v4 — Viewer Polish, Dashboard, Growth Heatmap

**Project**: Close the feedback loop: persist adjustments, show real growth data, wire the personal dashboard.
**Agent**: Claude Sonnet
**Date**: 2026-03-18
**Prerequisite**: V3 tasks all complete (committed 9377703). Read `CLAUDE.md` first.

---

## RULES

1. **DO NOT read** `main.dart` or `controllers.py` in full. Grep first, read ±50 lines.
2. `body_viewer.js` is 610 lines — read in full (it's the main work target).
3. `measurement_overlay.js` (226 lines) and `styles.css` (257 lines) — read in full if needed.
4. Run verification after each task. Do not batch tasks then debug.
5. Commit after each task group (P1, P2, P3).
6. Static files (`web_app/static/`) do NOT need server restart.
7. Python files (`core/`, `web_app/controllers.py`, `web_app/models.py`) DO need server restart.

---

## PRIORITY 1 — Viewer Adjustment Persistence (T4.3)

### Problem
The viewer's Width/Depth/Length sliders deform the mesh in real-time (working), but clicking
"Save to Profile" calls a function that doesn't actually POST to the server. Adjustments are
lost on page refresh.

### P1.1 — Wire saveAdjustments() to API

**File**: `web_app/static/viewer3d/body_viewer.js`

Grep for `saveAdjustments` — it's called from `index.html` button click. Current implementation
likely logs to console or is a stub.

**Fix**: Make `saveAdjustments()` POST the accumulated deltas to the body_profile endpoint, then
regenerate the mesh.

```javascript
// In saveAdjustments() or wherever the save button handler is:
async function saveAdjustments() {
    const region = currentRegion;  // e.g. 'chest', 'thigh', 'bicep'
    if (!region || !adjustmentDeltas) {
        console.warn('No adjustments to save');
        return;
    }

    // Map viewer region names to profile measurement fields
    const regionToFields = {
        'chest':    { width: 'chest_circ_cm',     depth: 'chest_depth_cm' },
        'waist':    { width: 'waist_circ_cm',     depth: 'waist_depth_cm' },
        'hips':     { width: 'hip_circ_cm',       depth: 'hip_depth_cm' },
        'thigh':    { width: 'thigh_circ_cm',     depth: null },
        'calf':     { width: 'calf_circ_cm',      depth: null },
        'bicep':    { width: 'bicep_circ_cm',     depth: null },
        'forearm':  { width: 'forearm_circ_cm',   depth: null },
        'shoulder': { width: 'shoulder_width_cm', depth: null },
        'neck':     { width: 'neck_circ_cm',      depth: null },
    };

    const fields = regionToFields[region];
    if (!fields) return;

    // Convert mm delta to cm for profile fields
    const updates = {};
    if (fields.width && adjustmentDeltas.width)
        updates[fields.width] = adjustmentDeltas.width / 10;  // mm → cm delta
    if (fields.depth && adjustmentDeltas.depth)
        updates[fields.depth] = adjustmentDeltas.depth / 10;

    // POST deltas (server adds to existing values)
    const params = new URLSearchParams(window.location.search);
    const customerId = params.get('customer') || '1';
    try {
        const resp = await fetch(`/web_app/api/customer/${customerId}/body_profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ adjustments: updates }),
        });
        const data = await resp.json();
        if (data.status === 'success') {
            showStatus('Saved — regenerating mesh...');
            // Regenerate mesh with updated profile
            const regen = await fetch(`/web_app/api/customer/${customerId}/body_model`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const result = await regen.json();
            if (result.glb_url) {
                loadModel(result.glb_url);  // reload with new mesh
                showStatus('Mesh updated');
            }
        }
    } catch (e) {
        console.error('Save failed:', e);
        showStatus('Save failed');
    }
}
```

### P1.2 — Backend: handle adjustment deltas in body_profile

**File**: `web_app/controllers.py` — grep for `body_profile` (the POST handler).

The endpoint currently does a full overwrite of profile fields. Add support for an `adjustments`
key that ADDS deltas to existing values rather than replacing them:

```python
# Inside the body_profile POST handler, after getting request.json:
adjustments = data.get('adjustments', {})
if adjustments:
    row = db(db.customer.id == customer_id).select().first()
    for field, delta_cm in adjustments.items():
        if field in db.customer.fields and isinstance(delta_cm, (int, float)):
            current = float(row.get(field) or 0)
            db(db.customer.id == customer_id).update(**{field: current + delta_cm})
    db.commit()
    return dict(status='success', message='Adjustments applied')
```

**Verification**: Open viewer → adjust chest width +10mm → Save to Profile → refresh page →
regenerate mesh → chest should be 1cm wider than original.

---

## PRIORITY 2 — Real Growth Heatmap (T4.4 partial)

### Problem
The viewer's Heatmap mode exists but uses fake test data (`i / vertexCount` gradient).
It should show real vertex displacement between two meshes (before vs after).

### P2.1 — Add compare endpoint that returns vertex colors

**File**: `web_app/controllers.py` — grep for `compare_3d` to see the existing comparison stub.

The compare endpoint should:
1. Load two GLB/OBJ meshes (by mesh_id)
2. Compute per-vertex displacement
3. Return a JSON array of vertex colors (RGB) or the displacement values

```python
# In the compare_3d handler:
@action('api/customer/<customer_id:int>/compare_meshes', method=['POST'])
@action.uses(db, cors)
def compare_meshes(customer_id):
    """Compare two meshes and return per-vertex displacement as heatmap colors."""
    data = request.json or {}
    mesh_id_old = int(data.get('mesh_id_old', 0))
    mesh_id_new = int(data.get('mesh_id_new', 0))

    if not mesh_id_old or not mesh_id_new:
        return dict(status='error', message='Need mesh_id_old and mesh_id_new')

    old_row = db.mesh_model[mesh_id_old]
    new_row = db.mesh_model[mesh_id_new]
    if not old_row or not new_row:
        return dict(status='error', message='Mesh not found')

    import numpy as np
    from core.mesh_reconstruction import _load_glb_vertices  # we'll add this

    verts_old = _load_glb_vertices(old_row.glb_path)
    verts_new = _load_glb_vertices(new_row.glb_path)

    if verts_old is None or verts_new is None:
        return dict(status='error', message='Could not load mesh vertices')

    # Vertex count may differ — use nearest-vertex matching
    if len(verts_old) == len(verts_new):
        disp = np.linalg.norm(verts_new - verts_old, axis=1)
    else:
        from scipy.spatial import cKDTree
        tree = cKDTree(verts_old)
        _, idx = tree.query(verts_new)
        disp = np.linalg.norm(verts_new - verts_old[idx], axis=1)

    # Normalize to [0, 1] for heatmap
    max_disp = float(np.percentile(disp, 95)) or 1.0  # 95th percentile cap
    norm = np.clip(disp / max_disp, 0, 1).tolist()

    return dict(
        status='success',
        displacements_mm=disp.tolist(),
        heatmap_values=norm,  # 0=no change (blue), 1=max change (red)
        max_displacement_mm=float(disp.max()),
        mean_displacement_mm=float(disp.mean()),
        num_vertices=len(norm),
    )
```

### P2.2 — Add _load_glb_vertices helper

**File**: `core/mesh_reconstruction.py` — add a function to extract vertex positions from a GLB:

```python
def _load_glb_vertices(glb_path):
    """Load vertex positions from a GLB file. Returns (N, 3) float32 or None."""
    try:
        import pygltflib
        import struct
        glb = pygltflib.GLTF2().load(glb_path)
        accessor = glb.accessors[glb.meshes[0].primitives[0].attributes.POSITION]
        bv = glb.bufferViews[accessor.bufferView]
        data = glb.binary_blob()[bv.byteOffset:bv.byteOffset + bv.byteLength]
        count = accessor.count
        verts = np.array(struct.unpack(f'<{count * 3}f', data)).reshape(count, 3)
        return verts.astype(np.float32)
    except Exception:
        return None
```

### P2.3 — Wire heatmap data into viewer

**File**: `web_app/static/viewer3d/body_viewer.js`

Grep for `applyHeatmap` or `heatmap` — find the existing heatmap toggle. Replace the fake
gradient with a fetch to the compare endpoint:

```javascript
async function applyRealHeatmap(meshIdOld, meshIdNew) {
    const params = new URLSearchParams(window.location.search);
    const cid = params.get('customer') || '1';
    const resp = await fetch(`/web_app/api/customer/${cid}/compare_meshes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mesh_id_old: meshIdOld, mesh_id_new: meshIdNew }),
    });
    const data = await resp.json();
    if (data.status !== 'success') return;

    // Apply heatmap_values as vertex colors
    const colors = new Float32Array(data.num_vertices * 3);
    data.heatmap_values.forEach((v, i) => {
        // Blue (0) → Green (0.5) → Red (1)
        colors[i * 3]     = v < 0.5 ? 0 : (v - 0.5) * 2;        // R
        colors[i * 3 + 1] = v < 0.5 ? v * 2 : (1 - v) * 2;      // G
        colors[i * 3 + 2] = v < 0.5 ? 1 - v * 2 : 0;             // B
    });

    const geom = bodyMesh.geometry;
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    bodyMesh.material = new THREE.MeshStandardMaterial({ vertexColors: true });

    // Update stats
    document.getElementById('stats').innerHTML +=
        `<br>Max Δ: ${data.max_displacement_mm.toFixed(1)}mm` +
        `<br>Mean Δ: ${data.mean_displacement_mm.toFixed(1)}mm`;
}
```

Add URL params `?compare_old=1&compare_new=2` to trigger comparison mode:

```javascript
// In the init/load section of body_viewer.js:
const compareOld = params.get('compare_old');
const compareNew = params.get('compare_new');
if (compareOld && compareNew) {
    // Load the newer mesh, then overlay heatmap
    loadModel(`/api/mesh/${compareNew}.glb`);
    bodyMesh.addEventListener('loaded', () => {
        applyRealHeatmap(parseInt(compareOld), parseInt(compareNew));
    });
}
```

**Verification**:
```bash
# Generate two meshes with slightly different profiles
curl -s -X POST http://localhost:8000/web_app/api/customer/1/body_model \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
# → mesh_id=5

# Adjust chest and regenerate
curl -s -X POST http://localhost:8000/web_app/api/customer/1/body_profile \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"adjustments": {"chest_circ_cm": 2.0}}'
curl -s -X POST http://localhost:8000/web_app/api/customer/1/body_model \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
# → mesh_id=6

# Open comparison:
# http://localhost:8000/web_app/static/viewer3d/index.html?model=/api/mesh/6.glb&compare_old=5&compare_new=6
```

Expected: Chest region shows red/yellow, rest shows blue.

---

## PRIORITY 3 — Personal Dashboard (wire up app.js)

### Problem
`web_app/static/personal/index.html` (140 lines) has a full dashboard layout with stats, body map,
progress charts, and recent scans — but `app.js` doesn't exist. All data is static placeholder.

### P3.1 — Create app.js

**File**: `web_app/static/personal/app.js` (NEW)

Read `index.html` first to see all the element IDs and expected data shape.

The dashboard needs:

```javascript
// web_app/static/personal/app.js

const API = '/web_app/api';
let token = null;
let customerId = null;

// ── Auth ─────────────────────────────────────────────────────────────────────
async function login(email) {
    const resp = await fetch(`${API}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
    });
    const data = await resp.json();
    if (data.status === 'success') {
        token = data.token;
        customerId = data.customer_id;
        localStorage.setItem('token', token);
        localStorage.setItem('customerId', customerId);
        document.getElementById('login-modal').style.display = 'none';
        loadDashboard();
    }
}

// ── Dashboard data ───────────────────────────────────────────────────────────
async function loadDashboard() {
    const headers = { 'Authorization': `Bearer ${token}` };

    // Scans summary
    const scansResp = await fetch(`${API}/customer/${customerId}/scans`, { headers });
    const scansData = await scansResp.json();
    const scans = scansData.scans || [];

    // Stats
    const muscleGroups = new Set(scans.map(s => s.muscle_group));
    const bestGrowth = scans.reduce((max, s) => Math.max(max, s.growth_pct || 0), 0);
    document.getElementById('stat-scans').textContent = scans.length;
    document.getElementById('stat-muscles').textContent = muscleGroups.size;
    document.getElementById('stat-growth').textContent = bestGrowth.toFixed(1) + '%';

    // Recent scans grid
    const grid = document.getElementById('recent-scans');
    grid.innerHTML = '';
    scans.slice(0, 6).forEach(scan => {
        const card = document.createElement('div');
        card.className = 'scan-card';
        card.innerHTML = `
            <div class="scan-muscle">${scan.muscle_group}</div>
            <div class="scan-volume">${scan.volume_cm3?.toFixed(1) || '—'} cm³</div>
            <div class="scan-growth ${(scan.growth_pct || 0) >= 0 ? 'positive' : 'negative'}">
                ${(scan.growth_pct || 0) >= 0 ? '+' : ''}${(scan.growth_pct || 0).toFixed(1)}%
            </div>
            <div class="scan-date">${new Date(scan.created_on).toLocaleDateString()}</div>
        `;
        grid.appendChild(card);
    });

    // 3D viewer link
    const meshResp = await fetch(`${API}/customer/${customerId}/scans?type=body`, { headers });
    const meshData = await meshResp.json();
    // Find latest body mesh
    const viewerLink = document.getElementById('viewer-link');
    if (viewerLink) {
        // Use most recent mesh_model
        viewerLink.href = `/web_app/static/viewer3d/index.html?customer=${customerId}`;
    }

    // Progress chart (if Chart.js loaded)
    loadProgressChart(scans);
}

async function loadProgressChart(scans) {
    if (typeof Chart === 'undefined') return;

    // Group by muscle, plot volume over time
    const byMuscle = {};
    scans.forEach(s => {
        if (!byMuscle[s.muscle_group]) byMuscle[s.muscle_group] = [];
        byMuscle[s.muscle_group].push({ x: new Date(s.created_on), y: s.volume_cm3 });
    });

    const colors = ['#4a9eff', '#ff6b6b', '#51cf66', '#fcc419', '#cc5de8', '#20c997'];
    const datasets = Object.entries(byMuscle).map(([muscle, pts], i) => ({
        label: muscle,
        data: pts.sort((a, b) => a.x - b.x),
        borderColor: colors[i % colors.length],
        fill: false,
        tension: 0.3,
    }));

    const ctx = document.getElementById('progress-chart');
    if (ctx) {
        new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                scales: {
                    x: { type: 'time', time: { unit: 'day' } },
                    y: { title: { display: true, text: 'Volume (cm³)' } },
                },
            },
        });
    }
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    token = localStorage.getItem('token');
    customerId = localStorage.getItem('customerId');
    if (token && customerId) {
        loadDashboard();
    } else {
        // Show login modal or auto-login demo
        login('demo@muscle.com');
    }

    // Login form handler
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', e => {
            e.preventDefault();
            login(document.getElementById('login-email').value);
        });
    }

    // Demo button
    const demoBtn = document.getElementById('demo-btn');
    if (demoBtn) {
        demoBtn.addEventListener('click', () => login('demo@muscle.com'));
    }
});
```

### P3.2 — Add style.css if missing

Check if `web_app/static/personal/style.css` exists. If not, create a minimal one that styles
the scan cards and stats row. Match the dark theme from the 3D viewer (background #1a1a2e,
accent #4a9eff).

### P3.3 — Verify

Open `http://localhost:8000/web_app/static/personal/index.html` — should show:
- Scan count, muscle group count, best growth %
- Recent scan cards with volume and growth
- Link to 3D viewer

**Note**: Read `index.html` first to match exact element IDs. The IDs above are guesses —
adapt to whatever the HTML actually uses.

---

## PRIORITY 4 — Body Region Labels on Mesh (T1.5)

### P4.1 — Add floating HTML labels over mesh regions

**File**: `web_app/static/viewer3d/body_viewer.js`

After the mesh loads, compute 3D anchor positions for body regions and project them to screen
space each frame:

```javascript
const REGION_LABELS = [
    { name: 'Head',     y_frac: 0.97 },  // fraction of body height
    { name: 'Neck',     y_frac: 0.90 },
    { name: 'Chest',    y_frac: 0.78 },
    { name: 'Bicep',    y_frac: 0.72, x_offset: 1.5 },  // offset outward
    { name: 'Waist',    y_frac: 0.62 },
    { name: 'Hips',     y_frac: 0.55 },
    { name: 'Thigh',    y_frac: 0.42 },
    { name: 'Knee',     y_frac: 0.30 },
    { name: 'Calf',     y_frac: 0.18 },
    { name: 'Ankle',    y_frac: 0.05 },
];

function createRegionLabels() {
    const container = document.getElementById('viewer-container') ||
                      document.getElementById('canvas-container');
    const bbox = new THREE.Box3().setFromObject(bodyMesh);
    const minY = bbox.min.y, maxY = bbox.max.y;
    const height = maxY - minY;

    REGION_LABELS.forEach(label => {
        const el = document.createElement('div');
        el.className = 'region-label';
        el.textContent = label.name;
        el.dataset.worldY = minY + height * label.y_frac;
        el.dataset.xOffset = label.x_offset || 0;
        container.appendChild(el);
    });
}

function updateRegionLabels() {
    document.querySelectorAll('.region-label').forEach(el => {
        const worldY = parseFloat(el.dataset.worldY);
        const xOff = parseFloat(el.dataset.xOffset || 0);
        const pos = new THREE.Vector3(xOff * 50, worldY, 0);  // 50mm per offset unit
        pos.project(camera);
        const x = (pos.x * 0.5 + 0.5) * renderer.domElement.clientWidth;
        const y = (-pos.y * 0.5 + 0.5) * renderer.domElement.clientHeight;
        el.style.left = x + 'px';
        el.style.top = y + 'px';
        el.style.display = (pos.z > 1) ? 'none' : '';  // behind camera
    });
}
// Call updateRegionLabels() in the render loop
```

**File**: `web_app/static/viewer3d/styles.css` — add:

```css
.region-label {
    position: absolute;
    color: #fff;
    font-size: 11px;
    background: rgba(74, 158, 255, 0.7);
    padding: 2px 6px;
    border-radius: 3px;
    pointer-events: none;
    transform: translate(-50%, -50%);
    white-space: nowrap;
    z-index: 10;
}
```

### P4.2 — Toggle labels on/off

Add a "Labels" button next to the existing view mode buttons in `index.html`:

```html
<button onclick="toggleLabels()">Labels</button>
```

```javascript
let labelsVisible = false;
function toggleLabels() {
    labelsVisible = !labelsVisible;
    document.querySelectorAll('.region-label')
        .forEach(el => el.style.display = labelsVisible ? '' : 'none');
}
```

**Verification**: Open viewer → click Labels → floating labels appear at correct body positions → rotate camera → labels follow → click Labels again → hidden.

---

## TOKEN-SAVING TIPS

1. `body_viewer.js` (610 lines) — READ IN FULL, this is the main work target.
2. `controllers.py` — grep for `body_profile` and `compare_3d` only.
3. `mesh_reconstruction.py` — grep for `export_glb` (line ~120) — add `_load_glb_vertices` nearby.
4. `personal/index.html` — READ IN FULL (140 lines, need all element IDs).
5. `styles.css` (257 lines) — read in full to avoid duplicate CSS.
6. Do NOT read `main.dart` — no Flutter work in V4.
7. Static file changes (JS/CSS/HTML) do NOT need server restart.
8. Python changes DO need server restart — batch all P2 Python changes, restart once.

## EXECUTION ORDER

```
P1.1 (saveAdjustments JS)       — 20 min, viewer-only, no restart
P1.2 (body_profile adjustments) — 20 min, Python, needs restart
  ↓  restart server once
P2.1 (compare_meshes endpoint)  — 30 min, Python
P2.2 (_load_glb_vertices)       — 15 min, Python
  ↓  restart server once
P2.3 (heatmap in viewer JS)     — 30 min, static only
  ↓
P3.1 (personal/app.js)          — 30 min, static only
P3.2 (personal/style.css)       — 15 min, static only
  ↓
P4.1 (region labels JS+CSS)     — 20 min, static only
P4.2 (labels toggle)            — 10 min, static only
```

Total: ~3 hours. Two server restarts needed (after P1.2 and after P2.2).

---

## KNOWN CONSTRAINTS — DO NOT OVER-ENGINEER

- **Vertex count mismatch between meshes**: Use nearest-vertex matching in compare, not error.
- **No Chart.js CDN in personal/index.html**: Check if it's already loaded; if not, add CDN link.
- **Region labels are approximate**: Y-fraction positions are good enough. Don't try to detect exact joint positions from mesh topology.
- **Personal dashboard login**: Just auto-login as demo@muscle.com. Don't build a real auth flow.
- **Heatmap color ramp**: The blue→green→red in P2.3 matches what body_viewer.js already does in its stub. Reuse the existing color logic if possible.

---

## WHAT NOT TO DO IN V4

- Don't touch the Flutter app (no Dart changes)
- Don't refactor body_viewer.js into modules (it works as-is)
- Don't add WebSocket/SSE for live updates (overkill)
- Don't implement the live camera page (separate project)
- Don't add normal maps or lighting normalization (V5)
- Don't add Catmull-Clark subdivision (V5)
