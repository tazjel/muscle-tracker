# Muscle Tracker — Upgrade Plan: v5.0 → v6.0
**Created**: 2026-03-15 | **Model**: Claude Opus
**Objective**: Maximize capability delivery to impress the paying customer and build toward the business version

---

## CURRENT STATUS (v5.0 — All Done)

✅ 181/181 tests passing
✅ Full vision pipeline: contour extraction, shape scoring, definition, body composition
✅ 3D mesh reconstruction + Three.js viewer
✅ Personal dashboard (body map, charts, scan cards)
✅ Video analyzer + comprehensive session report PDF
✅ JWT-secured REST API (23 endpoints)
✅ Flutter companion app

**One gap**: The new `core/*.py` modules (body composition, definition scorer, measurement overlay, circumference, video analyzer, session report) exist but are NOT yet wired into the API, CLI, or Flutter app. The customer cannot access them yet.

---

## PHASE A — CONNECT (v5.1) — Priority 1
**Theme**: Make everything that was built actually usable. No new features yet — just wire existing modules end-to-end.
**Customer impact**: Every scan now returns 6× more data automatically.
**Effort**: ~3 days

### A-1 — Complete Scan Pipeline Integration
**File**: `web_app/controllers.py`, `web_app/models.py`

Add to `_process_and_save_scan()`:
1. Call `circumference.estimate_circumference()` → store `circumference_cm` in DB
2. Call `definition_scorer.score_muscle_definition()` → store `definition_score`, `definition_grade`
3. Call `measurement_overlay.draw_measurement_overlay()` → save `{scan_id}_annotated.png`
4. Include all new fields in scan result JSON response

DB columns to add in `models.py`:
```python
Field('circumference_cm', 'double'),
Field('definition_score', 'double'),
Field('definition_grade', 'string', length=16),
Field('annotated_img', 'string', length=256),
```

**Test**: Run existing test suite. Add `test_scan_pipeline_integration.py`.

---

### A-2 — Body Composition API Endpoint
**File**: `web_app/controllers.py`

```
POST /api/customer/<customer_id>/body_composition
  Body: { image (file), weight_kg, height_cm, gender }
  → segment body → extract landmarks → estimate_body_composition()
  → save annotated visual
  → return: { bmi, body_fat_pct, lean_mass_kg, waist_hip_ratio, classification, confidence, visual_url }
```

DB columns to add:
```python
Field('body_fat_pct', 'double'),
Field('lean_mass_kg', 'double'),
Field('waist_hip_ratio', 'double'),
```

---

### A-3 — 3D Mesh API Endpoints
**File**: `web_app/controllers.py`

```
POST /api/customer/<customer_id>/reconstruct_3d
  Body: { front_image (file), side_image (file) }
  → reconstruct_mesh_from_silhouettes()
  → save OBJ file + preview PNG
  → return: { mesh_url, preview_url, volume_cm3, num_vertices, num_faces }

GET  /api/scan/<scan_id>/mesh.obj         → serve OBJ for Three.js viewer
POST /api/customer/<customer_id>/compare_3d
  Body: { scan_id_before, scan_id_after }
  → compare_meshes() → colored displacement OBJ
  → return: { displacement_stats, colored_mesh_url }
```

---

### A-4 — Dashboard API Endpoints
**File**: `web_app/controllers.py`

The personal dashboard at `/static/personal/` currently works in demo mode only. Add:

```
GET /api/customer/<customer_id>/body_map
  → latest scan per muscle group, all metrics
  → return: [ { muscle_group, shape_score, volume_cm3, growth_pct, definition_grade, circumference_cm } ]

GET /api/customer/<customer_id>/quick_stats
  → return: { total_scans, active_groups, best_growth_pct, days_active, current_streak, avg_definition_score }

GET /api/customer/<customer_id>/progress_summary
  → all scans sorted by date with all metrics
  → includes circumference_cm, definition_score, volume_cm3 per scan
```

---

### A-5 — CLI Commands for New Features
**File**: `muscle_tracker.py`

```bash
python muscle_tracker.py circumference --image arm.jpg [--marker-size 20.0]
python muscle_tracker.py body-composition --image body.jpg --weight 80 --height 180 --gender male
python muscle_tracker.py definition --image bicep.jpg --muscle-group bicep
python muscle_tracker.py reconstruct-3d --front front.jpg --side side.jpg --output arm.obj
python muscle_tracker.py session-report --image scan.jpg --weight 80 --height 180 --output report.pdf
```

---

### A-6 — Flutter App: Display New Metrics
**File**: `companion_app/lib/main.dart`

After scan upload, show additional cards:
- Circumference reading with tape-measure icon
- Definition score + grade bar
- "View Annotated Photo" button (opens `annotated_img_url`)
- "View in 3D" button (launches Three.js viewer URL in webview)

---

## PHASE B — ENHANCE (v5.5) — Priority 2
**Theme**: Make the existing features significantly better. Bigger measurements, smarter analysis.
**Customer impact**: Numbers become more accurate, charts become richer.
**Effort**: ~4 days

### B-1 — Unified Pipeline Function
**File**: New `core/pipeline.py`

Single orchestrator that replaces 8 manual function calls in the controller:
```python
def full_scan_pipeline(image_front, image_side=None, image_before=None,
                       user_weight_kg=None, user_height_cm=None, gender='male',
                       muscle_group=None):
    """
    Steps: calibrate → segment → classify → extract contours → circumference
           → shape score → definition → volume (2D or 3D) → compare → body_comp
           → overlays → session report
    Returns comprehensive result dict with all metrics + image paths.
    """
```

Why: Eliminates code duplication between API and CLI. Makes testing easier.

---

### B-2 — Accurate 3D Volume from Mesh
**File**: New `core/mesh_volume.py`

Compute volume via the divergence theorem over mesh faces — more accurate than the 2D slice estimate. When both front+side images are available, `pipeline.py` uses this instead of `volumetrics.py`.

```python
def compute_mesh_volume(vertices, faces):
    """Signed volume via divergence theorem. Returns float cm³."""
```

---

### B-3 — Enhanced PDF Report (Comprehensive)
**File**: `core/report_generator.py`

Add to `generate_clinical_report()`:
- Measurement overlay image embedded (from `annotated_img`)
- Circumference estimate section
- Definition score with heatmap image (from `definition_scorer`)
- Body composition section (if full-body shot)
- 3D mesh wireframe preview (if mesh data exists)
- Mini body map thumbnail (if multi-muscle data exists)

Also enhance `core/session_report.py` to include progress trend chart (inline matplotlib figure).

---

### B-4 — Scan History Export
**File**: `web_app/controllers.py`

```
GET /api/customer/<customer_id>/export?format=csv
GET /api/customer/<customer_id>/export?format=json
  → All scan data: date, muscle, volume, circumference, shape_score, definition_score, growth_pct, body_fat_pct
  → CSV suitable for Google Sheets / Excel import
```

---

### B-5 — Progress API Enhancement
**File**: `web_app/controllers.py` — modify progress endpoint

Add to existing `/api/customer/<id>/progress` response:
- `circumference_trend`: list of `{date, muscle_group, circumference_cm}`
- `definition_trend`: list of `{date, muscle_group, definition_score}`
- `body_composition_trend`: list of `{date, body_fat_pct, lean_mass_kg}`
- `regression_projections`: extend existing linear projection to include circumference

---

### B-6 — Multi-Metric Progress Charts in Dashboard
**File**: `web_app/static/personal/app.js`, `style.css`

Dashboard currently shows 3 chart tabs (volume/circumference/shape). Add:
- **Definition** tab (definition_score over time)
- **Body Fat** tab (body_fat_pct trend if available)
- **Overlay mode**: show two metrics on same chart (e.g., volume + circumference)
- **Prediction line**: dashed line showing regression projection forward 30 days

---

## PHASE C — AI-POWERED COACH (v5.8) — Priority 3
**Theme**: Add intelligent recommendations using Claude API. Transform raw data into actionable advice.
**Customer impact**: "It knows what I should do next."
**Effort**: ~3 days

### C-1 — AI Training Recommendations
**File**: New `core/ai_coach.py`

Uses Anthropic Claude API to generate personalized recommendations:
```python
from anthropic import Anthropic

def generate_training_recommendations(scan_history, body_composition, symmetry_data):
    """
    Build a prompt from scan data → call Claude claude-sonnet-4-6 → return structured advice.

    Output: {
        'priority_muscles': ['left_bicep', 'hamstring'],
        'recommended_exercises': [{'muscle': 'bicep', 'exercise': 'Hammer Curl', 'sets': '4x8', 'reason': '...'}],
        'symmetry_fix': '...',
        'bf_recommendation': '...',
        'weekly_goal': '...',
    }
    """
```

API endpoint:
```
GET /api/customer/<customer_id>/recommendations
  → Fetch last 30 days of scans + body comp
  → Call ai_coach.generate_training_recommendations()
  → Return JSON with exercises, priorities, goals
```

---

### C-2 — AI Scan Interpretation
**File**: `core/ai_coach.py`

```python
def interpret_scan_result(scan_metrics, previous_scan=None, user_profile=None):
    """
    Generate a 3-sentence natural language summary of what the scan means:
    "Your left bicep grew 3.2% this week — excellent progress.
     Definition score dropped from 68 to 61, suggesting increased muscle size with slight water retention.
     Focus on full contractions and reduce sodium before your next scan."
    """
```

Include interpretation text in:
- PDF session report (new "AI Analysis" section)
- Flutter scan result screen
- Dashboard scan detail modal

---

### C-3 — Progress Insight Alerts
**File**: `web_app/controllers.py`, `core/ai_coach.py`

Detect and surface notable events automatically:
- New personal best (volume, circumference, definition)
- Symmetry imbalance exceeding threshold (>10%)
- Consistent growth streak (5+ scans improving)
- Plateau detection (3+ scans with <0.5% change)
- Body fat trend reversal

Return as `alerts` array in `quick_stats` endpoint.

---

## PHASE D — REAL-TIME & LIVE CAMERA (v5.9) — Priority 4
**Theme**: Move from upload-only to live camera analysis.
**Customer impact**: "I can see my measurements in real time."
**Effort**: ~4 days

### D-1 — Live Webcam Analysis (Web)
**File**: New `web_app/static/live/index.html`, `live.js`

Browser-based live camera page:
1. Access `getUserMedia()` camera stream
2. Send frames to `POST /api/live_analyze` every 500ms
3. Display: live contour overlay on video feed, real-time circumference reading, shape score updating

Server endpoint:
```
POST /api/live_analyze
  Body: { frame_base64, muscle_group }
  → Fast path: skip volume/3D, just contour + circumference + shape
  → Return: { contour_points, circumference_cm, shape_score, landmarks }
  → Target: <200ms response time
```

---

### D-2 — Flutter Live Preview Mode
**File**: `companion_app/lib/main.dart`

Add "Live Measure" button to Flutter app:
- Streams camera frames to `/api/live_analyze`
- Overlays contour outline on live camera feed
- Shows live circumference reading updating in real time
- "Lock & Save" button to capture best frame as a proper scan

---

### D-3 — Pose Quality HUD Enhancement
**File**: `companion_app/lib/main.dart`

Upgrade the existing pose overlay in Flutter:
- Add real-time MediaPipe pose landmark overlay (if available)
- Green/red skeleton joints (good pose = green, adjustment needed = red)
- On-screen guidance text: "Flex harder", "Rotate left 10°", "Step back"
- Auto-capture when pose quality score > threshold

---

## PHASE E — BUSINESS FEATURES (v6.0) — Priority 5
**Theme**: Unlock the multi-user business version if the customer funds it.
**Customer impact**: Enables selling to clinics/gyms, not just personal use.
**Effort**: ~7 days (full sprint)

### E-1 — Multi-Tenant Architecture
**Files**: `web_app/models.py`, `web_app/controllers.py`

Add:
- `clinic` table (name, logo, subdomain, settings)
- `User` role expansion: `superadmin`, `clinic_admin`, `trainer`, `athlete`
- Row-level isolation: all queries scoped to `clinic_id`
- Clinic branding: logo + color theme in reports/dashboard

### E-2 — Trainer ↔ Athlete Relationship
**Files**: New `web_app/static/trainer/` dashboard

Trainer view:
- Patient list with most recent metrics per patient
- Side-by-side multi-patient body map comparison
- Bulk report generation (all patients in date range)
- Alert feed: "Patient John's symmetry imbalance increased to 14%"

### E-3 — Stripe Billing Integration
**Files**: New `core/billing.py`, webhook handler

- Per-scan pricing OR monthly subscription tiers
- Clinic admin dashboard with usage/invoice view
- Trial period (50 scans free) → paid tier

### E-4 — Cloud Deployment (GCP)
**Files**: New `deploy/`, `Dockerfile` updates

- Cloud Run for API (auto-scaling)
- Cloud Storage for scan images/meshes/PDFs (replace local filesystem)
- Cloud SQL for database (replace local SQLite)
- Background jobs via Cloud Tasks (async CV processing)
- CDN for static assets

### E-5 — HIPAA Compliance Foundation
**Files**: `web_app/models.py`, `web_app/controllers.py`

- Encrypt PII fields at rest (AES-256)
- Audit log table (who accessed which patient, when)
- Data retention policy (configurable auto-delete)
- Consent tracking per patient

---

## IMMEDIATE QUICK WINS (Do This Week)

These are small improvements with high visibility — do these before starting Phase A:

| # | Task | File | Time | Impact |
|---|------|------|------|--------|
| QW-1 | Add `definition_score` column to personal dashboard scan cards | `app.js` | 30min | Customer sees new metric immediately |
| QW-2 | Wire session_report into `POST /api/customer/<id>/session_report` endpoint | `controllers.py` | 1hr | Full PDF from one API call |
| QW-3 | Add "Download Report" button to personal dashboard | `index.html` | 20min | Customer can download PDF from browser |
| QW-4 | Fix personal dashboard login: add `POST /api/auth/login` endpoint that returns JWT + customer_id | `controllers.py` | 1hr | Dashboard stops showing demo mode for real users |
| QW-5 | Add `GET /api/customer/<id>/scans` — if missing, dashboard can't load real data | `controllers.py` | 30min | Connects demo mode → real data |

---

## SUMMARY: PRIORITY ORDER

| Phase | Name | Days | Unlock |
|-------|------|------|--------|
| Quick Wins | Immediate polish | 3 | Dashboard works end-to-end |
| **A — Connect** | Wire existing modules into API/CLI/Flutter | 3 | Customer accesses all v5 features |
| **B — Enhance** | Pipeline unification, better PDF, export | 4 | Richer data, download everything |
| **C — AI Coach** | Claude API recommendations + scan interpretation | 3 | "It tells me what to do" |
| **D — Live Camera** | Real-time webcam + Flutter live preview | 4 | "I see my measurements live" |
| **E — Business** | Multi-tenant, billing, cloud, HIPAA | 7 | Sell to clinics/gyms |

**Total to impress the customer (A+B+C)**: ~10 days
**Total for business version (A+B+C+D+E)**: ~21 days

---

## TECHNICAL DEBT TO CLEAN (Background)

These don't add features but prevent bugs and make future work easier:

| Item | File | Fix |
|------|------|-----|
| Navy formula uses cm, not inches | `core/body_composition.py` | The formula specification uses inches. Current code uses cm. Validate with real measurements. |
| MediaPipe fallback silently disables body comp API | `core/body_segmentation.py` | Add explicit warning in API response when running without MediaPipe |
| `web_app/models.py` using SQLite | `models.py` | Fine for now, but add PostgreSQL adapter prep for cloud deployment |
| No request-level error logging | `controllers.py` | Add structured error logging to `logger.error()` with scan_id context |
| Personal dashboard auth flow incomplete | `app.js`, `controllers.py` | `mt_token` + `mt_customer_id` are stored but login endpoint doesn't exist |

---

## NEW FILES TO CREATE

```
# Phase A
web_app/controllers.py          (modify — add 8 new endpoints)
web_app/models.py                (modify — add 6 new columns)
muscle_tracker.py                (modify — add 5 CLI commands)
companion_app/lib/main.dart      (modify — new metrics display)
tests/test_scan_pipeline_integration.py   (new)

# Phase B
core/pipeline.py                 (new — unified pipeline function)
core/mesh_volume.py              (new — divergence theorem volume)
tests/test_pipeline.py           (new)

# Phase C
core/ai_coach.py                 (new — Claude API integration)
tests/test_ai_coach.py           (new — mock Claude responses)

# Phase D
web_app/static/live/index.html   (new — webcam live analysis page)
web_app/static/live/live.js      (new)
web_app/static/live/live.css     (new)

# Phase E
core/billing.py                  (new — Stripe integration)
deploy/cloud-run/                (new — GCP deployment config)
deploy/docker-compose.prod.yml   (new — production compose)
```

---

## SUCCESS CRITERIA PER PHASE

| Phase | Customer Can Say: |
|-------|-----------------|
| Quick Wins | "I can log in to my dashboard and see all my scans" |
| A — Connect | "Every scan gives me circumference, definition score, and body fat automatically" |
| B — Enhance | "I can download all my data as a spreadsheet. My PDF has everything in it." |
| C — AI Coach | "It analyzed my last 10 scans and told me I need to work on my left hamstring" |
| D — Live Camera | "I hold my phone up and it shows my measurements in real time" |
| E — Business | "I can sign up my 5 trainers and 50 clients" |
