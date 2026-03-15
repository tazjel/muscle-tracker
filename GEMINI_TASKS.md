# Gemini Task Sheet — Muscle Tracker v2.1+

**Date**: 2026-03-15
**From**: Claude (Implementation Lead)
**To**: Gemini CLI
**Context**: G12 Pose Correction Engine is now implemented and tested (19/19 tests pass). Below are the next tasks, scoped to be immediately actionable with clear acceptance criteria. Do NOT work on anything outside this list.

---

## Current Project State

- **Version**: v2.0 code complete, G12 (pose correction) just added
- **Test coverage**: `tests/test_volumetrics.py` (4 tests), `tests/test_pose.py` (1 test), `tests/test_pose_correction.py` (19 tests) — 24 total
- **No git history** — nothing is committed yet
- **No CI/CD, no CORS on API, no deployed database**
- **Source**: ~2,400 lines Python, ~370 lines Dart, 10 core modules

### What G12 Added (already done — do NOT redo)
- `core/pose_analyzer.py`: `analyze_pose()` function with angle measurement, 6 muscle group rule sets, natural language correction instructions, pose scoring (0-100)
- `muscle_tracker.py`: New `pose-check` CLI command
- `tests/test_pose_correction.py`: 19 tests covering angle math, instruction generation, rule validation, mocked full-pipeline tests

---

## Task 1: Git Init & First Commit (P0 — do this FIRST)

**Why**: Nothing is version-controlled. One bad edit destroys everything.

**Steps**:
1. Create a `.gitignore` with standard Python entries: `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.egg-info/`, `dist/`, `build/`, `.env`, `uploads/`, `companion_app/.dart_tool/`, `companion_app/build/`
2. `git init` in the project root
3. `git add` all source files (`.py`, `.dart`, `.md`, `requirements.txt`, `setup.py`)
4. Commit with message: `"feat: muscle tracker v2.0 with G12 pose correction engine"`

**Acceptance**: `git log` shows one commit, `git status` is clean.

**Do NOT**: Push to any remote. Do not create branches. Do not configure CI. Just init and commit.

---

## Task 2: Test Coverage for `core/symmetry.py` (P0)

**Why**: `symmetry.py` had a crash bug that was fixed in v2.0. It has zero tests. This module handles left/right limb comparison — getting it wrong has clinical implications.

**File to create**: `tests/test_symmetry.py`

**What to test**:
- `compare_symmetry()` with valid left/right image paths (mock `analyze_muscle_growth` to return known metrics)
- Composite imbalance percentage calculation
- Risk level assignment ("Normal", "Watch", "Imbalance")
- Dominant side detection
- Edge case: identical left/right metrics → 0% imbalance
- Edge case: missing/invalid image paths → error dict

**Constraints**:
- Mock `analyze_muscle_growth` — do NOT require actual image files
- Follow the same pattern as `tests/test_pose_correction.py` (mock mediapipe at module level if needed)
- Use `unittest`, not pytest fixtures

---

## Task 3: Test Coverage for `core/segmentation.py` (P1)

**File to create**: `tests/test_segmentation.py`

**What to test**:
- `load_ideal_template()` returns a valid contour for each of the 6 templates
- Each template contour has correct dtype (`np.int32`) and shape `(N, 1, 2)`
- `calculate_shape_score()` returns 100 when comparing a template to itself
- `calculate_shape_score()` returns < 100 for different templates
- `score_muscle_shape()` with unknown template → error dict
- `_score_to_grade()` boundary conditions: S >= 90, A >= 75, ..., F < 20

**Constraints**:
- These tests do NOT need MediaPipe or real images — the template generators create synthetic contours
- Keep tests fast (< 1 second total)

---

## Task 4: Add CORS Headers to Web API (P1)

**Why**: The Flutter companion app cannot call the API without CORS. This blocks any mobile testing.

**File to modify**: `web_app/controllers.py`

**What to do**:
1. Add a py4web `@action.uses(cors)` or manually set CORS headers in a fixture/plugin
2. If py4web doesn't have built-in CORS, add an `after_request` hook or `OPTIONS` handler that sets:
   - `Access-Control-Allow-Origin: *` (for dev; production will restrict)
   - `Access-Control-Allow-Methods: GET, POST, OPTIONS`
   - `Access-Control-Allow-Headers: Authorization, Content-Type`
3. Ensure preflight `OPTIONS` requests return 200

**Do NOT**: Add authentication changes. Do not modify any endpoint logic. Do not add new endpoints. CORS headers only.

---

## Task 5: Add `pose-check` Endpoint to Web API (P1)

**Why**: The mobile app needs to call pose analysis. Currently it's CLI-only.

**File to modify**: `web_app/controllers.py`

**Endpoint**: `POST /api/pose_check`

**Request**: Multipart form with:
- `image` (file, required)
- `muscle_group` (string, optional, default "bicep")

**Response**: Return the dict from `analyze_pose()` directly, wrapped in `{"status": "success", ...result}` or `{"status": "error", "message": ...}`.

**What to import**: `from core.pose_analyzer import analyze_pose`

**Constraints**:
- Validate file type (same `ALLOWED_EXTENSIONS` check as `upload_scan`)
- Validate file size (same `MAX_FILE_SIZE_BYTES` check)
- Require API token (same `require_api_token()` pattern)
- Read the image with `cv2.imread()` from the uploaded temp file
- Do NOT save the image to the database — this is a stateless check

---

## Rules for Gemini

1. **Do the tasks in order.** Task 1 must be done before anything else.
2. **Do NOT create proposal documents, roadmaps, or strategy files.** Implementation only.
3. **Do NOT refactor existing code** unless a task explicitly says to modify a file.
4. **Do NOT add features not listed here.** No LLM coaching, no video processing, no delta reporting.
5. **Do NOT create or modify README.md, ROADMAP.md, or any documentation files.**
6. **Run tests after writing them.** If a test fails, fix it before moving on.
7. **Keep changes minimal.** Each task should touch 1-2 files max.
8. **If something is unclear, skip it** and note what was unclear rather than guessing.

---

## What Comes After These Tasks

Once these 5 tasks are done, the next phase will be:
- G13 video keyframe extraction (requires stable image pipeline first)
- Flutter ghost overlay feature
- API authentication hardening

These are NOT part of this task sheet. Do not start them.
