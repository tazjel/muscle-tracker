# Next Session Brief — gtd3d (2026-03-22)

## READ FIRST: `.agent/TOOLS_GUIDE.md` — all verification/debugging tools in one place

## CRITICAL: Run Preflight Before Pipeline
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY scripts/photo_preflight.py          # ALWAYS run first — catches lighting issues in 1s
$PY scripts/agent_verify.py meshes/skin_densepose.glb  # Check seam + symmetry
```
**Current photos FAIL preflight** — all 4 have uneven left-right lighting (LR diff 25-46).
No amount of software blending fixes bad input photos.

## Current State
- Pipeline score: 87 WARN (MILD_ASYMMETRY: lr_diff=10.3)
- Root cause: uneven photo lighting, NOT a code bug
- Fix options: (1) retake photos with even lighting, (2) Task 8 TexDreamer AI infill

## Verification Tools (use these, don't iterate blindly)
| Tool | When | Time |
|------|------|------|
| `$PY scripts/photo_preflight.py` | Before pipeline | ~1s |
| `$PY scripts/agent_verify.py meshes/X.glb` | After pipeline | ~2s |
| `$PY scripts/agent_verify.py meshes/X.glb --render` | Visual check | ~10s |
| `$PY scripts/run_densepose_texture.py --verify` | Full pipeline + gate | ~35s |
| `$PY scripts/agent_browser.py viewer3d X.glb --rotate 0,90,180,270` | Screenshots | ~8s |

## Key Files
- `core/texture_bake.py` — angular view weighting, seam smoother, torso=front+back only
- `core/glb_inspector.py` — seam detection, symmetry check, render screenshot analysis
- `scripts/photo_preflight.py` — photo lighting/exposure pre-check
- `scripts/run_densepose_texture.py` — full pipeline with LAB harmonization, CLAHE, --verify

## Pending Work
- **Task 8 (TexDreamer)**: AI texture infill from single photo — eliminates multi-view seams
- **Task 9 (Photo→SMPL)**: Needs re-research (Gemini hallucinated model names)
- **Photo retake**: Even lighting needed (face window or 2 symmetric lights)
- research/SUMMARY.md has tasks 1-9 status

## Lessons Learned (Don't Repeat)
- Don't iterate on blending code if preflight shows bad photos — fix the input
- Old score_glb gave false PASS (94) — now correctly reports WARN with asymmetry
- Gemini's commit d8d6ec1 deleted export_glb — always check git diff before accepting Gemini work
- GLB must be in web_app/static/viewer3d/ to serve via py4web (no /api/mesh/ for standalone files)
