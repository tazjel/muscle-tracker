# Gemini 3D Upgrade Report — v5.5 "Cinematic Scan"

## Progress Summary
Successfully transitioned the engine from the low-poly "Zombie" mesh to the high-fidelity **MPFB2 (MakeHuman)** standard. Implemented neural rendering pipeline (3DGS).

### Completed Milestones
1.  **Workspace Purification**: Removed over 2.3 GB of legacy build artifacts.
2.  **Infrastructure Upgrade**: Created Blackwell-ready RunPod `Dockerfile` and `handler_v2.py`.
3.  **Anatomical Skeleton**: Verified 13,380-vertex MPFB2 mesh generation.
4.  **Local Photorealism**: Frequency-Separated Normal Mapping & Skin Pore detail.
5.  **Muscle Definition**: Completed the `muscle_projection.py` system.
6.  **3DGS Implementation (v6.0)**:
    - **train_splat**: Implemented full video-to-.spz pipeline with COLMAP camera estimation and gsplat 1.5.0+ training loop.
    - **anchor_splat**: Implemented GPU-accelerated nearest-neighbor binding (13,380 verts) for parametric Gaussian deformation.
    - **bake_cinematic**: Integrated placeholder for neural-to-PBR texture baking.

### Active Results
- **Snapshot**: [mpfb_v4_cinematic_final.png](file:///C:/Users/MiEXCITE/Projects/gtd3d/captures/mpfb_v4_cinematic_final.png)
- **Current Mesh**: MPFB2 Cinematic (19,158 verts / 38,312 faces)
- **RunPod Handler**: `handler_v2.py` logic is fully implemented and ready for deployment.

### Next Steps (Verification)
- **3DGS Deployment**: Once the RunPod environment is ready, push v6.0 to GHCR and verify endpoint health.
- **End-to-End Test**: Use `api/customer/<id>/cinematic_scan` to verify the full video -> splat -> anchored mesh flow.
- **Mobile Integration**: Verify the `mpfb_v4_body.glb` (PBR) in the Flutter mobile viewer for visual parity.

---

## Scan Lab Session — 2026-04-08 (Gemini)

### Status: In Progress
A dedicated `scan_lab` py4web app was created to test the scanning pipeline end-to-end.

**See full handoff notes:** `.agent/SESSION_HANDOFF.md`

### What Was Done
- [x] Verified all local dependencies (CUDA, DensePose-TorchScript, HMR2.0, etc.)
- [x] **Safeguarded RunPod** — requires `USE_CLOUD_GPU=true` env var to fire
- [x] Connected MatePad via WiFi ADB (`192.168.100.2:5556`)
- [x] Created Scan Lab dashboard (`apps/scan_lab/`)
- [x] Added `/capture` endpoint to companion app studio_server.dart
- [x] Updated scan_lab controller to use `/capture`

### Immediate TODOs (for Claude)
- [ ] **Fix camera resolution**: Companion app sends 208×208 instead of 4160×3120. The `_getLatestFrame()` in `main.dart:741` needs investigation. MatePad is 13MP (4160×3120) but frames are tiny.
- [ ] **Add video recording support**: User wants to record a rotation video, then extract best front/side/back frames. Add `/start_recording`, `/stop_recording`, `/download_video` to `studio_server.dart`.
- [ ] **Rebuild companion APK**: After fixing camera + adding video, rebuild and deploy to MatePad.
- [ ] **Test full pipeline**: Capture at 2.5m → Segment → Mesh → DensePose → Bake → Export GLB.

### Key Files Modified This Session
| File | What Changed |
|------|-------------|
| `core/hmr_shape.py` | `prefer_gpu` default: `'auto'` → `'local'` |
| `core/smpl_direct.py` | Local-first, cloud only if `USE_CLOUD_GPU=true` |
| `core/densepose_infer.py` | Cloud backend gated by `USE_CLOUD_GPU=true` |
| `companion_app/lib/studio_server.dart` | Added `/capture` GET endpoint |
| `apps/scan_lab/controllers.py` | Capture uses `/capture` + JPEG validation |
| `apps/scan_lab/templates/scan_lab_dashboard.html` | Default IP: `192.168.100.2` |
| `.agent/SHARED_ENVIRONMENT.md` | MatePad WiFi ADB info added |
