# Next Session Brief — 2026-03-22

## What Was Done This Session

### Sonnet Upgrade Tasks (S-U1 through S-U9) — ALL COMMITTED
| Commit | Task | What |
|--------|------|------|
| 30fa4ae | S-U1 | LAB color harmonization for multi-view texture |
| 362008d | S-U2 | SMPL vertex landmarks + hip circumference fix |
| 723c70b | S-U3 | Three.js muscle group highlighter |
| dcc1f9c | S-U4 | A2B regressor (measurements → betas) + ONNX |
| 4437a30 | S-U5+S-U7 | SMPLitex + IntrinsiX RunPod handlers |
| 7c93ca7 | S-U6 | Heatmap comparison viewer |
| 7aa4209 | S-U8 | ML body composition from SMPL betas |
| 20ba34d | S-U9 | CameraHMR RunPod path for shape estimation |

### Pipeline Bug Fixes — COMMITTED (03abd06)
- Mask resize fix (MediaPipe returns different resolution than input image)
- LAB harmonization wired into smpl_direct.py rasterizer
- DSINE resize to 1024px max for CPU practicality
- Read-only vertices array fix from HMR

### Per-Region Skin Texture Pipeline — COMMITTED
- `core/skin_patch.py` (b47fd81): Image Quilting + Laplacian blending
- API + viewer UI (9601a63): POST /api/customer/<id>/skin_region/<region>, skin upload panel

### Key Discovery
Full-body photo projection onto mesh is fundamentally broken (seams, gaps, distortion). New approach: per-region close-up skin photos tiled onto SMPL body parts. Pipeline works end-to-end in ~9 seconds.

## What's Next
- **GEMINI_NEXT_TASKS.md** — 4 research tasks (canonical UVs is HIGH priority)
- **SONNET_NEXT_TASKS.md** — 7 implementation tasks (PBR, canonical UVs, Flutter capture, pipeline wiring)
- A2B regressor needs retraining with 10,000+ samples (currently 500)
- Muscle highlighter vertex ranges are approximate — need real Meshcapade data

## Branch
`gemini/research-phase5` — all work on this branch

## Server
py4web on port 8000. Must restart after core/*.py changes. Demo user: demo@muscle.com / demo123, customer ID 1.
