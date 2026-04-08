# Next Session Brief — 2026-04-08

## What's Done
- **Pipeline pivot**: HMR2.0+DensePose → LHM++ (160K Gaussian splats, 2s inference, 8GB VRAM)
- **handler_v2.py**: v8.0 — LHM++ inference, Gaussian→GLB via pygltflib
- **Dockerfile fixes** (3 commits):
  - `--no-build-isolation` for diff-gaussian-rasterization (needs system torch)
  - `TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0"` set inline before CUDA compile (no GPU on CI)
  - `torch_scatter` installed directly from URL (not wget+rename)
  - Free disk space step added to workflow (remove dotnet, Android SDK, cached images)
- **Sonnet completed Tasks 2-4** (commit `6a4d401`):
  - Fixed `ref_view` off-by-one: `min(len(selected), 16) - 1`
  - Removed 3 dead code actions (`_train_splat`, `_anchor_splat`, `_bake_cinematic`) ~150 lines
  - Added `vertex_count`/`face_count` to `body_scan_session` table (model + controllers + SQLite migration)
- **Test images ready**: `test_frames/vid5_man/` — front1.jpg, back1.jpg, right_hand.jpg, left_hand.jpg

## What's In Progress
- **GitHub Actions Docker build**: Run `24148755188` — was at 8+ min (past all previous failures) when session ended
  - Check: `gh run list --workflow=257905070 --repo tazjel/muscle-tracker --limit 1`
  - If failed: `gh run view <RUN_ID> --log-failed --repo tazjel/muscle-tracker`
- **Docker Desktop being re-enabled** — user restarting PC to activate. Next session should build locally first.

## What's Next (in order)
1. **Check if Docker build succeeded or failed**
2. **If Docker Desktop is available**: build locally first (`docker build -t gtd3d-worker -f runpod/Dockerfile .`), fix issues with fast feedback, then push to GHCR
3. **Create RunPod endpoint** from `ghcr.io/tazjel/gtd3d-gpu-worker:latest` (user manual step)
4. **Set env vars**: `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT`
5. **End-to-end curl test** (Task 6 in `.agent/LIVE_SCAN_TASKS.md`)
6. **Verify GLB renders** in body_viewer.html (Task 7)

## Key Technical Details
- LHM++ CLI: `test_app_case.py --image_glob "*.png" --ref_view 4 --model_name LHMPP-700M`
- Weights: ~7GB from HuggingFace (Damo_XR_Lab/LHMPP-700M)
- Output: 160K Gaussian splats → GLB point cloud via pygltflib degenerate triangles
- body_viewer.html: THREE.GLTFLoader — may need GL_POINTS for point cloud visibility
- API contract: {glb_b64, vertex_count, face_count, texture_coverage, lhm_used}
- Actual SQLite DB: `database.db` at project root (NOT `apps/web_app/databases/storage.db`)

## Docker Build History (for debugging)
| Run | Duration | Failure | Fix |
|-----|----------|---------|-----|
| 24143479284 | 3m | `ModuleNotFoundError: torch` in diff-gaussian-rasterization | `--no-build-isolation` |
| 24147766255 | 3m24s | `IndexError: list index out of range` in `_get_cuda_arch_flags` | `TORCH_CUDA_ARCH_LIST` inline |
| 24148626885 | 1m58s | `no space left on device` extracting base image | Free disk space step |
| 24148755188 | 8m+? | Still running / unknown | — |

## RunPod
- Balance: $13.86
- Old endpoints: all deleted
- New endpoint: needs to be created after Docker build succeeds

## Rules
- py4web must use `--host 0.0.0.0` for MatePad access
- APK package: `com.example.companion_app`
- Rename repo muscle-tracker → gtd3d (still TODO)
- `fake_migrate_all=True` in common.py — new columns need manual ALTER TABLE

## Task File
- `.agent/LIVE_SCAN_TASKS.md` — Tasks 1-4 done, Tasks 5-7 remain
