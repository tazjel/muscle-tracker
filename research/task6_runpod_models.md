# Task 6: RunPod-Deployable Model Survey

## Goal
Survey which open-source models relevant to our pipeline can run as RunPod serverless workers — beyond what we already have.

## Our Current RunPod Setup
Already deployed on RunPod:
- **HMR2.0** — human mesh recovery from single image
- **rembg** — background removal
- **DSINE** — depth/surface normal estimation

Handler: `runpod/handler.py` — supports multiple model endpoints via action routing.

## Search Queries
1. `GitHub runpod-worker 3D human body 2025`
2. `GitHub "runpod" serverless SMPL OR "body mesh" OR avatar`
3. `site:researchgate.net "serverless" GPU inference "body reconstruction" 2025`
4. `GitHub awesome-3d-human-reconstruction 2024 2025`

## Extraction Table (fill per model)

| Field | What to capture |
|-------|----------------|
| Model name | |
| Purpose | What does it do for body reconstruction? |
| Framework | PyTorch? TF? JAX? |
| VRAM | Minimum GPU memory needed |
| Inference time | Per-image latency |
| RunPod worker exists? | Link if yes |
| License | Commercial use OK? |

## Filter OUT
- Models requiring >80GB VRAM (won't fit on A100)
- Models with no public weights
- Models that duplicate what we already have (HMR2, rembg, DSINE)
- Models focused on hand/face reconstruction only

## Models to Specifically Investigate
These are known models — check their current status:
- **SMPLer-X** — expressive whole-body from single image
- **BEDLAM / CLIFF** — robust body estimation
- **TokenHMR** — latest HMR variant
- **ICON / ECON** — clothed body reconstruction
- **PIFuHD** — implicit function body reconstruction
- **SiTH** — single-image to 3D human
- **TeCH** — text-conditioned human generation
- **DreamHuman** — text-to-3D human avatar

## Deliverable
Table of **5-8 models** we could add to our RunPod handler, ranked by impact on pipeline quality.

For each model, specify:
1. What gap it fills in our current pipeline
2. Docker base image recommendation
3. Estimated cold-start time on RunPod
4. Whether it can share a worker with existing models (same container) or needs its own

## Self-Review Checklist
- [ ] No model duplicates existing HMR2/rembg/DSINE functionality
- [ ] All models have public weights with acceptable licenses
- [ ] VRAM fits on A40 (48GB) or A100 (80GB)
- [ ] Each model has a clear "what it improves" statement for our pipeline
