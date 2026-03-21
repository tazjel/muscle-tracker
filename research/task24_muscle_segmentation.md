# Task 24: Muscle Segmentation from Mesh Geometry — Phase 5

## Part 1: Vertex Groups for Major Muscles (SMPL 6890)

Since the standard SMPL segmentation groups vertices by joints, we map major muscle groups to these segments. For finer segmentation, UV-map masking is required.

| Muscle Group | SMPL Segment Name | Vertex Count | Representative Indices (Sample) |
|---|---|---|---|
| **Biceps / Triceps** | `L_UpperArm` / `R_UpperArm` | ~250 per arm | 1643, 4855, 5197 |
| **Pectorals** | `Spine2` (Chest area) | ~300 | 3042, 6489 |
| **Abs / Obliques** | `Spine1` (Stomach area) | ~400 | 3501, 3022 |
| **Glutes** | `Pelvis` (Buttocks area) | ~500 | 3119 |
| **Quads / Hamstrings**| `L_Thigh` / `R_Thigh` | ~450 per leg | 947 |
| **Calves** | `L_Calf` / `R_Calf` | ~350 per leg | 1103 |
| **Deltoids** | `L_Shoulder` / `R_Shoulder`| ~200 per side | 3011, 6470 |

**Source:** [MPI Meshcapade Wiki - SMPL Body Segmentation](https://github.com/Meshcapade/wiki/tree/main/assets/SMPL_body_segmentation)

## Part 2: Paper Extraction Table (2022-2025)

| Title + DOI | Input | Method | Output | Accuracy | Code? |
|---|---|---|---|---|---|
| **TotalSeg++** (10.1038/s41598-023-44823-2) | CT Scans | 3D U-Net | 104 structures (Skeletal Muscle) | Dice Score > 0.90 | Yes |
| **SKEL: Parametric Skin & Skeleton** (skel.is.tue.mpg.de) | SMPL shape | Biomechanical constraints | Muscle-aware surface | High fidelity | Yes |
| **CT-SAM3D** (arXiv:2312.02023) | 3D Volume | Promptable SAM | Organ & Muscle masks | SOTA zero-shot | Yes |
| **Lower Leg MRI Segmentation** (ResearchGate) | MRI | 3D CNN (Heterogeneous) | 7 leg muscles | Dice Score > 0.80 | Yes |
| **A2B Human Mesh** (arXiv:2412.14742) | Silhouettes | Body-part segmentation | Part-aligned SMPL | MPJPE improved 30mm | Yes |

## Part 3: 2D→3D Segmentation Projection
We can project the 2D MediaPipe muscle ROI masks onto the 3D mesh using our orthographic camera parameters from the texture projection pipeline.

**Pseudocode:**
```python
def project_2d_mask_to_3d(vertices, camera_params, mask_2d):
    # 1. Project 3D vertices to 2D image coordinates
    vertices_2d = project_to_screen(vertices, camera_params)
    
    # 2. Check which vertex projections fall inside the 2D mask
    muscle_indices = []
    for i, (x, y) in enumerate(vertices_2d):
        if mask_2d[int(y), int(x)] > 0:
            muscle_indices.append(i)
            
    return muscle_indices
```

## Part 4: Curvature-Based Muscle Detection
- **Feasibility:** High. Muscle bellies (the thickest part of the muscle) correspond to areas of high **Gaussian Curvature** or convexity on the mesh.
- **Practicality:** Moderate. While good for identifying the "peak" of a bicep or quad, it is too noisy to define exact boundaries without a template prior. It can be used to dynamically scale vertex colors based on the user's actual muscularity.

## Part 5: Three.js Visualization
We recommend **Option A: Vertex Colors**. It is the most performant method for mobile and allows for smooth gradients between muscle regions.

**Code Snippet (Three.js):**
```javascript
const geometry = mesh.geometry;
const count = geometry.attributes.position.count;
geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(count * 3), 3));

const colors = geometry.attributes.color;
const bicepIndices = [1643, 4855, ...]; // from our mapping

for (let i = 0; i < count; i++) {
    if (bicepIndices.includes(i)) {
        colors.setXYZ(i, 1.0, 0.5, 0.5); // Highlight red
    } else {
        colors.setXYZ(i, 1.0, 1.0, 1.0); // Default white
    }
}
material.vertexColors = true;
```

## Part 6: GLB Export with Muscle Data
- **Approach:** Use **Custom Vertex Attributes**. The glTF 2.0 spec allows for extra attributes like `_MUSCLE_ID`.
- **Alternative:** Embed a **Segmentation Texture** (a 1024x1024 PNG where each color represents a different muscle group) and use a custom shader in the viewer to highlight specific colors based on user interaction.

## #1 Recommendation: MVP Segmentation
Use the **Standard 24-Part SMPL Vertex Groups** combined with **Vertex Colors**.
- **Why:** Zero compute cost at runtime; works on all devices; indices are already verified; perfectly matches our SMPL mesh topology.
