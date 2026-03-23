# Sonnet Implementation Tasks — Phase 3: Phenotype, DensePose, Live Deformation (2026-03-23)

## Context
Phases 1-2 done: MPFB2 template (13,380 verts), bone-axis deformation, texture part ID dispatcher, skin regions, e2e test 5/5. Phase 3 adds: runtime shape key morphing (muscle/fat sliders), DensePose skin texture on MPFB2, and live deformation API for viewer interaction.

## RULES — READ BEFORE STARTING
1. **Read `CLAUDE.md` FIRST** — paths, gotchas, conventions
2. **Read `.agent/next-session-brief.md`** — current state
3. **NEVER read `controllers.py` or `body_viewer.js` fully** — grep for exact lines
4. **NEVER modify the SMPL direct pipeline** (controllers.py lines 3143-3320)
5. **Use full Python path:** `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
6. **py4web does NOT hot-reload** — kill and restart after core/*.py changes
7. **Run `scripts/test_mpfb2_pipeline.py` after ANY core/*.py change** — regression check
8. **Stop after first successful test** — don't re-run for marginal improvements
9. **Blender path:** `"/c/Program Files/Blender Foundation/Blender 5.1/blender.exe"`

## File Sizes (grep-only unless noted)
- `controllers.py` — 3600+ lines (GREP ONLY)
- `body_viewer.js` — 4000+ lines (GREP ONLY)
- `body_deform.py` — 357 lines (OK to read)
- `texture_factory.py` — 530+ lines (OK to read)
- `blender_create_template.py` — 480 lines (OK to read)
- `run_densepose_texture.py` — 370 lines (OK to read)
- `skin_patch.py` — 561 lines (OK to read)

## Gemini Research to Check Before Starting
- `research/g_r15_shape_key_extraction_order.md` — REQUIRED for S-T7 (extraction order: before or after helper removal?)
- `research/g_r16_densepose_mpfb2_transfer.md` — REQUIRED for S-T9 (IUV transfer algorithm)
- `research/g_r17_viewer_slider_architecture.md` — REQUIRED for S-T11 (slider event model + key mapping)
- **If any file is missing, STOP and tell user** "Gemini research G-R1x not ready"

---

## Task S-T7: Export Shape Key Deltas (DO FIRST)

**Depends on:** G-R15 (extraction order research)

**File:** `scripts/blender_create_template.py` (480 lines, OK to read)

**What to do:**
1. Read G-R15 to determine correct extraction order (before or after helper vertex removal)
2. Add a new step BEFORE the bake (line 167: `bpy.ops.object.shape_key_remove(all=True, apply_mix=True)`):
   - Create `meshes/shape_deltas/` directory
   - Get basis shape key: `basis = obj.data.shape_keys.key_blocks['Basis']`
   - For each non-Basis key: compute `delta[i] = key.data[i].co - basis.data[i].co`
   - Filter to fitness-relevant keys (name contains `$ma`, `$mu`, `$fe`, `$wg`)
   - Save each as `meshes/shape_deltas/{sanitized_name}.npy` — shape `(N, 3)` float32
   - Save `meshes/shape_deltas/index.json`:
     ```json
     {"key_name": {"file": "sanitized_name.npy", "baked_value": 0.465, "category": "muscle"}}
     ```
3. Proceed with existing bake step (unchanged)

**Key concern:** If G-R15 says shape keys auto-reindex after vertex removal, extract AFTER step 4 (helper removal) but BEFORE step 6 (baking). If NOT, extract BEFORE step 4 and manually re-index.

**Verification:**
```bash
"/c/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --python scripts/blender_create_template.py
ls meshes/shape_deltas/
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "import numpy as np, json; idx=json.load(open('meshes/shape_deltas/index.json')); print(f'{len(idx)} shape keys exported'); k=list(idx.keys())[0]; d=np.load(f'meshes/shape_deltas/{idx[k][\"file\"]}'); print(f'{k}: {d.shape}, max_delta={abs(d).max():.4f}m')"
```

**DO NOT:** Change the existing mesh output (verts, faces, UVs, GLB must remain identical). Only ADD the delta export step.

---

## Task S-T8: Runtime Shape Key Application

**Depends on:** S-T7

**File:** `core/body_deform.py` (357 lines, OK to read)

**What to do:**
1. Add `_load_shape_deltas()` function:
   - Load `meshes/shape_deltas/index.json`
   - Lazy-load `.npy` delta arrays on first access
   - Cache in module-level dict

2. Add new profile keys to `_DEFAULT` dict:
   - `'muscle_factor': 0.5` (0.0=min, 1.0=max)
   - `'weight_factor': 0.5`
   - `'gender_factor': 1.0` (0.0=female, 1.0=male)

3. In `deform_template()`, AFTER loading base verts but BEFORE height scaling (line ~207):
   ```python
   # Apply shape key deltas
   deltas = _load_shape_deltas()
   for key_name, info in deltas.items():
       target = p.get(info['profile_key'], info['baked_value'])
       diff = target - info['baked_value']
       if abs(diff) > 0.01:
           verts += info['delta'] * diff
   ```

4. Map shape key categories to profile keys:
   - `$ma` keys → `gender_factor`
   - `$mu` keys → `muscle_factor`
   - `$wg` keys → `weight_factor`

**Verification:**
```bash
$PY -c "
from core.body_deform import deform_template
lean = deform_template({'height_cm': 175, 'muscle_factor': 0.2})
buff = deform_template({'height_cm': 175, 'muscle_factor': 0.9})
print(f'Lean vol: {lean[\"volume_cm3\"]:.0f}, Buff vol: {buff[\"volume_cm3\"]:.0f}')
assert buff['volume_cm3'] > lean['volume_cm3'], 'More muscle should = more volume'
print('PASS')
"
```

Then run regression: `$PY scripts/test_mpfb2_pipeline.py`

**DO NOT:** Change height scaling, bone-axis deformation, or boundary smoothing. Only ADD shape key blending as a pre-step.

---

## Task S-T9: DensePose Texture on MPFB2

**Depends on:** G-R16 (IUV transfer research)

**File:** `scripts/run_densepose_texture.py` (370 lines, OK to read)

**What to do:**
1. After loading the target mesh/GLB, detect vertex count:
   - 6890 → SMPL path (existing, unchanged)
   - 13380 → MPFB2 path (new)
2. For MPFB2 path:
   - Load `meshes/template_uvs.npy` for UV coordinates
   - Use `get_part_ids(13380)` from `texture_factory.py` for part IDs
   - Follow the transfer algorithm from G-R16 for DensePose IUV → MPFB2 UV mapping
3. Keep SMPL path completely unchanged (backward compatible)

**Verification:**
```bash
$PY scripts/run_densepose_texture.py --verify --mesh meshes/gtd3d_body_template.glb --photo captures/test_front.jpg
```
(If no test photo exists, create a simple test with a placeholder image)

**DO NOT:** Modify `core/densepose_infer.py`. Do not change SMPL path behavior.

---

## Task S-T10: Live Deformation API Endpoint

**Depends on:** None (can start immediately)

**File:** `web_app/controllers.py` — GREP ONLY, add new endpoint

**What to do:**
1. Grep for `generate_body_model` to find its location (~line 3077)
2. Add new endpoint AFTER the generate_body_model function:
   ```python
   @action('api/customer/<customer_id:int>/update_deformation', method=['POST'])
   @action.uses(db, cors)
   def update_deformation(customer_id):
   ```
3. Implementation:
   - Parse JSON body for partial measurements
   - Load current profile from `db.body_profile(customer_id)`
   - Merge: `{**stored_profile, **partial_updates}`
   - Call `deform_template(merged)` + `export_glb()`
   - Insert/update mesh record in DB
   - Return `{status, mesh_id, glb_url, viewer_url}`
4. Must be fast (<2s total) — no texture projection, just deformation + GLB

**Where to add:** Grep for the end of `generate_body_model` (the return dict), add after that function.

**Verification:**
```bash
# Start server first, then:
curl -s http://localhost:8000/web_app/api/customer/1/update_deformation \
  -X POST -H "Content-Type: application/json" \
  -d '{"chest_circumference_cm": 105, "bicep_circumference_cm": 38}'
```

**DO NOT:** Read the full controllers.py. Do not touch generate_body_model. Do not add texture projection to this endpoint (deformation only, for speed).

---

## Task S-T11: Wire Viewer Sliders to Live API

**Depends on:** S-T10, G-R17 (slider architecture)

**File:** `web_app/static/viewer3d/body_viewer.js` — GREP ONLY for slider lines

**What to do:**
1. Read G-R17 to understand slider event model and key mapping
2. Add a `change` event listener (not `input` — avoid spamming) to measurement sliders
3. On change: collect all current slider values, POST to `/api/customer/<id>/update_deformation`
4. On success: reload GLB from returned `glb_url` using existing `_loadGLB()` function
5. Add 500ms debounce to batch rapid slider changes
6. Show/hide a "Updating..." status during server call

**Key info needed from G-R17:**
- How sliders are created (static HTML or JS-generated?)
- Event names they fire
- How to get customer_id from the page context
- Key-to-measurement mapping

**Verification:** Open viewer in browser, adjust a slider, confirm mesh visually updates.

**DO NOT:** Read full body_viewer.js. Only grep for slider-related code and add the wiring.

---

## Task S-T12: Full Pipeline Integration Test

**Depends on:** S-T7, S-T8, S-T9, S-T10, S-T11

**Create:** `scripts/test_mpfb2_full.py`

**What to test:**
1. `deform_template()` with default params (regression)
2. `deform_template()` with shape key params (`muscle_factor=0.8`) — verify volume changes
3. `generate_roughness_map()` + `generate_ao_map()` on deformed mesh
4. `export_glb()` with UVs
5. Run `scripts/agent_verify.py` on output GLB (quality gate)
6. Print per-step timing + pass/fail summary

**Verification:** `$PY scripts/test_mpfb2_full.py`

**DO NOT:** Test SMPL pipeline. Do not start py4web. Do not test DensePose (requires GPU).

---

## DEPENDENCY GRAPH
```
G-R15 ──> S-T7 (export deltas) ──> S-T8 (runtime shape keys)
                                              │
G-R16 ──> S-T9 (DensePose MPFB2) ────────────┤
                                              │
S-T10 (deformation API) ──────────────────────┤
  │                                           │
G-R17 ──> S-T11 (viewer sliders) ─────────────┤
                                              │
                              S-T12 (full e2e test)
```

**Execution order:**
1. S-T10 (no dependencies, can start now)
2. S-T7 → S-T8 (after G-R15)
3. S-T9 (after G-R16)
4. S-T11 (after S-T10 + G-R17)
5. S-T12 (after all above)

---

## WHAT NOT TO DO
- Do NOT re-run Blender script EXCEPT in S-T7 (and only ONCE)
- Do NOT modify `muscle_highlighter.js` — it works
- Do NOT modify `_get_smpl_part_ids()` or `_get_mpfb2_part_ids()` — they work
- Do NOT touch Flutter app or main.dart
- Do NOT read full `controllers.py` or `body_viewer.js` — grep only
- Do NOT add npm/pip packages
- Do NOT add texture projection to the `update_deformation` endpoint (keep it fast)
- Do NOT modify the SMPL direct pipeline (controllers.py lines 3143-3320)
