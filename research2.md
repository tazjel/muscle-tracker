# Task 2: Silhouette + Keypoint → SMPL Fitting (Replacing Manual Measurements)

## Goal
Find papers that estimate SMPL shape from 2 photos (front + side) without manual body measurements — using silhouettes, keypoints, or both.

## Our Current State
- User manually enters 24 body measurements in the Flutter app
- These feed into `core/smpl_fitting.py` to build SMPL mesh
- We already capture front + side photos — we want to skip manual entry entirely

## Search Queries
1. `site:researchgate.net silhouette "SMPL" shape estimation "two views" OR "dual view" OR "front and side" 2024 2025`
2. `site:researchgate.net keypoint "body shape" regression SMPL "single image" 2024 2025`
3. `"anthropometric" measurement prediction "pose estimation" smartphone 2025`

## Extraction Table (fill per paper)

| Field | What to capture |
|-------|----------------|
| Title + DOI | |
| Input | How many images? What resolution? Any constraints (T-pose, underwear, plain background?) |
| Method | How does it go from pixels → SMPL betas? (optimization? regression? diffusion?) |
| Accuracy | Per-vertex error (mm), measurement error (cm), comparison to ground truth |
| Speed | Inference time (seconds) |
| Code available? | GitHub link if yes |
| Runs on RunPod? | PyTorch? GPU requirements? |

## Filter OUT
- Papers requiring depth cameras or LiDAR
- Papers that only work with >4 views
- Papers with no quantitative evaluation

## Deliverable
**Top 3 papers** ranked by "can replace our manual measurement entry".

For the #1 pick, provide:
1. Exact model weights needed (URLs, file sizes)
2. Inference code structure (pseudocode showing input→output flow)
3. How it connects to our `core/smpl_fitting.py` or `core/smpl_direct.py`
4. Whether it can run on RunPod A40 (48GB) or needs A100 (80GB)

## Self-Review Checklist
- [ ] Method works with exactly 2 phone photos (front + side)
- [ ] No depth sensor required
- [ ] Inference time < 30 seconds on GPU
- [ ] Code/weights are publicly available
- [ ] Output is SMPL-compatible (betas, or mesh we can convert)
