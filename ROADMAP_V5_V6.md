# Muscle Tracker — Personal Edition Roadmap (v4.0 → v5.0)

**Created**: 2026-03-15 | **Current**: v4.0 (Shipped)
**Customer**: 1 paying user — personal application, 1-month evaluation
**Goal**: Demonstrate maximum Vision, 3D, and Camera capability
**Success Criteria**: Customer is impressed enough to fund the business version

---

## WHAT THIS IS NOT

This roadmap deliberately EXCLUDES:
- App Store / Play Store submission
- Social features (leaderboards, challenges, galleries)
- Multi-tenant / multi-clinic architecture
- Billing / subscriptions / HIPAA compliance
- CI/CD / infrastructure / logging (invisible to user)
- Market launch / growth features

All of these are Phase 2 (business version) — only built if the customer funds it.

---

## COMPLETED (v1.0 → v4.0) — What the Customer Already Gets

| Capability | Module | Output |
|-----------|--------|--------|
| Muscle growth analysis | `vision_medical.py` | Area/width/height metrics, growth % |
| Before/after alignment | `alignment.py` | Homography-aligned images |
| Calibrated measurements | `calibration.py` | mm-accurate via ArUco markers |
| Volume estimation (3 models) | `volumetrics.py`, `volumetrics_advanced.py` | cm³ volume (cylinder, prismatoid, slice) |
| Left/right symmetry | `symmetry.py` | Imbalance %, risk level, dominant side |
| Shape scoring (6 templates) | `segmentation.py` | Grade S→F, exercise recommendations |
| Pose correction | `pose_analyzer.py` | Joint angle analysis, natural language fix instructions |
| ML body segmentation | `body_segmentation.py` | Pixel-accurate body mask, pose landmarks |
| Auto muscle detection | `muscle_classifier.py` | Which muscle is being photographed |
| Growth heatmaps | `visualization.py` | Before/after overlay with growth/loss zones |
| Side-by-side comparison | `visualization.py` | Labeled before/after with contours |
| Symmetry visual | `visualization.py` | Mirrored comparison with imbalance bar |
| Progress trending | `progress.py` | Linear regression, projections, streaks, correlation |
| PDF clinical report | `report_generator.py` | Professional PDF with all metrics |
| Video keyframe extraction | `keyframe_extractor.py` | Best frames from video |
| Flutter capture app | `companion_app/` | Camera, pose overlay, alignment HUD, upload |
| Web dashboard | `web_app/static/dashboard/` | Clinical SPA with patient management |
| REST API (JWT secured) | `web_app/controllers.py` | 15+ endpoints for all operations |
| Docker deployment | `Dockerfile`, `docker-compose.yml` | One-command deployment |
| Test suite | `tests/` | 143 passing tests |

**Stats**: 16 core modules, 2,358 lines of CV code, 143 tests.

---

## PHASE 1: VISUAL MEASUREMENT ENGINE (v4.1) — Week 1–2

> **Goal**: Every photo scan produces rich, annotated visual output with measurements drawn directly on the image.
> **Customer Impact**: "I can see the measurements on my photos — like a smart ruler for muscles"

### What Gets Built

| # | Feature | Owner | Days | What the Customer Sees |
|---|---------|-------|------|----------------------|
| 1.1 | **Measurement Overlay** | Gemini | 1.5 | Photos with dimension lines, area labels, bounding box drawn on |
| 1.2 | **Circumference Estimator** | Gemini | 1 | "Your bicep circumference: 38.2 cm (15.0 inches)" — replaces tape measure |
| 1.3 | **Body Composition** | Gemini | 1.5 | Body fat %, lean mass, waist-to-hip ratio from photo |
| 1.4 | **Definition Scorer** | Gemini | 1 | "Definition: Lean (72/100)" — texture analysis for vascularity/striations |
| 1.5 | **Enhanced Report** | Claude | 2 | All-in-one PDF with every metric + embedded images |
| 1.6 | **Integration** | Claude | 1 | Wire new modules into API endpoints + CLI |

### New Files Created

```
core/measurement_overlay.py      — Draw measurements on photos
core/circumference.py            — Tape-measure replacement
core/body_composition.py         — Body fat/lean mass estimation
core/definition_scorer.py        — Texture analysis for muscle definition
tests/test_measurement_overlay.py
tests/test_circumference.py
tests/test_body_composition.py
tests/test_definition_scorer.py
```

### Output the Customer Sees

1. **Annotated Photo**: Every scan photo now has width/height dimension lines, area label, contour outline, bounding box
2. **Circumference Reading**: "Estimated circumference: 38.2 cm / 15.0 in" from a single photo
3. **Body Composition Card**: BMI, body fat %, lean mass, waist-to-hip ratio, classification
4. **Definition Grade**: "Shredded" / "Defined" / "Lean" / "Smooth" / "Bulking" + heatmap showing where definition is highest
5. **Comprehensive PDF**: One report with ALL analysis results + embedded annotated images

**Phase 1 Gate**: Customer takes a photo → gets back annotated image + circumference + definition score + PDF. All from one photo.

---

## PHASE 2: 3D CAPABILITIES (v4.5) — Week 2–3

> **Goal**: Generate 3D models from front + side photos. Interactive viewer in browser.
> **Customer Impact**: "It built a 3D model of my arm from two photos"

### What Gets Built

| # | Feature | Owner | Days | What the Customer Sees |
|---|---------|-------|------|----------------------|
| 2.1 | **3D Mesh Generator** | Gemini | 2 | Visual hull reconstruction → OBJ/STL file |
| 2.2 | **Three.js Viewer** | Gemini | 1.5 | Interactive 3D viewer in browser (rotate, zoom, measure) |
| 2.3 | **3D Comparison** | Gemini | 1.5 | Before/after 3D with growth displacement coloring |
| 2.4 | **3D Volume Calculation** | Claude | 1 | Accurate volume from mesh (more precise than 2D estimation) |
| 2.5 | **3D Report Integration** | Claude | 1 | 3D preview images embedded in PDF reports |

### New Files Created

```
core/mesh_reconstruction.py      — Visual hull → 3D mesh from 2 photos
core/mesh_comparison.py          — Before/after 3D displacement mapping
web_app/static/viewer3d/         — Three.js interactive 3D viewer
  index.html
  viewer.js
tests/test_mesh_reconstruction.py
tests/test_mesh_comparison.py
```

### Output the Customer Sees

1. **3D Model File**: Downloadable OBJ/STL of their muscle (can open in any 3D viewer or 3D print)
2. **Interactive 3D Viewer**: Rotate the model in the browser, zoom, pan, toggle wireframe
3. **3D Growth Map**: Before/after meshes with green (growth) and red (loss) coloring on the surface
4. **3D Preview in Report**: Rendered preview image of the 3D model in the PDF report
5. **Precise Volume**: Volume calculated from actual 3D mesh instead of 2D estimation

**Phase 2 Gate**: Customer submits front + side photo → gets 3D model in browser, downloadable OBJ, and 3D comparison if they have a previous scan.

---

## PHASE 3: PERSONAL DASHBOARD & VISUALIZATION (v4.8) — Week 3–4

> **Goal**: A personal home screen that ties everything together.
> **Customer Impact**: "I can see my whole body's progress at a glance"

### What Gets Built

| # | Feature | Owner | Days | What the Customer Sees |
|---|---------|-------|------|----------------------|
| 3.1 | **Body Map** | Gemini | 2 | Full-body outline with muscle scores color-coded |
| 3.2 | **Progress Timelapse** | Gemini | 1.5 | Animated GIF of muscle progression over time |
| 3.3 | **Personal Dashboard** | Gemini | 2.5 | Home screen with body map, charts, recent scans, 3D link |
| 3.4 | **Comparison Slider** | Gemini | 1 | Before/after split-screen image with draggable divider |
| 3.5 | **Chart Enhancements** | Claude | 1 | Multi-metric charts (volume + circumference + definition over time) |

### New Files Created

```
core/body_map.py                 — Full-body visualization with per-muscle scores
core/timelapse.py                — Animated GIF progression + comparison slider
web_app/static/personal/         — Personal dashboard
  index.html
  style.css
  app.js
tests/test_body_map.py
tests/test_timelapse.py
```

### Output the Customer Sees

1. **Body Map**: Human body outline with each scanned muscle group color-coded by score (green = strong, red = needs work), unscanned regions in gray
2. **Progress GIF**: Animated loop of their muscle growing over scans — sharable
3. **Personal Dashboard**:
   - Body map front and center
   - Recent scans as image cards
   - Volume/circumference/definition charts over time
   - Quick stats: total scans, best growth, streak
   - "View in 3D" button
4. **Comparison Slider**: Two photos merged with a vertical line — drag to reveal before/after

**Phase 3 Gate**: Customer opens dashboard → sees body map, progress charts, recent scans, can click into any scan for full analysis, can open 3D viewer.

---

## PHASE 4: VIDEO & ADVANCED CAPTURE (v5.0) — Week 4

> **Goal**: Process video input. Generate the ultimate session report.
> **Customer Impact**: "I just record a video and it analyzes everything"

### What Gets Built

| # | Feature | Owner | Days | What the Customer Sees |
|---|---------|-------|------|----------------------|
| 4.1 | **Video Analyzer** | Gemini | 2 | Upload video → auto-extract best frames → analyze all |
| 4.2 | **Session Report** | Gemini | 2 | All-in-one PDF: every analysis type in one document |
| 4.3 | **Multi-Angle Volume** | Claude | 2 | Better volume from video (more viewing angles) |
| 4.4 | **Flutter Video Capture** | Claude | 1.5 | Record video with guided rotation prompts |

### New Files Created

```
core/video_analyzer.py           — Video → keyframes → multi-frame analysis
core/session_report.py           — Comprehensive single-session PDF
tests/test_video_analyzer.py
tests/test_session_report.py
```

### Output the Customer Sees

1. **Video Upload**: Upload a 10-second video → engine extracts best frames, analyzes each
2. **Session Report PDF** (the crown jewel — everything in one document):
   - Cover page
   - Annotated photo with measurements
   - Growth analysis (if before/after)
   - Volumetric analysis with slice visualization
   - Circumference estimate
   - Shape score with template comparison
   - Definition score with heatmap
   - Body composition
   - Symmetry audit
   - 3D mesh preview
   - Pose quality assessment
   - Progress trend chart
   - Training recommendations

**Phase 4 Gate**: Customer records a video → gets a 12-page PDF covering every analysis the engine can do. This is the document that sells the business version.

---

## MASTER TIMELINE (4 weeks)

```
Week 1          Week 2          Week 3          Week 4
├───────────────┤
Phase 1: Visual Measurements
        ├───────────────┤
        Phase 2: 3D Capabilities
                ├───────────────┤
                Phase 3: Personal Dashboard
                        ├───────────────┤
                        Phase 4: Video & Session Report
```

**Execution model:**
- Gemini builds new modules (new files only, protected list enforced)
- Claude integrates, enhances core, wires endpoints, handles complex ML
- Customer tests weekly, provides feedback

---

## WORK ASSIGNMENT

### Gemini Builds (New Files Only — see GEMINI_MISSION_V5.md)

| Phase | Missions | New Files | Est. Tokens |
|-------|----------|-----------|-------------|
| 1 | 1.1–1.4 | 4 core + 4 test files | ~35% budget |
| 2 | 2.1–2.3 | 2 core + 2 test + 3 web files | ~30% budget |
| 3 | 3.1–3.3 | 2 core + 2 test + 3 web files | ~25% budget |
| 4 | 4.1–4.2 | 2 core + 2 test files | ~10% budget |

### Claude Builds (Core Integration + Complex Features)

| Phase | Tasks | What |
|-------|-------|------|
| 1 | 1.5–1.6 | Enhanced report + wire new modules into API/CLI |
| 2 | 2.4–2.5 | 3D volume calc + report integration |
| 3 | 3.5 | Multi-metric charts, dashboard API endpoints |
| 4 | 4.3–4.4 | Multi-angle volume from video, Flutter video capture |

### Customer Validates

| Week | What Customer Tests |
|------|-------------------|
| 1 | Scan photos → see annotated images + circumference + definition |
| 2 | Submit front + side → see 3D model in browser |
| 3 | Use dashboard → see body map + progress charts |
| 4 | Record video → receive comprehensive session report |

---

## NEW FEATURES SUMMARY (v4.1 → v5.0)

| Feature | Type | Replaces/Competes With |
|---------|------|----------------------|
| Measurement Overlay | Vision | Manual tape measure photos |
| Circumference Estimation | Vision | Physical tape measure |
| Body Composition | Vision | DEXA scan ($50-150), calipers |
| Muscle Definition Score | Vision | Subjective visual assessment |
| 3D Mesh Reconstruction | 3D | ZOZOFIT ($400 suit), 3D scanners ($2,000+) |
| Interactive 3D Viewer | 3D | Desktop 3D software |
| 3D Growth Comparison | 3D | Nothing on market (unique) |
| Body Map | Dashboard | Manual tracking spreadsheets |
| Progress Timelapse | Dashboard | Manual photo collages |
| Video Analysis | Camera | Frame-by-frame manual review |
| Session Report (All-in-One) | Output | Multiple separate tools |

**Competitive position**: With all v5.0 features, the customer gets capabilities that currently require $2,000+ in equipment (3D scanner, DEXA, professional software) — from just a phone camera.

---

## AFTER v5.0: IF CUSTOMER FUNDS BUSINESS VERSION

Only if the customer is satisfied and pays for business development:

| Phase | Version | Features |
|-------|---------|----------|
| Business v1 | v6.0 | Multi-tenant, RBAC, clinic branding, Stripe billing |
| Business v2 | v6.5 | Cloud deployment (GCP), async processing, monitoring |
| Business v3 | v7.0 | HIPAA compliance, DICOM export, App Store submission |
| Business v4 | v7.5 | AI Coach (Claude API), exercise programming, chat |
| Business v5 | v8.0 | Social features, leaderboards, app marketplace |

These are NOT in scope for the current engagement. They exist here only as a signal to the customer of where the product can go.
