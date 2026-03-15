# Gemini Task Sheet — Muscle Tracker v2.2+

**Date**: 2026-03-15
**From**: Claude (Implementation Lead)
**To**: Gemini CLI
**Status**: Previous task sheet COMPLETE. All 5 tasks done. This is the new task sheet.

---

## Current Project State

- **Version**: v2.2
- **Git**: 3 commits on `master`, clean working tree
- **Test coverage**: 105 tests across 8 test files, 100% pass rate (0.31s)
- **Auth**: JWT auth module (`core/auth.py`) + legacy dev token fallback
- **API**: CORS enabled, `pose-check` endpoint live, JWT token endpoints added
- **Core modules tested**: volumetrics, pose, pose_correction, segmentation, symmetry, vision_medical, progress, auth

### What was just added (already done — do NOT redo)
- `core/auth.py`: JWT create/verify with HS256, env-configurable secret + expiry
- `tests/test_auth.py`: 14 tests (creation, verification, expiry, wrong secret, roundtrip)
- `tests/test_vision_medical.py`: 18 tests (contour extraction, classification boundaries, full pipeline mocked)
- `tests/test_progress.py`: 35 tests (regression, R², streaks, trend analysis, correlation, date parsing)
- `web_app/controllers.py`: `require_auth()` replaces `require_api_token()` — tries JWT first, falls back to legacy static token. New endpoints: `POST /api/auth/token`, `POST /api/auth/admin_token`
- `requirements.txt`: Added `PyJWT>=2.8.0`

### Files changed
| File | Change |
|------|--------|
| `core/auth.py` | NEW — JWT module |
| `web_app/controllers.py` | JWT auth + token endpoints |
| `requirements.txt` | Added PyJWT |
| `tests/test_auth.py` | NEW — 14 tests |
| `tests/test_vision_medical.py` | NEW — 18 tests |
| `tests/test_progress.py` | NEW — 35 tests |

---

## Task 1: Commit current changes (P0 — do this FIRST)

**Steps**:
1. `git add` the new and modified files listed above
2. Commit with message: `"feat: JWT auth, vision_medical + progress tests (105 total)"`

**Acceptance**: `git log` shows 4 commits, `git status` is clean.

**Do NOT**: Push to any remote. Do not create branches.

---

## Task 2: Update Flutter app to use JWT auth (P0)

**Why**: The Flutter app currently uses a hardcoded `dev-secret-token`. It needs to obtain and use JWT tokens via the new `/api/auth/token` endpoint.

**File to modify**: `companion_app/lib/main.dart`

**What to do**:
1. Add a login/setup screen that takes a customer email (or customer_id)
2. On submit, `POST` to `$serverBaseUrl/api/auth/token` with `{"email": email}` or `{"customer_id": id}`
3. Store the returned JWT token in memory (a class variable is fine — no need for secure storage yet)
4. Use the JWT token in the `Authorization: Bearer <token>` header for all subsequent API calls (replace the hardcoded `dev-secret-token`)
5. If a 401 response is received, redirect back to the login screen

**Constraints**:
- Keep using the `http` package (already imported)
- Do NOT add new package dependencies
- Do NOT implement password fields — email-only lookup for now
- Do NOT implement secure token storage (SharedPreferences, etc.) — just hold in memory
- Keep the existing camera/capture flow exactly as-is
- The login screen should be minimal: email text field + "Connect" button

---

## Task 3: Test coverage for `core/calibration.py` (P1)

**File to create**: `tests/test_calibration.py`

**What to test**:
- `get_px_to_mm_ratio()` with `method="auto"` when no markers or pose detected → returns None
- `get_px_to_mm_ratio()` with `method="green"` on a synthetic image containing a green circle → returns a ratio
- `_detect_green_marker()` on an image with a green circle → returns correct mm/px ratio
- `_detect_green_marker()` on an image with no green → returns None
- `_detect_aruco()` on an image with no ArUco markers → returns None
- `get_px_to_mm_ratio()` with nonexistent file path → returns None
- `get_px_to_mm_ratio()` with `method="unknown"` → returns None

**How to make synthetic green marker image**:
```python
img = np.zeros((500, 500, 3), dtype=np.uint8)
cv2.circle(img, (250, 250), 50, (0, 200, 0), -1)  # BGR green circle
```
The marker_size_mm / detected_pixel_diameter should give a predictable ratio.

**Constraints**:
- Mock mediapipe at module level (same pattern as other test files)
- Do NOT use real image files
- The ArUco test only needs to verify "no marker → None" (generating ArUco markers in tests is overkill)

---

## Task 4: Test coverage for `core/alignment.py` (P1)

**File to create**: `tests/test_alignment.py`

**What to test**:
- `align_images()` with two identical images → returns the image, confidence > 0
- `align_images()` with two completely different images (e.g., random noise) → returns original image, confidence = 0
- `align_images()` with `method="unknown"` → returns original image, None matrix, 0 confidence
- `_align_orb()` returns (None, None, 0.0) when no features are found (uniform image)
- Verify the returned aligned image has the same shape as the reference image

**Constraints**:
- Use synthetic images (np.zeros, np.random, drawn shapes)
- Do NOT use real photos
- Do NOT mock OpenCV — these tests should exercise the real ORB/SIFT pipeline on synthetic data

---

## Task 5: Update `CLAUDE_STATE_MUSCLE_TRACKER.md` (P1)

**Update the state file to reflect**:
- Version: v2.2
- 105 tests, 8 test files
- JWT auth implemented
- Auth endpoints: `/api/auth/token`, `/api/auth/admin_token`
- File tree: add `core/auth.py`
- Critical issues: update to reflect that auth is now done, CORS is done, tests exist
- Keep the same format as the existing file

**Do NOT**: Create new proposal documents. Do not modify ROADMAP.md. Do not create strategy files.

---

## Rules for Gemini

1. **Do the tasks in order.** Task 1 (commit) must be done first.
2. **Do NOT create proposal documents, roadmaps, or strategy files.** Implementation and tests only.
3. **Do NOT refactor existing code** unless a task explicitly says to modify a file.
4. **Do NOT add features not listed here.** No video processing, no ghost overlay, no LLM coaching, no G16, no G17.
5. **Run tests after writing them.** Full suite must pass before committing.
6. **Keep changes minimal.** Each task should touch 1-2 files max.
7. **If something is unclear, skip it** and note what was unclear rather than guessing.
8. **Use this Python for running tests**: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
9. **Do NOT revert, overwrite, or modify files that Claude has changed.** The following files were written by Claude and must not be touched: `core/auth.py`, `web_app/controllers.py`, `requirements.txt`, `tests/test_auth.py`, `tests/test_vision_medical.py`, `tests/test_progress.py`, `tests/test_pose.py`, `tests/test_pose_correction.py`. If you need to import from these files, import — do not rewrite them.
10. **Do NOT modify `core/pose_analyzer.py`** unless a task explicitly says to. The G16 3D changes were reverted because they broke tests and were not on the task sheet. If you want to propose changes to existing modules, describe them in a comment — do not implement them.

---

## What Comes After These Tasks

Once these 5 tasks are done, the next phase will be:
- G13 video keyframe extraction
- Flutter ghost overlay (pose alignment assistance)
- Report generator tests

These are NOT part of this task sheet. Do not start them.
