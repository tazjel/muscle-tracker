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
| 22 | **SMPL-Anthropometry Mapping** — exact vertex indices + measurement key mapping | HIGH | ⬜ Pending | Gemini |
| 23 | **A2B Regressor Training Guide** — data, architecture, ONNX export | HIGH | ⬜ Pending | Gemini |
| 24 | **Muscle Segmentation** — vertex groups, 2D→3D projection, viewer overlay | MEDIUM | ⬜ Pending | Gemini |
| 25 | **SMPLitex + IntrinsiX Actual API** — fix Task 19 fabricated code | HIGH | ⬜ Pending | Gemini |
| **Remaining Backlog** | | | | |
| 3 | Texture Generation (360°) — covered by Task 19+25 pipeline | LOW | ⬜ Deferred | Gemini |
| 5 | Longitudinal Tracking — related to Task 21 morphing | LOW | ⬜ Deferred | Gemini |

## Phase 2 Issues (Why Redo)
- Fake/placeholder arXiv IDs (e.g., `2409.xxxxx`)
- Unverified repo URLs and fabricated star counts
- Rival analysis used real names (Rule 7 violation), no APKs extracted
- GitHub survey had 5 arXiv papers mixed in as "repos"
- Three.js analysis had no implementation detail

## Phase 3 Improvements
- All 10 anchor repos **verified live** by Claude with correct URLs and star counts
- Rival seed list of 13 apps **verified with real package IDs and App Store URLs**
- Tasks demand **code snippets**, not just paper summaries
- Strict "UNVERIFIED" labeling rule enforced
- No placeholder DOIs allowed

## Verified Starting Resources (Phase 3 Anchors)

### Confirmed GitHub Repos
| Repo | URL | Stars | Paper |
|------|-----|-------|-------|
| SMPLitex | github.com/dancasas/SMPLitex | 116 | BMVC 2023 |
| TexDreamer | github.com/ggxxii/texdreamer | 90 | ECCV 2024 Oral |
| SiTH | github.com/SiTH-Diffusion/SiTH | 208 | CVPR 2024 |
| PSHuman | github.com/pengHTYX/PSHuman | 436 | CVPR 2025 |
| TEXGen | github.com/CVMI-Lab/TEXGen | 324 | SIGGRAPH Asia 2024 |
| IntrinsiX | github.com/Peter-Kocsis/IntrinsiX | 52 | NeurIPS 2025 |
| UV-IDM | github.com/Luh1124/UV-IDM | 41 | CVPR 2024 |
| SSS-GS | github.com/cgtuebingen/SSS-GS | 164 | NeurIPS 2024 |
| MeshGen | github.com/heheyas/MeshGen | 64 | CVPR 2025 |
| Hunyuan3D-2 | github.com/Tencent/Hunyuan3D-2 | 13.3k | 2025 |
| GaussianSplats3D | github.com/mkkellogg/GaussianSplats3D | 2.7k | — |

### Confirmed Rival Apps
| Codename | Platform | Category | Pricing |
|----------|----------|----------|---------|
| rival-B7 | Both | 3D body scan + fitness | $3.99/mo-$99.99 lifetime |
| rival-B8 | Both | 3D body scan + BMI | Free + Premium |
| rival-B9 | iOS | Body scan via depth | $9.99/mo-$79.99/yr |
| rival-B10 | Both | Photorealistic avatar | $20/mo |
| rival-B11 | iOS | 3D body prediction | Subscription |
| rival-B12 | Both | Single-photo measurement | Free/Premium |
| rival-B13 | iOS + Web | 60+ measurements | $350/mo enterprise |
| rival-B14 | Hardware | Robotic 3D scanner | $199/mo |
| rival-B15 | Hardware | DEXA + 3D digital twin | $1,599 + $239/mo |
| rival-B16 | Both | Silhouette AI Body Comp | $4.99/mo, $39.99/yr |
| rival-B17 | Both | Tailoring & AI Sizing | B2B Premium |
| rival-B18 | iOS | LiDAR-based wellness | $9.99/mo, $79.99/yr |

## Top Actions (Phase 3 & 4 Results)

1. **Deploy SMPLitex** (github.com/dancasas/SMPLitex) on RunPod for 100% UV coverage
2. **Add micro-normal tiling** to Three.js viewer (cheapest visual win)
3. **Wrap-lighting SSS** via additive ShaderMaterial overlay
4. **Auto-Measurements**: Replace manual UX with HMR2.0 -> SMPL mesh -> `trimesh` geometry slicing for 24 circumferences.
5. **FutureMe Morphing**: Implement AI Regressor (A2B) to map target weights directly into new SMPL betas.

## Verified Research Deliverables
- [Task 7: Texture Seam Fix](task7_texture_seam_fix.md)
- [Task 8: Diffusion Texture Infill](task8_diffusion_texture_infill.md)
- [Task 9: Photo-to-SMPL](task9_photo_to_smpl_no_measurements.md)
- [Task 10: Skin Texture v1](task10_skin_texture_photorealism.md) ⚠️ has unverified URLs
- [Task 11: Three.js Alternatives v1](task11_threejs_alternatives.md) ⚠️ shallow
- [Task 12: Rival Analysis v1](task12_rival_apk_analysis.md) ⚠️ no APKs extracted
- [Task 13: GitHub Survey v1](task13_skin_rendering_github_repos.md) ⚠️ mixed repos/papers
- [Task 14: Skin Texture v2](task14_skin_texture_photorealism_v2.md) ✅ Phase 3
- [Task 15: Rival APK Extraction](task15_rival_apk_extraction.md) ✅ Phase 3
- [Task 16: Three.js Skin Shader](task16_threejs_skin_shader.md) ✅ Phase 3
- [Task 17: ML Body Composition](task17_body_composition_ml.md) ✅ Phase 4
- [Task 18: Photo→SMPL Auto](task18_photo_to_smpl_auto.md) ✅ Phase 4
- [Task 19: RunPod Deployment Guide](task19_runpod_deployment_guide.md) ✅ Phase 4
- [Task 20: Open Hardware Scanning](task20_open_hardware_scanning.md) ✅ Phase 4
- [Task 21: FutureMe Body Morphing](task21_futureme_body_morphing.md) ✅ Phase 4
- [Task 22: SMPL-Anthropometry Mapping](task22_smpl_anthropometry_mapping.md) ⬜ Phase 5
- [Task 23: A2B Regressor Training](task23_a2b_regressor_training.md) ⬜ Phase 5
- [Task 24: Muscle Segmentation](task24_muscle_segmentation.md) ⬜ Phase 5
- [Task 25: SMPLitex + IntrinsiX Actual API](task25_smplitex_actual_api.md) ⬜ Phase 5

---
**Status Update**: 2026-03-22 | Phase 5 tasks created. Branch: `gemini/research-phase5`.
