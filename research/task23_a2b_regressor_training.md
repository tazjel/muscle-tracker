# Task 23: A2B Regressor Training Guide — Phase 5

## Context
Phase 4 Task 21 recommended an "A2B: Anthropometric to Beta" regressor for FutureMe morphing. Sonnet T9 implements a simple linear MVP (`core/body_morphing.py`). This task researches how to train a proper learned regressor to replace the linear approximation.

**Goal:** Provide a complete training guide: data sources, architecture, training script, validation, and ONNX export for client-side inference.

## Codebase Entry Points
- `core/body_morphing.py:morph_body_to_weight()` — Sonnet T9 creates this (linear MVP)
- `core/smpl_direct.py:build_smpl_mesh(betas)` — SMPL forward pass
- `core/measurement_extraction.py:extract_measurements()` — Sonnet T7 creates this

## Questions to Answer

**Q1: Does the A2B paper actually exist?**
Task 21 cited `arXiv:2412.03556`. Verify this paper exists on arXiv. If the DOI is fabricated, find the REAL equivalent paper/repo that maps anthropometric measurements → SMPL betas. Look for:
- "Anthropometric to SMPL" papers
- "Measurements to body shape" papers
- "Body shape from demographics" papers

**Q2: ANSUR dataset access**
- URL to download ANSUR-II dataset
- File format (CSV? JSON?)
- How many subjects? What measurements are included?
- License for commercial use?
- Does it include 3D scans or just tape measurements?

**Q3: CAESAR dataset access**
- Same questions as Q2
- Is there a public subset or do we need a DUA?
- Does it include SMPL registrations (betas)?

**Q4: Training script**
Provide a complete training script:
```python
# Input: (height_cm, weight_kg, age, gender, waist_cm, hip_cm, chest_cm)
# Output: 10 SMPL betas
# Architecture: 3-layer MLP with ReLU
# Training: MSE loss, Adam optimizer
# Validation: hold-out 20%, per-measurement error in cm
```

**Q5: Synthetic training data from SMPL**
Can we generate our own training data?
1. Sample random betas (10 values, normal distribution)
2. Build SMPL mesh with `build_smpl_mesh(betas)`
3. Extract measurements with `extract_measurements(vertices, faces)`
4. Now we have paired (measurements → betas) data
5. Train inverse mapping: measurements → betas

This avoids needing ANSUR/CAESAR entirely. Is this approach valid? What are the pitfalls?

**Q6: Validation protocol**
- Hold-out test set: what split ratio?
- Metrics: per-measurement error (cm), per-vertex error (mm)
- How to compute per-vertex error: run both predicted and true betas through SMPL, compare vertex positions

**Q7: ONNX export for client-side inference**
Provide exact steps:
1. Train PyTorch model
2. Export to ONNX
3. Load in browser via `onnxruntime-web`
4. Expected model size (KB)
5. Inference time in browser (ms)

## Deliverable
- Verified paper/repo reference (Q1)
- Data access guide for ANSUR/CAESAR (Q2-Q3)
- Complete training script (Q4)
- Synthetic data generation approach with analysis (Q5)
- Validation protocol (Q6)
- ONNX export guide (Q7)
