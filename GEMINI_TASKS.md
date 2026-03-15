# Gemini Autonomous Roadmap — Muscle Tracker v2.5 → v3.0

> **READ FIRST — ENVIRONMENT**
> - OS: Windows 11. Your shell tool is `run_shell_command` (PowerShell). Use `C:\Users\MiEXCITE\...` backslash paths.
> - **ONLY WORKING TOOLS: `run_shell_command` and `list_directory`** — everything else is blocked or missing.
> - `run_bash_command` → DOES NOT EXIST. `write_file` → NOT FOUND. `read_file` → BLOCKED. `cli_help` → BLOCKED.
> - **Read files**: `run_shell_command` → `Get-Content C:\Users\MiEXCITE\Projects\muscle_tracker\<file>`
> - **Write files**: `run_shell_command` → `python -c "open(r'C:\path\file','w').write('''content''')"`
> - **Edit files**: `run_shell_command` → `python -c "p=r'C:\path\file';t=open(p).read();open(p,'w').write(t.replace('old','new'))"`
> - **Run tests**: `run_shell_command` → `python -m pytest C:\Users\MiEXCITE\Projects\muscle_tracker\tests\ -v`
> - Do NOT call `cli_help`. Do NOT spawn sub-agents. Do NOT retry blocked tools in a loop.

**Mode**: AUTONOMOUS — no human in the loop
**Instructions**: Execute phases sequentially. After each phase, run the review gate. Keep going until you run out of tokens or all phases are complete.

---

## HOW THIS WORKS

After completing each phase:

1. **Run tests**: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
2. **Commit** your work with the specified message
3. **Run the review gate**: Execute this command and read the output:
```bash
bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh
```
4. **Parse the response**:
   - `CONTINUE` → proceed to the next phase immediately
   - `FIX: <instructions>` → follow the instructions, re-commit, re-run the review gate
   - `STOP: <reason>` → halt all work, report the reason
5. **If the review gate fails to run** (network error, timeout), check that all tests pass. If they do, proceed to the next phase. If not, fix the failing tests first.

**DO NOT WAIT for human input between phases. Keep going.**

---

## COMPLETED PHASES (do not redo)

- ~~Phase 1: User Feedback Loop (v2.4)~~ — DONE (commit fb4ec44)
  - ResultsScreen, HistoryScreen, ProgressScreen implemented

---

## PHASE 2: "Health Tracking" (v2.5)

### Task 2.1: Health log entry screen
**File**: `companion_app/lib/main.dart`
- New `HealthLogScreen` with form fields: calories, protein (g), carbs (g), fat (g), water (ml), activity type, activity duration (min), sleep hours, body weight (kg), notes
- On submit, POST to `$serverBaseUrl/api/customer/<customerId>/health_log` with JWT
- Success/error feedback via SnackBar
- Add a "Log Health" button accessible from HistoryScreen or camera screen

### Task 2.2: Health log history view
**File**: `companion_app/lib/main.dart`
- New `HealthLogListScreen` — calls `GET $serverBaseUrl/api/customer/<customerId>/health_logs`
- ListView of cards: date, calories, protein, sleep, activity
- Accessible from HealthLogScreen or HistoryScreen

### Task 2.3: Display correlation data on ProgressScreen
**File**: `companion_app/lib/main.dart`
- If the progress API response contains `correlation` data, show below the trend section:
  - "Protein vs Growth: strong positive (0.85)"
  - Color green for positive, red for negative

### Task 2.4: Commit + Review Gate
- Run tests, commit: `"feat: health log entry, history, correlation display (v2.5)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`
- Act on the response, then proceed to Phase 3

---

## PHASE 3: "Multi-Customer Support" (v2.6)

### Task 3.1: Store customer_id from login
**File**: `companion_app/lib/main.dart`
- After JWT login, store `customer_id` from the response in a global variable (like `_jwtToken`)
- Replace ALL hardcoded `customer/1` and `upload_scan/1` URLs with the stored `_customerId`

### Task 3.2: Customer registration screen
**File**: `companion_app/lib/main.dart`
- "Create Account" button on LoginScreen
- New `RegisterScreen`: name, email, height (cm), weight (kg), gender dropdown
- POST to `$serverBaseUrl/api/customers` (this endpoint doesn't require auth for registration)
- On success, auto-login with the new email

### Task 3.3: Profile display
**File**: `companion_app/lib/main.dart`
- Profile indicator on camera screen showing customer name
- Tap → dialog with name, email, height, weight
- "Logout" button → clear token + customer_id, return to LoginScreen

### Task 3.4: Commit + Review Gate
- Run tests, commit: `"feat: multi-customer support, registration, profile (v2.6)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`
- Act on the response, then proceed to Phase 4

---

## PHASE 4: "Video Keyframe Extraction" (v2.7)

### Task 4.1: Keyframe extraction module
**File to create**: `core/keyframe_extractor.py`
- `extract_keyframes(video_path, num_frames=3)`:
  - Open video with `cv2.VideoCapture`
  - Sample frames evenly, score by Laplacian variance (sharpness)
  - Return the `num_frames` sharpest as BGR numpy arrays
- `save_keyframes(frames, output_dir)`:
  - Save each as JPEG, return list of paths
- Handle: nonexistent file → empty list, video shorter than num_frames → return what's available

### Task 4.2: Tests for keyframe extractor
**File to create**: `tests/test_keyframe_extractor.py`
- Create synthetic video with `cv2.VideoWriter` (temp file)
- Test correct number of frames returned
- Test frames are valid numpy arrays (3 channels)
- Test short video (< num_frames)
- Test nonexistent path → empty list
- Clean up temp files

### Task 4.3: Video upload API endpoint
**File**: `web_app/controllers.py`
- New endpoint: `POST /api/upload_video/<customer_id:int>`
- Accept video file (`.mp4`, `.mov`, `.avi`) + `muscle_group`
- Call `extract_keyframes()`, run `analyze_muscle_growth` on extracted frames
- Return same format as `upload_scan`
- Add `from core.keyframe_extractor import extract_keyframes, save_keyframes` to imports

### Task 4.4: Video capture in Flutter
**File**: `companion_app/lib/main.dart`
- Toggle on camera screen: "Photo" / "Video" mode
- Video mode: 5-second recording with countdown timer
- Save video to app directory
- Upload to `/api/upload_video/<customerId>` instead of `/api/upload_scan/<customerId>`
- Photo mode remains default

### Task 4.5: Commit + Review Gate
- Run tests, commit: `"feat: video keyframe extraction, video upload API, video capture (v2.7)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`
- Act on the response, then proceed to Phase 5

---

## PHASE 5: "Ghost Overlay" (v2.8)

### Task 5.1: Ghost overlay painter
**File**: `companion_app/lib/main.dart`
- New `GhostOverlayPainter` CustomPainter
- Loads previous scan image from local scans directory at 20% opacity
- Overlays on camera preview
- Only active when a previous scan exists for the selected muscle group

### Task 5.2: Toggle + scan fetching
**File**: `companion_app/lib/main.dart`
- Ghost icon toggle button on camera screen
- On enable: check local scans directory for most recent front/side image
- If not found locally, fetch latest scan info from API and note that no local image is available (show "No previous scan" message)
- Match overlay to current capture phase (front overlay during front capture, side during side)

### Task 5.3: Commit + Review Gate
- Run tests, commit: `"feat: ghost overlay for pose alignment (v2.8)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`
- Act on the response, then proceed to Phase 6

---

## PHASE 6: "Reporting & Export" (v2.9)

### Task 6.1: Report viewer in Flutter
**File**: `companion_app/lib/main.dart`
- "Generate Report" button on ResultsScreen and HistoryScreen
- Call `GET $serverBaseUrl/api/customer/<id>/report/<scan_id>`
- Display returned PNG bytes with `Image.memory(responseBodyBytes)`
- Full-screen viewer with pinch-to-zoom

### Task 6.2: Save report to device
**File**: `companion_app/lib/main.dart`
- "Save" button on report viewer
- Save PNG to app documents directory
- Show file path in SnackBar
- If `share_plus` package is available, add a "Share" button too (add to pubspec.yaml if needed)

### Task 6.3: Report badges on history
**File**: `companion_app/lib/main.dart`
- On HistoryScreen, add a report icon next to each scan card
- Tapping generates/views the report for that scan

### Task 6.4: Commit + Review Gate
- Run tests, commit: `"feat: report viewer, save/share, report badges (v2.9)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`
- Act on the response, then proceed to Phase 7

---

## PHASE 7: "Production Polish" (v3.0)

### Task 7.1: Error handling sweep
**File**: `companion_app/lib/main.dart`
- Add try/catch with user-friendly messages to every API call
- Add 10-second timeout to all HTTP requests
- Handle no internet gracefully (show "No connection" with retry)

### Task 7.2: Loading states
**File**: `companion_app/lib/main.dart`
- All list screens: show loading indicator while fetching
- All form submissions: disable button + show spinner during submit

### Task 7.3: Input validation
**File**: `companion_app/lib/main.dart`
- LoginScreen: validate email format
- RegisterScreen: required fields, positive numbers
- HealthLogScreen: positive numbers for numeric fields

### Task 7.4: API rate limiting
**File**: `web_app/controllers.py`
- Simple in-memory rate limiter: max 30 requests/minute per token
- Apply to upload/analysis endpoints only
- Return 429 when exceeded

### Task 7.5: Database indexes
**File**: `web_app/models.py`
- Add indexes on frequently queried columns:
  - `muscle_scan.customer_id`, `muscle_scan.scan_date`, `muscle_scan.muscle_group`
  - `health_log.customer_id`, `health_log.log_date`
  - `symmetry_assessment.customer_id`

### Task 7.6: Version bump to v3.0
**Files**: `muscle_tracker.py` (line 3), `core/report_generator.py` (line 299), `setup.py`

### Task 7.7: Final commit + Review Gate
- Run tests, commit: `"feat: production polish, rate limiting, indexes, v3.0"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`
- If CONTINUE → you're done. Report the final project state.

---

## STRICT Rules (ALL phases)

1. **NO human in the loop.** Execute phases continuously. Only stop if: tokens exhausted, review gate says STOP, or all phases complete.
2. **NO proposal documents.** No `CLAUDE_UPGRADE_PROPOSAL_*.md`. No strategy files. No research. CODE ONLY.
3. **NO features outside the current phase.**
4. **Run tests before every commit.** All must pass.
5. **Protected files — DO NOT MODIFY**: `core/auth.py`, `core/pose_analyzer.py`, `web_app/controllers.py` (except Tasks 4.3 and 7.4 which explicitly name it), `tests/test_auth.py`, `tests/test_vision_medical.py`, `tests/test_progress.py`, `tests/test_pose.py`, `tests/test_pose_correction.py`
6. **After each commit, run the review gate** (`bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`) and follow its instructions.
7. **If review gate is unavailable**, self-check: tests pass + git status clean + no protected files touched → proceed.
8. **When all 7 phases are done or tokens are exhausted, write a final status** to `GEMINI_STATUS.md` with: phases completed, test count, files changed, any issues.
