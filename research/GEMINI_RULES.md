# Gemini Research Rules — READ BEFORE EVERY TASK

## Rule 1: RESEARCH ONLY — DO NOT MODIFY CODE
Tasks 7, 8, and 9 are **research tasks**. Your deliverable is a markdown file with findings.
- Do NOT modify any `.py`, `.js`, or `.html` files
- Do NOT commit code changes
- Do NOT refactor, rewrite, or "improve" existing code
- Write your findings ONLY in the `research/` directory

## Rule 2: DO NOT DELETE EXISTING FUNCTIONS
In a previous session you deleted `export_glb()` from `core/mesh_reconstruction.py` (484 lines), breaking the entire 3D pipeline. This required manual restoration.
- Never remove functions that other modules import
- If you think code should change, write a recommendation in your research file — do not touch the code

## Rule 3: VERIFY CLAIMS WITH EVIDENCE
- Every paper you cite must have a working URL (DOI or arXiv link)
- Every "code available" claim must include a GitHub/HuggingFace link you verified exists
- Every VRAM estimate must come from the paper or repo README, not your guess
- If you cannot verify something, say "UNVERIFIED" explicitly

## Rule 4: OUTPUT FORMAT
Each task deliverable must be a single markdown file in `research/` with:
- A filled extraction table (not empty template rows)
- Concrete code snippets or pseudocode where requested
- A clear #1 recommendation with integration steps

## Rule 5: DO NOT TOUCH THESE FILES
Protected files — do not read, modify, or reference the internals of:
- `core/mesh_reconstruction.py`
- `core/texture_bake.py`
- `core/densepose_texture.py`
- `web_app/controllers.py`
- `web_app/static/viewer3d/body_viewer.js`

You may reference their PUBLIC API (function names, inputs, outputs) but not rewrite them.
