# Sonnet Implementation Tasks — Per-Region Skin Texture Pipeline

## Context
Per-region skin texture pipeline is implemented (`core/skin_patch.py`, API endpoint, viewer UI). Tested with cropped full-body photos — works but quality is low because source patches were from distant full-body shots, not real close-ups. Need to improve quality, add PBR, wire into Flutter app, and harden the pipeline.

## Prerequisites
- Close-up skin photos at 10-15cm (user will capture these)
- Gemini research results from G-NEXT tasks (below)

---

## S-N1: Add PBR maps to skin region pipeline
**Files:** `core/skin_patch.py`, `core/texture_factory.py`
**What:** After compositing the skin atlas, generate matching normal map + roughness map from the tileable textures. Use `generate_roughness_map()` from texture_factory.py for anatomical roughness. Generate normal map from the skin texture using Sobel gradients (fake normal from albedo).
**Acceptance:** GLB exported with albedo + normal + roughness from skin region pipeline. Viewer shows MeshPhysicalMaterial.

## S-N2: Canonical SMPL UVs — eliminate cylindrical fallback
**Files:** `core/smpl_direct.py` (lines 340-346)
**What:** The cylindrical UV fallback causes limb distortion. Load canonical SMPL UVs from smplx package or from a UV data file. `_load_canonical_uvs()` currently returns None — fix it.
**Research needed:** G-NEXT-1 (Gemini: where to get canonical SMPL UVs)
**Acceptance:** `_load_canonical_uvs()` returns valid (6890, 2) UVs. Arms/legs no longer stretched.

## S-N3: Default skin tone estimation from face photo
**Files:** `core/skin_patch.py`
**What:** Currently `default_tone=(160, 140, 120)` is hardcoded BGR. Extract dominant skin color from the user's face or any uploaded region photo using LAB color space median. Apply as the fill color for uncovered regions.
**Acceptance:** Uncovered regions match the user's actual skin tone, not a generic beige.

## S-N4: Flutter close-up capture mode
**Files:** `companion_app/lib/main.dart`
**What:** Add a "Skin Capture" mode to the Flutter app. Show a region selector (5 minimum regions). When user selects a region, show camera with overlay guide (rectangle showing optimal crop area). Use MediaPipe landmarks from `core/body_segmentation.py` to estimate ROI. Capture at max resolution (50MP on A24). Upload to `/api/customer/<id>/skin_region/<region>`.
**Acceptance:** User can capture 5 skin regions from the app and see the model update in viewer.

## S-N5: Wire skin regions into generate_body_model
**Files:** `web_app/controllers.py` (around line 2907-2940)
**What:** In the `generate_body_model` flow, after SMPL mesh is built, check if the customer has any skin region tiles in `uploads/skin/customer_<id>/`. If yes, composite them into the UV atlas instead of/in addition to photo projection texture.
**Line refs:** smpl_result texture_image at line 2912, export_glb at line 2937
**Acceptance:** Body model API automatically uses skin region textures when available.

## S-N6: Improve Image Quilting quality
**Files:** `core/skin_patch.py`
**What:** Current implementation uses 50 random candidates per patch. Improvements:
1. Increase candidates to 200 for better matches
2. Add color jitter tolerance (±5 in LAB) to handle slight lighting variation
3. Add rotation augmentation — try 0°, 90°, 180°, 270° rotations of each candidate
4. Profile and optimize with NumPy vectorization (current loop is slow for large patches)
**Acceptance:** Tileable output shows no visible repetition when tiled 4x4.

## S-N7: Viewer skin upload UX improvements
**Files:** `web_app/static/viewer3d/muscle_highlighter.js`, `body_viewer.js`
**What:**
1. Show region coverage indicator (X/5 minimum regions uploaded)
2. Show thumbnail preview of uploaded skin patch next to each region button
3. Add "Reset Region" button to re-upload
4. Add loading spinner during upload
**Acceptance:** User can see progress toward full skin coverage.

---

## Dependency Order
S-N3 (skin tone) → S-N1 (PBR) → S-N5 (wire into pipeline)
S-N2 (canonical UVs) — independent, needs G-NEXT-1
S-N4 (Flutter) — independent
S-N6 (quality) — independent
S-N7 (viewer UX) — independent
