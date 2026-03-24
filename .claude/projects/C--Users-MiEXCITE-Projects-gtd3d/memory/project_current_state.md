---
name: Project current state March 2026
description: What's done, what's pending, key file sizes and line counts to avoid blind reads
type: project
---

## Completed (as of 2026-03-20)

- Phase 1 photorealism (HDRI, pore normals, SSS tuning, SSAO) — all in body_viewer.js
- RunPod cloud GPU pipeline v7: HMR2.0 + rembg + DSINE + texture_upscale + pbr_textures
- Docker image pushed: ghcr.io/tazjel/gtd3d-gpu-worker:latest (7.8GB)
- Direct SMPL pipeline (core/smpl_direct.py) with cloud GPU fallback
- PBR texture factory (core/texture_factory.py) with cloud GPU fallback
- Viewer: material sliders, lighting presets, SSAO, measurement overlay, comparison viewer
- /api/gpu_status health endpoint + viewer GPU indicator
- deploy.sh build+push+test script

## Pending Tasks

1. `SONNET_TASKS.md` — 6 tasks: Phase 2 texture pipeline (delight wiring, depth-to-normal, PBR in GLB, viewer PBR loading)
2. `SONNET_S24_ULTRA_TASKS.md` — 6 tasks: S24 Ultra device profile, camera intrinsics, ARCore depth scaffold, hi-res pipeline

## Large Files (NEVER read fully — always grep first)

| File | Lines | What |
|------|-------|------|
| web_app/controllers.py | 3200+ | REST API — 63 endpoints |
| web_app/static/viewer3d/body_viewer.js | 3700+ | Three.js viewer |
| companion_app/lib/main.dart | 2300+ | Flutter app |
| core/smpl_direct.py | 400+ | Direct SMPL pipeline |
| runpod/handler.py | 550+ | RunPod serverless worker |
| core/cloud_gpu.py | 400+ | RunPod client |
| core/texture_factory.py | 450+ | PBR texture generation |

## Key Line References

| What | File | Lines |
|------|------|-------|
| generate_body_model() | controllers.py | 2782-2979 |
| PBR bg thread | controllers.py | 2941-2964 |
| export_glb() | mesh_reconstruction.py | 147-300 |
| _setupEnvironment() | body_viewer.js | 1007-1027 |
| _initSSAO() | body_viewer.js | 1087-1116 |
| SKIN_MATERIAL | body_viewer.js | grep needed (multiple locations) |
| _loadGLB | body_viewer.js | grep needed |
| Sensor DB | calibration.py | 14-24 |
| DEFAULT_FOCAL/SENSOR | smpl_direct.py | 19-20 |

**Why:** Saves tokens by avoiding blind reads of large files.

**How to apply:** Always start with grep for the function/pattern, then read only the needed 30-50 lines.
