# Next Session Brief — 2026-03-23

## What Was Done This Session (Opus)

### MPFB2 Template Pipeline (Plan Steps 1-3 partially done)
- **`scripts/blender_create_template.py`** — CREATED but NOT YET RUN. Full pipeline script that:
  - Creates MPFB2 human, removes helpers, keeps body mesh only
  - Extracts verts/faces/UVs to numpy, vertex groups to JSON
  - Exports `meshes/gtd3d_body_template.glb` with PBR material
  - Creates `template_vert_segmentation.json` from bone weights
- **`web_app/static/viewer3d/template_vert_segmentation.json`** — placeholder created with bone→muscle mapping
- **`web_app/static/viewer3d/smpl_vert_segmentation.json`** — working SMPL segmentation (current fallback)

### Viewer Improvements (COMMITTED + PUSHED to master)
- **body_viewer.js**: Auto-detect Z-up vs Y-up GLB (no more sideways meshes), async muscle attach, mobile UI toggle functions, `gtd3d_body_template.glb` as first candidate in placeholder list
- **muscle_highlighter.js**: Async segmentation loading (tries template first, falls back to SMPL), proper error handling
- **styles.css**: Full mobile-responsive layout (card hidden by default on mobile, toggle buttons)
- **index.html**: Mobile toggle buttons for card and muscle panel
- **device_profiles.json**: Samsung A24 profile added

### Research
- Gemini Phase 6 research tasks (26-32) created and committed
- Task 32: MakeHuman body vertex segmentation research — complete with bone→muscle mapping table

## What's NOT Done (Critical Path)

### STEP 1 BLOCKER: Run Blender Script
The template script exists but has NOT been executed. Must run:
```bash
"/c/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background --python scripts/blender_create_template.py
```
This will produce: `meshes/template_verts.npy`, `template_faces.npy`, `template_uvs.npy`, `template_vertex_groups.json`, `gtd3d_body_template.glb`

### STEP 4: Wire viewer to serve template mesh (controllers.py)
### STEP 5: Runtime deformation module (core/body_deform.py)
### STEP 6: Wire export_glb to use template UVs

## Branch
All work pushed to `master` (was on gemini/research-phase5 earlier, merged)

## Server
py4web on port 8000. Must restart after core/*.py changes. Demo user: demo@muscle.com / demo123, customer ID 1.
