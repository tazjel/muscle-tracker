# Sonnet Task List — Muscle Tracker v6.0
## Updated: 2026-03-16 | Informed by real device testing & git history

> **Role**: Integration engineer, quality enforcer, bug fixer, feature wiring
> **Context**: Most Phase A–D code has been written. **Nothing has been verified working end-to-end on the actual device.** The #1 priority is making existing code work, not writing more.

---

## STATUS: What's Done vs. What's Broken

### Code Written (committed, but NOT verified on device)
| Area | Status | Commits |
|------|--------|---------|
| Scan pipeline (circumference, definition, overlay) | ✅ Written | `77d043e` |
| Body composition endpoint | ✅ Written | `b10c106` |
| 3D mesh API (reconstruct, compare, serve OBJ) | ✅ Written | `b10c106` |
| Dashboard API (body_map, quick_stats, progress_summary) | ✅ Written | `b10c106` |
| Live camera endpoint + Flutter LivePreviewScreen | ✅ Written | `b10c106` |
| Session report endpoint | ✅ Written | `b10c106` |
| Export endpoint (CSV/JSON) | ✅ Written | `b10c106` |
| CLI commands (circumference, body-comp, definition) | ✅ Written | `1f5b077` |
| Unified `core/pipeline.py` | ✅ Written | `b10c106` |
| PROFILE mode (Auto Mode 2) with screen lock | ✅ Written | `0418899` |
| 196 tests passing | ✅ Verified | All green |

### NOT Working / NOT Verified
| Issue | Severity | Evidence |
|-------|----------|----------|
| **No scan has EVER shown results on phone** | 🔴 CRITICAL | History screen always "No data found" |
| **PROFILE mode crashes at ~70% upload** | 🔴 HIGH | 20-image multipart times out at 60s |
| **PROFILE coverage always low** | 🟡 MEDIUM | Samsung A24 magnetometer unreliable |
| **PROFILE progress not cumulative** | 🟡 MEDIUM | Each 20s session analyzed in isolation |
| **ResultsScreen may crash or show empty** | 🔴 HIGH | Never tested with real server response |
| **AI Coach module doesn't exist** | ⚪ NOT STARTED | `core/ai_coach.py` is MISSING |
| **report_generator.py has uncommitted changes** | 🟡 MEDIUM | +113 lines in git diff |

---

## PHASE 0: MAKE IT WORK (Do This First — Nothing Else Matters)

> **Goal**: ONE successful scan → results visible on phone. Without this, the app has zero value.

### S-0.1 — Verify Scan Pipeline End-to-End 🔴 CRITICAL
**Type**: Debug / Integration test
**Steps**:
1. Start server: `py4web run apps --host 0.0.0.0 --port 8000`
2. Deploy app: `python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py deploy muscle-debug`
3. Select QUADRICEP → PHOTO mode → take front + side → confirm → check ResultsScreen
4. If ResultsScreen crashes or shows nothing:
   - Check `server.log` for Python tracebacks
   - Check `_process_and_save_scan()` in `controllers.py` (grep for it — line ~159-420)
   - Common failures: URL mismatch, JWT expired, muscle group name validation, cv2 import error
5. Check HistoryScreen loads saved scan

**Files to debug**: `web_app/controllers.py` (upload_scan → _process_and_save_scan), `companion_app/lib/main.dart` (ResultsScreen ~line 826)
**Success**: Photo taken → metrics shown on phone → scan appears in History

### S-0.2 — Fix ResultsScreen Data Binding
**Type**: Bug fix
**File**: `companion_app/lib/main.dart` (~line 826-1024)
**Problem**: ResultsScreen reads from a `result` map returned by the server. If the server response structure doesn't match what the Flutter code expects, the screen shows nothing or crashes.
**Fix**:
1. Grep for `result[` and `result['` in ResultsScreen to see what keys it expects
2. Grep for `return dict(` in `upload_scan` endpoint to see what keys the server sends
3. Make them match — either fix server response or fix Flutter parsing
4. Add null-safety: if a key is missing, show "N/A" instead of crashing

**Test**: Deploy, scan, confirm all metric cards show data (even if values seem wrong — showing SOMETHING is the goal)

### S-0.3 — Fix PROFILE Mode Upload Crash 🔴 HIGH
**Type**: Bug fix
**File**: `companion_app/lib/main.dart` (~line 467-570)
**Problem**: 20-image multipart upload times out at 60s over WiFi
**Fix** (pick one or both):
1. Change burst interval from 1s to 2s in `_startProfileCapture()` → only 10 images
2. Increase upload timeout from 60s to 120s in `_finishProfileCapture()`
3. Compress images before upload (quality: 70 instead of 100)

**Test**: PROFILE mode → 20 seconds → upload completes → ProfileProgressScreen shows zone coverage

---

## PHASE 1: MAKE IT RELIABLE (Fix known bugs before new features)

### S-1.1 — PROFILE Magnetometer Fallback
**Type**: Bug fix
**File**: `core/session_analyzer.py`
**Problem**: Samsung A24 magnetometer gives unreliable compass headings → all frames map to same zone → coverage stays low
**Fix**: In `analyze_session()`, if all compass readings are 0/None/identical, distribute frames evenly across zones based on frame order (assume user is slowly rotating)
**Test**: Run session_analyzer with mock data where compass=0 → should still give ~50% coverage credit

### S-1.2 — PROFILE Cumulative Progress
**Type**: Feature fix
**File**: `web_app/controllers.py` (upload_session endpoint, ~line 1589)
**Problem**: Each 20s PROFILE session is analyzed independently. Previous coverage is lost.
**Fix**:
1. In `upload_session`: before analyzing, load all previous session logs for this customer + muscle_group
2. Merge `covered_zones` from previous sessions with current session
3. Return cumulative coverage % so progress builds toward 100% over multiple runs
**Test**: Upload 3 sessions → coverage should accumulate, not reset each time

### S-1.3 — Commit Uncommitted report_generator.py Changes
**Type**: Housekeeping
**File**: `core/report_generator.py` (+113 lines uncommitted)
**Action**: Review the changes, run tests, commit if clean

---

## PHASE 2: POLISH RESULTS DISPLAY (User sees value)

### S-2.1 — Rich ResultsScreen in Flutter
**Type**: Enhancement
**File**: `companion_app/lib/main.dart` (ResultsScreen ~line 826)
**Show all available metrics from server response**:
- Volume (cm³) with icon
- Circumference (cm / inches)
- Definition score + letter grade (S/A/B/C/D/F) with color coding
- Shape score with star rating
- Growth % vs previous scan (if exists)
- "View Annotated Photo" button → opens `annotated_img_url`
- "View Report" button → opens PDF report endpoint
**Key**: Only show cards for metrics that are non-null in the response. Don't crash on missing data.

### S-2.2 — HistoryScreen Improvements
**Type**: Enhancement
**File**: `companion_app/lib/main.dart` (HistoryScreen ~line 1141)
**Current state**: Shows list or "No data found"
**Improvements**:
- Show scan thumbnail + date + muscle group + key metric (volume or circumference)
- Tap to open full ResultsScreen for that scan
- Pull-to-refresh
- Filter by muscle group dropdown

### S-2.3 — Dashboard Login Flow
**Type**: Bug fix
**Files**: `web_app/static/personal/app.js`, `web_app/controllers.py`
**Problem**: Personal dashboard runs in demo mode because auth flow is incomplete
**Fix**: Ensure `POST /api/auth/token` returns `customer_id` alongside the JWT, and `app.js` stores and uses it for all subsequent API calls instead of hardcoded demo data

---

## PHASE 3: AI COACH (New Feature — Claude API)

### S-3.1 — Create `core/ai_coach.py` ⚪ NOT STARTED
**Type**: New module
**File**: New `core/ai_coach.py`
**Feature**: Use Anthropic Claude API to generate personalized advice from scan data
```python
from anthropic import Anthropic

def generate_training_recommendations(scan_history, body_composition=None, symmetry_data=None):
    """
    Build structured prompt from scan metrics → call claude-sonnet-4-6 → return:
    {
        'priority_muscles': ['left_bicep', 'hamstring'],
        'recommended_exercises': [{'muscle': 'bicep', 'exercise': 'Hammer Curl', 'sets': '4x8', 'reason': '...'}],
        'symmetry_fix': '...',
        'weekly_goal': '...',
        'summary': '3-sentence plain English interpretation'
    }
    """

def interpret_scan_result(scan_metrics, previous_scan=None):
    """
    Generate 2-3 sentence natural language summary of what a scan means.
    E.g.: "Your left bicep grew 3.2% this week — excellent progress.
           Definition dropped slightly, suggesting muscle growth with water retention."
    """
```
**Dependencies**: `pip install anthropic` (or make it optional with try/except)
**Test**: `tests/test_ai_coach.py` with mocked API responses

### S-3.2 — Wire AI Coach into API
**Type**: Integration
**File**: `web_app/controllers.py`
**Add endpoint**:
```
GET /api/customer/<customer_id>/recommendations
  → Fetch last 30 days of scans + body comp + symmetry
  → Call ai_coach.generate_training_recommendations()
  → Return JSON
```
**Also**: Add `interpret_scan_result()` call to `_process_and_save_scan()` → include `ai_interpretation` text in scan result JSON

### S-3.3 — Progress Insight Alerts
**Type**: Enhancement
**File**: `web_app/controllers.py` (quick_stats endpoint, ~line 1210)
**Add `alerts` array** to quick_stats response, detecting:
- New personal best (volume, circumference, definition)
- Symmetry imbalance > 10%
- Growth streak (5+ improving scans)
- Plateau (3+ scans with < 0.5% change)
- Body fat trend reversal

---

## PHASE 4: ENHANCED REPORTING

### S-4.1 — Comprehensive PDF Report
**Type**: Enhancement
**File**: `core/report_generator.py`
**Add sections** to `generate_clinical_report()`:
- Measurement overlay image (from `annotated_img`)
- Circumference estimate
- Definition score with grade
- Body composition section (if available)
- 3D mesh wireframe preview (if mesh data exists)
- AI interpretation text (if ai_coach available)
- Mini body map thumbnail (if multi-muscle data)

### S-4.2 — 3D Preview in PDF
**Type**: Enhancement
**File**: `core/report_generator.py`
**If** mesh data exists for a scan, embed `mesh_reconstruction.generate_mesh_preview_image()` wireframe

---

## PHASE 5: BUSINESS FOUNDATIONS (v6.0 — only if customer funds it)

### S-5.1 — Multi-Tenant Architecture
**Files**: `web_app/models.py`, `web_app/controllers.py`
- Add `clinic` table (name, logo, subdomain, settings)
- Role expansion: `superadmin`, `clinic_admin`, `trainer`, `athlete`
- Row-level isolation: scope all queries by `clinic_id`

### S-5.2 — Trainer Dashboard
**Files**: New `web_app/static/trainer/`
- Patient list with most recent metrics
- Side-by-side multi-patient comparison
- Bulk report generation
- Alert feed for concerning trends

### S-5.3 — Cloud Deployment Prep
**Files**: New `deploy/`, `Dockerfile`
- Cloud Run config (auto-scaling)
- Cloud Storage for images (replace local uploads/)
- Cloud SQL adapter (replace SQLite)
- Async vision processing queue

---

## TASK PRIORITY ORDER

| Rank | Task | Type | Why | Time Est |
|------|------|------|-----|----------|
| **1** | **S-0.1** | Debug | **Nothing works without this** — verify scan pipeline | 2-4 hrs |
| **2** | **S-0.2** | Bug fix | ResultsScreen must show data | 1-2 hrs |
| **3** | **S-0.3** | Bug fix | PROFILE mode is the flagship feature | 1 hr |
| **4** | **S-1.1** | Bug fix | Magnetometer fallback for Samsung A24 | 1 hr |
| **5** | **S-1.2** | Feature | Cumulative PROFILE progress | 2 hrs |
| **6** | **S-1.3** | Housekeeping | Commit report_generator changes | 15 min |
| **7** | **S-2.1** | Enhancement | Rich ResultsScreen — customer sees value | 2-3 hrs |
| **8** | **S-2.2** | Enhancement | HistoryScreen shows real data | 2 hrs |
| **9** | **S-2.3** | Bug fix | Dashboard exits demo mode | 1 hr |
| **10** | **S-3.1** | New feature | AI Coach module | 3-4 hrs |
| **11** | **S-3.2** | Integration | Wire AI Coach into API | 1 hr |
| **12** | **S-3.3** | Enhancement | Progress alerts | 2 hrs |
| **13** | **S-4.1** | Enhancement | Rich PDF report | 3 hrs |
| **14** | **S-4.2** | Enhancement | 3D in PDF | 1 hr |
| 15+ | Phase 5 | Business | Only if funded | Days |

---

## RULES FOR SONNET

### Token Budget (MANDATORY)
- **Do NOT read `main.dart` or `controllers.py` in full** — use Grep to find the exact function
- **Do NOT run `flutter analyze`** — never
- **Do NOT explore sibling projects** (baloot-ai, GTDdebug, tazjel)
- **Do NOT add features beyond what is asked**
- **Run tests after every change**: `C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -q`
- **Stop if tests drop below 196** — you broke something, fix it
- **One task at a time** — finish it, test it, commit it, move on

### File Ownership
- **Sonnet owns**: `controllers.py`, `models.py`, `muscle_tracker.py`, `report_generator.py`, `companion_app/`
- **Gemini owns**: `core/*.py` (vision modules) — import from them, do NOT rewrite them
- Exception: `core/ai_coach.py` is Sonnet's to create (it doesn't exist yet)

### Key Patterns
```python
# Adding a py4web endpoint
@action('api/customer/<customer_id>/my_endpoint', method=['POST'])
@action.uses(db, auth)
def my_endpoint(customer_id):
    require_auth()  # JWT check — always call this
    data = request.json or {}
    return dict(status='ok', result={})

# DB column (py4web auto-migrates — no migration files needed)
Field('new_column', 'double'),
```

### Deploy & Test on Device
```bash
# Start server
cd C:/Users/MiEXCITE/Projects/muscle_tracker
py4web run apps --host 0.0.0.0 --port 8000

# Deploy to phone (WiFi ADB at 192.168.100.8:5555)
python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py deploy muscle-debug

# Screenshot phone
python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py screen

# Check crash log
python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py crash muscle-debug

# Check server health
curl -s http://localhost:8000/web_app/api/health
```

### Git Workflow
```bash
git add web_app/controllers.py web_app/models.py
git commit -m "feat|fix|test(scope): short description (S-X.Y)"
```

### Valid Muscle Group Names
`bicep`, `tricep`, `quadricep`, `hamstring`, `calf`, `glute`, `deltoid`, `lat`, `forearm`, `chest`
(Server rejects old names like `quad`, `delt`)

---

## KEY LINE NUMBERS (as of commit 0418899)

### `companion_app/lib/main.dart`
| Feature | Line |
|---------|------|
| AppConfig.serverBaseUrl | ~18 |
| CameraLevelScreen state | ~210-250 |
| _captureImage() | ~295 |
| _uploadScan() | ~318 |
| _startAutoCapture() | ~365 |
| _startProfileCapture() | ~467 |
| _finishProfileCapture() | ~510 |
| ResultsScreen | ~826 |
| ProfileProgressScreen | ~1025 |
| HistoryScreen | ~1141 |
| LivePreviewScreen | ~1394 |

### `web_app/controllers.py`
| Endpoint | Line |
|----------|------|
| upload_scan | ~159 |
| upload_video | ~224 |
| customer scans | ~427 |
| report | ~458 |
| progress | ~578 |
| body_composition | ~884 |
| reconstruct_3d | ~980 |
| body_map | ~1168 |
| quick_stats | ~1210 |
| live_analyze | ~1522 |
| upload_session (PROFILE) | ~1589 |
| profile_status | ~1698 |

---

## SUCCESS CRITERIA

| Phase | Customer Can Say |
|-------|-----------------|
| Phase 0 | "I took a photo and it showed me my muscle measurements!" |
| Phase 1 | "PROFILE mode works reliably and remembers my progress" |
| Phase 2 | "I can see my history and track my gains over time" |
| Phase 3 | "It tells me which muscles to focus on and what exercises to do" |
| Phase 4 | "I can download a professional PDF report of my scan" |
| Phase 5 | "My trainer can see all my clients' progress in one dashboard" |
