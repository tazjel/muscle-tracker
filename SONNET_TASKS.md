# Sonnet Task List — Muscle Tracker v5.0 Integration & Enhancement

> **Role**: Integration engineer, quality enforcer, advanced features
> **Context**: Gemini writes standalone `core/*.py` modules. Sonnet wires them into the API, CLI, reports, and Flutter app — making them usable end-to-end.
> **Priority**: Run these AFTER Gemini has committed each phase's modules.

---

## PHASE 0: QUALITY FIXES (Run Now — Before Gemini Continues)

### S-0.1 — Fix Mission 1.1 Measurement Overlay (Arrow Heads)
**File**: `core/measurement_overlay.py`
**Problem**: Width/height dimension lines have no arrowheads. Spec required arrow-headed dimension lines like engineering drawings.
**Fix**:
- Add `_draw_arrow_line(img, pt1, pt2, color, thickness)` helper that draws a line with triangular arrowheads at both ends
- Replace `cv2.line` calls for width/height dimension lines with the arrow version
- Use `cv2.fillPoly` for arrowhead triangles (6px wide, 10px long)
**Test**: Existing `tests/test_measurement_overlay.py` should still pass

### S-0.2 — Commit Pre-Written Test Files
**Action**: Stage and commit all 8 test files written by Sonnet as a single commit
```
git add tests/test_body_composition.py tests/test_definition_scorer.py \
       tests/test_mesh_reconstruction.py tests/test_mesh_comparison.py \
       tests/test_body_map.py tests/test_timelapse.py \
       tests/test_video_analyzer.py tests/test_session_report.py
git commit -m "test: add TDD test suite for v5 missions 1.3-4.2"
```

---

## PHASE 1: API INTEGRATION (After Gemini Completes Phase 1 Missions)

### S-1.1 — Wire Body Composition into API
**File**: `web_app/controllers.py`
**Add endpoint**:
```python
POST /api/customer/<customer_id>/body_composition
```
- Accept: `image` (file upload) + optional JSON body: `weight_kg`, `height_cm`, `gender`
- Pipeline: `body_segmentation.segment()` → get landmarks → `body_composition.estimate_body_composition()` → return JSON
- Also call `generate_composition_visual()` and save annotated image
**DB**: Add `body_fat_pct`, `lean_mass_kg`, `waist_hip_ratio` columns to `muscle_scan` table

### S-1.2 — Wire Circumference into Scan Pipeline
**File**: `web_app/controllers.py` — modify `_process_and_save_scan()`
**Change**: After volume estimation, also call `circumference.estimate_circumference()` and store result
**DB**: Add `circumference_cm` column to `muscle_scan` table
**API response**: Include `circumference_cm` and `circumference_inches` in scan result JSON

### S-1.3 — Wire Definition Scorer into Scan Pipeline
**File**: `web_app/controllers.py` — modify `_process_and_save_scan()`
**Change**: After shape scoring, call `definition_scorer.score_muscle_definition()` and store result
**DB**: Add `definition_score`, `definition_grade` columns to `muscle_scan` table

### S-1.4 — Wire Measurement Overlay into Scan Pipeline
**File**: `web_app/controllers.py` — modify `_process_and_save_scan()`
**Change**: After all analysis, call `measurement_overlay.draw_measurement_overlay()` and save annotated image alongside original
**Storage**: Save as `{scan_id}_annotated.png` in uploads/

### S-1.5 — Add CLI Commands for New Features
**File**: `muscle_tracker.py`
**Add commands**:
```
muscle_tracker.py circumference --image <img> [--marker-size 20.0] [--method elliptical|perimeter]
muscle_tracker.py body-composition --image <img> [--weight 80] [--height 180] [--gender male]
muscle_tracker.py definition --image <img> [--muscle-group bicep]
```

---

## PHASE 2: 3D INTEGRATION (After Gemini Completes Phase 2 Missions)

### S-2.1 — Wire 3D Mesh into API
**File**: `web_app/controllers.py`
**Add endpoints**:
```python
POST /api/customer/<customer_id>/reconstruct_3d
  → Accept front + side images
  → Call mesh_reconstruction.reconstruct_mesh_from_silhouettes()
  → Save OBJ file, generate preview PNG
  → Return: { mesh_url, preview_url, volume_cm3, num_vertices, num_faces }

GET /api/customer/<customer_id>/mesh/<scan_id>.obj
  → Serve OBJ file for Three.js viewer

POST /api/customer/<customer_id>/compare_3d
  → Accept two scan IDs
  → Load meshes, call mesh_comparison.compare_meshes()
  → Export colored OBJ, return displacement stats
```

### S-2.2 — 3D Volume from Mesh (More Accurate)
**File**: `core/volumetrics.py` or new `core/mesh_volume.py`
**Feature**: Use the actual mesh vertices/faces to compute precise volume via divergence theorem, replacing the 2D estimation when 3D data is available
**Integration**: If both front+side images exist, prefer 3D mesh volume over 2D cylinder estimate

### S-2.3 — Embed 3D Preview in PDF Reports
**File**: `core/report_generator.py`
**Change**: If 3D mesh data exists for a scan, call `mesh_reconstruction.generate_mesh_preview_image()` and embed the wireframe render in the PDF report as an additional section

### S-2.4 — Add 3D CLI Command
**File**: `muscle_tracker.py`
**Add command**:
```
muscle_tracker.py reconstruct-3d --front <img> --side <img> [--marker-size 20.0] [--output mesh.obj] [--preview preview.png]
```

---

## PHASE 3: DASHBOARD & REPORTING (After Gemini Completes Phase 3 Missions)

### S-3.1 — Dashboard API Endpoints
**File**: `web_app/controllers.py`
**Add endpoints** that the personal dashboard (`web_app/static/personal/app.js`) expects:
```python
GET /api/customer/<customer_id>/body_map
  → Aggregate latest scan per muscle group
  → Return: { muscle_groups: [ { name, side, volume_cm3, shape_score, growth_pct, definition_grade } ] }

GET /api/customer/<customer_id>/quick_stats
  → Return: { total_scans, active_muscle_groups, best_growth_pct, best_muscle,
              symmetry_score, days_since_first_scan, current_streak }

GET /api/customer/<customer_id>/circumference_history
  → Return: [ { scan_date, muscle_group, circumference_cm } ]
```

### S-3.2 — Enhanced PDF Report (All-in-One)
**File**: `core/report_generator.py`
**Enhance** `generate_clinical_report()` to include:
- Measurement overlay image (from `measurement_overlay.py`)
- Circumference estimate
- Definition score + heatmap
- Body composition section (if data available)
- 3D mesh preview (if data available)
- Body map thumbnail (if multiple muscle groups scanned)
This makes the existing report endpoint (`GET /api/customer/<id>/report/<scan_id>`) automatically richer

### S-3.3 — Progress API Enhancement
**File**: `web_app/controllers.py` — modify progress endpoint
**Add**: circumference trend, definition score trend, body composition trend to the existing progress response

---

## PHASE 4: FLUTTER APP UPDATE (After Phases 1-3)

### S-4.1 — Add New Scan Results to Flutter
**File**: `companion_app/lib/main.dart`
**Change**: After scan upload, display new metrics:
- Circumference reading
- Definition score + grade
- Body composition card (if full-body shot)
- "View in 3D" button that opens web viewer URL

### S-4.2 — Add Body Composition Screen
**File**: `companion_app/lib/main.dart` (or new file)
**Feature**: Full-body photo capture mode that:
- Guides user to stand in T-pose
- Captures front photo
- Calls `POST /api/customer/<id>/body_composition`
- Displays: BMI, body fat %, lean mass, WHR, classification
- Shows composition visual overlay on the photo

### S-4.3 — Add 3D Scan Flow
**File**: `companion_app/lib/main.dart`
**Feature**: Guided two-photo flow:
- Step 1: "Take front photo" with pose overlay
- Step 2: "Take side photo" with pose overlay
- Upload both → `POST /api/customer/<id>/reconstruct_3d`
- Show 3D preview image + "Open 3D Viewer" button (launches web viewer)

---

## PHASE 5: END-TO-END PIPELINE (Final Polish)

### S-5.1 — Single-Scan Pipeline Function
**File**: New `core/pipeline.py`
**Feature**: One function that runs EVERYTHING on a scan:
```python
def full_scan_pipeline(image_front, image_side=None, image_before=None,
                       user_weight_kg=None, user_height_cm=None, gender='male'):
    """
    Run complete analysis pipeline:
    1. Calibrate (if ArUco markers present)
    2. Segment body + detect muscle group
    3. Extract contours + metrics
    4. Estimate circumference
    5. Score shape + definition
    6. Estimate volume (2D or 3D if side view available)
    7. Compare with before (if provided)
    8. Estimate body composition (if full body)
    9. Generate all overlays
    10. Return comprehensive result dict
    """
```
**Why**: Currently the API endpoint chains ~8 function calls manually. This consolidates the pipeline so both API and CLI share the same flow.

### S-5.2 — Scan History Export
**File**: `web_app/controllers.py`
**Add endpoint**:
```python
GET /api/customer/<customer_id>/export
  → Generate CSV of all scan data (date, muscle, volume, circumference, score, etc.)
  → Also option for JSON export
```

### S-5.3 — Regression Test for Full Pipeline
**File**: `tests/test_pipeline_integration.py`
**Feature**: End-to-end test that:
- Creates a synthetic image with known contour
- Runs full_scan_pipeline()
- Verifies all output keys present
- Verifies metrics are in reasonable ranges
- Verifies overlay images are generated

---

## TASK PRIORITY ORDER

| Rank | Task | Why | Depends On |
|------|------|-----|-----------|
| 1 | S-0.1 | Fix visible bug in shipped code | Nothing |
| 2 | S-0.2 | Commit test files so Gemini can use them | Nothing |
| 3 | S-1.2 | Circumference in scan pipeline — most practical | Gemini 1.2 (done) |
| 4 | S-1.4 | Overlay in scan pipeline — visible to customer | Gemini 1.1 (done) |
| 5 | S-1.1 | Body composition API | Gemini 1.3 |
| 6 | S-1.3 | Definition scorer in pipeline | Gemini 1.4 |
| 7 | S-1.5 | CLI commands | Gemini Phase 1 |
| 8 | S-2.1 | 3D API endpoints | Gemini 2.1 |
| 9 | S-2.3 | 3D in PDF reports | Gemini 2.1 |
| 10 | S-3.1 | Dashboard API | Gemini 3.3 |
| 11 | S-3.2 | Enhanced PDF report | All Phase 1-2 modules |
| 12 | S-5.1 | Pipeline consolidation | All core modules |
| 13 | S-4.1 | Flutter updates | API endpoints done |
| 14 | S-5.3 | Integration test | Pipeline function |

---

## NOTES FOR SONNET

- **Protected files you CAN modify**: `controllers.py`, `muscle_tracker.py`, `models.py`, `report_generator.py`, `__init__.py` — these are YOUR domain
- **Protected files Gemini cannot touch**: Everything above. You own integration.
- **Pattern**: Import from `core.*`, add `@action` route, handle auth, call function, return JSON
- **DB migrations**: py4web auto-migrates on model changes. Just add fields to `models.py`.
- **Existing tests must pass**: Run `python -m pytest tests/ -v` after each change
- **Token tip**: Tasks S-1.2 and S-1.4 can be done NOW since Gemini already shipped missions 1.1 and 1.2
