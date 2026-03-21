# Task 25: SMPLitex + IntrinsiX Actual API — Fix Task 19 Fabrication — Phase 5

## Context
Phase 4 Task 19 provided handler code for SMPLitex and IntrinsiX deployment, but **the inference code was fabricated**:
- SMPLitex was guessed as `StableDiffusionInpaintPipeline` — this is WRONG
- IntrinsiX was guessed as `FluxPipeline` with a text prompt — this is WRONG
- Neither code was based on reading the actual repos

**Goal:** Read the ACTUAL source code of both repos and provide CORRECT inference APIs, input/output formats, and handler code.

## Codebase Entry Points
- `runpod/handler.py` — existing lazy-load pattern: `_run_hmr()`, `_run_rembg()`, `_run_dsine()`
- Pattern: global model variable, `_load_xxx()` function, `_run_xxx(input_data)` function

## Verified Repos
| Repo | URL | Stars | License |
|---|---|---|---|
| SMPLitex | https://github.com/dancasas/SMPLitex | ~116 | ? |
| IntrinsiX | https://github.com/Peter-Kocsis/IntrinsiX | ~52 | ? |

## CRITICAL: READ THE ACTUAL REPOS

You MUST clone or read these repos to answer. Do NOT guess from paper descriptions.

## Questions to Answer

### SMPLitex

**Q1: What is the ACTUAL inference API?**
Read `SMPLitex/inference.py` or equivalent entry point. What class/function is called?
- Is it a custom model or built on a standard library (diffusers, etc.)?
- What's the exact model class name?
- What checkpoints need to be downloaded?

**Q2: What input format does SMPLitex expect?**
- UV map format: PNG? numpy array? Tensor?
- UV layout: SMPL native? SMPL-X? Custom?
- Resolution: 256? 512? 1024?
- Does it need a mask for the missing regions?
- Does it need the SMPL mesh/betas alongside the UV?

**Q3: What output does SMPLitex produce?**
- Complete UV texture? Partial fill? Multi-channel?
- Resolution of output?
- Format: PIL Image? numpy? Tensor?

**Q4: Provide CORRECT handler code**
```python
# Based on ACTUAL repo reading
def _load_smplitex():
    """Exact code from the real repo"""
    pass

def _run_smplitex(partial_uv, mask):
    """Exact inference call"""
    pass
```

### IntrinsiX

**Q5: What is the ACTUAL inference API?**
Read `IntrinsiX/inference.py` or equivalent. What class/function is called?
- Is it a FLUX pipeline? If so, how is it configured differently from a standard FluxPipeline?
- What's the actual model loading code?

**Q6: What input format does IntrinsiX expect?**
- Single image? Multi-view? UV map?
- Does it need a text prompt or is it purely image-conditioned?
- Resolution requirements?

**Q7: What output does IntrinsiX produce?**
- Separate PBR maps or concatenated grid?
- Which maps: albedo, normal, roughness, metallic, displacement?
- How to split the output into individual maps?

**Q8: Provide CORRECT handler code**
```python
def _load_intrinsix():
    """Exact code from the real repo"""
    pass

def _run_intrinsix(albedo_image):
    """Exact inference call"""
    pass
```

### Licensing

**Q9: Commercial use assessment**
- SMPLitex license: is it MIT, Apache, or restricted by SMPL's non-commercial clause?
- IntrinsiX license: MIT? Or restricted by FLUX's license?
- SMPL body model itself has a non-commercial license from MPI. Does this block commercial use of SMPLitex outputs?
- Are there commercial alternatives that produce similar results without SMPL license restrictions?

## Deliverable
- CORRECTED SMPLitex handler code based on actual repo (Q1-Q4)
- CORRECTED IntrinsiX handler code based on actual repo (Q5-Q8)
- License assessment with commercial viability (Q9)
- Exact dependency list for each (pip packages, model weights, download URLs)
- Updated pipeline timing estimate based on actual inference calls
