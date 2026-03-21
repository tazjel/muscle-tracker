# Gemini Research Rules — READ BEFORE EVERY TASK

## Rule 1: RESEARCH ONLY — DO NOT MODIFY CODE
All tasks are **research tasks**. Your deliverable is a markdown file with findings.
- Do NOT modify any `.py`, `.js`, or `.html` files
- Do NOT commit code changes
- Do NOT refactor, rewrite, or "improve" existing code
- Write your findings ONLY in the `research/` directory (and `benchmarks/rivals/` for Task 15)

## Rule 2: DO NOT DELETE EXISTING FUNCTIONS
In a previous session you deleted `export_glb()` from `core/mesh_reconstruction.py` (484 lines), breaking the entire 3D pipeline. This required manual restoration.
- Never remove functions that other modules import
- If you think code should change, write a recommendation in your research file — do not touch the code

## Rule 3: VERIFY CLAIMS WITH EVIDENCE (STRICT — Phase 2 failed this)
Phase 2 had fake arXiv IDs (`2409.xxxxx`), fabricated star counts, and wrong repo URLs. This MUST NOT happen again.

- Every paper must have a **real DOI or arXiv ID** (e.g., `arXiv:2312.13913`). If you cannot find the real ID, write: `"Title Here" — DOI NOT FOUND`
- Every GitHub repo must have the **exact URL** you can open. If you cannot verify it exists, write `UNVERIFIED`
- **NEVER fabricate star counts** — if you can't check, write "unknown"
- Every VRAM estimate must come from the paper/repo README, not your guess. If not stated, write `NOT STATED`
- **NEVER use placeholder IDs** like `arxiv:2409.xxxxx` — this is an automatic FAIL

## Rule 4: OUTPUT FORMAT
Each task deliverable must be a single markdown file in `research/` with:
- A filled extraction table (not empty template rows)
- Concrete code snippets or pseudocode where requested
- A clear #1 recommendation with integration steps
- Answered questions (not "further research needed")

## Rule 5: DO NOT TOUCH THESE FILES
Protected files — do not read, modify, or reference the internals of:
- `core/mesh_reconstruction.py`
- `core/texture_bake.py`
- `core/densepose_texture.py`
- `web_app/controllers.py`
- `web_app/static/viewer3d/body_viewer.js`

You may reference their PUBLIC API (function names, inputs, outputs) but not rewrite them.

## Rule 6: BRANCH WORKFLOW (MANDATORY)
- **ALWAYS work on a branch**, never commit directly to master
- Phase 3: `git checkout -b gemini/research-phase3` from master
- Commit research files to the branch
- Claude handles master — Gemini handles branches only
- If you need to update SUMMARY.md, do it on your branch

## Rule 7: RIVAL NAME RULE
- NEVER write any rival app's real name in any file, comment, or output
- Use codenames: `rival-B1` through `rival-B15+` for body/fitness rivals
- This is a hard rule — no exceptions
- Phase 2 violated this — do NOT repeat

## Rule 8: APK EXTRACTION (Task 15)
- Save APK data to `benchmarks/rivals/rival-BX/`
- Create `info.json` per rival with the schema defined in Task 15
- Do NOT install rivals on devices — extraction and analysis only
- Check `lib/` for engine detection, `assets/` for 3D formats
- For iOS-only apps, use web research + job postings + dev blog for tech stack

## Rule 9: USE THE TOOLS GUIDE FOR DEBUGGING
- Read `.agent/TOOLS_GUIDE.md` before debugging — it has every tool you need
- Do NOT read script source files (agent_browser.py is 1138 lines — the guide covers it in 30)
- Use `photo_preflight.py` BEFORE the pipeline, `agent_verify.py` AFTER
- All tools output JSON — use exit codes for quick pass/fail checks

## Rule 10: USE THE VERIFIED ANCHOR REPOS (Phase 3)
The SUMMARY.md contains a table of **11 verified GitHub repos** with correct URLs and star counts. Use these as your starting point. Do NOT re-search for repos you already know exist — read their READMEs and papers instead. Your job is to go DEEPER on verified repos, not find more shallow ones.

## Rule 11: PRACTICAL OUTPUT REQUIRED
Phase 2 was too abstract. Phase 3 tasks demand:
- **Code snippets** (not "use XYZ library")
- **Exact CLI commands** (not "deploy to RunPod")
- **Specific API calls** (not "use Three.js WebGPU")
- **Integration pseudocode** showing where new code plugs into our pipeline
- If a task asks a question, ANSWER IT with citations — don't say "further research needed"

## Rule 12: REFERENCE CODEBASE ENTRY POINTS (Phase 4)
Each Phase 4 task specifies **our codebase entry points** (file + function name). Your research must explain how findings integrate with these specific functions:
- Do NOT propose replacing the whole pipeline — propose additions/extensions
- Use the exact function signatures shown in the task files
- Pseudocode must match our existing patterns (e.g., RunPod lazy-load pattern, depth dict format)
- Branch for Phase 4: `gemini/research-phase4`
- Branch for Phase 5: `gemini/research-phase5`

## Rule 13: READ THE ACTUAL REPO CODE (Phase 5 — CRITICAL)
Phase 4 Task 19 produced FABRICATED inference code for SMPLitex and IntrinsiX because the API was guessed from paper descriptions, not read from source code.
- When a task says "read the actual repo," you MUST clone or read the source code files
- Do NOT guess APIs from paper abstracts or README overviews
- Provide the EXACT class names, function signatures, and import paths from the source
- If you cannot access the repo, say so explicitly — do NOT fabricate working code
- Mark any code you haven't verified against the actual source as `UNVERIFIED`
