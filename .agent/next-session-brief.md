# Next Session Brief — 2026-03-23

## What's DONE (Phases 1-3 Complete)

### Phase 1: MPFB2 Template Pipeline
- Template mesh: 13,380 verts, 26,756 faces, 15 muscle groups, CC0 license
- `core/body_deform.py` — runtime deformation (bone-axis PCA + Laplacian smoothing + shape key deltas)
- `core/texture_factory.py` — `get_part_ids(n_verts)` dispatcher (SMPL 6890 / MPFB2 13380)
- `controllers.py` — `/api/mesh/template.glb`, `deform_template()` fallback, part ID dispatcher
- `body_viewer.js` — template GLB first candidate, debounced slider→server wiring
- `muscle_highlighter.js` — async template segmentation (works for both meshes)

### Phase 2: Bone-Axis Deformation
- PCA per muscle group → scale perpendicular to bone axis
- 2-ring boundary smoothing with distance-weighted falloff

### Phase 3: Shape Keys + Live Deformation + DensePose Detection
- `blender_create_template.py` Step 5b: exports 8 shape key deltas (ALL GENDER, zero muscle/weight)
- `body_deform.py`: `_load_shape_deltas()` + phenotype keys (muscle_factor, weight_factor, gender_factor)
- `controllers.py`: `POST /api/customer/<id>/update_deformation` endpoint (crash bug FIXED: was db.customer_profile → db.customer)
- `body_viewer.js`: `_scheduleDeformationUpdate()` with 500ms debounce → GLB reload
- `run_densepose_texture.py`: `--mesh`/`--photo` args, auto-detects MPFB2 (13380 verts)
- `models.py`: Added muscle_factor, weight_factor, gender_factor to customer table
- `controllers.py`: Added phenotype fields to `_BODY_PROFILE_FIELDS` whitelist
- Tests: `test_mpfb2_pipeline.py` 5/5, `test_mpfb2_full.py` 8/8

### Research (g_r7 through g_r17) — ALL COMMITTED
- g_r16 has encoding corruption → being REPLACED by G-R19

### Commits on master
- `9e9d34b` — MPFB2 template pipeline
- `6311b72` — Phase 1 texture compatibility
- `3b15bdf` — Phase 2 bone-axis deformation
- `84be316` — Phase 3: shape key deltas + live deformation + viewer wiring
- `8970063` — Fix update_deformation crash + phenotype DB fields

## What's NEXT — Phase 4

### CRITICAL GAP: No muscle/weight shape keys
The template exported 0 muscle/weight deltas. `$mu`/`$wg` filter found nothing. MPFB2 likely uses its macro system (not shape keys) for muscle/weight. G-R18 research needed.

### 3 Gemini research tasks (G-R18, G-R19, G-R20) — all parallel
- G-R18: MPFB2 muscle/weight macro system (blocks S-T16)
- G-R19: Regenerate corrupted G-R16 DensePose transfer (blocks S-T19)
- G-R20: Phenotype slider UX design (blocks S-T18)

### 4 Sonnet implementation tasks (S-T16 through S-T19)
- S-T16: Blender muscle/weight delta export (after G-R18)
- S-T17: Verify muscle/weight runtime effect (after S-T16)
- S-T18: Phenotype sliders in viewer (after S-T17 + G-R20)
- S-T19: DensePose→MPFB2 end-to-end test (after G-R19)

### Task Files
- `GEMINI_NEXT_TASKS.md` — G-R18, G-R19, G-R20
- `SONNET_NEXT_TASKS.md` — S-T16 through S-T19
- Plan: `.claude/plans/recursive-percolating-emerson.md`

## Branch
All on `master`.

## Server
py4web on port 8000. Must restart after web_app/*.py or models.py changes. Demo: demo@muscle.com / demo123, customer ID 1.
