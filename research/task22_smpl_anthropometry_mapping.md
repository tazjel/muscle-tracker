# Task 22: SMPL-Anthropometry Deep Dive — Phase 5

## Context
Sonnet task T7 (`core/measurement_extraction.py`) uses approximate landmark heights for cross-sections. We need the EXACT vertex indices, measurement names, and accuracy data from the `DavidBoja/SMPL-Anthropometry` repo to refine our implementation.

**Goal:** Provide a complete mapping from SMPL-Anthropometry measurements to our 24 `DEFAULT_PROFILE` keys, with accuracy validation data.

## Codebase Entry Points
- `core/smpl_fitting.py:DEFAULT_PROFILE` — our 24 measurement key names
- `core/smpl_direct.py:build_smpl_mesh()` — returns 6890 vertices, 13776 faces (SMPL, not SMPL-X)
- `core/measurement_extraction.py` — Sonnet T7 creates this with trimesh.section approach

## Verified Anchor
- **DavidBoja/SMPL-Anthropometry**: https://github.com/DavidBoja/SMPL-Anthropometry (~40 stars, MIT license)

## Questions to Answer

**Q1: What measurements does SMPL-Anthropometry extract?**
Read the actual repo README and source code. List ALL measurement names with their SMPL vertex landmark indices (or vertex pairs/rings used for each).

**Q2: Map to our 24 DEFAULT_PROFILE keys**
Our keys (from `smpl_fitting.py`): height_cm, weight_kg, neck_circumference, chest_circumference, waist_circumference, hip_circumference, shoulder_width, arm_length, forearm_length, upper_arm_length, inseam, thigh_circumference, calf_circumference, bicep_circumference, forearm_circumference, wrist_circumference, ankle_circumference, torso_length, ...

Provide a mapping table:
| Our Key | SMPL-Anthropometry Name | Vertex Indices | Notes |
|---|---|---|---|

Mark any of our keys that CANNOT be extracted with SMPL-Anthropometry.

**Q3: Accuracy per measurement**
What error (in cm) does each measurement have compared to physical tape measure? Does the repo or paper provide validation data?

**Q4: SMPL vs SMPL-X compatibility**
Our pipeline uses SMPL (6890 vertices). Does SMPL-Anthropometry work with SMPL or only SMPL-X (10475 vertices)? If SMPL-X only, can vertex indices be mapped back to SMPL?

**Q5: A-pose vs T-pose**
Our meshes are generated in A-pose (arms at ~30° from body). Does SMPL-Anthropometry handle this or require T-pose? If T-pose only, how do we convert?

**Q6: Installation and usage**
Provide:
1. Exact pip install command (or git clone + setup.py)
2. Minimal Python code to extract measurements from our mesh:
```python
# Exact code that works with our build_smpl_mesh() output
from core.smpl_direct import build_smpl_mesh
mesh = build_smpl_mesh()
# ... how to call SMPL-Anthropometry on mesh['vertices'], mesh['faces']
```

## Deliverable
- Complete measurement mapping table (Q2)
- Accuracy validation data (Q3)
- SMPL/SMPL-X compatibility answer with workaround if needed (Q4)
- Working code snippet (Q6)
