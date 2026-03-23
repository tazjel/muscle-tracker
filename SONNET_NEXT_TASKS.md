# Sonnet Implementation Tasks — Phase 4: Phenotype Pipeline Completion (2026-03-23)

## Context
Phase 3 done + committed: shape key delta export (8 gender keys), `update_deformation` endpoint, viewer slider→server wiring, DensePose MPFB2 auto-detection, 8/8 integration test. Phase 4 fixes: (1) muscle/weight shape keys (currently no effect), (2) phenotype sliders in viewer, (3) DensePose→MPFB2 end-to-end validation.

**S-T13/14/15 ALREADY DONE:** Phase 3 committed, crash bug fixed, phenotype DB fields added.

## RULES — READ BEFORE STARTING
1. Read `CLAUDE.md` FIRST, then `.agent/next-session-brief.md`
2. NEVER read full `controllers.py` (3571 lines) or `body_viewer.js` (4000+ lines) — grep for exact lines
3. NEVER modify the SMPL direct pipeline (controllers.py lines 3143-3320)
4. Python: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
5. Blender: `"/c/Program Files/Blender Foundation/Blender 5.1/blender.exe"`
6. py4web does NOT hot-reload — kill and restart after `web_app/*.py` or `models.py` changes
7. Run `scripts/test_mpfb2_pipeline.py` after ANY `core/*.py` change
8. Stop after first successful test — don't re-run for marginal improvements

## File Sizes (grep-only unless noted)
- `controllers.py` — 3571 lines (GREP ONLY)
- `body_viewer.js` — 4000+ lines (GREP ONLY)
- `body_deform.py` — 421 lines (OK to read)
- `texture_factory.py` — 530+ lines (OK to read)
- `blender_create_template.py` — 540 lines (OK to read)
- `run_densepose_texture.py` — 370 lines (OK to read)
- `models.py` — ~200 lines (OK to read)
- `index.html` — viewer HTML (OK to read)

## Gemini Research to Check Before Starting
- `research/g_r18_mpfb2_muscle_weight_macros.md` — REQUIRED for S-T16 (how MPFB2 does muscle/weight)
- `research/g_r19_densepose_mpfb2_transfer_v2.md` — REQUIRED for S-T19 (DensePose transfer algorithm)
- `research/g_r20_phenotype_slider_ux.md` — REQUIRED for S-T18 (slider labels, ranges, layout)
- **If any file is missing, STOP and tell user** "Gemini research G-R1x not ready"

---

## Task S-T16: Blender — Export Muscle/Weight Shape Key Deltas

**Depends on:** G-R18 (MUST read first for the correct MPFB2 API calls)

**File:** `scripts/blender_create_template.py` (540 lines, OK to read)

**What to do:**
1. Read `research/g_r18_mpfb2_muscle_weight_macros.md` to learn the MPFB2 macro API for muscle/weight
2. The current script (Step 2, lines 51-66) tries to set `$mu` shape key values, but those keys don't exist or have zero effect
3. Based on G-R18 findings, modify the script to:
   - Generate mesh at muscle=0.5 (baseline) → read vertex positions
   - Generate mesh at muscle=1.0 → read vertex positions → compute delta
   - Generate mesh at weight=1.0 → read vertex positions → compute delta
   - Save deltas as `meshes/shape_deltas/muscle_delta.npy` and `weight_delta.npy`
   - Update `meshes/shape_deltas/index.json` with new entries:
     ```json
     "muscle_delta": {"file": "muscle_delta.npy", "baked_value": 0.5, "category": "muscle"},
     "weight_delta": {"file": "weight_delta.npy", "baked_value": 0.5, "category": "weight"}
     ```
4. The approach depends entirely on G-R18 — the MPFB2 macro system may require creating multiple human meshes or using bone transforms

**Verification:**
```bash
"/c/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --python scripts/blender_create_template.py
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "import numpy as np, json; idx=json.load(open('meshes/shape_deltas/index.json')); cats=[v['category'] for v in idx.values()]; print(f'Categories: {set(cats)}'); assert 'muscle' in cats, 'No muscle deltas!'"
```

**DO NOT:** Change existing gender delta files. Do NOT change template mesh output (verts, faces, UVs, GLB must remain identical).

---

## Task S-T17: Verify Muscle/Weight Runtime Effect

**Depends on:** S-T16

**File:** `core/body_deform.py` (421 lines, OK to read)

**What to do:**
1. The loading code at lines 69-112 already handles `muscle` and `weight` categories — no code changes should be needed
2. Clear the shape delta cache by restarting Python (or set `_shape_delta_cache = None`)
3. Run verification test

**Verification:**
```bash
$PY -c "
from core.body_deform import deform_template
lean = deform_template({'height_cm': 175, 'muscle_factor': 0.2})
buff = deform_template({'height_cm': 175, 'muscle_factor': 0.9})
print(f'Lean: {lean[\"volume_cm3\"]:.0f}, Buff: {buff[\"volume_cm3\"]:.0f}')
assert buff['volume_cm3'] > lean['volume_cm3'], 'Muscle should increase volume'
print('PASS')
"
```

Then run regression: `$PY scripts/test_mpfb2_pipeline.py`

**If deltas are still zero:** Escalate to user — "G-R18 approach didn't produce muscle deltas, need deeper investigation"

**DO NOT:** Change height scaling, bone-axis deformation, or boundary smoothing.

---

## Task S-T18: Add Phenotype Sliders to Viewer

**Depends on:** S-T15 (done) + S-T17 + G-R20

**Files:**
- `web_app/static/viewer3d/index.html` — add slider HTML (near line 149)
- `web_app/static/viewer3d/body_viewer.js` — add event handlers (near line 845) + modify payload (near line 1733)

**What to do:**
1. Read `research/g_r20_phenotype_slider_ux.md` for slider labels, ranges, and layout
2. **HTML** — Add a phenotype panel in the Adjust tab ABOVE the per-region `#adjust-panel` div:
   - Muscle slider: `<input type="range" id="pheno-muscle" min="0" max="100" value="50">`
   - Body Fat slider: `<input type="range" id="pheno-weight" min="0" max="100" value="50">`
   - Gender slider: `<input type="range" id="pheno-gender" min="0" max="100" value="100">` (100=Male)
3. **JS listeners** (near line 845, after existing adj- slider listeners):
   ```javascript
   ['pheno-muscle', 'pheno-weight', 'pheno-gender'].forEach(id => {
     const el = document.getElementById(id);
     if (el) {
       el.addEventListener('input', () => {
         const val = document.getElementById(id + '-val');
         if (val) val.textContent = el.value;
       });
       el.addEventListener('change', () => _scheduleDeformationUpdate());
     }
   });
   ```
4. **JS payload** — Modify `_doDeformationUpdate()` (grep for `const updates = {}` near line 1733) to add phenotype fields:
   ```javascript
   const muscleEl = document.getElementById('pheno-muscle');
   const weightEl = document.getElementById('pheno-weight');
   const genderEl = document.getElementById('pheno-gender');
   if (muscleEl) updates.muscle_factor = parseInt(muscleEl.value) / 100;
   if (weightEl) updates.weight_factor = parseInt(weightEl.value) / 100;
   if (genderEl) updates.gender_factor = parseInt(genderEl.value) / 100;
   ```

**Verification:** Open viewer in browser, drag muscle slider, confirm mesh reloads with different shape.

**DO NOT:** Read full `body_viewer.js`. Do NOT modify `muscle_highlighter.js`.

---

## Task S-T19: DensePose→MPFB2 End-to-End Test

**Depends on:** G-R19

**What to do:**
1. Read `research/g_r19_densepose_mpfb2_transfer_v2.md` for transfer algorithm details
2. Find a test photo: `ls captures/` or `ls scripts/dual_captures/` for a front-facing body photo
3. Run preflight: `$PY scripts/photo_preflight.py <photo_path>`
4. Run pipeline:
   ```bash
   $PY scripts/run_densepose_texture.py --mesh meshes/gtd3d_body_template.glb --photo <photo_path> --output meshes/test_densepose_mpfb2.glb
   ```
5. Verify: `$PY scripts/agent_verify.py meshes/test_densepose_mpfb2.glb`
6. Check coverage > 50%

**Note:** Requires RunPod DensePose endpoint. If down, skip and report "DensePose endpoint unavailable, deferring S-T19".

**DO NOT:** Modify `core/densepose_infer.py`. Do NOT change SMPL path behavior.

---

## DEPENDENCY GRAPH
```
G-R18 ──→ S-T16 (Blender muscle/weight deltas) ──→ S-T17 (verify runtime)
                                                          │
G-R20 ─────────────────────────────────────────────────→ S-T18 (viewer sliders)

G-R19 ──→ S-T19 (DensePose e2e test)
```

**Execution order:**
1. Check G-R18 exists → S-T16 → S-T17 (sequential)
2. Check G-R19 exists → S-T19 (independent)
3. After S-T17 + check G-R20 → S-T18

---

## WHAT NOT TO DO
- Do NOT re-run `blender_create_template.py` except in S-T16 (once)
- Do NOT modify `muscle_highlighter.js` — it works
- Do NOT modify `_get_smpl_part_ids()` or `_get_mpfb2_part_ids()` — they work
- Do NOT touch Flutter app
- Do NOT read full `controllers.py` or `body_viewer.js` — grep only
- Do NOT add npm/pip packages
- Do NOT modify the SMPL direct pipeline
- Do NOT change existing gender shape key delta files

---

## Verification (after all tasks)
1. `$PY scripts/test_mpfb2_pipeline.py` — regression (5/5)
2. `$PY scripts/test_mpfb2_full.py` — full pipeline (8/8)
3. `curl -X POST http://localhost:8000/web_app/api/customer/1/update_deformation -H "Content-Type: application/json" -d '{"muscle_factor":0.8}'` — returns success, volume changes
4. Viewer: drag muscle slider → mesh reloads with visibly different shape
5. `$PY -c "import json; idx=json.load(open('meshes/shape_deltas/index.json')); print([v['category'] for v in idx.values()])"` — includes 'muscle' and 'weight'
