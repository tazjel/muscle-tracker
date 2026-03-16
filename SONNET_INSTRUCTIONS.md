# Muscle Tracker — Sonnet Agent Instructions

## What Is This Project
Python + Flutter muscle tracking app. Computer vision pipeline for muscle analysis.
**This is the user's personal fitness project — not Tazjel, not Baloot.**

- **Project root**: `C:\Users\MiEXCITE\Projects\muscle_tracker\`
- **Python**: `C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\python.exe`
- **Flutter**: `C:\Users\MiEXCITE\development\flutter\bin\flutter.bat`

---

## Token Budget Rules (READ FIRST — MANDATORY)

- **Do NOT read whole modules** — use Grep to find the exact function you need
- **Do NOT run `flutter analyze`** — never, ever
- **Do NOT explore sibling projects** (baloot-ai, GTDdebug, tazjel) unless asked
- **Do NOT add features beyond what is asked** — no speculative infrastructure
- **Sequential Bash calls only** — parallel cascade-fails on Windows
- **Run tests after every change**: `python -m pytest tests/ -q`
- **Stop if tests drop below 196** — that means you broke something, fix it before continuing
- **One task at a time** — finish it, test it, commit it, move on

---

## Architecture

```
muscle_tracker/
├── muscle_tracker.py          ← CLI entry point (6 commands)
├── core/                      ← All CV/ML modules (YOU DO NOT OWN THESE)
│   ├── auth.py                ← JWT auth helpers
│   ├── pose_analyzer.py       ← MediaPipe pose correction
│   ├── calibration.py         ← ArUco + green marker detection
│   ├── vision_medical.py      ← CLAHE, morphological filtering, verdicts
│   ├── alignment.py           ← SIFT feature matching
│   ├── volumetrics.py         ← Volume estimation (π·a·b·h)
│   ├── symmetry.py            ← Weighted composite symmetry scoring
│   ├── segmentation.py        ← 6 muscle templates, grades S–F
│   ├── visualization.py       ← Growth zones, side-by-side diffs
│   ├── progress.py            ← Trend regression, R², projections
│   └── report_generator.py    ← Clinical PNG report
├── web_app/                   ← YOU OWN THIS DOMAIN
│   ├── models.py              ← py4web DAL schema (SQLite, auto-migrates)
│   ├── controllers.py         ← 23 endpoints, JWT auth, CORS
│   └── static/                ← Personal dashboard JS/CSS
├── companion_app/lib/main.dart ← Flutter app (YOU OWN THIS)
└── tests/                     ← 196 tests passing
```

**Sonnet owns**: `controllers.py`, `models.py`, `muscle_tracker.py`, `report_generator.py`, `companion_app/`
**Gemini owns**: `core/*.py` (vision modules) — do NOT rewrite these, import from them

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Python | 3.9+, NumPy 1.24+, OpenCV 4.8+, py4web, PyJWT |
| Vision | MediaPipe 0.10 (pose), SIFT/ArUco (calibration) |
| Database | SQLite via py4web DAL (auto-migrates on model change) |
| Flutter | 3.11+, camera, sensors_plus, http |

**Dependencies already installed**: numpy, opencv-python, py4web, mediapipe, PyJWT
**Do NOT add new packages** unless explicitly asked.

---

## Run & Test

```bash
# Run all tests
cd C:\Users\MiEXCITE\Projects\muscle_tracker
python -m pytest tests/ -q

# Run specific test file
python -m pytest tests/test_volumetrics.py -v

# Run CLI
python muscle_tracker.py growth --before img1.jpg --after img2.jpg
python muscle_tracker.py volumetrics --image img.jpg
python muscle_tracker.py symmetry --before img1.jpg --after img2.jpg
python muscle_tracker.py shape-check --image img.jpg
python muscle_tracker.py pose-check --image img.jpg
python muscle_tracker.py report --before img1.jpg --after img2.jpg
```

**Current test count**: 196 passing (as of 2026-03-16)

---

## Key Patterns

### Adding a py4web endpoint (`controllers.py`)
```python
@action('api/customer/<customer_id>/my_endpoint', method=['POST'])
@action.uses(db, auth)
def my_endpoint(customer_id):
    require_auth()  # JWT check — always call this
    data = request.json or {}
    # ... call core.* functions ...
    return dict(status='ok', result={})
```

### Adding a DB column (`models.py`)
```python
# py4web auto-migrates on startup — just add the field:
Field('new_column', 'double'),
```
No migration files needed. py4web handles it automatically.

### Importing core modules
```python
from core.circumference import estimate_circumference
from core.definition_scorer import score_muscle_definition
from core.measurement_overlay import draw_measurement_overlay
from core.body_composition import estimate_body_composition
from core.mesh_reconstruction import reconstruct_mesh_from_silhouettes
```

---

## Current Open Work (Priority Order)

See `SONNET_TASKS.md` for full task list. Short version:

**All code-writing from old S-0.x through S-5.x is DONE.** The gap is now **verification + bug fixes + AI Coach.**

| Priority | Task | What | Files |
|----------|------|------|-------|
| 🔴 1 | S-0.1 | Verify scan pipeline works on real device | `controllers.py`, `main.dart` |
| 🔴 2 | S-0.2 | Fix ResultsScreen data binding | `main.dart` (~line 826) |
| 🔴 3 | S-0.3 | Fix PROFILE mode upload timeout | `main.dart` (~line 467-570) |
| 🟡 4 | S-1.1 | Magnetometer fallback for PROFILE | `core/session_analyzer.py` |
| 🟡 5 | S-1.2 | Cumulative PROFILE progress | `controllers.py` (~line 1589) |
| 🟢 6 | S-3.1 | Create AI Coach module (NEW) | New `core/ai_coach.py` |
| 🟢 7 | S-2.1 | Rich ResultsScreen display | `main.dart` (~line 826) |

**Rule**: Fix bugs first (Phase 0-1), then enhance display (Phase 2), then new features (Phase 3+).

---

## Do NOT Do

- Do NOT run `flutter analyze`
- Do NOT rewrite or "improve" `core/*.py` vision modules (Gemini owns them)
- Do NOT add new pip packages without asking
- Do NOT use `db.executesql()` raw SQL — use py4web DAL methods (`db.table.insert(...)`, `db(query).select()`)
- Do NOT commit broken tests — always run `python -m pytest tests/ -q` before committing
- Do NOT touch `web_app/static/personal/` JS files (frontend is owned by the design agent)
- Do NOT open `.archive/` files — completed old work, not relevant

---

## Git Workflow

```bash
cd C:\Users\MiEXCITE\Projects\muscle_tracker

# Check status
git status --short
git log --oneline -5

# Commit one task at a time
git add web_app/controllers.py web_app/models.py
git commit -m "feat(api): wire circumference into scan pipeline (S-1.2)"
```

Commit message format: `feat|fix|test|refactor(scope): short description (task-id)`

---

## Key Context

- **v5.0 code is complete** — all vision modules + API endpoints + Flutter screens written
- **All wiring is done** — circumference, definition, overlay, body composition, 3D mesh, dashboard APIs, live camera, export — all endpoints exist in controllers.py (23+ endpoints)
- **NOTHING has been verified on the real device** — scan pipeline has never produced visible results on phone
- **Gap is now: debug + fix + verify**, NOT write more code
- **PROFILE mode (Auto Mode 2)** is the flagship feature but crashes at 70% upload
- **AI Coach (`core/ai_coach.py`) does NOT exist yet** — this is the only major new module to create
- **Gemini** writes new `core/` modules independently — Sonnet wires them in
- **196 tests passing** — do not break them
- **MediaPipe may fail on Windows** — `pose_analyzer.py` already has a graceful fallback, don't fight it
- **report_generator.py has +113 uncommitted lines** — review and commit
