# Sonnet Implementation Tasks — MPFB2 Template Pipeline (2026-03-23)

## Context
Switching from SMPL to MPFB2/MakeHuman mesh. A 6-step plan exists in `.claude/plans/cryptic-nibbling-petal.md`. Steps 1-3 are partially done (script created, viewer updated). Steps 4-6 remain.

## RULES — READ BEFORE STARTING
1. **Read `CLAUDE.md` FIRST** — paths, gotchas, conventions
2. **Read `.agent/next-session-brief.md`** — current state summary
3. **Read the plan file** `.claude/plans/cryptic-nibbling-petal.md` — full architecture
4. **NEVER read large files whole** — grep for specific line numbers
5. **NEVER run `flutter analyze`** — delegate to Gemini
6. **NEVER use MCP tools** — use project scripts or create new ones
7. **Run `photo_preflight.py` before pipeline, `agent_verify.py` after**
8. **Stop after first successful run** — don't re-run for marginal improvements
9. **py4web does NOT hot-reload** — must kill and restart server after core/*.py changes
10. **Use full Python path:** `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`

## Key File Sizes (DO NOT read fully — grep only)
- `controllers.py` — 2200+ lines. Grep for `generate_body_model` (~line 2126)
- `body_viewer.js` — 3900+ lines. Grep for specific functions
- `muscle_highlighter.js` — ~350 lines (OK to read)
- `blender_create_template.py` — ~300 lines (OK to read)

---

## Task S-T1: Run Blender Template Script (HIGHEST PRIORITY — DO THIS FIRST)

**What:** Execute the existing script to generate the template mesh.

**Command:**
```bash
"/c/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --python scripts/blender_create_template.py
```

**Expected outputs in `meshes/`:**
- `template_verts.npy` — (N, 3) float32
- `template_faces.npy` — (M, 3) int32
- `template_uvs.npy` — (N, 2) float32
- `template_vertex_groups.json` — bone→vertex list mapping
- `gtd3d_body_template.glb` — production GLB

**Expected output in `web_app/static/viewer3d/`:**
- `template_vert_segmentation.json` — muscle group→vertex indices

**If script fails:** Read the error, check Gemini research in `research/g_r7_*.md` for correct vertex group names, fix the mapping, retry. Common issues:
- MPFB2 operator name might be `create_human` or `add_human` — check `bpy.ops.mpfb.` tab completion
- Shape key names might differ — check `research/g_r8_*.md`
- Vertex group names might have `DEF-` prefix

**Verification:**
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "import numpy as np; v=np.load('meshes/template_verts.npy'); print(f'Verts: {v.shape}, range: {v.min():.2f} to {v.max():.2f}')"
$PY -c "import json; d=json.load(open('web_app/static/viewer3d/template_vert_segmentation.json')); print({k:len(v) for k,v in d.items()})"
```

---

## Task S-T2: Wire Viewer to Serve Template Mesh

**What:** Update `controllers.py` to serve the template GLB as default mesh.

**Where to look:** Grep `controllers.py` for `serve_mesh` or `mesh.*glb` to find the serving function.

**Changes needed:**
1. If no customer-specific mesh exists, serve `meshes/gtd3d_body_template.glb` instead of returning 404
2. The viewer already tries `gtd3d_body_template.glb` as first candidate (done in body_viewer.js)

**Verification:** Open `http://192.168.100.16:8000/web_app/static/viewer3d/index.html` — should load the template mesh without needing `?model=` parameter.

---

## Task S-T3: Create Runtime Deformation Module

**What:** `core/body_deform.py` — deform template mesh based on user measurements (24 body measurements from profile).

**Architecture:**
```python
def deform_template(profile: dict) -> dict:
    base_verts = np.load('meshes/template_verts.npy')
    faces = np.load('meshes/template_faces.npy')
    uvs = np.load('meshes/template_uvs.npy')
    groups = json.load(open('meshes/template_vertex_groups.json'))

    # For each measurement (chest_circ, waist_circ, hip_circ, etc.):
    #   1. Find which vertex group corresponds to that measurement
    #   2. Scale those vertices to match the target circumference
    #   3. Smooth blending at boundaries

    return {'vertices': deformed, 'faces': faces, 'uvs': uvs}
```

**Key constraint:** UVs and faces NEVER change. Only vertex positions change.

**Depends on:** S-T1 (need the template numpy files first)

---

## Task S-T4: Wire Deformation into Body Model API

**What:** Update `generate_body_model` in `controllers.py` to use `deform_template()` instead of `build_body_mesh()` (SMPL).

**Where:** `controllers.py` ~line 2126, function `generate_body_model`

**Changes:**
1. Import `from core.body_deform import deform_template`
2. Replace `build_body_mesh(profile)` call with `deform_template(profile)`
3. Keep the rest of the pipeline (texture projection, GLB export) the same
4. The deformed mesh uses template UVs (much better than cylindrical UVs)

---

## Task S-T5: Verify Muscle Highlights on Template Mesh

**What:** After S-T1, open viewer and test muscle group highlights.

**Steps:**
1. Load template GLB in viewer
2. Click each muscle group button
3. Verify highlights cover correct body regions
4. If highlight is wrong, check `template_vert_segmentation.json` — the bone→muscle mapping might need adjustment

**The muscle_highlighter.js already tries template segmentation first** (async load with fallback to SMPL segmentation). No code changes needed unless segmentation is wrong.

---

## DEPENDENCY GRAPH
```
S-T1 (run Blender) ──→ S-T2 (wire viewer)
                    ──→ S-T3 (deformation module) ──→ S-T4 (wire API)
                    ──→ S-T5 (verify highlights)
```
S-T1 MUST complete before anything else. S-T2, S-T3, S-T5 can run in parallel after S-T1.

---

## WHAT NOT TO DO
- Do NOT re-create `blender_create_template.py` — it already exists and is complete
- Do NOT modify `muscle_highlighter.js` — it already handles template segmentation
- Do NOT modify `body_viewer.js` — it already prefers template GLB and handles Y-up
- Do NOT touch the skin texture pipeline (`core/skin_patch.py`) — separate concern
- Do NOT run `flutter analyze` or modify Flutter app
- Do NOT explore `research/` files unless you need to fix a script bug
- Do NOT add comments, docstrings, or type annotations to existing code you didn't write
