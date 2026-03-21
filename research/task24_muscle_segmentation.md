# Task 24: Muscle Segmentation from Mesh Geometry — Phase 5

## Context
Backlog task 4, now informed by Phase 4 findings. We know standard SMPL can't distinguish muscle vs fat tissue. However, we can identify muscle GROUP regions on the mesh surface for visualization (highlighting biceps, quads, etc. in the viewer).

**Goal:** Research how to define and visualize muscle group regions on the SMPL mesh surface, either from published vertex groups or from 2D segmentation projection.

## Codebase Entry Points
- `core/body_segmentation.py` — MediaPipe / GrabCut muscle ROI detection (2D)
- `core/mesh_reconstruction.py:export_glb()` — exports GLB with PBR textures
- `web_app/static/viewer3d/body_viewer.js` — Three.js viewer with click regions
- SMPL mesh: 6890 vertices, 13776 faces

## Questions to Answer

**Q1: Published SMPL vertex groups for muscle regions?**
Are there published vertex index lists for major muscle groups on the SMPL mesh?
- Biceps, triceps, deltoids, pectorals, lats, abs, obliques, quads, hamstrings, glutes, calves
- Sources: SMPL body part segmentation, SMPL-X part labels, academic datasets

**Q2: Papers on 3D body muscle segmentation (2022+)**
Fill table with 5+ papers (verified DOIs):
| Title + DOI | Input | Method | Output | Accuracy | Code? |
|---|---|---|---|---|---|

**Q3: 2D→3D segmentation projection**
Our `body_segmentation.py` already detects muscle ROIs in 2D images via MediaPipe. Can we project these 2D regions onto the 3D mesh?
- Method: ray casting from camera through 2D pixel → find which face/vertex it hits on the mesh
- Feasibility: does this work with our orthographic texture projection in `texture_projector.py`?
- Provide pseudocode for 2D mask → 3D vertex selection

**Q4: Curvature-based muscle detection**
Can muscle groups be identified from mesh geometry alone (curvature analysis, convexity)?
- E.g., bicep region = high convexity area on upper arm
- Practical or too noisy?

**Q5: Three.js visualization of muscle regions**
How to highlight muscle groups in the viewer:
- Option A: Vertex colors (per-vertex color attribute on the mesh)
- Option B: Separate overlay texture with color-coded muscle regions
- Option C: Multi-material mesh (different material per muscle group)
Which approach works best with our existing `MeshPhysicalMaterial` setup?
Provide code snippet for the recommended approach.

**Q6: GLB export with muscle region data**
How to embed muscle group information in the GLB file:
- Custom vertex attributes?
- Color-coded overlay texture?
- glTF extras/extensions?
Provide code for `export_glb()` modification.

## Deliverable
- Vertex group table for major muscles (Q1)
- Paper extraction table (Q2)
- 2D→3D projection pseudocode (Q3)
- Curvature analysis feasibility (Q4)
- Three.js visualization code (Q5)
- GLB export approach (Q6)
- Clear #1 recommendation: which segmentation method for MVP
