# Next Session Brief — 2026-03-24

## What Was Done This Session

### Beast Mesh Fix (3 commits)
1. **Client-side viewer fix** (`body_viewer.js`):
   - Backup original vertex positions on GLB load, restore before each apply (no more cumulative deformation)
   - Auto-detect Z-up vs Y-up geometry (was hardcoded to Y, but MPFB2 template is Z-up)
   - Proper mm→meters scaling for slider values (was using raw scene units → 1900% overscaling)
   - Connected muscle group buttons to region adjustment system via `selectMuscleRegion`
   - Added debug hooks: `window._adjustDebug()`, `window._getBodyMesh()`, `window._getRegionZRange()`

2. **Server-side `deform_template()` fix** (`core/body_deform.py`):
   - **Root cause 1**: 3 ethnicity shape keys (Asian/Caucasian/African male) were ALL applied additively — they're mutually exclusive variants, compounding 180mm displacement. Fix: only apply `muscle` and `weight` category deltas.
   - **Root cause 2**: PCA circumference scaling used SMPL segmentation (6,890 verts) indices on MPFB2 template (13,380 verts) — wrong vertex indices created spikes. Fix: disabled PCA scaling, using proportional height scaling only.
   - `deform_template()` now produces clean meshes. Save re-enabled with server-side mesh regeneration.

3. **Live adjustment sliders** — all 6 width/depth/length sliders (Scene + Studio tabs) auto-apply on drag, no Apply button needed.

### DB State
- Cleaned all beast mesh records (IDs 18-39, plus test IDs 40-43)
- Latest mesh: **#17** (`body_1_1774286054.glb`, 10MB, pipeline:smpl_direct)
- `deform_template()` is **FIXED** — Save will regenerate via `POST /body_model` and load the new mesh inline

### Browser Debugging
- Playwright + `agent_browser.py` confirmed working for: console logs, screenshots, JS eval, visual diff
- `scripts/test_adjust.py` — Playwright test for persistent-session adjust/reset flow
- Use `agent_browser.py audit <url>` for quick one-shot viewer check

## Current State
- Viewer URL: `http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/17.glb`
- Server needs restart after `core/body_deform.py` changes (py4web doesn't hot-reload core/)
- Commits: `e58a0b5` (viewer fix), `cf64c5b` (deform fix), `8f093b8` (live sliders)

## What Needs Work

### Region Adjustments
- Effect is subtle at ±30mm slider range — may need larger range for visible feedback
- Only muscle/weight shape deltas are active; gender/ethnicity deltas disabled
- Per-region PCA scaling disabled — needs proper MPFB2 vertex segmentation (13,380 verts) to re-enable
- `_doDeformationUpdate()` is disabled (was never wired to UI anyway)

### Skin Texture (Carried Over)
- Square close-up photo tiled onto cylindrical UV mesh doesn't look right
- Need seamless tiling or proper UV-space skin atlas

### Other Open Items
- Texture atlas from RunPod has background bleed in UV gaps
- Canonical SMPL UVs not loading (falling back to cylindrical — seam at U=0/1)

## Key Files Modified
- `web_app/static/viewer3d/body_viewer.js` — adjust system, debug hooks, save flow
- `web_app/static/viewer3d/muscle_highlighter.js` — selectMuscleRegion connection
- `web_app/static/viewer3d/index.html` — live slider oninput handlers
- `core/body_deform.py` — disabled ethnicity shape deltas + PCA scaling

## Quick Commands
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe

# Test deform_template produces clean mesh
$PY -c "import sys;sys.path.insert(0,'.');from core.body_deform import deform_template;m=deform_template();print(m['num_vertices'],'verts',m['volume_cm3'],'cm3')"

# Browser audit
$PY scripts/agent_browser.py audit "http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/17.glb" --out captures/audit.png

# Visual diff
$PY scripts/agent_browser.py diff captures/before.png captures/after.png --out captures/diff.png
```
