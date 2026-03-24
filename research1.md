# Task 1: Body Composition Prediction from SMPL Shape Parameters

## Goal
Find papers that predict body fat %, lean mass, or regional composition from 3D body mesh or SMPL beta parameters — without DXA/BIA hardware.

## Our Current State
- We have SMPL mesh with 10 beta shape parameters per user
- We compute Navy formula body fat % from circumference measurements
- We want ML-based prediction directly from shape params or mesh geometry

## Search Queries
Run these on ResearchGate, Google Scholar, arXiv, and Semantic Scholar:

1. `site:researchgate.net "body composition" "SMPL" OR "body shape" prediction 2024 2025`
2. `site:researchgate.net "body fat" "3D mesh" OR "3D scan" estimation regression 2025`
3. `"body composition" "shape parameters" smartphone OR "single image" deep learning 2024 2025`
4. `NPJ Digital Medicine body composition 3D convolutional 2025`

## Extraction Table (fill per paper)

| Field | What to capture |
|-------|----------------|
| Title + DOI | For citation |
| Input format | What goes in? (SMPL betas? Mesh vertices? Silhouette? Measurements?) |
| Output metrics | What it predicts (body fat %, lean mass kg, regional fat, visceral fat?) |
| Model architecture | What ML model? (GPR, CNN, transformer, linear regression?) |
| Training data size | How many subjects? What scanner? |
| Accuracy | R², MAE, correlation with DXA |
| Can we replicate? | YES/NO + reason (do we have the inputs? is code/weights available?) |
| Integration path | How would this plug into `core/body_composition.py`? |

## Filter OUT
- Papers requiring CT/MRI/DXA **input** (we only have photos + mesh)
- Papers using proprietary scanning hardware we can't replicate
- Papers with no accuracy metrics reported
- Papers older than 2022

## Deliverable
A ranked table of **top 5 papers** by "replicability for gtd3d", with the #1 pick having a **3-step integration plan**:
1. What to download (model weights, code repo)
2. What input format to prepare (from our SMPL betas/mesh)
3. How to wire into our pipeline (`core/body_composition.py` → API endpoint)

## Self-Review Checklist
Before submitting, verify:
- [ ] Every recommended paper has available code or weights
- [ ] Method works with our inputs (SMPL betas, mesh vertices, or measurements derived from mesh)
- [ ] No proprietary hardware required
- [ ] Accuracy metrics are reported and compared to DXA ground truth
- [ ] Integration path is concrete, not vague
