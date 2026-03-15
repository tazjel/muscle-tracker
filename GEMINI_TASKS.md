# Gemini Task Sheet — Muscle Tracker v2.3 "Production Hardening"

**Date**: 2026-03-15
**From**: Claude (Implementation Lead)
**To**: Gemini CLI
**Mission**: Harden the existing codebase for real-world use. No new research. No new proposals. Implementation only.

---

## Current Project State

- **Version**: v2.2 — 5 commits on `master`, clean working tree
- **Tests**: 116 passing across 10 test files (0.34s)
- **Core modules** (11): auth, calibration, alignment, pose_analyzer, vision_medical, volumetrics, symmetry, segmentation, visualization, progress, report_generator
- **Untested modules**: `report_generator.py` (331 lines), `visualization.py` (176 lines)
- **API**: py4web with CORS, JWT auth, 13 endpoints
- **Flutter app**: Camera capture, level indicator, body guide overlay, JWT login screen, review screen
- **Database**: SQLite with 4 tables (customer, muscle_scan, symmetry_assessment, health_log)

### What is NOT done yet
- `report_generator.py` and `visualization.py` have zero tests
- The Flutter app has no pose-check integration (the `/api/pose_check` endpoint exists but the app doesn't call it)
- No way to select muscle group in the Flutter app (hardcoded to "bicep")
- The CLI `report` command version string still says v2.0
- No `.env.example` file documenting required environment variables for deployment

---

## Task 1: Test `report_generator.py` (P0)

**File to create**: `tests/test_report_generator.py`

**What to test**:
- `generate_clinical_report()` with only a `scan_result` → produces a PNG file at the output path
- `generate_clinical_report()` with `scan_result` + `volume_result` → produces a taller PNG (more sections)
- `generate_clinical_report()` with all sections (scan, volume, shape, symmetry, trend) → produces output without crashing
- `_render_header()` returns a numpy array with shape `(120, 1200, 3)`
- `_render_footer()` returns a numpy array with shape `(50, 1200, 3)`
- `_draw_progress_bar()` does not crash with edge values (0.0, 1.0, negative, >1.0)
- Verify output file is actually written to disk (use `tempfile.mktemp(suffix='.png')` for paths, clean up after)

**How to construct test inputs**:
```python
scan_result = {
    "status": "Success",
    "verdict": "Moderate Increase",
    "confidence": {"detection": 85.0, "alignment": 70.0, "calibration": "high"},
    "metrics": {"growth_pct": 3.5, "area_delta_mm2": 120.0}
}
volume_result = {"volume_cm3": 157.08, "model": "elliptical_cylinder",
                 "height_mm": 100, "semi_axis_a_mm": 25, "semi_axis_b_mm": 20}
shape_result = {"score": 82.0, "grade": "A", "template": "bicep_peak",
                "recommendations": {"assessment": "Strong shape"}}
```

**Constraints**:
- These tests use real OpenCV (no mocking needed) — they just generate images from dicts
- Clean up temp files in `tearDown` or `addCleanup`
- Do NOT mock mediapipe — this module doesn't use it

---

## Task 2: Test `visualization.py` (P0)

**File to create**: `tests/test_visualization.py`

**What to test**:
- `generate_growth_heatmap()` with two synthetic images and contours → produces output file
- `generate_side_by_side()` with two images → produces output with width = 2*W + 4 (separator)
- `generate_symmetry_visual()` with two images and symmetry data → produces output
- `_draw_legend()` does not crash on a canvas with or without metrics
- `_draw_label()` does not crash

**How to create synthetic test data**:
```python
img = np.zeros((300, 300, 3), dtype=np.uint8)
contour = np.array([[100,100],[200,100],[200,200],[100,200]]).reshape(-1,1,2).astype(np.int32)
```

**Constraints**:
- Use `tempfile` for output paths, clean up after
- Real OpenCV, no mocking

---

## Task 3: Add muscle group selector to Flutter app (P1)

**File to modify**: `companion_app/lib/main.dart`

**What to do**:
1. Add a `DropdownButton<String>` or `SegmentedButton` to the `CameraLevelScreen` that lets the user select from: `bicep`, `tricep`, `quad`, `calf`, `delt`, `lat`
2. Store the selection in a state variable (default: `"bicep"`)
3. Pass the selected muscle group in the upload request: `request.fields['muscle_group'] = selectedMuscleGroup;`
4. Display the selected muscle group in the top bar next to "MUSCLE TRACKER"

**Constraints**:
- Keep it minimal — a dropdown in the top bar or above the capture button
- Do NOT add new packages
- Do NOT change the camera/capture/review flow
- Do NOT modify any Python files

---

## Task 4: Add pose-check call before upload in Flutter (P1)

**File to modify**: `companion_app/lib/main.dart`

**What to do**:
1. After the front image is captured (before moving to side view), call `POST $serverBaseUrl/api/pose_check` with the captured image and the selected muscle group
2. If the response has `"status": "corrections_needed"`, show a dialog with the correction instructions (from `response["corrections"]`) and let the user choose "Retake" or "Continue Anyway"
3. If the response has `"status": "ok"`, proceed to side view automatically
4. If the call fails (network error, timeout), skip the check and proceed normally — don't block the user

**Request format**:
```dart
var request = http.MultipartRequest('POST', Uri.parse('$serverBaseUrl/api/pose_check'));
request.headers['Authorization'] = 'Bearer $_jwtToken';
request.files.add(await http.MultipartFile.fromPath('image', frontPath));
request.fields['muscle_group'] = selectedMuscleGroup;
```

**Constraints**:
- The pose check is advisory, not blocking — "Continue Anyway" must always be available
- Add a 5-second timeout on the HTTP call
- Do NOT modify any Python files
- Do NOT add new packages

---

## Task 5: Create `.env.example` and update version string (P1)

**File to create**: `.env.example`

**Contents**:
```
# Required for production JWT auth (random 64-char hex string)
MUSCLE_TRACKER_JWT_SECRET=

# JWT token expiry in seconds (default: 3600 = 1 hour)
MUSCLE_TRACKER_JWT_EXPIRY=3600

# Admin token endpoint secret
MUSCLE_TRACKER_ADMIN_SECRET=

# Legacy static API token (dev mode only, will be removed)
MUSCLE_TRACKER_API_TOKEN=dev-secret-token
```

**Also**: Update the version string in `report_generator.py` line 299 from `"v2.0"` to `"v2.3"`, and in `muscle_tracker.py` line 3 from `"v2.0"` to `"v2.3"`.

**Constraints**:
- Do NOT put actual secrets in `.env.example`
- Do NOT modify any other files
- Add `.env` to `.gitignore` if it's not already there

---

## Task 6: Commit everything (P0 — do this LAST)

**Steps**:
1. Run the full test suite: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
2. Confirm 120+ tests pass (existing 116 + new report_generator + visualization tests)
3. `git add` the new and modified files
4. Commit with message: `"feat: report/visualization tests, Flutter muscle group selector + pose check, v2.3"`

**Acceptance**: All tests pass, `git status` is clean.

---

## STRICT Rules for Gemini

1. **Do the tasks in order.** Do not skip ahead.
2. **Do NOT create proposal documents, roadmaps, or strategy files.** No `CLAUDE_UPGRADE_PROPOSAL_*.md`. No research documents. Implementation and tests ONLY.
3. **Do NOT implement features not listed here.** No G16, G17, G18, no 3D reconstruction, no LRM, no Gaussian Splatting, no video processing, no dashboard SPA.
4. **Do NOT refactor existing code** unless a task explicitly says to modify a file.
5. **Run the full test suite after writing tests.** All 120+ tests must pass before committing.
6. **Keep changes minimal.** Each task should touch 1-2 files max.
7. **If something is unclear, skip it** and note what was unclear.
8. **Use this Python**: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
9. **Do NOT modify these Claude-owned files**: `core/auth.py`, `web_app/controllers.py`, `requirements.txt`, `tests/test_auth.py`, `tests/test_vision_medical.py`, `tests/test_progress.py`, `tests/test_pose.py`, `tests/test_pose_correction.py`.
10. **Do NOT modify `core/pose_analyzer.py`** or any other core module unless a task explicitly names it.
11. **When you finish all 6 tasks, STOP.** Do not propose next steps, research topics, or additional upgrades. Just report what you did.

---

## What is NOT on this task sheet (do not start these)

- Video keyframe extraction
- 3D reconstruction / Gaussian Splatting
- Shadow-based depth inference
- Dashboard SPA
- Cloud deployment
- Any research or SOTA analysis
