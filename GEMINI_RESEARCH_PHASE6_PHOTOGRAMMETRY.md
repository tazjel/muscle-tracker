 # GEMINI Research Phase 6: Latest Photogrammetry & Neural Rendering (2026)
 
## 1. Executive Summary: The "Gaussian" Shift
As of March 2026, traditional photogrammetry (Point Clouds -> Poisson Reconstruction -> Textured Meshes) has been largely superseded for high-fidelity human scanning by **3D Gaussian Splatting (3DGS)** and **Neural Radiance Fields (NeRF)**. 

While traditional methods remain the standard for precise metric measurement (sub-millimeter engineering), **3DGS** is the 2026 standard for "Cinematic Scans" because it captures fine-grained details like hair, skin translucency, and subsurface scattering naturally through view-dependent effects (Spherical Harmonics).

---

## 2. Core Technique: Mesh-Guided Gaussian Splatting (MG-3DGS)
For the **gtd3d** project, the most critical advancement is the integration of 3DGS with parametric meshes like **MPFB2 (MakeHuman)** or **SMPL-X**.

### A. The "Zombie" Problem Fix
Our current v5.5 "zombie" look is caused by hard UV-mapped textures on a static mesh. MG-3DGS solves this by:
- **Anchoring Gaussians to Vertices:** Each vertex of our 13k MPFB2 mesh acts as an anchor for a "cloud" of semi-transparent Gaussian primitives.
- **Parametric Deformation:** When a user moves an MPFB2 slider (e.g., `Bicep_Mass`), the underlying mesh deforms, and the high-fidelity Gaussian skin "follows" the mesh accurately.
- **Frameworks:** **ExAvatar** and **PGHM (Parametric Gaussian Human Model)** are the leading 2025-2026 research implementations.

### B. Monocular "Online" Reconstruction (ODHSR)
New 2025 frameworks allow for high-quality reconstruction from a **single smartphone video**:
- **ODHSR (Online Dense Human-Scene Reconstruction):** Performs camera tracking, pose estimat  ion, and 3DGS training simultaneously.
- **Benefit for gtd3d:** A user can record a 10-second "orbit" video of themselves, and the sys tem generates a cinematic 3DGS model in minutes, not hours.

---

## 3. Web & Mobile Rendering: The "Spark" Engine
Rendering these models in Three.js/Web has evolved significantly:
- **Spark (by World Labs):** The 2026 industry-standard library for Three.js. It uses **WebGPU** for real-time Gaussian sorting and supports **SPZ (Splat Zip)** compression.
- **SPZ Compression:** Reduces a 150MB `.ply` scan to ~10-15MB, making it viable for mobile browsers.
- **Integration:** Spark allows 3DGS models to receive shadows from Three.js lights, bridging th           e gap between "neural clouds" and "3D scenes."
  
-- -

## 4. Biomechanically Accurate Reconstruction (HSMR)
For our **Muscle Tracker** component:
- **HSMR (Human Skeleton and Mesh Recovery):** A 2025 technique that reconstructs the human body with an internal biomechanical skeleton.
- **Use Case:** It ensures that "flexing" animations and muscle group segments (from Task 24) align with the actual skeletal constraints of the scanned person, preventing "rubber-joint" artifacts.
                 
---  

## 5.  Strategic Recommendations for gtd3d v6.0
1. **P  ilot 3DGS Integration:** Move from traditional PBR Albedo/Normal maps to a hybrid "Splat Skin" approach.
2. **Imp  lement Spark Renderer:** Replace current `MeshPhysicalMaterial` with a `SparkSplat` layer for the skin, while keeping the MPFB2 mesh for volume and measurement.
3. **Adopt   SPZ Format:** Standardize our asset pipeline on `.spz` for photogrammetry captures.
4. **Frequency-Separated Blending:** Use the 2026 "Multi-scale 3DGS" to capture both pore-level detail and overall body shape without the visual noise common in 2024 methods.

---
**Status:** Research Verified. Ready for Prototype Phase.
