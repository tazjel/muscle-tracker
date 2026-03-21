# Sonnet Upgrade Tasks V2 — Phase 4 Research Implementation

**Agent:** Sonnet | **Date:** 2026-03-22
**Server restart:** YES after Python changes | **Port:** 8000
**Python:** `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
**When done:** Commit with descriptive message to master branch.
**Depends on:** Complete V1 tasks (T1-T6) first. These tasks build on Phase 4 research findings.

> Goal: Implement auto-measurement, ML body composition, and FutureMe morphing
> features based on Gemini Phase 4 research (Tasks 17-21).

---

## CRITICAL RULES — READ BEFORE ANY TASK

1. **`onBeforeCompile` is BANNED** — body_viewer.js:628 says it breaks `MeshPhysicalMaterial`.
2. **Do NOT use `transmission` or `thickness`** on skin material — makes mesh transparent.
3. **Always grep before reading** — `controllers.py` is 3200+ lines, `body_viewer.js` is ~3800 lines.
4. **Test commands use `$PY`** — always set `PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe` first.
5. **Read `.agent/TOOLS_GUIDE.md`** for all verification tool usage.
6. **T7 must be done before T8 and T10** — they depend on `measurement_extraction.py`.
7. **T9 must be done before T11** — T11 depends on `body_morphing.py`.

**Recommended order:** T7 → T8 → T9 → T10 → T11

---

## T7 — Auto-Measurement Extraction from SMPL Mesh

**Effort:** 2 hours | **Depends on:** Nothing | **Risk:** Low
**Based on:** Phase 4 Task 18 research (trimesh cross-section method)

### What to read
```bash
grep -n 'DEFAULT_PROFILE\|measurement\|circumference' core/smpl_fitting.py
grep -n 'build_smpl_mesh\|vertices.*faces' core/smpl_direct.py
```

### What to create
**File:** `core/measurement_extraction.py` (NEW)

Extract body circumferences by slicing the SMPL mesh with horizontal planes at anatomical landmark heights. Uses `trimesh.section()` — NO hardcoded vertex indices.

```python
"""Extract body measurements from SMPL mesh geometry via cross-sections."""
import trimesh
import numpy as np

# SMPL anatomical landmark heights (meters, A-pose, average adult)
# These are approximate — Gemini Task 22 will refine with exact vertex indices
LANDMARK_HEIGHTS = {
    'neck': 1.48,
    'chest': 1.30,
    'waist': 1.05,
    'hip': 0.92,
    'bicep_l': 1.25,
    'bicep_r': 1.25,
    'forearm_l': 1.10,
    'forearm_r': 1.10,
    'thigh_l': 0.72,
    'thigh_r': 0.72,
    'calf_l': 0.35,
    'calf_r': 0.35,
}


def extract_measurements(vertices, faces):
    """Extract circumference measurements from SMPL mesh via cross-sections.

    Args:
        vertices: (6890, 3) ndarray — SMPL vertex positions in meters
        faces: (13776, 3) ndarray — SMPL face indices

    Returns:
        dict with measurement names → values in cm
    """
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    measurements = {}

    for name, height in LANDMARK_HEIGHTS.items():
        origin = [0, height, 0]
        try:
            section = mesh.section(plane_origin=origin, plane_normal=[0, 1, 0])
            if section is not None:
                path_2d, _ = section.to_planar()
                measurements[name] = round(path_2d.length * 100, 1)  # meters→cm
        except Exception:
            pass  # Skip failed cross-sections

    # Height = max_y - min_y
    measurements['height'] = round(
        (vertices[:, 1].max() - vertices[:, 1].min()) * 100, 1
    )

    # Shoulder width = max x-distance at shoulder height
    shoulder_mask = np.abs(vertices[:, 1] - 1.42) < 0.03  # ~shoulder height
    if shoulder_mask.any():
        shoulder_verts = vertices[shoulder_mask]
        measurements['shoulder_width'] = round(
            (shoulder_verts[:, 0].max() - shoulder_verts[:, 0].min()) * 100, 1
        )

    return measurements


def map_to_profile_keys(measurements):
    """Map extracted measurements to DEFAULT_PROFILE key names.

    Returns dict compatible with smpl_fitting.build_body_mesh(profile).
    Keys that couldn't be extracted are omitted.
    """
    mapping = {
        'height_cm': measurements.get('height'),
        'neck_circumference': measurements.get('neck'),
        'chest_circumference': measurements.get('chest'),
        'waist_circumference': measurements.get('waist'),
        'hip_circumference': measurements.get('hip'),
        'bicep_circumference': measurements.get('bicep_r'),
        'forearm_circumference': measurements.get('forearm_r'),
        'thigh_circumference': measurements.get('thigh_r'),
        'calf_circumference': measurements.get('calf_r'),
        'shoulder_width': measurements.get('shoulder_width'),
    }
    return {k: v for k, v in mapping.items() if v is not None}
```

### Test
```bash
$PY -c "
from core.smpl_direct import build_smpl_mesh
from core.measurement_extraction import extract_measurements, map_to_profile_keys
m = build_smpl_mesh()
raw = extract_measurements(m['vertices'], m['faces'])
print('Raw measurements:', raw)
profile = map_to_profile_keys(raw)
print('Profile keys:', profile)
"
```

### DO NOT
- Modify `smpl_fitting.py` or `smpl_direct.py` — this is a NEW file only
- Use hardcoded vertex indices — use `trimesh.section` with plane heights
- Import `SMPL-Anthropometry` — pure trimesh for now (Phase 5 research will provide exact vertices)
- Use anything except horizontal plane normals `[0, 1, 0]`

---

## T8 — ML Body Composition Ensemble

**Effort:** 1.5 hours | **Depends on:** T7 | **Risk:** Low
**Based on:** Phase 4 Task 17 research (Ridge regressor + Navy fallback)

### What to read
```bash
grep -n 'estimate_body_composition\|navy\|body_fat\|lean_mass' core/body_composition.py
```

### What to modify
**File:** `core/body_composition.py` (MODIFY — add new function, don't touch existing)

Add `estimate_body_composition_ml()` that uses SMPL betas + mesh measurements as features. Gracefully falls back to None if model file doesn't exist.

```python
# Add these imports at top of file
import pickle

# Add after existing functions
_ML_MODEL = None

def _load_body_comp_model():
    """Lazy-load ML model for body composition prediction."""
    global _ML_MODEL
    if _ML_MODEL is not None:
        return _ML_MODEL
    model_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'body_comp_ridge.pkl')
    if os.path.exists(model_path):
        with open(model_path, 'rb') as f:
            _ML_MODEL = pickle.load(f)
    return _ML_MODEL


def estimate_body_composition_ml(betas, measurements, weight_kg, height_cm):
    """ML-enhanced body composition from SMPL betas + mesh measurements.

    Args:
        betas: list of 10 SMPL shape parameters
        measurements: dict from measurement_extraction.extract_measurements()
        weight_kg: user's weight in kg
        height_cm: user's height in cm

    Returns:
        dict with body_fat_pct, lean_mass_kg, fat_mass_kg, method, confidence
        or None if ML model not available (caller should use Navy fallback)
    """
    model = _load_body_comp_model()
    if model is None:
        return None

    features = np.array([
        weight_kg, height_cm,
        measurements.get('waist', 0),
        measurements.get('hip', 0),
        measurements.get('chest', 0),
        measurements.get('neck', 0),
        float(betas[0]), float(betas[1]), float(betas[2])
    ]).reshape(1, -1)

    body_fat_pct = float(np.clip(model.predict(features)[0], 3, 60))
    lean_mass = round(weight_kg * (1 - body_fat_pct / 100), 1)
    fat_mass = round(weight_kg * body_fat_pct / 100, 1)

    return {
        'body_fat_pct': round(body_fat_pct, 1),
        'lean_mass_kg': lean_mass,
        'fat_mass_kg': fat_mass,
        'method': 'ml_ridge',
        'confidence': 'high'
    }
```

Then modify the existing `estimate_body_composition()` to try ML first:
```python
# At the end of estimate_body_composition(), before returning:
# If betas and measurements are available, try ML ensemble
if betas is not None and mesh_measurements is not None:
    ml_result = estimate_body_composition_ml(betas, mesh_measurements, weight_kg, height_cm)
    if ml_result is not None:
        # Ensemble: average Navy and ML predictions
        result['body_fat_pct'] = round(
            (result['body_fat_pct'] + ml_result['body_fat_pct']) / 2, 1
        )
        result['method'] = 'navy_ml_ensemble'
        result['confidence'] = 'high'
```

### Test
```bash
$PY -c "from core.body_composition import estimate_body_composition; print(estimate_body_composition(height_cm=175, weight_kg=80))"
```

### DO NOT
- Delete the existing Navy method — it's the fallback
- Require the ML model file to exist — return None gracefully
- Train the model in this task — just add inference code + placeholder path
- Change the return format of `estimate_body_composition()` — add fields, don't remove

---

## T9 — FutureMe Body Morphing MVP

**Effort:** 2 hours | **Depends on:** Nothing | **Risk:** Low
**Based on:** Phase 4 Task 21 research (beta interpolation with ±15% cap)

### What to read
```bash
grep -n 'betas\|beta\[' core/smpl_direct.py core/smpl_fitting.py
```

### What to create
**File:** `core/body_morphing.py` (NEW)

```python
"""FutureMe body morphing — predict SMPL betas for target weight."""
import numpy as np

# Empirical beta-weight sensitivity mapping (from SMPL PCA analysis)
# beta[0] = height/scale, beta[1] = weight/mass, beta[2] = proportions
BETA_WEIGHT_SENSITIVITY = np.array([
    0.00,   # beta[0]: height — NEVER change (causes height drift)
    0.15,   # beta[1]: mass — primary driver of weight appearance
    0.03,   # beta[2]: proportions — slight waist/hip adjustment
    0.02,   # beta[3]: chest depth
    0.01,   # beta[4]: thigh thickness
    0.0, 0.0, 0.0, 0.0, 0.0  # beta[5-9]: preserve individual identity
])

MAX_DELTA_FRACTION = 0.15  # Safety cap: ±15% of current weight


def morph_body_to_weight(current_betas, current_weight_kg, target_weight_kg):
    """Predict new SMPL betas for target weight visualization.

    Uses linear beta interpolation with empirical sensitivity mapping.
    Caps delta at ±15% of current weight to prevent unrealistic morphs.

    Args:
        current_betas: list/array of 10 SMPL shape parameters
        current_weight_kg: user's current weight
        target_weight_kg: desired visualization weight

    Returns:
        list of 10 new SMPL betas
    """
    delta_kg = target_weight_kg - current_weight_kg
    max_delta = current_weight_kg * MAX_DELTA_FRACTION
    delta_kg = float(np.clip(delta_kg, -max_delta, max_delta))

    new_betas = np.array(current_betas, dtype=np.float32).copy()
    new_betas += BETA_WEIGHT_SENSITIVITY * delta_kg
    return new_betas.tolist()


def get_morph_range(current_weight_kg):
    """Return allowed min/max target weights for the slider.

    Args:
        current_weight_kg: user's current weight

    Returns:
        (min_kg, max_kg) tuple
    """
    delta = current_weight_kg * MAX_DELTA_FRACTION
    return (
        round(current_weight_kg - delta, 1),
        round(current_weight_kg + delta, 1)
    )
```

### Test
```bash
$PY -c "
from core.body_morphing import morph_body_to_weight, get_morph_range
betas = [0.0]*10
print('Range for 80kg:', get_morph_range(80))
print('Current:', betas[:5])
print('-5kg:', morph_body_to_weight(betas, 80, 75)[:5])
print('+5kg:', morph_body_to_weight(betas, 80, 85)[:5])
print('Capped +20kg:', morph_body_to_weight(betas, 80, 100)[:5])
"
```

### DO NOT
- Require external ML model — this is the linear MVP (A2B regressor is Phase 5 research)
- Change beta[0] (height sensitivity MUST be 0.00 — prevents height drift artifact)
- Allow morphs beyond ±15% (safety cap from rival UX research)
- Use terms "fat" or "obese" anywhere in code comments — use "mass" or "weight"

---

## T10 — Auto-Measure API Endpoint

**Effort:** 1.5 hours | **Depends on:** T7 | **Risk:** Medium
**Based on:** Phase 4 Task 18 integration plan

### What to read
```bash
grep -n 'def upload_scan\|def upload_quad_scan\|def generate_body_model\|call_runpod' web_app/controllers.py
grep -n '_run_hmr\|betas\|handler' runpod/handler.py
```

### What to modify
**File:** `web_app/controllers.py` (MODIFY — add new endpoint)

Add a new API endpoint that accepts front + optional side images, calls HMR2.0 on RunPod, builds SMPL mesh, extracts measurements via T7's `measurement_extraction.py`.

```python
@action('api/customer/<id:int>/auto_measure', method='POST')
def auto_measure(id):
    """Accept front+side images, return auto-estimated body measurements.

    POST /api/customer/<id>/auto_measure
    Form data: front (required), side (optional)
    Returns: {measurements: {...}, betas: [...], method: 'hmr2_auto'}
    """
    import numpy as np

    front = request.files.get('front')
    if not front:
        return dict(error='front image required'), 400

    # 1. Call HMR2.0 on RunPod for front image
    front_result = _call_runpod({'action': 'hmr', 'image': _encode_image(front)})
    front_betas = front_result.get('betas', [0]*10)

    # 2. Optionally process side image for better accuracy
    side = request.files.get('side')
    if side:
        side_result = _call_runpod({'action': 'hmr', 'image': _encode_image(side)})
        side_betas = side_result.get('betas', front_betas)
        # Average betas for better AP/ML volume constraint (30-40% improvement)
        fused_betas = [(a + b) / 2 for a, b in zip(front_betas, side_betas)]
    else:
        fused_betas = front_betas

    # 3. Build SMPL mesh from fused betas
    from core.smpl_direct import build_smpl_mesh
    mesh = build_smpl_mesh(betas=fused_betas)

    # 4. Extract measurements via trimesh cross-sections
    from core.measurement_extraction import extract_measurements, map_to_profile_keys
    raw = extract_measurements(mesh['vertices'], mesh['faces'])
    profile_keys = map_to_profile_keys(raw)

    return dict(
        measurements=profile_keys,
        raw_measurements=raw,
        betas=[round(b, 4) for b in fused_betas],
        method='hmr2_dual' if side else 'hmr2_front_only'
    )
```

**Note:** Find the existing `_call_runpod()` or equivalent function by grepping. Use the same pattern.

### Test
```bash
curl -X POST http://localhost:8000/web_app/api/customer/1/auto_measure \
  -F "front=@scripts/dual_captures/front.jpg"
```

### DO NOT
- Modify existing endpoints (`upload_scan`, `upload_quad_scan`, `generate_body_model`)
- Run HMR2.0 locally — MUST use RunPod via existing call pattern
- Block on side image — it's optional (front-only works with lower accuracy)
- Add authentication check if other endpoints don't have it (match existing pattern)

---

## T11 — FutureMe Morph API + Viewer Slider

**Effort:** 2 hours | **Depends on:** T9 | **Risk:** Medium
**Based on:** Phase 4 Task 21 integration plan

### What to read
```bash
grep -n 'def.*body_model\|def.*mesh\|customer.*profile' web_app/controllers.py | head -20
grep -n 'slider\|range\|morph\|loadModel\|GLTFLoader\|controls' web_app/static/viewer3d/body_viewer.js | head -20
```

### What to modify

**File 1:** `web_app/controllers.py` (MODIFY — add endpoint)

```python
@action('api/customer/<id:int>/future_morph', method='POST')
def future_morph(id):
    """Return morphed GLB mesh for target weight visualization.

    POST /api/customer/<id>/future_morph
    JSON body: {target_weight_kg: float}
    Returns: GLB binary file
    """
    data = request.json or {}
    target_weight = float(data.get('target_weight_kg', 0))
    if target_weight <= 0:
        return dict(error='target_weight_kg required and must be positive'), 400

    # Get current customer profile
    customer = db(db.customer.id == id).select().first()
    if not customer:
        return dict(error='customer not found'), 404

    current_weight = float(customer.get('weight', 75))
    current_betas = customer.get('smpl_betas', [0]*10)
    if isinstance(current_betas, str):
        import json
        current_betas = json.loads(current_betas)

    # Morph betas
    from core.body_morphing import morph_body_to_weight
    new_betas = morph_body_to_weight(current_betas, current_weight, target_weight)

    # Build mesh + export GLB
    from core.smpl_direct import build_smpl_mesh
    mesh = build_smpl_mesh(betas=new_betas)

    from core.mesh_reconstruction import export_glb
    import tempfile, os
    glb_path = tempfile.mktemp(suffix='.glb')
    export_glb(mesh['vertices'], mesh['faces'], glb_path)

    # Return GLB file
    with open(glb_path, 'rb') as f:
        glb_data = f.read()
    os.unlink(glb_path)

    response.headers['Content-Type'] = 'model/gltf-binary'
    return glb_data
```

**File 2:** `web_app/static/viewer3d/body_viewer.js` (MODIFY — add slider)

Find the existing controls/UI panel area by grepping for `controls` or `panel` or `gui`. Add the weight slider near existing UI elements.

```javascript
// === FutureMe Weight Slider ===
function _addWeightSlider(currentWeight, customerId) {
    const container = document.createElement('div');
    container.id = 'futureme-panel';
    container.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.7);padding:12px 20px;border-radius:8px;color:#fff;font-family:sans-serif;z-index:100;text-align:center;';

    const minW = Math.round(currentWeight * 0.85);
    const maxW = Math.round(currentWeight * 1.15);

    container.innerHTML = `
        <div style="font-size:12px;margin-bottom:6px;">Goal Weight</div>
        <input type="range" id="weight-slider" min="${minW}" max="${maxW}" value="${currentWeight}" step="0.5"
               style="width:200px;">
        <div id="weight-label" style="font-size:14px;margin-top:4px;">${currentWeight} kg</div>
        <div style="font-size:9px;color:#999;margin-top:4px;">Prediction based on statistical averages</div>
    `;
    document.body.appendChild(container);

    let debounceTimer;
    document.getElementById('weight-slider').addEventListener('input', (e) => {
        const target = parseFloat(e.target.value);
        document.getElementById('weight-label').textContent = target + ' kg';

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(async () => {
            try {
                const resp = await fetch(
                    '/web_app/api/customer/' + customerId + '/future_morph',
                    {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({target_weight_kg: target})
                    }
                );
                if (resp.ok) {
                    const blob = await resp.blob();
                    const url = URL.createObjectURL(blob);
                    // Reload model with morphed GLB
                    _loadGLB(url);
                }
            } catch (err) {
                console.warn('Morph failed:', err);
            }
        }, 300);  // 300ms debounce
    });
}
```

### Test
```bash
# Backend test
curl -X POST http://localhost:8000/web_app/api/customer/1/future_morph \
  -H "Content-Type: application/json" \
  -d '{"target_weight_kg": 75}' --output /tmp/morph.glb

# Viewer test
$PY scripts/agent_browser.py viewer3d skin_densepose.glb
```

### DO NOT
- Use Three.js MorphTargets (requires precomputed targets at GLB export — too complex for MVP)
- Allow slider beyond ±15% range
- Use words "fat" or "obese" in UI — use "Current" and "Goal"
- Skip the disclaimer text ("Prediction based on statistical averages")
- Fetch morph on every slider pixel — use 300ms debounce
