# Task 3: Single-Image Photorealistic Texture Generation

## Goal
Find papers that generate full 360-degree body texture from 1-2 photos — better than our current DensePose UV baking (62.5% coverage).

## Our Current State
- We use DensePose to map visible pixels to UV space → `core/densepose_texture.py`
- Front photo gives ~62.5% UV coverage; back/sides are empty
- We have basic color fill for unseen regions but it looks flat
- Pipeline runs on RunPod (HMR2 + rembg + DSINE already deployed)

## Search Queries
1. `site:researchgate.net "texture generation" "human body" OR "human avatar" diffusion 2024 2025`
2. `"TexDreamer" OR "IDOL" OR "PSHuman" texture generation single image 3D human`
3. `site:researchgate.net "UV texture" inpainting "body mesh" OR SMPL 2025`
4. `"texture completion" "human body" "unseen regions" diffusion OR GAN 2024 2025`

## Extraction Table (fill per paper)

| Field | What to capture |
|-------|----------------|
| Title + DOI | |
| Input | Single image? Multi-view? Needs segmentation mask? |
| Output | UV texture resolution? PBR maps or just albedo? |
| Method | Diffusion? GAN? Optimization? |
| Coverage | Does it fill unseen regions (back of body)? How? |
| Quality metric | FID, LPIPS, SSIM, or user study? |
| Model size | VRAM needed? Can fit on RunPod A40/A100? |
| Code/weights | Available? License? |

## Filter OUT
- Methods that only work for faces (not full body)
- Methods requiring >48GB VRAM (won't fit on A40)
- Methods with no visible results or code

## Deliverable
**Top 3 methods** ranked by "quality of back-of-body generation from front photo".

For #1 pick, provide:
1. Architecture diagram (text-based) showing the pipeline stages
2. VRAM estimate for inference
3. Integration plan for our `runpod/handler.py` (new endpoint or extend existing)
4. Expected quality improvement over our DensePose baking

## Self-Review Checklist
- [ ] Method generates full 360° texture, not just visible regions
- [ ] Works with single front-facing photo as minimum input
- [ ] VRAM ≤ 48GB (A40) or ≤ 80GB (A100)
- [ ] Code and weights are publicly available
- [ ] License allows commercial use (or is research-only but we can retrain)
