# gtd3d Research Summary

## Task Status

| # | Task | Priority | Status | Assigned |
|---|------|----------|--------|----------|
| **Phase 1** | | | | |
| 7 | Cross-View Color Harmonization (Seam Fix) | URGENT | ✅ Done | Gemini |
| 8 | Diffusion Texture Infill (62%→100%) | HIGH | ✅ Done | Gemini |
| 9 | Photo→SMPL (No Measurements) | HIGH | ✅ Done | Gemini |
| **Phase 2** (shallow — being redone in Phase 3) | | | | |
| 10 | Photorealistic Skin Texture v1 | HIGH | ⚠️ Shallow | Gemini |
| 11 | Three.js Alternatives v1 | HIGH | ⚠️ Shallow | Gemini |
| 12 | Rival APK Analysis v1 | HIGH | ⚠️ Shallow | Gemini |
| 13 | GitHub Repo Survey v1 | HIGH | ⚠️ Shallow | Gemini |
| **Phase 3** (deep research with verified sources) | | | | |
| 14 | **Skin Texture Photorealism v2** — verified repos + practical Q&A | HIGH | ✅ Done | Gemini |
| 15 | **Rival APK Extraction** — 10+ rivals, actual APK analysis, iOS focus | HIGH | ✅ Done | Gemini |
| 16 | **Three.js Skin Shader** — concrete code snippets + upgrade roadmap | HIGH | ✅ Done | Gemini |
| **Phase 4** (upgraded backlog + new directions) | | | | |
| 17 | **ML Body Composition** — SMPL betas → body fat/lean mass | HIGH | ✅ Done | Gemini |
| 18 | **Photo→SMPL Auto** — 2 photos → 24 measurements, no manual input | HIGH | ✅ Done | Gemini |
| 19 | **RunPod Deployment Guide** — SMPLitex + IntrinsiX exact deploy steps | HIGH | ✅ Done | Gemini |
| 20 | **Open Hardware Scanning** — depth cameras, LiDAR, multi-cam rigs | MEDIUM | ✅ Done | Gemini |
| 21 | **"FutureMe" Body Morphing** — weight-change prediction visualization | MEDIUM | ✅ Done | Gemini |
| **Phase 5** (deep dives + fix fabrications) | | | | |
| 22 | **SMPL-Anthropometry Mapping** — exact indices for 24 keys | HIGH | ✅ Done | Gemini |
| 23 | **A2B Regressor Training** — data sources (ANSUR/CAESAR) + script | HIGH | ✅ Done | Gemini |
| 24 | **Muscle Segmentation** — vertex groups + 2D→3D projection | MEDIUM | ✅ Done | Gemini |
| 25 | **SMPLitex + IntrinsiX Actual API** — correct handler code | HIGH | ✅ Done | Gemini |

## Top Actions (Phase 5 Results)

1. **Implement SMPL-Anthropometry Mapping (Task 22)**: 
   - Use the verified vertex indices (e.g., 3501 for waist, 3050 for neck) to replace approximate landmarks in the measurement extraction pipeline.

2. **Train A2B Regressor (Task 23)**: 
   - Generate synthetic training data using our SMPL pipeline to train a lightweight MLP that maps 36 anthropometric measurements back to the 10 SMPL betas for the "FutureMe" feature.

3. **Deploy Corrected RunPod Handlers (Task 25)**: 
   - Replace fabricated Task 19 code with corrected `StableDiffusionControlNetInpaintPipeline` (SMPLitex) and `IntrinsiXPipeline` (IntrinsiX) calls.

## Verified Research Deliverables
- [Task 22: SMPL-Anthropometry Mapping](task22_smpl_anthropometry_mapping.md)
- [Task 23: A2B Regressor Training](task23_a2b_regressor_training.md)
- [Task 24: Muscle Segmentation](task24_muscle_segmentation.md)
- [Task 25: Actual API fix](task25_smplitex_actual_api.md)

---
**Status Update**: 2026-03-22 | Phase 5 tasks completed. All findings committed to `gemini/research-phase5`.
