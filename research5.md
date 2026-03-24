# Task 5: Pose-Invariant Body Shape Comparison (Longitudinal Tracking)

## Goal
Find papers that compare body shape across time (different scan sessions) in a pose-invariant way — so we can show "you gained 2cm on your chest since last month".

## Our Current State
- We store per-user body measurements over time in py4web DAL
- We rebuild SMPL mesh each session from new measurements
- No pose normalization — if user stands differently, mesh differs
- No visual diff between sessions in the Three.js viewer

## Search Queries
1. `site:researchgate.net "body shape" comparison "over time" OR longitudinal 3D scan 2024 2025`
2. `site:researchgate.net "shape registration" SMPL temporal tracking fitness 2024 2025`
3. `"body measurement" change detection 3D mesh registration 2024 2025`

## Extraction Table (fill per paper)

| Field | What to capture |
|-------|----------------|
| Title + DOI | |
| Registration method | ICP? SMPL beta space? Canonical pose alignment? |
| What it compares | Circumferences? Volumes? Surface distances? Shape descriptors? |
| Visualization | How does it show changes to the user? Heatmap? Overlay? |
| Accuracy | Measurement repeatability (mm)? |

## Filter OUT
- Papers focused on clothing/fashion (body shape under garments)
- Papers requiring controlled lab environment
- Papers with no quantitative repeatability metrics

## Deliverable
**Top 2 approaches** + recommended visualization method for our Three.js viewer.

Specifically address:
1. How to normalize pose: since we use SMPL, we can zero out pose params (theta) and compare in canonical A-pose — is this sufficient?
2. How to compute per-region change: circumference deltas at anatomical landmarks
3. How to visualize in Three.js: heatmap overlay showing growth/loss regions (red = gained, blue = lost)
4. What data format to store for comparison (SMPL betas over time? Mesh snapshots?)

## Self-Review Checklist
- [ ] Method works in SMPL beta space (pose-invariant by zeroing theta)
- [ ] Visualization is implementable in Three.js (WebGL, no server-side rendering)
- [ ] Accuracy is sub-centimeter for circumference tracking
- [ ] Approach handles real-world variance (different lighting, phone angles, etc.)
