# Muscle Tracker — System State (Updated 2026-03-15)

## Status: v2.2 — Tested & Secured

## What Changed (v2.0 → v2.2) — Session 2026-03-15

The system was stabilized, secured, and tested. Summary:

### Core Engine (10 modules)
| Module | Key Upgrade |
|--------|------------|
| `auth.py` | **NEW**: JWT token creation, verification, HS256, roles, expiration. |
| `pose_analyzer.py` | **NEW**: G12 pose correction engine with natural language feedback. |
| `calibration.py` | ArUco markers + green fallback, circularity scoring, morphological cleanup |
| `alignment.py` | Lowe's ratio test, SIFT fallback, confidence scoring, graceful failure |
| `vision_medical.py` | CLAHE, morphological filtering, contour area gating, solidity confidence, 7-level verdicts |
| `volumetrics.py` | **FIXED**: proper `V = π·a·b·h` math. Added prismatoid model. Input validation. Returns full breakdown |
| `symmetry.py` | **FIXED**: crash bug (bad dict key). Multi-metric weighted composite. Risk levels |
| `segmentation.py` | 6 templates: bicep_peak, tricep_horseshoe, quad_sweep, calf_diamond, delt_cap, lat_spread. Grades S–F |
| `visualization.py` | Growth/loss zone masks, side-by-side, symmetry visual with metric overlay |
| `progress.py` | **NEW**: Trend engine — regression, R², projections, streaks, diet correlation |
| `report_generator.py` | **NEW**: Clinical PNG report with growth, volume, shape, symmetry, trend sections |

### Web API
| Module | Key Upgrade |
|--------|------------|
| `models.py` | Extended schema: demographics, muscle groups, symmetry_assessment table, expanded health_log |
| `controllers.py` | Added JWT Auth (`require_auth()`), `/api/auth/token`, CORS enabled, added `pose-check` endpoint. |

### CLI (`muscle_tracker.py`)
All 6 commands functional: `growth`, `volumetrics`, `symmetry`, `shape-check`, `report`, `pose-check`.

### Flutter App (`companion_app/lib/main.dart`)
Added JWT login/setup screen. Captures use JWT Authorization Header. Removed boilerplate platform files from git.

### Infrastructure & Testing
- Git initialized.
- **116 Tests Passing** across 10 test files (`tests/` directory fully populated).

## Critical Issues for Next Agent

1. **Flutter upload** uses `http` package directly, but might need robust background retry (dio/workmanager).
2. **py4web model validators** may need import adjustments.
3. (RESOLVED) ~~No tests~~ — 116 tests added.
4. (RESOLVED) ~~No git repo~~ — Git initialized and clean.
5. (RESOLVED) ~~No authentication~~ — JWT added to Web API and Flutter.
6. (RESOLVED) ~~No CORS~~ — CORS fixture added to API.

## Roadmap

See `ROADMAP.md` for the full 24-week, 6-phase, 24-mission plan:
- Phase 1: Foundation & Stabilization (tests, security, CI/CD) -> **IN PROGRESS / MOSTLY DONE**
- Phase 2: Intelligence Upgrade (MediaPipe ML, auto muscle detection)
- Phase 3: Mobile App Production (camera hardening, auth, offline)
- Phase 4: Clinical Web Dashboard (SPA, charts, PDF reports)
- Phase 5: Cloud & Scale (Cloud SQL, GCS, Docker, async processing)
- Phase 6: Competitive Edge (3D mesh, AI coach, photogrammetry)

## File Tree (source files only)

```
muscle_tracker/
├── muscle_tracker.py
├── setup.py
├── requirements.txt
├── ROADMAP.md
├── GEMINI_TASKS.md
├── core/
│   ├── __init__.py
│   ├── auth.py
│   ├── pose_analyzer.py
│   ├── calibration.py
│   ├── vision_medical.py
│   ├── alignment.py
│   ├── volumetrics.py
│   ├── symmetry.py
│   ├── segmentation.py
│   ├── visualization.py
│   ├── progress.py
│   └── report_generator.py
├── web_app/
│   ├── __init__.py
│   ├── models.py
│   └── controllers.py
├── tests/
│   ├── __init__.py
│   ├── test_alignment.py
│   ├── test_auth.py
│   ├── test_calibration.py
│   ├── test_pose.py
│   ├── test_pose_correction.py
│   ├── test_progress.py
│   ├── test_segmentation.py
│   ├── test_symmetry.py
│   ├── test_vision_medical.py
│   └── test_volumetrics.py
└── companion_app/
    └── lib/main.dart
```

## Tech Stack
- **Python 3.9+**: OpenCV 4.8+, NumPy 1.24+, py4web, PyJWT
- **Flutter/Dart 3.11+**: camera, sensors_plus, path_provider, http
- **Database**: SQLite (migration-ready for PostgreSQL/Cloud SQL)
