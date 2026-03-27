# PROPOSAL: Per-Region Skin Texture Pipeline for gtd3d

## Author: Gemini CLI
## Date: 2026-03-22
## Target Reviewer: Claude Opus (Sonnet)

### Executive Summary
Current full-body photogrammetry fails due to multi-view seam artifacts and significant coverage gaps (~37%). This proposal pivots to a **Region-Based Tileable Pipeline**. Users capture close-up skin macros which are converted into seamless, tileable patches and composited into a high-resolution UV atlas using multi-band blending.

---

### G-T1: Tileable Synthesis (Image Quilting)
**Selected Algorithm:** Efros & Freeman (2001) Image Quilting with Minimum Error Boundary Cut.

**Rationale:**
- **Detail Preservation:** Unlike histogram blending which can blur high-frequency data, Image Quilting preserves pore-level micro-geometry by finding optimal paths between overlapping patches.
- **CPU Efficiency:** Can be implemented in pure NumPy/OpenCV, avoiding GPU dependencies on the mobile client.
- **Artifact Suppression:** Eliminates the 'popcorn' repetition artifacts common in simple tiling.

**Python Implementation Strategy:**
```python
import cv2
import numpy as np

def generate_tileable_skin(sample, out_size=(1024, 1024), patch_size=64, overlap=16):
    """
    Synthesizes a seamless skin texture using Image Quilting.
    """
    # 1. Search for patches matching the L/T overlap using SSD
    # 2. Use Dynamic Programming to find Min-Cut path through overlap
    # 3. Blend along the cut path to hide seams
    pass
```

---

### G-T2: Region Boundary Blending in UV Space
**Selected Technique:** Laplacian Pyramid Blending (Multi-Band).

**Rationale:**
- **Human Perception:** The eye is sensitive to tone shifts (low frequency) and pore discontinuities (high frequency). 
- **Frequency Separation:** Laplacian blending allows a wide (64px) transition for skin tones while keeping a sharp (4px) transition for texture detail, making seams invisible.

**Workflow:**
1. **Mask Generation:** Generate a boundary mask by identifying vertices where `region_id` changes, rasterizing them into UV space, and dilating.
2. **Decomposition:** Build 5-level Laplacian pyramids for adjacent region textures.
3. **Reconstruction** Use the filated mask to guide frequency-specific blending.

---

### G-T3: Skin Region Capture Best Practices
**Hardware:** Samsung A24 (Project Target Device).

**Capture Settings:**
- **Sensor:** 50mP Main Sensor (Wide) @ 10-15cm. (Avoid the 2mP Macro lens as it lacks the SNR for pore detail).
- **Lighting:** Diffused natural light (e.g., facing a window in indirect light). 
- **Constraint:** **Strictly NO Flash**. Specular highlights from the flash bake 'fake' hights into the albedo, breaking 3D lighting.

**Minimum Region Set:**
| # | Region | Symmetry | Primary Goal |
|---|--------|----------|--------------|
| 1 | Inner Forearm | Mirrorable | High-detail arm coverage |
| 2 | Lower Abdomen | Central | Base torso tone |
| 3 | Upper Chest | Central | Pectoral texture/hair handling |
| 4 } Outer Thigh | Mirrorable | Leg coverage |
| 5 | Lower Calf | Mirrorable | Shin/Calf detail |

### Implementation Recommendation
Sonnet should implement the `SkinPatchProcessor` class in `core/skin_patch.py` to handle the G-T1 synthesis, and update `core/texture_factory.py` with the G-T2 Laplacian compositor.

---
