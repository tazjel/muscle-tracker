# Gemini Task Sheet — Muscle Tracker v2.4 "User Experience"

**Date**: 2026-03-15
**From**: Claude (Implementation Lead)
**To**: Gemini CLI
**Mission**: Make the app usable end-to-end. Right now a user can capture and upload, but they never see their results or history. Fix that.

---

## Current Project State

- **Version**: v2.3 — 6 commits, 127 tests, clean tree
- **Flutter app screens**: Login → Camera (with muscle group selector + pose check) → Review → Upload → snackbar
- **Problem**: After upload, the user sees a snackbar saying "Volume: 157.08 cm³" and that's it. No results breakdown. No history. No progress tracking. The app is a dead end after each scan.
- **API endpoints available but unused by the app**:
  - `GET /api/customer/<id>/scans` — returns scan history
  - `GET /api/customer/<id>/progress` — returns trend analysis
  - `POST /api/customer/<id>/health_log` — log diet/activity
  - `GET /api/customer/<id>/health_logs` — get logs

---

## Task 1: Results screen after upload (P0)

**File to modify**: `companion_app/lib/main.dart`

**What to do**: After a successful upload in `_uploadScan()`, instead of showing a snackbar and resetting, navigate to a new `ResultsScreen` that displays the scan results.

**ResultsScreen requirements**:
- Takes the API response `result` map as a constructor parameter
- Displays in a clean card layout:
  - Volume: `result["volume_cm3"]` cm³ (large, prominent)
  - Muscle group: from `_selectedMuscleGroup`
  - Shape score + grade: `result["shape_score"]` / `result["shape_grade"]` (if present)
  - Growth: `result["growth_pct"]`% / `result["volume_delta_cm3"]` cm³ (if present, color green for gain, red for loss)
  - Calibrated: yes/no badge
- A "New Scan" button that pops back to the camera screen
- A "View History" button that navigates to the HistoryScreen (Task 2)

**Constraints**:
- Replace the snackbar, don't keep both
- Use the existing dark theme / teal accent colors
- Do NOT add new packages

---

## Task 2: Scan history screen (P0)

**File to modify**: `companion_app/lib/main.dart`

**What to do**: Add a `HistoryScreen` that fetches and displays past scans.

**How it works**:
1. On init, call `GET $serverBaseUrl/api/customer/1/scans` with the JWT header (use the existing `_jwtToken` global)
2. Pass `muscle_group` as a query parameter if the user has one selected
3. Display results in a `ListView` with cards, each showing:
   - Date (formatted from `scan_date`)
   - Muscle group
   - Volume (cm³)
   - Growth % (if available, colored)
   - Shape grade (if available)
4. Handle empty state: "No scans yet" message
5. Handle loading state: CircularProgressIndicator
6. Handle error state: error message with retry button

**Also**: Add a history icon button (📋 `Icons.history`) to the camera screen's top bar so users can access history anytime.

**Constraints**:
- The customer ID is hardcoded to 1 for now (matching the upload logic at line 362)
- Do NOT add new packages
- Do NOT modify Python files

---

## Task 3: Add report generation API endpoint (P0)

**File to modify**: `web_app/controllers.py`

**What to add**: A new endpoint that generates a clinical report PNG for a given scan.

**Endpoint**: `GET /api/customer/<customer_id:int>/report/<scan_id:int>`

**Logic**:
1. Call `require_auth()`
2. Fetch the scan record from `db.muscle_scan(scan_id)` — verify it belongs to the customer
3. Build the input dicts that `generate_clinical_report()` expects:
   - `scan_result`: construct from the scan's stored metrics (area, width, height, growth_pct, detection_confidence)
   - `volume_result`: construct from volume_cm3, volume_model, height_mm, etc.
   - `shape_result`: construct from shape_score, shape_grade if present
4. Call `generate_clinical_report(scan_result, volume_result, shape_result, output_path=temp_path, patient_name=customer.name)`
5. Return the PNG file using py4web's file response mechanism

**Import needed**: `from core.report_generator import generate_clinical_report`

**Constraints**:
- Use `tempfile.mktemp(suffix='.png')` for the output path
- Clean up the temp file after sending (or let the OS handle it)
- Return 404 if scan not found or doesn't belong to customer
- Do NOT modify `core/report_generator.py`
- Do NOT modify any other existing endpoint

---

## Task 4: Add progress/trend API call to Flutter (P1)

**File to modify**: `companion_app/lib/main.dart`

**What to do**: Add a `ProgressScreen` accessible from the `HistoryScreen`.

**How it works**:
1. Add a "View Trends" button at the top of the `HistoryScreen`
2. On tap, call `GET $serverBaseUrl/api/customer/1/progress?muscle_group=<selected>`
3. Display the response in a simple layout:
   - Trend direction: "GAINING" / "LOSING" / "MAINTAINING" (large, colored text)
   - Total change: `volume_summary.total_change_cm3` cm³ / `volume_summary.total_change_pct`%
   - Weekly rate: `trend.weekly_rate_cm3` cm³/week
   - Consistency (R²): `trend.consistency_r2`
   - 30-day projection: `trend.projected_30d_cm3` cm³
   - Growth streak: `growth_streak.consecutive_gains` periods
   - Best period: `best_period.volume_change_cm3` cm³
4. Handle "Insufficient Data" status (< 2 scans) with a friendly message

**Constraints**:
- Keep the UI simple — text cards, no charts library
- Do NOT add new packages
- Do NOT modify Python files

---

## Task 5: Commit everything (P0 — do this LAST)

**Steps**:
1. Run the full test suite: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
2. Confirm all 127+ tests pass
3. `git add` new and modified files
4. Commit with message: `"feat: results screen, scan history, progress view, report API endpoint (v2.4)"`

**Acceptance**: All tests pass, `git status` is clean.

---

## STRICT Rules for Gemini

1. **Do the tasks in order.** Tasks 1-2 are the highest priority.
2. **Do NOT create proposal documents, roadmaps, or strategy files.** Implementation ONLY.
3. **Do NOT implement features not listed here.** No 3D reconstruction, no video processing, no research.
4. **Do NOT refactor existing code** unless a task explicitly says to modify a file.
5. **Run the full test suite before committing.** All tests must pass.
6. **Keep changes minimal.** Flutter tasks modify only `main.dart`. The API task modifies only `controllers.py`.
7. **Do NOT modify these Claude-owned files**: `core/auth.py`, `requirements.txt`, `tests/test_auth.py`, `tests/test_vision_medical.py`, `tests/test_progress.py`, `tests/test_pose.py`, `tests/test_pose_correction.py`.
8. **Do NOT modify any `core/*.py` module** unless a task explicitly names it.
9. **When you finish all 5 tasks, STOP.** Report what you did. Do not propose next steps.
10. **Use this Python**: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
