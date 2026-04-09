# GTD3D Studio Architecture Map — 3D & Vision Core

This document provides a technical map of the 3D/Vision capabilities of the `gtd3d` project to assist in codebase exploration and system upgrades.

---

## 1. Mesh & Anatomical Core
The project has transitioned from legacy SMPL models to the high-fidelity **MPFB2 (MakeHuman)** standard.

- **Primary Mesh (Cinematic)**: MPFB2 Template.
  - **Topology**: 13,380 vertices / ~38,000 faces.
  - **Logic**: `scripts/blender_mpfb_v4_cinematic.py` (The master generation script).
  - **Deformation**: `core/body_deform.py` handles parametric shape changes.
- **Anatomy & Muscle**:
  - **Muscle Mapping**: `core/muscle_mapping.py` & `core/muscle_projection.py`.
  - **Volumetrics**: `core/mesh_volume.py` (uses Divergence Theorem for precise `cm³` calculation).
  - **Phenotypes**: Supports `gender_factor`, `muscle_factor`, and `weight_factor` shape keys.
- **Fitting & Alignment**:
  - **HMR 2.0**: `core/hmr_shape.py` for initial human mesh recovery from photos.
  - **Alignment**: `core/alignment.py` for centering and scaling meshes to real-world measurements.

## 2. Photorealistic Rendering & Texturing
The goal is "Cinematic" quality using modern PBR and Neural Rendering.

- **Neural Rendering (3DGS)**:
  - **Pipeline**: Video-to-.spz flow using **gsplat 1.5.0+**.
  - **Training**: `core/pipeline.py` (v6.0 logic).
  - **Anchoring**: `anchor_splat` logic binds Gaussians to the 13,380 MPFB2 vertices for parametric animation.
- **PBR Skin System**:
  - **Core**: `core/skin_pro.py` and `core/skin_texture.py`.
  - **Technique**: Frequency-separated normal mapping for high-frequency pore detail.
  - **Color Matching**: `scripts/skin_texture_from_photos.py` matches professional PBR textures (e.g., FreePBR) to user skin tone in **LAB color space**.
- **Texture Baking**:
  - **UV Projection**: `core/texture_projector.py` and `core/densepose_texture.py`.
  - **Baking**: `core/texture_bake.py` (Blender-driven PBR baking).

## 3. Vision & Data Capture
The studio consumes data from the Flutter companion app and processes it via AI pipelines.

- **DensePose**: `core/densepose_infer.py`. Maps 2D pixels to 3D surface coordinates.
- **Capture Pipeline**:
  - **Studio App**: `apps/scan_lab/` (The main scanning dashboard).
  - **Companion App**: `companion_app/` (Flutter). Supports MJPEG/H.264 streaming, remote flash/zoom, and high-res capture.
  - **Camera Estimation**: Uses **COLMAP** for SFM (Structure from Motion) required by 3DGS.

## 4. Infrastructure & Automation
- **Blender Engine**: Extensive use of Blender as a headless processing engine via `scripts/blender_*.py`.
- **Cloud GPU (RunPod)**:
  - **Integration**: `core/cloud_gpu.py`.
  - **Handlers**: `runpod/handler_v2.py` for Blackwell-ready inference.
- **Verification Tools**:
  - `scripts/agent_browser.py`: Automated UI/Viewer auditing.
  - `scripts/agent_verify.py`: Quality gate for mesh integrity.

---

## 5. Suggestions for the "New Studio" (v6.0+)

### A. Real-time Neural Preview
- **Idea**: Integrate a **Web-based 3DGS Viewer** (using Three.js or `gsplat.js`) into the dashboard.
- **Power**: Users see the "Neural Cloud" immediately after video upload, before the final mesh is baked.

### B. Dynamic Physique Dashboard
- **Idea**: Implement a "Physique Morph" UI with sliders.
- **Power**: Map the MPFB2 shape keys (Muscle/Fat/Proportion) to UI sliders for real-time anatomical adjustment of the scan.

### C. "Digital Twin" Overlay (AR)
- **Idea**: Use the companion app's camera feed and project the 3D model back onto the user's body in real-time.
- **Power**: Allows the user to "see" their progress or target physique as a virtual mirror.

### D. Multi-Device "Volumetric Stage"
- **Idea**: Allow the Studio to sync multiple companion apps (e.g., 3 phones) for simultaneous multi-angle capture.
- **Power**: Eliminates the need for the user to rotate; captures the full volume in one "Matrix-style" snapshot.

### E. Automated "Cinematic Audit"
- **Idea**: A pre-export quality gate script.
- **Power**: Automatically checks for texture stretching, EWR (Edge Warmth Ratio) consistency, and PBR map balance before the user downloads their GLB.

---

**File Path for Review:** [GTD3D_STUDIO_ARCHITECTURE_MAP.md](file:///C:/Users/MiEXCITE/Projects/gtd3d/research/GTD3D_STUDIO_ARCHITECTURE_MAP.md)
