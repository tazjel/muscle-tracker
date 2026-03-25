# G-R19: DensePose IUV-to-MPFB2 UV Transfer (V2)

### 1. DensePose IUV Structure
- **I (Index)**: Body part ID (1-24) mapped to specific anatomical regions (e.g., 1/2 for torso, 15-18 for arms).
- **U, V (Coordinates)**: Continuous surface coordinates (0-1) parameterizing the 3D surface of that specific SMPL body part.

### 2. Transfer Algorithm for MPFB2 (V3 Spatial Projection)
**CRITICAL FINDING**: `core/texture_bake.py` (V3) **does NOT use DensePose U/V coordinates for matching**.
Instead, it uses a **Spatial Projection** approach:
1. DensePose `I` (Index) is used purely as a **semantic body mask** to isolate regions in the 2D photo.
2. The 3D MPFB2 vertices are mapped to regions using `_segment_vertices()`.
3. Vertices are geometrically projected (`_project_vertices()`) into a normalized 2D bounding box based on their physical X/Y/Z positions (e.g., arm length maps to Y, circumference to X).
4. The projection samples the photo color if it falls within the DensePose body mask (`hit_body = iuv[..., 0] > 0`).

### 3. Region Mapping
MPFB2 vertices are assigned regions via spatial heuristics (height/width bounds). These regions correspond to DensePose parts via `REGION_PARTS` (e.g., `torso: [1, 2]`, `upper_arm_r: [16, 18]`).

### 4. Edge Cases & Fallbacks
- **No DensePose Coverage**: For misses, the algorithm searches nearby body pixels in concentric radii (5px, 15px, 30px).
- **Unassigned Vertices**: Filled using a `KDTree` nearest-neighbor search against successfully colored vertices.
- **Seams**: Handled via `build_seam_mask()` and `smooth_seam()` using a two-pass Gaussian/Bilateral blur in UV space.

### 5. Pre-Conditions for E2E Test
- RunPod DensePose endpoint active.
- Minimum of Front and Back photos to ensure full mesh coverage.
- Output must be an IUV mask array where channel 0 is the part index.