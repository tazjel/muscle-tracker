# MUSCLE TRACKER v2.0 → v3.0 ROADMAP
**Created**: 2026-03-15 | **Target GA**: 2026-09-01 (24 weeks)

---

## TEAM ROLES

| Code | Role | Profile |
|------|------|---------|
| **BE** | Backend Engineer | Python, OpenCV, NumPy, py4web, API design |
| **ML** | ML / CV Engineer | Computer vision, model training, MediaPipe, ONNX |
| **FE** | Frontend Engineer | Flutter/Dart, mobile UX, camera APIs |
| **FS** | Full-Stack Engineer | Python + Flutter + DevOps, integration glue |
| **QA** | QA Engineer | Testing, automation, clinical validation protocols |
| **DES** | UI/UX Designer | Mobile UI, clinical report design, branding |

---

## PHASE 1: FOUNDATION & STABILIZATION (Weeks 1–4)

> **Goal**: Make v2.0 production-safe. Fix all broken paths, add tests, harden security.

### Mission 1.1 — Test Suite Bootstrap
| Item | Detail |
|------|--------|
| **Owner** | QA + BE |
| **Estimate** | 5 days |
| **Priority** | P0 — Critical |
| **Description** | Create pytest infrastructure with fixtures for test images. Unit tests for every `core/` module. Target: 80% coverage on core engine. |
| **Deliverables** | `tests/` directory, `conftest.py` with sample image fixtures, `test_calibration.py`, `test_vision_medical.py`, `test_volumetrics.py`, `test_symmetry.py`, `test_segmentation.py`, `test_alignment.py`, `test_progress.py`, `test_report_generator.py` |
| **Dependencies** | None — can start Day 1 |

### Mission 1.2 — Sample Data & Calibration Fixtures
| Item | Detail |
|------|--------|
| **Owner** | QA |
| **Estimate** | 3 days |
| **Priority** | P0 |
| **Description** | Create synthetic test images: calibration markers (ArUco + green), muscle contour mockups at known dimensions, paired before/after sets with known growth percentages. These are required for all other testing. |
| **Deliverables** | `tests/fixtures/` with 10+ image pairs, `tests/generate_fixtures.py` script |
| **Dependencies** | None |

### Mission 1.3 — Web API Security Hardening
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 4 days |
| **Priority** | P0 — Critical |
| **Description** | Add authentication (py4web Auth or JWT). Rate limiting on upload endpoints. CORS configuration. Input sanitization on all form fields. HTTPS enforcement config. Audit log table for scan access. |
| **Deliverables** | Updated `controllers.py` with `@action.uses(auth.user)`, `web_app/auth.py`, rate limiter middleware, CORS headers |
| **Dependencies** | None |

### Mission 1.4 — CI/CD Pipeline
| Item | Detail |
|------|--------|
| **Owner** | FS |
| **Estimate** | 3 days |
| **Priority** | P1 |
| **Description** | GitHub Actions workflow: lint (flake8/pylint), test (pytest), build Flutter APK, Docker image for web backend. Branch protection rules. |
| **Deliverables** | `.github/workflows/ci.yml`, `Dockerfile`, `.flake8`, `pyproject.toml` (tool config) |
| **Dependencies** | Mission 1.1 (tests must exist) |

### Mission 1.5 — Error Handling & Logging Overhaul
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 3 days |
| **Priority** | P1 |
| **Description** | Structured JSON logging across all modules. Custom exception classes (`CalibrationError`, `DetectionError`, `AlignmentError`). Graceful degradation paths (uncalibrated mode, unaligned mode). Request ID tracing in web API. |
| **Deliverables** | `core/exceptions.py`, updated all `core/*.py` with try/except and structured logging, `web_app/middleware.py` |
| **Dependencies** | None |

**Phase 1 Total: ~18 person-days (4 weeks with 1 engineer, 2 weeks with 2)**

---

## PHASE 2: INTELLIGENCE UPGRADE (Weeks 5–10)

> **Goal**: Replace heuristic contour detection with ML-powered body segmentation. This is the single biggest accuracy improvement possible.

### Mission 2.1 — MediaPipe Body Segmentation Integration
| Item | Detail |
|------|--------|
| **Owner** | ML |
| **Estimate** | 8 days |
| **Priority** | P0 — Game Changer |
| **Description** | Integrate MediaPipe Pose + Selfie Segmentation for pixel-accurate body masks. Extract per-muscle ROIs using pose landmarks (shoulder, elbow, wrist → bicep region). Replace adaptive threshold with ML segmentation as primary method, keep threshold as fallback. |
| **Deliverables** | `core/body_segmentation.py`, `core/landmark_detector.py`, updated `vision_medical.py` with ML path |
| **Dependencies** | Mission 1.1 (tests for regression) |

### Mission 2.2 — Muscle Group Auto-Detection
| Item | Detail |
|------|--------|
| **Owner** | ML |
| **Estimate** | 6 days |
| **Priority** | P1 |
| **Description** | Using MediaPipe pose landmarks, auto-detect which muscle group is being photographed (bicep, quad, calf, etc.) based on the visible body region and pose angles. Eliminates need for user to manually select muscle group. |
| **Deliverables** | `core/muscle_classifier.py`, integration into `vision_medical.py` and `controllers.py` |
| **Dependencies** | Mission 2.1 |

### Mission 2.3 — Multi-Point Calibration
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 4 days |
| **Priority** | P1 |
| **Description** | Support multiple ArUco markers in a single frame. Average their ratios for higher precision. Detect and reject outliers (damaged/occluded markers). Report calibration confidence interval. |
| **Deliverables** | Updated `calibration.py` with multi-marker mode, calibration board spec document |
| **Dependencies** | Mission 1.2 (test fixtures) |

### Mission 2.4 — Advanced Volume Models
| Item | Detail |
|------|--------|
| **Owner** | BE + ML |
| **Estimate** | 5 days |
| **Priority** | P2 |
| **Description** | Add slice-based volume estimation: divide the muscle contour into horizontal slices, compute elliptical cross-section per slice, integrate. More accurate for tapered/irregular muscles than single cylinder model. Add DEXA-equivalent density estimation using body composition lookup tables. |
| **Deliverables** | `core/volumetrics_advanced.py` with `slice_integration` model, density tables in `data/density_tables.json` |
| **Dependencies** | Mission 2.1 (accurate contours) |

### Mission 2.5 — Shape Template Learning
| Item | Detail |
|------|--------|
| **Owner** | ML |
| **Estimate** | 5 days |
| **Priority** | P2 |
| **Description** | Allow clinics to create custom "ideal" templates from real athlete photos instead of synthetic parametric curves. Extract contour from a labeled image, normalize, and save as a reusable template. Template library management (CRUD). |
| **Deliverables** | `core/template_builder.py`, `api/templates` CRUD endpoints, `data/templates/` storage |
| **Dependencies** | Mission 2.1 |

**Phase 2 Total: ~28 person-days (6 weeks with 1 ML engineer, 3 weeks with 2)**

---

## PHASE 3: MOBILE APP PRODUCTION (Weeks 7–12)

> **Goal**: Ship a polished, reliable companion app to Play Store / TestFlight.

### Mission 3.1 — Camera Pipeline Hardening
| Item | Detail |
|------|--------|
| **Owner** | FE |
| **Estimate** | 5 days |
| **Priority** | P0 |
| **Description** | Auto-focus lock before capture. Exposure/white-balance lock for consistent lighting. Image quality validation (blur detection via Laplacian variance, brightness check). Retry prompt if quality below threshold. EXIF metadata preservation. |
| **Deliverables** | `lib/services/camera_service.dart`, `lib/utils/image_quality.dart` |
| **Dependencies** | None |

### Mission 3.2 — User Authentication & Profile
| Item | Detail |
|------|--------|
| **Owner** | FE + BE |
| **Estimate** | 5 days |
| **Priority** | P0 |
| **Description** | Login/register screens. JWT token management. Profile screen (name, DOB, height, weight). Token refresh flow. Biometric unlock option. |
| **Deliverables** | `lib/screens/login_screen.dart`, `lib/screens/profile_screen.dart`, `lib/services/auth_service.dart`, `lib/models/user.dart` |
| **Dependencies** | Mission 1.3 (backend auth) |

### Mission 3.3 — Scan History & Progress Dashboard
| Item | Detail |
|------|--------|
| **Owner** | FE + DES |
| **Estimate** | 7 days |
| **Priority** | P1 |
| **Description** | Timeline view of all past scans with thumbnails. Tap to view full report. Line chart of volume over time (fl_chart package). Filter by muscle group. Compare any two scans side-by-side. |
| **Deliverables** | `lib/screens/history_screen.dart`, `lib/screens/scan_detail_screen.dart`, `lib/widgets/progress_chart.dart`, `lib/services/api_service.dart` |
| **Dependencies** | Mission 3.2 (auth for API calls) |

### Mission 3.4 — Guided Capture Workflow v2
| Item | Detail |
|------|--------|
| **Owner** | FE + DES |
| **Estimate** | 5 days |
| **Priority** | P1 |
| **Description** | Step-by-step wizard: select muscle group → position guide overlay (pose-specific) → sensor alignment → capture front → rotate prompt with animation → capture side → review → upload. Voice prompts (TTS) for hands-free operation. Haptic feedback on level lock. |
| **Deliverables** | `lib/screens/capture_wizard.dart`, `lib/widgets/pose_guide.dart`, `lib/services/haptic_service.dart` |
| **Dependencies** | Mission 3.1 |

### Mission 3.5 — Offline Mode & Sync
| Item | Detail |
|------|--------|
| **Owner** | FE |
| **Estimate** | 4 days |
| **Priority** | P2 |
| **Description** | SQLite local database (sqflite) for offline scan storage. Queue uploads when connectivity returns. Conflict resolution (server wins). Scan status indicators (pending/synced/failed). |
| **Deliverables** | `lib/services/local_db.dart`, `lib/services/sync_service.dart` |
| **Dependencies** | Mission 3.2, Mission 3.3 |

### Mission 3.6 — App Store Preparation
| Item | Detail |
|------|--------|
| **Owner** | FE + DES |
| **Estimate** | 4 days |
| **Priority** | P1 |
| **Description** | App icon and splash screen. Play Store / App Store listing assets (screenshots, description). Privacy policy. HIPAA compliance checklist (if targeting US clinics). ProGuard / obfuscation. Signing configuration. |
| **Deliverables** | Store listing assets, signed APK/IPA, privacy policy page |
| **Dependencies** | All Mission 3.x complete |

**Phase 3 Total: ~30 person-days (6 weeks with 1 FE, 3 weeks with 2)**

---

## PHASE 4: CLINICAL WEB DASHBOARD (Weeks 11–16)

> **Goal**: Build the clinic-facing web portal for patient management and reporting.

### Mission 4.1 — Web Frontend Framework Setup
| Item | Detail |
|------|--------|
| **Owner** | FS |
| **Estimate** | 3 days |
| **Priority** | P0 |
| **Description** | Choose and set up frontend: Vue.js or React SPA served by py4web static. Tailwind CSS for clinical dark theme. API client layer. Auth integration. |
| **Deliverables** | `web_app/static/spa/` with build tooling, base layout, auth flow |
| **Dependencies** | Mission 1.3 (backend auth) |

### Mission 4.2 — Patient Management Dashboard
| Item | Detail |
|------|--------|
| **Owner** | FS + DES |
| **Estimate** | 6 days |
| **Priority** | P0 |
| **Description** | Patient list with search/filter. Patient detail view with demographics, scan timeline, and health log. Add/edit patient modal. Bulk actions (export, archive). |
| **Deliverables** | Patient list page, patient detail page, CRUD modals |
| **Dependencies** | Mission 4.1 |

### Mission 4.3 — Interactive Scan Viewer
| Item | Detail |
|------|--------|
| **Owner** | FS |
| **Estimate** | 5 days |
| **Priority** | P1 |
| **Description** | View scan images with zoom/pan. Toggle contour overlay on/off. Slider to compare before/after (onion skin). Display all metrics alongside the image. Download report PNG. |
| **Deliverables** | Scan viewer component with overlay controls |
| **Dependencies** | Mission 4.2 |

### Mission 4.4 — Progress Charts & Analytics
| Item | Detail |
|------|--------|
| **Owner** | FS + DES |
| **Estimate** | 5 days |
| **Priority** | P1 |
| **Description** | Chart.js or D3 interactive charts: volume over time, symmetry trends, shape score progression. Diet/activity correlation scatter plots. Exportable as image/CSV. Clinic-wide aggregate stats (average gain per patient, most improved). |
| **Deliverables** | Analytics dashboard page, chart components, CSV export |
| **Dependencies** | Mission 4.2 |

### Mission 4.5 — PDF Report Generation
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 4 days |
| **Priority** | P1 |
| **Description** | Server-side PDF generation (ReportLab or WeasyPrint) of clinical reports. Branded header/footer. All scan data, images, charts in a printable format. Email delivery option. |
| **Deliverables** | `core/pdf_report.py`, `api/report/<scan_id>/pdf` endpoint |
| **Dependencies** | Mission 4.4 (chart images to embed) |

### Mission 4.6 — Multi-Clinic / Multi-Tenant Support
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 5 days |
| **Priority** | P2 |
| **Description** | Add `clinic` table. Scope all queries by clinic_id. Role-based access (admin, clinician, patient). Clinic branding (logo, colors on reports). |
| **Deliverables** | Updated models, middleware for tenant scoping, admin panel |
| **Dependencies** | Mission 1.3, Mission 4.2 |

**Phase 4 Total: ~28 person-days (6 weeks with 1 FS, 3 weeks with 2)**

---

## PHASE 5: CLOUD & SCALE (Weeks 15–20)

> **Goal**: Deploy to production cloud infrastructure for real clinic use.

### Mission 5.1 — Database Migration to Cloud SQL
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 3 days |
| **Priority** | P0 |
| **Description** | Migrate from SQLite to Google Cloud SQL (PostgreSQL). Update DAL connection string. Migration scripts for schema. Connection pooling. Automated backups. |
| **Deliverables** | `web_app/db_config.py`, migration scripts, Cloud SQL instance config |
| **Dependencies** | GCP project setup |

### Mission 5.2 — Cloud Storage for Scan Images
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 3 days |
| **Priority** | P0 |
| **Description** | Move image storage from local `uploads/` to Google Cloud Storage. Signed URLs for secure access. Image compression pipeline (thumbnail + full-res). CDN for fast delivery. |
| **Deliverables** | `web_app/storage.py`, updated upload/retrieve logic, GCS bucket config |
| **Dependencies** | Mission 5.1 |

### Mission 5.3 — Containerization & Orchestration
| Item | Detail |
|------|--------|
| **Owner** | FS |
| **Estimate** | 4 days |
| **Priority** | P1 |
| **Description** | Docker Compose for local dev (web + db + worker). Cloud Run deployment config. Auto-scaling rules. Health check endpoints. Environment-based configuration. |
| **Deliverables** | `docker-compose.yml`, `Dockerfile.web`, `Dockerfile.worker`, Cloud Run config, `.env.example` |
| **Dependencies** | Mission 5.1, Mission 5.2 |

### Mission 5.4 — Async Vision Processing Queue
| Item | Detail |
|------|--------|
| **Owner** | BE |
| **Estimate** | 5 days |
| **Priority** | P1 |
| **Description** | Move vision engine processing off the request thread. Use Cloud Tasks or Celery + Redis. Upload endpoint returns immediately with scan_id, client polls for results. Webhook notification when processing completes. |
| **Deliverables** | `web_app/tasks.py`, `web_app/worker.py`, status polling endpoint, webhook config |
| **Dependencies** | Mission 5.3 |

### Mission 5.5 — Monitoring & Alerting
| Item | Detail |
|------|--------|
| **Owner** | FS |
| **Estimate** | 3 days |
| **Priority** | P1 |
| **Description** | Structured logging to Cloud Logging. Error tracking (Sentry). Uptime monitoring. Dashboard for: API latency, scan processing time, error rates, active users. Alerts for downtime and error spikes. |
| **Deliverables** | Sentry integration, Cloud Monitoring dashboard, alert policies |
| **Dependencies** | Mission 5.3 |

**Phase 5 Total: ~18 person-days (5 weeks with 1 engineer, 2.5 weeks with 2)**

---

## PHASE 6: COMPETITIVE EDGE FEATURES (Weeks 19–24)

> **Goal**: Features that make Muscle Tracker unbeatable vs. ZOZOFIT / Abody.ai / Shapez.

### Mission 6.1 — 3D Mesh Reconstruction
| Item | Detail |
|------|--------|
| **Owner** | ML |
| **Estimate** | 10 days |
| **Priority** | P2 — Differentiator |
| **Description** | From front + side photos, generate a textured 3D mesh of the muscle using visual hull reconstruction. Interactive 3D viewer (Three.js on web, model_viewer on Flutter). Export as OBJ/STL for 3D printing. |
| **Deliverables** | `core/mesh_reconstruction.py`, web 3D viewer component, Flutter 3D viewer |
| **Dependencies** | Mission 2.1 (ML segmentation) |

### Mission 6.2 — AI Coach Recommendations
| Item | Detail |
|------|--------|
| **Owner** | BE + ML |
| **Estimate** | 6 days |
| **Priority** | P2 |
| **Description** | Based on shape scores, symmetry indices, and growth trends, generate personalized training programs. Exercise database with target muscle groups. Weekly plan adjustments based on scan progress. Integration with Claude API for natural language coaching. |
| **Deliverables** | `core/coach.py`, `data/exercises.json`, coaching endpoint, chat interface |
| **Dependencies** | Phase 2 complete |

### Mission 6.3 — Multi-Photo Photogrammetry
| Item | Detail |
|------|--------|
| **Owner** | ML |
| **Estimate** | 8 days |
| **Priority** | P3 |
| **Description** | Instead of just front + side, support 4–8 photos taken in a circle around the limb. Structure-from-motion to build a denser point cloud. Significantly more accurate volume estimation. Guided capture with angle prompts. |
| **Deliverables** | `core/photogrammetry.py`, multi-angle capture workflow in app |
| **Dependencies** | Mission 6.1 |

### Mission 6.4 — Competition Mode
| Item | Detail |
|------|--------|
| **Owner** | FS + DES |
| **Estimate** | 5 days |
| **Priority** | P3 |
| **Description** | Leaderboards by muscle group (opt-in, anonymized). "Challenge a friend" feature. Before/after transformation galleries. Achievement badges (streak, gains milestones, symmetry perfection). |
| **Deliverables** | Leaderboard API + UI, challenge system, badge engine |
| **Dependencies** | Phase 4 complete |

**Phase 6 Total: ~29 person-days (6 weeks with 1 engineer, 3 weeks with 2)**

---

## MASTER TIMELINE

```
Week   1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19 20 21 22 23 24
       ├──────────┤
       PHASE 1: Foundation (18 days)
                  ├────────────────────┤
                  PHASE 2: Intelligence (28 days)
                        ├────────────────────────┤
                        PHASE 3: Mobile App (30 days)
                                          ├────────────────────┤
                                          PHASE 4: Web Dashboard (28 days)
                                                      ├──────────────┤
                                                      PHASE 5: Cloud (18 days)
                                                               ├──────────────┤
                                                               PHASE 6: Edge (29 days)
```

## STAFFING SCENARIOS

### Scenario A: Solo Developer (1 person)
| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1 | 4 weeks | Week 4 |
| Phase 2 | 6 weeks | Week 10 |
| Phase 3 | 6 weeks | Week 16 |
| Phase 4 | 6 weeks | Week 22 |
| Phase 5 | 4 weeks | Week 26 |
| Phase 6 | 6 weeks | Week 32 |
| **Total** | **~32 weeks (8 months)** | |

### Scenario B: Small Team (3 people: BE + FE + ML)
| Phase | Duration | Notes |
|-------|----------|-------|
| Phase 1 | 2 weeks | BE + ML in parallel |
| Phase 2 | 4 weeks | ML lead, BE supports |
| Phase 3 | 4 weeks | FE lead (parallel with Phase 2) |
| Phase 4 | 3 weeks | BE + FE collaborate |
| Phase 5 | 2.5 weeks | BE lead |
| Phase 6 | 4 weeks | All three |
| **Total** | **~16 weeks (4 months)** | Phases 2+3 overlap |

### Scenario C: Full Team (5 people: BE + FE + ML + FS + QA)
| Phase | Duration | Notes |
|-------|----------|-------|
| Phase 1 | 1.5 weeks | Everyone bootstraps in parallel |
| Phase 2 | 3 weeks | ML + BE, others start Phase 3 |
| Phase 3 | 3 weeks | FE + DES (parallel with Phase 2) |
| Phase 4 | 2.5 weeks | FS + BE (parallel with Phase 3 tail) |
| Phase 5 | 2 weeks | FS + BE |
| Phase 6 | 3 weeks | Full team |
| **Total** | **~11 weeks (2.5 months)** | Heavy parallelism |

---

## MILESTONES & CHECKPOINTS

| Milestone | Target | Gate Criteria |
|-----------|--------|---------------|
| **M1: Test Green** | Week 4 | 80% core test coverage, CI passing, security audit clean |
| **M2: ML Vision** | Week 10 | MediaPipe integration live, auto muscle detection >90% accuracy |
| **M3: App Beta** | Week 12 | APK on TestFlight/Play internal track, full capture→upload→result flow |
| **M4: Clinic Pilot** | Week 16 | Web dashboard live, 1 clinic onboarded, 50 real scans processed |
| **M5: Cloud GA** | Week 20 | Cloud SQL + GCS + Cloud Run, <2s API response, 99.5% uptime |
| **M6: Market Ready** | Week 24 | 3D viewer, AI coach, App Store published, 5 clinics active |

---

## RISK REGISTER

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| MediaPipe accuracy on muscle photos | High | Medium | Keep threshold fallback, train custom model if needed |
| py4web scaling limits | Medium | Medium | Abstract DAL layer, prepare FastAPI migration path |
| HIPAA compliance complexity | High | High (US market) | Engage compliance consultant at Phase 4, encrypt at rest |
| App Store rejection (health claims) | Medium | Medium | Disclaimer: "educational, not medical device", avoid FDA-trigger language |
| OpenCV version conflicts across platforms | Low | High | Pin versions, Docker for server, test matrix in CI |

---

## BUDGET ESTIMATE (if hiring)

| Role | Rate (USD/hr) | Hours | Cost |
|------|---------------|-------|------|
| Senior BE/ML Engineer | $80–120 | 320 | $25,600–$38,400 |
| Senior Flutter Developer | $70–100 | 240 | $16,800–$24,000 |
| Full-Stack Developer | $60–90 | 200 | $12,000–$18,000 |
| QA Engineer (part-time) | $50–70 | 120 | $6,000–$8,400 |
| UI/UX Designer (contract) | $60–90 | 80 | $4,800–$7,200 |
| **Total** | | **960 hrs** | **$65,200–$96,000** |

Cloud infrastructure: ~$150–300/month (GCP: Cloud Run + Cloud SQL + GCS + monitoring)
