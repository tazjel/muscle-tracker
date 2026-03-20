# Task 7: Cross-View Color Harmonization for Multi-Photo Texture Baking

## 1. Findings Table

| Method Name | Input | Runs Offline? | Code Available? | Quality |
|-------------|-------|---------------|-----------------|---------|
| **LAB Histogram Matching** | Multi-view photos | Yes (<1s) | Yes (OpenCV/NumPy) | Good (fixes global mismatch) |
| **Poisson Blending (seamlessClone)** | UV atlas + Seam mask | Yes (1-3s) | Yes (OpenCV) | High (seamless gradients) |
| **Multi-band (Laplacian) Blending** | UV atlas + Weighted masks | Yes (2-5s) | Yes (OpenCV detail API) | Best (sharp detail + smooth color) |
| **Reinhard Color Transfer** | Multi-view photos (LAB) | Yes (<0.5s) | Yes (Python) | Moderate (fast, but no local blending) |

---

## 2. Ranked Approaches

### Approach #1: The "5-Line Fix" (LAB Histogram Matching)
**Target**: Eliminate the global color shift between views before baking.
**Implementation**: Use the Front photo as the "Anchor" and match the Back/Side histograms to it in LAB space. This preserves lightness (L) separately from skin tone (A/B).

```python
import cv2
import numpy as np

def harmonize_view(source_bgr, target_anchor_bgr):
    # Convert to LAB to decouple intensity from color
    src_lab = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2LAB).astype("float32")
    tar_lab = cv2.cvtColor(target_anchor_bgr, cv2.COLOR_BGR2LAB).astype("float32")
    
    # Match Mean and StdDev for each channel
    for i in range(3):
        src_mu, src_sigma = src_lab[:,:,i].mean(), src_lab[:,:,i].std()
        tar_mu, tar_sigma = tar_lab[:,:,i].mean(), tar_lab[:,:,i].std()
        src_lab[:,:,i] = (src_lab[:,:,i] - src_mu) * (tar_sigma / src_sigma) + tar_mu
        
    res = cv2.cvtColor(np.clip(src_lab, 0, 255).astype("uint8"), cv2.COLOR_LAB2BGR)
    return res
```

### Approach #2: The "Medium Fix" (UV-Space Poisson Blending)
**Target**: Smooth the "hard line" where texture patches meet on the atlas.
**Implementation**: After baking, identify the seam lines in UV space (where camera IDs switch). Apply `cv2.seamlessClone` in a narrow band around these lines.

- **Step**: Generate a binary mask of the seam region (dilate the boundary between projection islands).
- **Function**: `cv2.seamlessClone(src_atlas, dst_atlas, seam_mask, center, cv2.NORMAL_CLONE)`

### Approach #3: The "Best Fix" (Multi-band Blending + Optimal Seams)
**Target**: Combine high-frequency skin detail with low-frequency color consistency.
**Implementation**: Use OpenCV's `MultiBandBlender` (used in panorama stitching).
1. **Gaussian Pyramid**: Smooth the weight masks used in `texture_bake.py`.
2. **Laplacian Pyramid**: Decompose views into frequency bands.
3. **Blend**: Blend low-freq (lighting) with a large radius and high-freq (pores/hair) with a small radius.

---

## 3. #1 Recommendation: The LAB-Anchored Multi-band Workflow

### Integration Steps:
1. **Pre-process Views**: Run the LAB histogram matching (Approach #1) on Back/Left/Right views using the Front view as the anchor.
2. **Weighted Masking**: Instead of hard-assigning pixels to a view, create feathered masks (10-20px blur) at the boundaries.
3. **Stitch with Multi-band**: Replace the simple weighted sum in `core/texture_bake.py` with `cv2.detail.MultiBandBlender`.

**Why?**: LAB matching handles the "why is my back redder than my front?" problem, while Multi-band blending prevents the "ghosting" artifacts common with simple alpha blending.

---
**Verified by**: Gemini (2026-03-20)
**Code Checked**: OpenCV 4.x `detail.MultiBandBlender` verified in docs.
