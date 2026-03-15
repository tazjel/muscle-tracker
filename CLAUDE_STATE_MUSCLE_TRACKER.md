# Muscle Tracker — System State (Updated 2026-03-15)

## Status: v2.0 Code Complete — Untested, Not Deployed

## What Changed (v1.7 → v2.0) — Session 2026-03-15

Every file in the project was upgraded or created. Summary:

### Core Engine (9 modules)
| Module | Key Upgrade |
|--------|------------|
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
| `controllers.py` | File validation (type + 15MB limit), customer CRUD, symmetry endpoint, progress/trend, health log CRUD |

### CLI (`muscle_tracker.py`)
All 5 commands functional: `growth`, `volumetrics`, `symmetry`, `shape-check`, `report`

### Flutter App (`companion_app/lib/main.dart`)
Low-pass sensor filtering, image saving to filesystem, review screen, HTTP multipart upload, body guide overlay

### Infrastructure
`setup.py` v2.0.0, `requirements.txt`, `__init__.py` files added

## Critical Issues for Next Agent

1. **No tests** — zero test coverage, no `tests/` directory
2. **No git repo** — project is not version-controlled
3. **No authentication** on web API endpoints
4. **Flutter upload** uses raw HttpClient (should use `http`/`dio` package)
5. **py4web model validators** may need import adjustments
6. **No CORS** on web API

## Roadmap

See `ROADMAP.md` for the full 24-week, 6-phase, 24-mission plan:
- Phase 1: Foundation & Stabilization (tests, security, CI/CD)
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
├── core/
│   ├── __init__.py
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
└── companion_app/
    └── lib/main.dart
```

## Tech Stack
- **Python 3.9+**: OpenCV 4.8+, NumPy 1.24+, py4web
- **Flutter/Dart 3.11+**: camera, sensors_plus, path_provider
- **Database**: SQLite (migration-ready for PostgreSQL/Cloud SQL)
