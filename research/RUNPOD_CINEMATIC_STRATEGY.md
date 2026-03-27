# STRATEGY: RunPod Cinematic 3DGS Pipeline (v6.0)

## 1. Vision: The "Hybrid Skin" Architecture
We will move away from static UV textures for our "Cinematic Scan" mode. Instead, we will use a **Hybrid Skin** where the **MPFB2 mesh** provides the underlying structure and measurements, while a **3D Gaussian Splat (3DGS)** provides the visual photorealism.

### Why RunPod?
Training a high-quality 3DGS model from a 10-second smartphone video requires significant CUDA power. RunPod Serverless is the ideal choice because:
- **Cost:** We only pay for the ~7–10 minutes of training time.
- **Scale:** Multiple users can process scans simultaneously.
- **Power:** Access to RTX 4090/5090 GPUs ensures sub-10-minute turnaround.

---

## 2. Proposed RunPod Actions (v2 Handler)

We will extend `runpod/handler.py` with three new core actions:

### Action A: `train_splat` (Video → .spz)
- **Input:** Base64 video file or URL.
- **Process:** 
    1. Extract frames (FFmpeg).
    2. Pose Estimation (GLOMAP/COLMAP).
    3. 3DGS Training (`gsplat` backend).
- **Output:** Compressed `.spz` (Splat Zip) file.

### Action B: `anchor_splat` (Splat → Mesh Alignment)
- **Input:** `.spz` splat + MPFB2 vertex data.
- **Process:** 
    1. Align the 3DGS "cloud" to the MPFB2 base mesh.
    2. For each Gaussian, find the nearest 3 vertices on the MPFB2 mesh.
    3. Store "Barycentric Anchors"—this ensures the Gaussians move when the mesh sliders (muscles) move.
- **Output:** Anchored Splat metadata.

### Action C: `bake_cinematic_maps` (Neural → PBR)
- **Input:** 3DGS model.
- **Process:** Use a "Neural Baker" to extract high-frequency detail from the Splat and convert it into high-fidelity PBR Albedo/Normal maps (4096px).
- **Output:** v6.0 PBR Texture Set.

---

## 3. Implementation Roadmap

### Phase 1: Infrastructure (Next Session)
- Update `Dockerfile` in `runpod/` to include `gsplat`, `nerfstudio`, and `ffmpeg`.
- Implement `Action A` (Training) as a proof-of-concept.

### Phase 2: Mesh-Guided Logic
- Develop the `anchor_splat` algorithm to link neural data to our 13,380 vertices.
- Ensure "Muscle Definition" (Task 24) is respected by the Gaussian cloud.

### Phase 3: Web Integration
- Update `body_viewer.js` to load these custom `.spz` files from RunPod.
- Implement the "Spark" WebGPU renderer for 120FPS mobile viewing.

---
**Recommendation:** We should utilize RunPod primarily for **Training** and **Baking**. Once a user's scan is "baked" into a cinematic PBR set, we can serve the PBR version for standard viewing (free) and the full 3DGS Splat for "Cinematic Mode" (premium/paid).

**Status:** Strategy Defined. Ready for implementation.
