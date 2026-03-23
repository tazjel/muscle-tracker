# Next Session Brief — 2026-03-23

## What Was Done (Opus + Gemini)

### MPFB2 Template Pipeline — FULLY WORKING
- **`scripts/blender_create_template.py`** — RUN + FIXED (front/back Y-axis flip for pec/trap splitting)
- **Template mesh generated:** 13,380 verts, 26,756 faces, 15 muscle groups, 4,623 assigned verts
- **`core/body_deform.py`** — CREATED (325 lines). Runtime deformation: height + per-region radial scaling + Laplacian smoothing. Input: profile dict (cm). Output: verts (mm), faces, UVs, volume.
- **`controllers.py`** — NEW route `/api/mesh/template.glb`. `deform_template()` wired as primary fallback in `generate_body_model`. Template UVs preserved (not overwritten by cylindrical).
- **`body_viewer.js`** — tries `/web_app/api/mesh/template.glb` first in placeholder candidates
- **Gemini research** — g_r7 (vertex groups), g_r8 (shape keys), g_r9 (UVs), g_r10 (deformation) complete

### Template Files in `meshes/` (committed, force-added past .gitignore)
- `template_verts.npy`, `template_faces.npy`, `template_uvs.npy`, `template_normals.npy`
- `template_joint_landmarks.json`, `gtd3d_body_template.glb` (612 KB)
- `web_app/static/viewer3d/template_vert_segmentation.json`

### Commit: `9e9d34b` on master

## What's NOT Done — Phase 1: Texture Compatibility

**Problem:** 6 callsites use `_get_smpl_part_ids()` (returns 6890-length array). MPFB2's 13,380-vert mesh gets wrong part IDs → skin compositing fails, roughness falls back to height zones.

### Blocked on Gemini Research
- `research/g_r11_mpfb2_smpl_region_map.md` — MPFB2→SMPL part ID mapping (HIGH PRIORITY)
- `research/g_r14_unassigned_vertex_analysis.md` — strategy for 8,757 unassigned verts

### Sonnet Tasks (after Gemini research)
- **S-T1:** Add `get_part_ids(n_verts)` dispatcher in `texture_factory.py` (lines 102, 121, 283)
- **S-T2:** Add `MPFB2_CAPTURE_REGIONS` in `skin_patch.py` (line 37)
- **S-T3:** Replace `_get_smpl_part_ids` at 3 callsites in `controllers.py` (lines 2370, 2554, 3220)
- **S-T4:** Fix all-zeros `body_part_ids` in `body_deform.py` (line 274)
- **S-T5:** End-to-end test script
- **S-T6:** Bone-axis-aligned deformation (after G-R13)

### Task Files
- `GEMINI_NEXT_TASKS.md` — 4 research tasks (G-R11, G-R12, G-R13, G-R14)
- `SONNET_NEXT_TASKS.md` — 6 implementation tasks (S-T1 through S-T6)
- Plan: `.claude/plans/recursive-percolating-emerson.md`

## Branch
All on `master`.

## Server
py4web on port 8000. Must restart after core/*.py changes. Demo: demo@muscle.com / demo123, customer ID 1.
