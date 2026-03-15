# Gemini Mission Brief — Muscle Tracker Personal Edition v5.0

> **Date**: 2026-03-15
> **Current Version**: v4.0 (Shipped) + Missions 1.1, 1.2 done
> **Target**: Personal Vision Application — 1 paying customer, 1-month evaluation
> **Objective**: Maximize visible, useful VISION output. Every feature must produce something the user can SEE and USE.
> **Codename**: Operation Eagle Eye

---

## HOW TO WRITE FILES (CRITICAL — READ FIRST)

You are on **Windows with Git Bash**. Use Python to write files. This is the fastest method — do NOT use PowerShell escape gymnastics.

### Write a file (ONE command, fast):

```bash
python -c "
import textwrap, pathlib
pathlib.Path(r'C:/Users/MiEXCITE/Projects/muscle_tracker/core/NEW_FILE.py').write_text(textwrap.dedent('''
    import numpy as np
    import cv2

    def my_function():
        return True
''').strip() + '\n')
"
```

### Write a LARGE file (use a helper script):

```bash
cat > /tmp/_write.py << 'PYEOF'
import pathlib
content = r"""
import numpy as np
import cv2
import math

def function_one():
    pass

def function_two():
    pass
"""
pathlib.Path(r'C:/Users/MiEXCITE/Projects/muscle_tracker/core/NEW_FILE.py').write_text(content.strip() + '\n')
PYEOF
python /tmp/_write.py
```

### Read a file:
```bash
cat core/somefile.py
```

### Run tests:
```bash
cd C:/Users/MiEXCITE/Projects/muscle_tracker && python -m pytest tests/test_specific.py -v
```

### Git (only commit implementation files — tests are already tracked):
```bash
cd C:/Users/MiEXCITE/Projects/muscle_tracker && git add core/file.py && git commit -m "feat(vision): description (personal-v5 mission X.N)"
```

**RULE: Never use PowerShell. Never use `python -c "open(...).write('''...''')"` with nested quotes. Use the patterns above.**

---

## WORKFLOW: TDD — TESTS ARE ALREADY WRITTEN

**Tests for every mission have been pre-written by Claude Sonnet.** They are already in `tests/`. Your ONLY job is to write the implementation code that makes them pass.

**Your workflow for each mission:**
1. Read the test file: `cat tests/test_<module>.py` (to see what's expected)
2. Write the implementation file (one shot, complete)
3. Run: `python -m pytest tests/test_<module>.py -v`
4. If tests pass → `git add core/<module>.py && git commit`
5. If tests fail → fix implementation, re-run ONCE. If still failing, commit what works and note failures.

**DO NOT modify any test file.** Tests are protected. If a test seems wrong, skip it and note `[TEST DISPUTE: ...]` in your commit.

---

## SPEED RULES (NON-NEGOTIABLE)

1. **Do NOT read existing core/ files** unless you need to import from them. Everything you need is in the summary tables below.
2. **DO read the test file first** for each mission — it tells you exactly what to implement.
3. **Do NOT output explanations**. Just write code and short status.
4. **One file = one write command**. Don't write partial files and append.
5. **Target: 5 minutes per mission**. If you're debugging for more than 2 minutes, skip and move on.
6. **Write the COMPLETE file in one shot**. Plan the full implementation mentally, then write it all at once.
7. **Do NOT re-read your own output**. You just wrote it — you know what's in it.
8. **Do NOT write tests**. They already exist. Only write `core/*.py` and `web_app/static/*` files.

---

## ABSOLUTE RULES (VIOLATION = MISSION FAILURE)

### Rule 1: NEVER MODIFY PROTECTED FILES
These files are maintained by Claude. Modifying them causes regressions.

**PROTECTED — DO NOT TOUCH:**
```
core/auth.py
core/vision_medical.py
core/calibration.py
core/alignment.py
core/volumetrics.py
core/volumetrics_advanced.py
core/symmetry.py
core/segmentation.py
core/visualization.py
core/progress.py
core/report_generator.py
core/pose_analyzer.py
core/body_segmentation.py
core/muscle_classifier.py
core/keyframe_extractor.py
core/__init__.py
web_app/models.py
web_app/controllers.py
web_app/__init__.py
muscle_tracker.py
setup.py
requirements.txt
Dockerfile
docker-compose.yml
tests/conftest.py
tests/test_*.py  (ALL test files — tests are pre-written by Sonnet, DO NOT modify or create)
```

### Rule 2: ONLY BUILD WHAT IS ASSIGNED
### Rule 3: ONE MISSION AT A TIME — Commit after each
### Rule 4: DO NOT WRITE OR MODIFY TESTS — They are pre-written
### Rule 5: COMMIT FORMAT
```
feat(vision): short description (personal-v5 mission X.N)
```

---

## EXISTING CAPABILITIES (DO NOT READ THESE FILES — USE THIS SUMMARY)

| Module | What It Does | Key Output |
|--------|-------------|------------|
| `vision_medical.py` | CLAHE → contour extraction → area/width/height | dict with metrics + contours |
| `calibration.py` | ArUco + green marker → px-to-mm ratio | float (mm/px) or None |
| `alignment.py` | ORB/SIFT → homography warp for before/after | aligned image + confidence |
| `volumetrics.py` | Elliptical cylinder + prismatoid from areas | volume_cm3 |
| `volumetrics_advanced.py` | Slice-integration for tapered muscles (20 slices) | volume_cm3 + per-slice data |
| `symmetry.py` | Left vs right limb comparison | symmetry_indices + verdict |
| `segmentation.py` | 6 Hu Moment templates → shape score 0-100 | score + grade S/A/B/C/D/F |
| `visualization.py` | Growth heatmap, side-by-side, symmetry visual | saved image files |
| `progress.py` | Linear regression, R², projections | trend dict + projections |
| `report_generator.py` | PDF clinical report (ReportLab) | saved PDF file |
| `pose_analyzer.py` | Pose angle analysis → correction instructions | corrections list + pose_score |
| `body_segmentation.py` | MediaPipe seg + pose landmarks + ROI crop | binary mask, landmarks dict |
| `muscle_classifier.py` | Auto-detect muscle group from pose angles | muscle group string |
| `keyframe_extractor.py` | Extract keyframes from video | list of frame images |

**Key types:** Contours: `np.ndarray (N,1,2) int32` | Images: `np.ndarray BGR (H,W,3) uint8` | Landmarks: `dict name→(x,y)`

---

## COMPLETED MISSIONS (DO NOT REDO)

| Mission | Status | Commit |
|---------|--------|--------|
| 1.1 Measurement Overlay | DONE | 7e6225d |
| 1.2 Circumference Estimator | DONE | b980fa3 |

---

## REMAINING MISSIONS — DO THESE IN ORDER

---

### Mission 1.3 — Body Composition Estimator ⚠️ REDO NEEDED
**Status**: Code exists but NOT committed. Has bugs. Delete and rewrite.

**First**: `rm core/body_composition.py` (old buggy version)

**Tests**: Already at `tests/test_body_composition.py` — read it first, then make them pass.

Create `core/body_composition.py` (~100 lines):

```python
# Functions needed:

def estimate_body_composition(landmarks, contour_torso=None,
                              waist_width_mm=None, hip_width_mm=None,
                              neck_circumference_mm=None,
                              user_weight_kg=None, user_height_cm=None,
                              gender="male"):
    """
    Returns dict with: bmi, waist_to_hip_ratio, estimated_body_fat_pct,
                       classification, confidence

    IMPORTANT implementation notes:
    - BMI = weight / (height_m)^2
    - WHR = waist / hip (from params or estimated from landmarks)
    - Body fat: USE THE NAVY METHOD (not a generic BMI formula):
      Men:   86.010 * log10(waist_circ - neck_circ) - 70.041 * log10(height) + 36.76
      Women: 163.205 * log10(waist_circ + hip_circ - neck_circ) - 97.684 * log10(height) - 78.387
    - If circumferences not provided, estimate from landmark pixel distances:
      waist_circ ≈ waist_width * π * 0.65 (elliptical correction)
      neck_circ ≈ shoulder_width * 0.38 * π * 0.6
    - Do NOT hardcode age. The Navy method doesn't use age.
    - Classification thresholds:
      Male:   <14% Athletic, <18% Fit, <25% Average, else Above Average
      Female: <21% Athletic, <25% Fit, <32% Average, else Above Average
    """

def estimate_lean_mass(body_weight_kg, body_fat_pct):
    """Returns dict: fat_mass_kg, lean_mass_kg"""

def generate_composition_visual(image_bgr, landmarks, composition_result):
    """Draw metrics box + landmark lines on image. Return annotated image."""
```

**Commit**: `git add core/body_composition.py && git commit -m "feat(vision): add body composition estimator with Navy method (personal-v5 mission 1.3)"`

---

### Mission 1.4 — Muscle Definition Scorer
**Priority**: P1 | **New file**
**Tests**: Already at `tests/test_definition_scorer.py` — read it first.

Create `core/definition_scorer.py` (~120 lines):

```python
def score_muscle_definition(image_bgr, contour, muscle_group="bicep"):
    """
    Texture analysis within muscle contour:
    1. Mask ROI inside contour
    2. Grayscale + CLAHE
    3. Gabor filter at 4 orientations (0, 45, 90, 135°) → texture_score
    4. Laplacian variance → edge_density
    5. Local std dev (5x5 kernel) → contrast_score
    6. overall = 0.4*texture + 0.35*edge + 0.25*contrast
    7. Grade: ≥80 Shredded, ≥65 Defined, ≥50 Lean, ≥35 Smooth, else Bulking

    Returns dict: texture_score, edge_density, contrast_score,
                  overall_definition, grade
    """

def generate_definition_heatmap(image_bgr, contour):
    """
    Local Laplacian variance in sliding window → heatmap.
    Warm = high texture, cool = smooth.
    Returns heatmap overlay image.
    """
```

**Commit**: `git add core/definition_scorer.py && git commit -m "feat(vision): add muscle definition scorer (personal-v5 mission 1.4)"`

---

### Mission 2.1 — Visual Hull 3D Mesh Generator
**Priority**: P0 | **New file**
**Tests**: Already at `tests/test_mesh_reconstruction.py` — read it first.

Create `core/mesh_reconstruction.py` (~250 lines):

```python
def reconstruct_mesh_from_silhouettes(contour_front, contour_side,
                                      pixels_per_mm_front, pixels_per_mm_side,
                                      num_slices=40):
    """
    Algorithm:
    1. Get bounding rects for both contours
    2. Normalize heights to match
    3. For each slice (horizontal band):
       - Get width from front contour at that height
       - Get depth from side contour at that height
       - Generate elliptical cross-section vertices (16 points per slice)
    4. Connect adjacent slices → triangle faces
    5. Cap top and bottom with triangle fans
    6. Compute vertex normals (average of adjacent face normals)
    7. Volume via divergence theorem: V = (1/6) * Σ |v0·(v1×v2)| for each face

    Returns dict: vertices (V,3), faces (F,3), normals (V,3),
                  volume_cm3, num_vertices, num_faces
    """

def export_obj(vertices, faces, normals, output_path):
    """Write Wavefront OBJ. Format: v x y z / vn nx ny nz / f v//vn ..."""

def export_stl(vertices, faces, normals, output_path):
    """Write binary STL."""

def generate_mesh_preview_image(vertices, faces, output_path,
                                rotation=(30, 45, 0), size=(800, 600)):
    """
    Simple wireframe render:
    1. Apply rotation matrix
    2. Orthographic projection to 2D
    3. Draw edges with cv2.line
    4. Save PNG
    Returns output_path
    """
```

**Commit**: `git add core/mesh_reconstruction.py && git commit -m "feat(3d): add visual hull mesh reconstruction (personal-v5 mission 2.1)"`

---

### Mission 2.2 — Three.js 3D Viewer
**Priority**: P1 | **New files**

Create `web_app/static/viewer3d/index.html` (~80 lines):
- Dark theme, responsive
- File input for OBJ upload
- Canvas for Three.js
- Controls: wireframe toggle, screenshot button, reset view
- Stats display: vertices, faces, volume

Create `web_app/static/viewer3d/viewer.js` (~150 lines):
- Load Three.js + OrbitControls from CDN (use unpkg or cdnjs)
- OBJLoader from CDN
- Load OBJ from file input or URL param `?obj=path`
- Height-based vertex coloring (blue→green→red)
- OrbitControls (rotate, zoom, pan)
- Wireframe toggle
- Screenshot (canvas.toDataURL → download)
- Measurement mode: click two points → show distance line + label

**Commit**: `feat(3d): add Three.js interactive 3D viewer (personal-v5 mission 2.2)`

---

### Mission 2.3 — 3D Comparison
**Priority**: P2 | **New file**
**Tests**: Already at `tests/test_mesh_comparison.py` — read it first.

Create `core/mesh_comparison.py` (~120 lines):

```python
def compare_meshes(mesh_before, mesh_after):
    """
    For each vertex in mesh_after, find nearest in mesh_before (brute force OK for <5k verts).
    Signed distance = norm(after - nearest_before) * sign(radial direction).

    Returns dict: displacement_map (V,), mean_growth_mm, max_growth_mm,
                  volume_change_cm3, growth_zones (clustered regions)
    """

def export_colored_obj(vertices, faces, displacement_map, output_path):
    """OBJ with vertex colors: green=growth, red=loss, gray=unchanged."""
```

**Commit**: `git add core/mesh_comparison.py && git commit -m "feat(3d): add mesh comparison with displacement mapping (personal-v5 mission 2.3)"`

---

### Mission 3.1 — Body Map Visualization
**Priority**: P0 | **New file**
**Tests**: Already at `tests/test_body_map.py` — read it first.

Create `core/body_map.py` (~200 lines):

```python
def generate_body_map(scan_records, output_path="body_map.png"):
    """
    Draw a front-view human body outline using cv2 drawing primitives.
    Overlay muscle regions as filled polygons, colored by shape_score:
    - Green (>75), Yellow (50-75), Red (<50), Gray (unscanned)
    Labels: muscle name + volume + growth%
    Save to output_path. Return path.
    """

def generate_body_map_data(scan_records):
    """Aggregate scan records → dict keyed by muscle_group with latest metrics."""
```

**Tests**: Already at `tests/test_body_map.py` — read it first.

**Commit**: `git add core/body_map.py && git commit -m "feat(dashboard): add body map visualization (personal-v5 mission 3.1)"`

---

### Mission 3.2 — Progress Timelapse Generator
**Priority**: P1 | **New file**
**Tests**: Already at `tests/test_timelapse.py` — read it first.

Create `core/timelapse.py` (~150 lines):

```python
def generate_progress_timelapse(image_paths, contours, metrics_list,
                                output_path="progress.gif", fps=2):
    """
    Build frames: each image gets contour overlay + metrics text + date + growth%.
    Resize all to same dimensions.
    Save as GIF using cv2 + imageio (or PIL).
    Return output_path.
    """

def generate_comparison_slider_image(img_before, img_after,
                                     contour_before, contour_after,
                                     position=0.5, output_path="slider.png"):
    """Vertical split: left=before, right=after, divider line at position."""
```

**Tests**: Already at `tests/test_timelapse.py` — read it first.

**Commit**: `git add core/timelapse.py && git commit -m "feat(dashboard): add progress timelapse generator (personal-v5 mission 3.2)"`

---

### Mission 3.3 — Personal Dashboard Page
**Priority**: P0 | **New files**

Create `web_app/static/personal/index.html` (~300 lines):
- Dark theme, responsive, clinical aesthetic
- Sections: Header, Body Map, Recent Scans (cards), Progress Charts (Chart.js from CDN), Quick Stats, 3D Viewer link
- API calls: `GET /api/scans/{id}`, `GET /api/customer/{id}/progress`

Create `web_app/static/personal/style.css` (~150 lines):
- CSS variables for dark theme colors
- Grid layout, card components, responsive breakpoints

Create `web_app/static/personal/app.js` (~200 lines):
- Fetch data from API, render body map SVG, init Chart.js charts
- Scan card click → detail view
- "View in 3D" → opens viewer3d/

**Commit**: `feat(dashboard): add personal dashboard page (personal-v5 mission 3.3)`

---

### Mission 4.1 — Video Scan Analyzer
**Priority**: P2 | **New file**

Create `core/video_analyzer.py` (~160 lines):

```python
def analyze_muscle_video(video_path, muscle_group=None, output_dir="video_output"):
    """
    1. Use keyframe_extractor.extract_keyframes(video_path)
    2. For each keyframe: vision_medical.analyze_muscle_growth()
    3. Pick best frame (highest contour solidity)
    4. Aggregate stats across frames
    Returns dict: keyframes, measurements, best_frame, summary
    """
```

**Tests**: Already at `tests/test_video_analyzer.py` — read it first.

**Commit**: `git add core/video_analyzer.py && git commit -m "feat(video): add video scan analyzer (personal-v5 mission 4.1)"`

---

### Mission 4.2 — Session Report
**Priority**: P2 | **New file**

Create `core/session_report.py` (~200 lines):

```python
def generate_session_report(scan_results, output_path="session_report.pdf"):
    """
    ReportLab PDF with all available analysis:
    Cover page, annotated photo, growth analysis, volumetrics,
    circumference, shape score, definition, body composition,
    symmetry, 3D preview, trend chart, recommendations.
    Only include sections where data is available.
    """
```

**Tests**: Already at `tests/test_session_report.py` — read it first.

**Commit**: `git add core/session_report.py && git commit -m "feat(report): add comprehensive session report (personal-v5 mission 4.2)"`

---

## COMPLETION CHECKLIST

After all missions:
```bash
cd C:/Users/MiEXCITE/Projects/muscle_tracker
python -m pytest tests/ -v          # ALL tests must pass
git log --oneline -12               # Verify one commit per mission
git diff --name-only HEAD~10        # Verify no protected files modified
```

## MISSION PRIORITY (if running low on tokens)

Complete in this order: **1.3 → 1.4 → 2.1 → 3.3 → 3.1 → 2.2 → 2.3 → 3.2 → 4.1 → 4.2**

If you can only do some, commit what's done and stop. Incomplete code is worse than skipped missions.
