# Sonnet Implementation Tasks — MPFB2 Texture Compatibility (2026-03-23)

## Context
MPFB2 template pipeline works (13,380 verts, deformation, viewer). But 6 callsites in the texture subsystem are hardcoded to SMPL's 6890-vert topology via `_get_smpl_part_ids()`. When MPFB2 mesh hits these paths, skin compositing fails and roughness falls back to low-quality height zones. Both pipelines must coexist: SMPL for photo-based (HMR2.0), MPFB2 for measurement-based.

## RULES — READ BEFORE STARTING
1. **Read `CLAUDE.md` FIRST** — paths, gotchas, conventions
2. **Read `.agent/next-session-brief.md`** — current state
3. **NEVER read `controllers.py` or `body_viewer.js` fully** — grep for exact line numbers
4. **NEVER modify the SMPL direct pipeline** (controllers.py lines 3143-3320)
5. **NEVER re-run the Blender template script** — mesh is generated and correct
6. **NEVER modify `muscle_highlighter.js` or `body_viewer.js`** — they already work
7. **NEVER install new packages** — use numpy, scipy, cv2 only
8. **Use full Python path:** `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
9. **py4web does NOT hot-reload** — kill and restart after core/*.py changes
10. **Stop after first successful test** — don't re-run for marginal improvements

## File Sizes (grep-only unless noted)
- `controllers.py` — 3600+ lines (GREP ONLY)
- `body_viewer.js` — 3900+ lines (DO NOT TOUCH)
- `texture_factory.py` — 466 lines (OK to read)
- `skin_patch.py` — 538 lines (OK to read)
- `body_deform.py` — 325 lines (OK to read)

## Gemini Research to Check Before Starting
- `research/g_r11_mpfb2_smpl_region_map.md` — MPFB2→SMPL part ID mapping table (REQUIRED for S-T1)
- `research/g_r14_unassigned_vertex_analysis.md` — strategy for 8757 unassigned verts (REQUIRED for S-T1)
- If these files don't exist yet, STOP and tell user "Gemini research G-R11/G-R14 not ready"

---

## Task S-T1: MPFB2 Part ID Adapter (DO FIRST)

**File:** `core/texture_factory.py` (466 lines, OK to read)

**What to do:**
1. Add `_get_mpfb2_part_ids()` after line 102 (after `_get_smpl_part_ids`):
   - Load `web_app/static/viewer3d/template_vert_segmentation.json`
   - Map each of 15 groups to SMPL part IDs using table from `research/g_r11_mpfb2_smpl_region_map.md`
   - For 8,757 unassigned vertices: use `scipy.spatial.KDTree` nearest-neighbor from assigned vertices (or whatever G-R14 recommends)
   - Return `(13380,)` int32 array
   - Cache in module-level variable (same pattern as `_get_smpl_part_ids`)

2. Add dispatcher `get_part_ids(n_verts)`:
   - `6890` → `_get_smpl_part_ids()`
   - `13380` → `_get_mpfb2_part_ids()`
   - else → `None`

3. Update internal callers:
   - Line 121 (in `generate_roughness_map`): `_get_smpl_part_ids()` → `get_part_ids(len(uvs))`
   - Line 283 (in `generate_anatomical_overlay`): `_get_smpl_part_ids()` → `get_part_ids(len(uvs))`

**Proposed mapping** (verify against G-R11 research):
```python
_MPFB2_TO_SMPL = {
    'pectorals': 9, 'traps': 12, 'abs': 3, 'obliques': 3, 'glutes': 0,
    'quads_l': 1, 'quads_r': 2, 'calves_l': 4, 'calves_r': 5,
    'biceps_l': 16, 'biceps_r': 17, 'forearms_l': 18, 'forearms_r': 19,
    'deltoids_l': 13, 'deltoids_r': 14,
}
```

**Verification:**
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
from core.texture_factory import get_part_ids
import numpy as np
smpl = get_part_ids(6890)
print(f'SMPL: {smpl.shape if smpl is not None else None}')
mpfb = get_part_ids(13380)
print(f'MPFB2: {mpfb.shape}, unique={len(np.unique(mpfb))}')
assert mpfb is not None and len(mpfb) == 13380
assert len(np.unique(mpfb)) >= 10, 'Too few unique part IDs'
print('PASS')
"
```

**DO NOT:** Change `_get_smpl_part_ids` behavior. Do not read `controllers.py`.

---

## Task S-T2: MPFB2 Capture Regions — `core/skin_patch.py`

**Depends on:** S-T1

**File:** `core/skin_patch.py` (538 lines, OK to read)

**What to do:**
1. Add `MPFB2_CAPTURE_REGIONS` dict after line 36 (after existing `CAPTURE_REGIONS`):
```python
MPFB2_CAPTURE_REGIONS = {
    'forearm':    ['forearms_l', 'forearms_r'],
    'abdomen':    ['abs', 'obliques'],
    'chest':      ['pectorals'],
    'thigh':      ['quads_l', 'quads_r'],
    'calf':       ['calves_l', 'calves_r'],
    'upper_arm':  ['biceps_l', 'biceps_r'],
    'shoulders':  ['deltoids_l', 'deltoids_r'],
    'back':       ['traps'],
    'neck':       [],
    'hands':      [],
    'feet':       [],
    'face':       [],
}
```

2. Update `composite_skin_atlas` (line 440) to accept optional `seg_dict` param:
   - If `seg_dict` is provided AND `region_name` is in `MPFB2_CAPTURE_REGIONS`: use muscle group vertex indices from `seg_dict`
   - If `seg_dict` is None: use existing `part_ids` + `CAPTURE_REGIONS` path (backward compatible)

**Verification:**
```bash
$PY -c "
from core.skin_patch import MPFB2_CAPTURE_REGIONS, CAPTURE_REGIONS
assert set(MPFB2_CAPTURE_REGIONS.keys()) == set(CAPTURE_REGIONS.keys())
print('Region keys match:', sorted(MPFB2_CAPTURE_REGIONS.keys()))
print('PASS')
"
```

**DO NOT:** Modify `CAPTURE_REGIONS` (SMPL still needs it). Do not touch Image Quilting code.

---

## Task S-T3: Wire Dispatcher into controllers.py

**Depends on:** S-T1, S-T2

**File:** `web_app/controllers.py` — GREP ONLY, read 10-20 lines around each callsite

**Exact callsites to change (3 locations):**

1. **Lines 2370/2384** (inside `upload_skin_region`):
   - `from core.texture_factory import _get_smpl_part_ids` → `from core.texture_factory import get_part_ids`
   - `part_ids = _get_smpl_part_ids()` → `part_ids = get_part_ids(len(uvs))`

2. **Lines 2554/2568** (inside `select_skin_photo`):
   - Same pattern as above

3. **Lines 3220/3227** (inside `generate_body_model`, SMPL skin texture path):
   - `from core.texture_factory import _get_smpl_part_ids` → `from core.texture_factory import get_part_ids`
   - `_part_ids = _get_smpl_part_ids()` → `_part_ids = get_part_ids(len(uvs_for_glb))`

**Verification:**
```bash
grep -n '_get_smpl_part_ids' web_app/controllers.py
# Should return 0 lines

grep -n 'get_part_ids' web_app/controllers.py
# Should return 3+ lines
```

**DO NOT:** Read the full file. Do not modify SMPL direct pipeline (lines 3143-3320). Do not change endpoint signatures.

---

## Task S-T4: Fix body_part_ids in body_deform.py

**Depends on:** S-T1

**File:** `core/body_deform.py` (325 lines, OK to read)

**What to do:**
1. At line 274, replace `np.zeros(len(verts_mm), dtype=np.int32)` with proper part IDs:
```python
try:
    from core.texture_factory import get_part_ids
    _part_ids = get_part_ids(len(verts_mm))
except Exception:
    _part_ids = None
...
'body_part_ids': _part_ids if _part_ids is not None else np.zeros(len(verts_mm), dtype=np.int32),
```
   Use try/except to avoid circular import issues.

2. Add `'mesh_type': 'mpfb2'` key to return dict.

**Verification:**
```bash
$PY -c "
from core.body_deform import deform_template
m = deform_template()
print(f'body_part_ids: {m[\"body_part_ids\"].shape}, unique: {len(set(m[\"body_part_ids\"].tolist()))}')
assert m['body_part_ids'].max() > 0, 'All zeros — mapping failed'
print(f'mesh_type: {m.get(\"mesh_type\")}')
print('PASS')
"
```

**DO NOT:** Change deformation logic, boundary smoothing, or coordinate conversion.

---

## Task S-T5: End-to-End Test Script

**Depends on:** S-T1, S-T2, S-T3, S-T4

**Create:** `scripts/test_mpfb2_pipeline.py`

**What it should test:**
1. `deform_template(profile)` with sample measurements → check verts, faces, UVs, body_part_ids
2. `generate_roughness_map(uvs, atlas_size=512, vertices=verts)` → check non-None, correct shape
3. `generate_ao_map(verts, faces, uvs, atlas_size=512)` → check non-None
4. `export_glb(verts, faces, 'meshes/test_mpfb2_e2e.glb', uvs=uvs)` → check file exists
5. Print pass/fail for each step, total time

**Verification:** Run the script itself:
```bash
$PY scripts/test_mpfb2_pipeline.py
```

**DO NOT:** Test the SMPL pipeline. Do not start py4web. Do not upload anything.

---

## Task S-T6: Bone-Axis-Aligned Deformation (Phase 2)

**Depends on:** G-R13 research, S-T4

**File:** `core/body_deform.py` (325 lines)

**What to do:**
1. Replace radial XY scaling (lines 219-256) with per-group PCA-axis scaling:
   - For each muscle group, compute PCA of its vertex positions
   - First principal component = bone direction
   - Scale in the plane perpendicular to the bone axis
2. Upgrade `_smooth_boundaries` to distance-weighted blend (not binary boundary)

**Verification:**
```bash
$PY -c "
from core.body_deform import deform_template
import numpy as np
m = deform_template({'chest_circumference_cm': 120, 'bicep_circumference_cm': 45})
v = m['vertices']
assert np.isfinite(v).all(), 'Non-finite vertices!'
print(f'Height: {v[:,2].max()-v[:,2].min():.0f}mm, Vol: {m[\"volume_cm3\"]:.0f}cm3')
print('PASS')
"
```

**DO NOT:** Change height scaling. Do not change output format. Do not modify UVs.

---

## DEPENDENCY GRAPH
```
S-T1 (part ID adapter) ──┬──> S-T2 (skin_patch regions)
                          │         │
                          ├─────────┴──> S-T3 (controllers wiring)
                          │
                          └──> S-T4 (body_deform fix)
                                    │
S-T1 + S-T2 + S-T3 + S-T4 ────────> S-T5 (e2e test)

G-R13 (research) ──────────────────> S-T6 (bone-axis deform)
```

**Execution order:** S-T1 → (S-T2 + S-T4 parallel) → S-T3 → S-T5 → S-T6

---

## WHAT NOT TO DO
- Do NOT re-create `blender_create_template.py` or re-run Blender
- Do NOT modify `muscle_highlighter.js` — already handles template segmentation
- Do NOT modify `body_viewer.js` — already prefers template GLB
- Do NOT touch `core/smpl_direct.py` — SMPL direct pipeline is separate
- Do NOT modify `_get_smpl_part_ids()` function — only add new functions alongside
- Do NOT run `flutter analyze` or modify Flutter app
- Do NOT add comments, docstrings, or type annotations to existing code you didn't write
- Do NOT explore `research/` files unless fixing a specific bug
