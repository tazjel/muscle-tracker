# gtd3d Research Summary

## Task Status

| # | Task | Priority | Status | Assigned |
|---|------|----------|--------|----------|
| 7 | **Cross-View Color Harmonization (Seam Fix)** | URGENT | ✅ Done | Gemini |
| 8 | **Diffusion Texture Infill (62%→100%)** | HIGH | ✅ Done | Gemini |
| 9 | **Photo→SMPL (No Measurements)** | HIGH | ✅ Done | Gemini |
| 3 | Texture Generation (360°) | HIGH | ⬜ Pending | Gemini |
| 1 | Body Composition from Shape Params | HIGH | ⬜ Pending | Gemini |
| 2 | Silhouette → SMPL Fitting | HIGH | ⬜ Pending | Gemini |
| 6 | RunPod Model Survey | MEDIUM | ⬜ Pending | Gemini |
| 4 | Muscle Segmentation | LOW | ⬜ Pending | Gemini |
| 5 | Longitudinal Tracking | LOW | ⬜ Pending | Gemini |

## Top 3 Actions (Ready for Claude)

1. **Implement Task 7 (LAB + Multi-band)**: 
   - Harmonize Back/Side views to the Front photo in LAB space.
   - Replace weighted sum in `texture_bake.py` with `cv2.detail.MultiBandBlender` to kill the visible back seam.
   
2. **Deploy Task 8 (TexDreamer)**:
   - Host **TexDreamer** on RunPod. 
   - Pass the 62.5% partial atlas to the model to "hallucinate" high-fidelity skin/anatomy for the remaining 37.5% (back/sides).

3. **Migrate to Task 9 (Focused SMPLer-X)**:
   - Replace HMR2 with **Focused SMPLer-X (2025)**.
   - This enables accurate (±2cm) body shape from front+side photos, allowing us to delete the manual measurement entry form.

## Verified Research Deliverables
- [Task 7: Texture Seam Fix](task7_texture_seam_fix.md)
- [Task 8: Diffusion Texture Infill](task8_diffusion_texture_infill.md)
- [Task 9: Photo-to-SMPL](task9_photo_to_smpl_no_measurements.md)

---
**Status Update**: 2026-03-20 | Gemini Research Phase 1 Complete.
