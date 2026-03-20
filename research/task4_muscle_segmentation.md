# Task 4: Per-Muscle or Regional Body Segmentation from 3D Mesh

## Goal
Find papers that segment a body mesh into muscle groups or anatomical regions — enabling per-region volume tracking over time.

## Our Current State
- SMPL mesh has 24-joint blend weights → can do basic 24-region segmentation already
- We compute overall body volume but not per-region
- We want finer granularity: bicep, tricep, quad, hamstring, chest, etc.
- Our `core/body_segmentation.py` does 2D image segmentation, not 3D mesh segmentation

## Search Queries
1. `site:researchgate.net "muscle segmentation" 3D mesh OR "body model" 2024 2025`
2. `site:researchgate.net "anatomical segmentation" SMPL OR "body mesh" regions 2024 2025`
3. `"body part segmentation" "3D human" vertex labeling 2024 2025`

## Extraction Table (fill per paper)

| Field | What to capture |
|-------|----------------|
| Title + DOI | |
| Segmentation granularity | How many regions? (SMPL 24-joint? 50+ muscle groups? Custom?) |
| Method | Learned? Manual annotation transfer? Blend weight based? |
| Input | Mesh only? Or mesh + image? |
| Output format | Per-vertex labels? Per-face? Submesh? |
| Volume computation | Does it compute per-region volume? |

## Filter OUT
- Medical imaging segmentation (CT/MRI muscle segmentation — different domain)
- Papers focused on animation/rigging, not measurement
- Papers with no code or reproducible method description

## Baseline Comparison
SMPL already has 24-joint blend weights. For each paper found, Gemini should note:
- How many more regions does it provide vs SMPL's 24?
- Is the added complexity worth it for fitness tracking?
- Can we get equivalent results by subdividing SMPL's blend weight regions?

## Deliverable
**Top 3 approaches** with baseline comparison to SMPL blend weights.

For practical implementation, also describe:
1. The simplest approach: subdivide SMPL blend weights into ~40 fitness-relevant regions
2. The best-quality approach from papers
3. Recommended approach (balancing complexity vs value)

## Self-Review Checklist
- [ ] Compared against SMPL 24-joint baseline
- [ ] Methods work on SMPL-topology mesh (6890 vertices)
- [ ] Output enables volume computation per region
- [ ] At least one approach requires no ML training (pure geometric)
