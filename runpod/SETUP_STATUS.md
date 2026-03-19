# RunPod Setup Status

## FULLY WORKING (tested 2026-03-20)

- [x] RunPod account created ($10 credit)
- [x] Docker image built + pushed: `ghcr.io/tazjel/gtd3d-gpu-worker:latest`
- [x] GitHub Container Registry package set to **public**
- [x] RunPod template: `gtd3d-gpu-v6` (ID: `volsj14gxj`)
- [x] RunPod endpoint: `gtd3d-body-mesh-v6` (ID: `1lbdnj99ui3fe4`)
- [x] API key + endpoint saved to `~/.secrets.env`
- [x] `core/cloud_gpu.py` — RunPod client integrated
- [x] `core/smpl_direct.py` — auto-detects cloud GPU, falls back to local
- [x] **END-TO-END TEST PASSED** — HMR2.0 shape prediction + rembg body masks from real body photos

## Test Results (2026-03-20)
- Input: 2 body photos (front + back, 3120x4160, resized to 1024px)
- HMR2.0 betas: [0.372, 1.264, -0.041, 0.162, -0.34, ...]
- SMPL vertices: 6890x3 (full mesh in T-pose)
- Body masks: front + back segmentation
- Cold start: ~180s, inference: ~90s
- Payload size: 164KB

## Environment Variables (in ~/.secrets.env)
```
RUNPOD_API_KEY=rpa_VKS...
RUNPOD_ENDPOINT=1lbdnj99ui3fe4
```

## Docker Fixes Applied (v1→v6)
1. v1: Base setup
2. v2: pyrender stub (no OpenGL on headless GPU)
3. v3: SMPL_NEUTRAL.pkl weights added
4. v4: Added omegaconf, pytorch-lightning, chumpy
5. v5: Pinned numpy<2.0 (but wrong approach)
6. v6: Force-reinstall numpy==1.26.4 AFTER all deps (torch ABI compat)

## Files
- `runpod/handler.py` — Serverless worker (HMR2.0 + rembg + DSINE)
- `runpod/Dockerfile` — Docker image definition
- `runpod/SMPL_NEUTRAL.pkl` — SMPL body model weights (19MB)
- `core/cloud_gpu.py` — Client to call RunPod from pipeline
- `core/smpl_direct.py` — Auto-uses cloud GPU when configured
