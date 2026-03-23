# Next Session Brief — 2026-03-23

## What's DONE (Phases 1-2 Complete)

### Phase 1: MPFB2 Template Pipeline
- Template mesh: 13,380 verts, 26,756 faces, 15 muscle groups, CC0 license
- `core/body_deform.py` — runtime deformation (bone-axis PCA scaling + 2-ring Laplacian smoothing)
- `core/texture_factory.py` — `get_part_ids(n_verts)` dispatcher (SMPL 6890 / MPFB2 13380)
- `core/skin_patch.py` — `MPFB2_CAPTURE_REGIONS` + `composite_skin_atlas(seg_dict=...)`
- `controllers.py` — `/api/mesh/template.glb` route, `deform_template()` as primary fallback, all 3 `_get_smpl_part_ids` callsites replaced with dispatcher
- `body_viewer.js` — template GLB as first candidate
- `muscle_highlighter.js` — async template segmentation loading (works for both meshes)
- E2E test: `scripts/test_mpfb2_pipeline.py` — 5/5 pass, 1.5s

### Phase 2: Bone-Axis Deformation
- PCA per muscle group → scale perpendicular to bone axis
- 2-ring boundary smoothing with distance-weighted falloff
- Verified: extreme measurements produce correct volume changes

### All Gemini Research (g_r7 through g_r14) — COMMITTED
- Vertex groups, shape keys, UV layout, deformation, region mapping, unassigned verts, shape key deltas, bone-axis PCA

### Commits on master
- `9e9d34b` — MPFB2 template pipeline
- `6311b72` — Phase 1 texture compatibility
- `3b15bdf` — Phase 2 bone-axis deformation

## What's NEXT — Phase 3

### 3 Gemini research tasks (G-R15, G-R16, G-R17) — all can run in parallel
- G-R15: Shape key delta extraction order (blocks S-T7)
- G-R16: DensePose IUV-to-MPFB2 UV transfer (blocks S-T9)
- G-R17: Viewer slider architecture (blocks S-T11)

### 6 Sonnet implementation tasks (S-T7 through S-T12)
- S-T7: Export shape key deltas from Blender (after G-R15)
- S-T8: Runtime shape key application in body_deform.py (after S-T7)
- S-T9: DensePose texture on MPFB2 mesh (after G-R16)
- S-T10: Live deformation API endpoint (NO dependencies — start immediately)
- S-T11: Wire viewer sliders to live API (after S-T10 + G-R17)
- S-T12: Full pipeline integration test (after all above)

### Task Files
- `GEMINI_NEXT_TASKS.md` — G-R15, G-R16, G-R17
- `SONNET_NEXT_TASKS.md` — S-T7 through S-T12
- Plan: `.claude/plans/recursive-percolating-emerson.md`

## Branch
All on `master`.

## Server
py4web on port 8000. Must restart after core/*.py changes. Demo: demo@muscle.com / demo123, customer ID 1.
