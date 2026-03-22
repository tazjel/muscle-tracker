# Gemini Research Tasks — Skin Texture Pipeline Phase 2

## Context
Per-region skin texture pipeline is working (`core/skin_patch.py`). Image Quilting + Laplacian blending implemented. Need research to improve quality and solve remaining issues.

---

## G-NEXT-1: Canonical SMPL UV Layout — How to Load
**Priority: HIGH** (blocks S-N2)

### Goal
Find how to load the official SMPL UV coordinates (not cylindrical fallback) without Meshcapade license.

### What We Need
1. Does the `smplx` Python package include UV data? If so, which file and what format?
2. Does SMPL_NEUTRAL.pkl contain UV data? Check keys: `vt`, `ft`, `uvs`, `texcoords`
3. If not in smplx, is there a freely available SMPL UV layout file (.obj with vt/vn, or .json)?
4. Format: per-vertex (6890, 2) or per-face-corner? How to convert to per-vertex?
5. Provide exact Python code to load canonical UVs from whatever source exists

### Anti-Fabrication
- Actually check the smplx package source on GitHub (https://github.com/vchoutas/smplx)
- Check SMPL pickle file keys — don't guess
- If no free source exists, say so clearly

---

## G-NEXT-2: Normal Map from Albedo — Best CPU Algorithm
**Priority: MEDIUM**

### Goal
Find the best algorithm to generate a convincing normal map from a skin albedo texture (no depth sensor, no GPU).

### What We Need
1. Compare approaches:
   - Sobel gradients → tangent-space normal
   - Photometric stereo (single image, assumed lighting)
   - Frequency-based height estimation (high-pass filter → normals)
   - Neural (CycleGAN albedo→normal) — any lightweight ONNX model?
2. For skin specifically: what frequency range captures pore detail?
3. Recommended approach with OpenCV/NumPy code (~20 lines)
4. What normal map strength looks best for skin in Three.js? (normalScale value)

---

## G-NEXT-3: Skin Tone Extraction from Photo — Robust Method
**Priority: MEDIUM**

### Goal
Find the best algorithm to extract the dominant skin tone from a close-up skin photo, handling:
- Mixed lighting (warm indoor + cool outdoor)
- Hair on skin
- Shadows
- Camera white balance variation

### What We Need
1. Compare: simple LAB median vs k-means clustering vs YCrCb skin detection
2. Which color space is most robust for skin tone extraction?
3. How to handle dark skin vs light skin (different detection thresholds?)
4. Code: function that takes BGR image → returns BGR skin tone color

---

## G-NEXT-4: Image Quilting Optimization — Vectorized SSD
**Priority: LOW**

### Goal
The current Image Quilting implementation tests 50 random candidates per patch using a Python loop. Find how to vectorize the SSD computation for 200+ candidates.

### What We Need
1. Can we pre-extract all possible patches as a (N, patch_h, patch_w, 3) tensor?
2. Vectorized SSD against overlap regions using NumPy broadcasting?
3. Memory estimate for 512×512 source, 64×64 patches, 16px overlap
4. Any existing Python Image Quilting implementation we can reference? (GitHub links)

---

## Timeline
- G-NEXT-1: HIGH priority, do first (blocks Sonnet S-N2)
- G-NEXT-2, G-NEXT-3: MEDIUM, do after G-NEXT-1
- G-NEXT-4: LOW, do if time permits
