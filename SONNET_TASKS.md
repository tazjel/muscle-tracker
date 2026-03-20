# Sonnet Tasks — Direct 2D Silhouette Measurement Pipeline

**Agent:** Sonnet | **Date:** 2026-03-20
**Server restart:** YES after Python changes | **Port:** 8000
**Python:** `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
**When done:** Commit with descriptive message.

> Goal: Upgrade body measurement from SMPL-beta-fitting (which fails on real bodies)
> to direct 2D silhouette measurement. Front+side photo widths → circumferences via
> ellipse formula. SMPL used only for 3D visualization afterward.

---

## T1 — Extend Pose Landmark Access

**File:** `core/body_segmentation.py`
**Action:** Add function after existing `get_pose_landmarks()` (~line 107)
**Depends on:** Nothing

### What to do
1. Read `core/body_segmentation.py` — understand `get_pose_landmarks()` and `_POSE_LANDMARK_NAMES`
2. Add `_FULL_LANDMARK_NAMES` dict mapping all 33 MediaPipe Pose landmarks:
   ```
   NOSE=0, LEFT_EYE_INNER=1, LEFT_EYE=2, LEFT_EYE_OUTER=3,
   RIGHT_EYE_INNER=4, RIGHT_EYE=5, RIGHT_EYE_OUTER=6,
   LEFT_EAR=7, RIGHT_EAR=8, MOUTH_LEFT=9, MOUTH_RIGHT=10,
   LEFT_SHOULDER=11, RIGHT_SHOULDER=12, LEFT_ELBOW=13, RIGHT_ELBOW=14,
   LEFT_WRIST=15, RIGHT_WRIST=16, LEFT_PINKY=17, RIGHT_PINKY=18,
   LEFT_INDEX=19, RIGHT_INDEX=20, LEFT_THUMB=21, RIGHT_THUMB=22,
   LEFT_HIP=23, RIGHT_HIP=24, LEFT_KNEE=25, RIGHT_KNEE=26,
   LEFT_ANKLE=27, RIGHT_ANKLE=28, LEFT_HEEL=29, RIGHT_HEEL=30,
   LEFT_FOOT_INDEX=31, RIGHT_FOOT_INDEX=32
   ```
3. Add `get_full_pose_landmarks(image_bgr: np.ndarray) -> dict | None`:
   - Same pattern as `get_pose_landmarks()` but iterate `_FULL_LANDMARK_NAMES`
   - Use visibility threshold **0.3** (not 0.5) — heel/foot landmarks are sometimes partially visible
   - Return dict of name → (x_px, y_px) or None if pose not detected

### Test
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
from core.body_segmentation import get_full_pose_landmarks
print('Function imported successfully')
"
```

---

## T2 — Create Width Sampling Module (Part 1)

**File:** `core/silhouette_measure.py` (CREATE NEW)
**Action:** New module with core width-sampling functions
**Depends on:** Nothing (parallel with T1)

### What to do
1. Create `core/silhouette_measure.py` with imports: `numpy`, `math`
2. Implement `_mask_width_at_y(mask, y_px, band_px=5)`:
   - `mask` is (H, W) uint8, 255=body
   - Scan rows `[y-band_px, y+band_px]` (clipped to bounds)
   - For each row: find leftmost and rightmost non-zero pixel
   - Return max width (pixels) across scanned rows, or 0.0 if empty

3. Implement `_find_widest_in_band(mask, y_center_px, band_fraction=0.05)`:
   - `band_fraction` = fraction of image height
   - Search all rows in band, return `(max_width_px, best_y_px)`

4. Implement `measure_widths_at_landmarks(mask, landmarks, ratio_mm_px)`:
   - `landmarks` is dict from `get_full_pose_landmarks()`: name → (x, y)
   - Derive measurement Y-heights:
     ```python
     shoulder_mid_y = (landmarks['LEFT_SHOULDER'][1] + landmarks['RIGHT_SHOULDER'][1]) / 2
     hip_mid_y = (landmarks['LEFT_HIP'][1] + landmarks['RIGHT_HIP'][1]) / 2
     nose_y = landmarks.get('NOSE', landmarks.get('LEFT_EAR', (0, shoulder_mid_y - 50)))[1]

     neck_y = shoulder_mid_y - 0.4 * (shoulder_mid_y - nose_y)
     chest_y = shoulder_mid_y + 0.3 * (hip_mid_y - shoulder_mid_y)
     waist_y = shoulder_mid_y + 0.6 * (hip_mid_y - shoulder_mid_y)
     hip_y = hip_mid_y
     ```
   - For torso (neck, chest, waist, hip): use `_find_widest_in_band()` on full mask
   - For limbs (thigh, calf, bicep): split mask into left/right halves using landmark X positions, measure each half independently, average
     ```python
     # Thigh example:
     left_hip_y = landmarks['LEFT_HIP'][1]
     left_knee_y = landmarks['LEFT_KNEE'][1]
     thigh_y = left_hip_y + 0.3 * (left_knee_y - left_hip_y)
     left_x = int(landmarks['LEFT_HIP'][0])
     left_half = mask[:, :left_x + mask.shape[1]//4]  # generous half
     left_thigh_w = _find_widest_in_band(left_half, int(thigh_y))[0]
     # Same for right, average both
     ```
   - Multiply all pixel widths by `ratio_mm_px`
   - Return: `{neck_width_mm, chest_width_mm, waist_width_mm, hip_width_mm, thigh_width_mm, calf_width_mm, bicep_width_mm, shoulder_width_mm}`
   - `shoulder_width_mm` = Euclidean distance LEFT_SHOULDER↔RIGHT_SHOULDER × ratio

### Test
```bash
$PY -c "
import numpy as np
from core.silhouette_measure import _mask_width_at_y, _find_widest_in_band
mask = np.zeros((1000, 500), dtype=np.uint8)
mask[100:900, 150:350] = 255
w = _mask_width_at_y(mask, 500)
print(f'Width at y=500: {w} (expect 200)')
w2, y2 = _find_widest_in_band(mask, 500, 0.05)
print(f'Widest: {w2} at y={y2}')
assert abs(w - 200) < 2
print('PASS')
"
```

---

## T3 — Height and Length Measurements (Part 2)

**File:** `core/silhouette_measure.py` (append)
**Action:** Add height and segment length functions
**Depends on:** T2

### What to do
1. Add `measure_height_from_mask(mask, ratio_mm_px)`:
   - Find min/max Y of non-zero pixels in mask
   - Return `(max_y - min_y) * ratio_mm_px` in mm, or 0.0 if empty

2. Add `measure_lengths_from_landmarks(landmarks, ratio_mm_px, mask=None)`:
   - Helper: `_dist(a, b) = sqrt((a[0]-b[0])^2 + (a[1]-b[1])^2)`
   - `shoulder_width_mm` = `_dist(LEFT_SHOULDER, RIGHT_SHOULDER) * ratio`
   - `arm_length_mm` = average of (L_SHOULDER→L_ELBOW + L_ELBOW→L_WRIST) and right side, × ratio
   - `torso_length_mm` = `_dist(shoulder_midpoint, hip_midpoint) * ratio`
   - `floor_to_knee_mm` = if mask provided, `(max_y_of_mask - knee_midpoint_y) * ratio`; else estimate from ankle
   - Return: `{shoulder_width_mm, arm_length_mm, torso_length_mm, floor_to_knee_mm}`

### Test
```bash
$PY -c "
import numpy as np
from core.silhouette_measure import measure_height_from_mask, measure_lengths_from_landmarks
mask = np.zeros((2000, 1000), dtype=np.uint8)
mask[100:1900, 300:700] = 255
h = measure_height_from_mask(mask, 1.0)
print(f'Height: {h} mm (expect 1800)')
lm = {
    'LEFT_SHOULDER': (400, 300), 'RIGHT_SHOULDER': (600, 300),
    'LEFT_HIP': (420, 900), 'RIGHT_HIP': (580, 900),
    'LEFT_KNEE': (420, 1300), 'RIGHT_KNEE': (580, 1300),
    'LEFT_ELBOW': (350, 500), 'RIGHT_ELBOW': (650, 500),
    'LEFT_WRIST': (320, 700), 'RIGHT_WRIST': (680, 700),
}
lengths = measure_lengths_from_landmarks(lm, 1.0, mask)
for k, v in sorted(lengths.items()): print(f'  {k}: {v:.1f}')
print('PASS')
"
```

---

## T4 — Circumference Assembly (Part 3)

**File:** `core/silhouette_measure.py` (append)
**Action:** Convert front+side widths to circumferences
**Depends on:** T2

### What to do
1. **READ** `core/circumference.py` first — it already has `estimate_circumference_from_two_views(width_front_mm, width_side_mm)` returning mm
2. Add import at top: `from core.circumference import estimate_circumference_from_two_views`
3. Implement `compute_circumferences(front_widths, side_widths=None)`:
   - Key mapping (strip `_width_mm` suffix, add `_circumference_cm` suffix):
     ```
     neck_width_mm     → neck_circumference_cm
     chest_width_mm    → chest_circumference_cm
     waist_width_mm    → waist_circumference_cm
     hip_width_mm      → hip_circumference_cm
     thigh_width_mm    → thigh_circumference_cm
     calf_width_mm     → calf_circumference_cm
     bicep_width_mm    → bicep_circumference_cm
     ```
   - If `side_widths` provided: `circ_cm = estimate_circumference_from_two_views(front_w, side_w) / 10.0`
   - If `side_widths` is None (single-view fallback):
     ```python
     a = front_w / 2.0
     b = 0.6 * a
     circ_mm = math.pi * (3*(a+b) - math.sqrt((3*a+b)*(a+3*b)))
     circ_cm = circ_mm / 10.0
     ```
   - Round all values to 1 decimal
   - Return dict with `_circumference_cm` keys

### Test
```bash
$PY -c "
from core.silhouette_measure import compute_circumferences
front = {'chest_width_mm': 320, 'waist_width_mm': 290, 'hip_width_mm': 310,
         'neck_width_mm': 120, 'thigh_width_mm': 180, 'calf_width_mm': 120,
         'bicep_width_mm': 110}
side  = {'chest_width_mm': 220, 'waist_width_mm': 210, 'hip_width_mm': 240,
         'neck_width_mm': 110, 'thigh_width_mm': 160, 'calf_width_mm': 110,
         'bicep_width_mm': 100}
dual = compute_circumferences(front, side)
single = compute_circumferences(front)
print('Dual:')
for k, v in sorted(dual.items()): print(f'  {k}: {v} cm')
print('Single:')
for k, v in sorted(single.items()): print(f'  {k}: {v} cm')
assert 60 < dual['chest_circumference_cm'] < 130
print('PASS')
"
```

---

## T5 — Full Measurement Orchestrator (Part 4)

**File:** `core/silhouette_measure.py` (append)
**Action:** Main function that takes photos → returns all measurements
**Depends on:** T1, T2, T3, T4

### What to do
1. Add imports at top of file:
   ```python
   import cv2
   from core.silhouette_extractor import extract_silhouette
   from core.body_segmentation import get_full_pose_landmarks
   from core.calibration import get_px_to_mm_ratio
   ```

2. **IMPORTANT:** Before coding, **read the actual function signatures** in these files:
   - `core/silhouette_extractor.py` — check what `extract_silhouette()` returns
   - `core/calibration.py` — check `get_px_to_mm_ratio()` params
   - `core/body_composition.py` — check `estimate_body_composition()` params

3. Implement `measure_body_from_photos(front_image_path, side_image_path=None, camera_distance_cm=100.0, user_height_cm=None, user_weight_kg=None, gender='male')`:

   Steps inside:
   - Load front image with `cv2.imread()`
   - Call `extract_silhouette(front_image_path, camera_distance_cm)` → get mask and ratio
   - Call `get_full_pose_landmarks(front_img)` → landmarks dict
   - If `user_height_cm` provided, cross-check: measure mask height in mm, compare to expected, recalibrate ratio if >10% off
   - Call `measure_widths_at_landmarks(mask, landmarks, ratio)` for front
   - If side photo provided, repeat extraction + landmarks + widths for side
   - Call `compute_circumferences(front_widths, side_widths)`
   - Call `measure_height_from_mask()` and `measure_lengths_from_landmarks()`
   - Assemble measurements dict with keys: `height_cm`, all `*_circumference_cm`, `shoulder_width_cm`, `arm_length_cm`, `torso_length_cm`, `floor_to_knee_cm`
   - If weight provided: add `weight_est_kg` and `bmi_est`
   - Return: `{status, measurements, circumferences, lengths, height_cm, body_composition, confidence ('high'|'estimated'), debug}`

   Error handling: wrap each step in try/except, return `{status: 'error', message: ...}` on failure

### Test
```bash
$PY -c "
from core.silhouette_measure import measure_body_from_photos
import glob
imgs = glob.glob('uploads/*.jpg') + glob.glob('scripts/dual_captures/*.jpg')
if imgs:
    r = measure_body_from_photos(imgs[0], camera_distance_cm=100)
    print(f'Status: {r[\"status\"]}')
    if r['status'] == 'success':
        for k, v in sorted(r['measurements'].items()): print(f'  {k}: {v}')
else:
    print('No test images found — upload a body photo to uploads/ first')
"
```

---

## T6 — SMPL GLB Generation from Measurements (Part 5)

**File:** `core/silhouette_measure.py` (append)
**Action:** Generate 3D GLB for the measurement viewer
**Depends on:** T5

### What to do
1. Add import: `from core.smpl_optimizer import optimize_from_profile`
2. Implement `generate_measurement_glb(measurements, output_path)`:
   ```python
   def generate_measurement_glb(measurements, output_path):
       import os, json, trimesh

       # Build profile dict for optimizer
       profile = {}
       key_map = ['height_cm', 'chest_circumference_cm', 'waist_circumference_cm',
                   'hip_circumference_cm', 'neck_circumference_cm', 'shoulder_width_cm',
                   'torso_length_cm', 'arm_length_cm', 'floor_to_knee_cm',
                   'thigh_circumference_cm', 'bicep_circumference_cm']
       for key in key_map:
           if key in measurements and measurements[key]:
               profile[key] = measurements[key]
       if 'weight_est_kg' in measurements:
           profile['weight_kg'] = measurements['weight_est_kg']

       result = optimize_from_profile(profile)

       os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
       mesh = trimesh.Trimesh(vertices=result['vertices'] / 1000.0,
                               faces=result['faces'], process=False)
       mesh.export(output_path)

       json_path = output_path.replace('.glb', '_data.json')
       viewer_data = {
           'profile': measurements,
           'fitted': result['measurements'],
           'rings': result['rings'],
           'betas': [round(float(b), 4) for b in result['betas']],
       }
       with open(json_path, 'w') as f:
           json.dump(viewer_data, f, indent=2)

       return {
           'glb_path': output_path,
           'json_path': json_path,
           'betas': result['betas'].tolist(),
           'rings': result['rings'],
           'measurements_fitted': result['measurements'],
       }
   ```

### Test
```bash
$PY -c "
from core.silhouette_measure import generate_measurement_glb
import os
meas = {'height_cm': 168, 'chest_circumference_cm': 97,
        'waist_circumference_cm': 90, 'hip_circumference_cm': 92,
        'neck_circumference_cm': 35, 'shoulder_width_cm': 37}
r = generate_measurement_glb(meas, 'meshes/test_measure.glb')
print(f'GLB: {os.path.exists(r[\"glb_path\"])}')
print(f'JSON: {os.path.exists(r[\"json_path\"])}')
"
```

---

## T7 — Synthetic Validation Script

**File:** `scripts/test_silhouette_measure.py` (CREATE NEW)
**Action:** Validate measurement accuracy against known SMPL bodies
**Depends on:** T2, T3, T4

### What to do
1. Use `smpl_optimizer.smpl_forward(betas)` to generate mesh with known measurements
2. Use `smpl_optimizer.render_silhouette(verts, faces, 'front')` and `'side'` for 2D contours
3. Rasterize contours into 1000×2000 binary masks (draw filled polygon)
4. Derive synthetic landmarks from SMPL joint positions:
   ```python
   verts, joints = smpl_forward(betas)
   # joints is (24,3) in mm, Z-up
   # Front view: project (X, Z) to image coords
   # Map joint indices: 0=pelvis, 1=left_hip, 2=right_hip, 12=neck, 15=head, etc.
   ```
5. Run `measure_widths_at_landmarks()` on synthetic masks
6. Run `compute_circumferences()` with front+side widths
7. Compare against `smpl_optimizer.extract_measurements()` ground truth
8. Test 3 body types: betas=[0,...], [-2,1,0,...,0], [2,-1,0,...,0]
9. Print error table with % diff per measurement
10. Print PASS/FAIL (threshold: <5% error on circumferences)

### Test
```bash
$PY scripts/test_silhouette_measure.py
```

---

## T8 — REST API Endpoint

**File:** `web_app/controllers.py`
**Action:** Add `POST /api/customer/<id>/measure_body`
**Depends on:** T5, T6

### What to do
1. **Grep** `web_app/controllers.py` for `upload_scan` to see the auth + file handling pattern
2. **Grep** for `@action` decorator pattern
3. Add new endpoint after `generate_body_model` (around line 2950):

   ```
   POST /api/customer/<customer_id>/measure_body
   Body (multipart/form-data):
     front: JPEG (required)
     side: JPEG (optional)
     camera_distance_cm: float (default 100)
     gender: string (default 'male')
   ```

4. Implementation:
   - Auth: copy JWT validation pattern from `upload_scan`
   - Save uploaded files to `uploads/measure_front_{id}.jpg` and `uploads/measure_side_{id}.jpg`
   - Load customer profile for height/weight if available
   - Call `silhouette_measure.measure_body_from_photos(front_path, side_path, ...)`
   - Call `silhouette_measure.generate_measurement_glb(measurements, glb_path)`
   - Return:
     ```json
     {
       "status": "success",
       "measurements": {...},
       "body_composition": {...},
       "confidence": "high",
       "glb_url": "/web_app/static/meshes/body_1.glb",
       "measurement_viewer_url": "/web_app/static/viewer3d/measurement_viewer.html"
     }
     ```

### Test
```bash
# Restart server, then:
TOKEN=$(curl -s http://localhost:8000/web_app/api/login -X POST \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@muscle.com","password":"demo123"}' | \
  $PY -c 'import sys,json; print(json.load(sys.stdin).get("token",""))')

curl -s http://localhost:8000/web_app/api/customer/1/measure_body \
  -X POST -H "Authorization: Bearer $TOKEN" \
  -F "front=@uploads/test_front.jpg" | $PY -m json.tool
```

---

## T9 — Demo CLI Script

**File:** `scripts/measure_body_demo.py` (CREATE NEW)
**Action:** Command-line demo with formatted output
**Depends on:** T5, T6

### What to do
Create argparse script:
```
Usage: python measure_body_demo.py --front photo.jpg [--side side.jpg] [--distance 100] [--height 168] [--weight 63]
```

1. Call `measure_body_from_photos()` with args
2. Print formatted table:
   ```
   ══════════════════════════════════════════════
     BODY MEASUREMENTS (2D Silhouette Analysis)
   ══════════════════════════════════════════════
     Measurement          Value     Confidence
   ──────────────────────────────────────────────
     Height              168.2 cm    high
     Chest circ.          96.5 cm    high
     ...
   ```
3. If `--height` given, show measured vs known comparison
4. Call `generate_measurement_glb()` and print viewer URL:
   ```
   View: http://192.168.100.16:8000/web_app/static/viewer3d/measurement_viewer.html
   ```

### Test
```bash
$PY scripts/measure_body_demo.py --front uploads/test_front.jpg --distance 100
```

---

## T10 — Flutter App Integration

**File:** `companion_app/lib/main.dart`
**Action:** Add "Body Measurement" capture mode
**Depends on:** T8

### What to do
1. **Grep** `main.dart` for `_captureMode` and `_uploadScan` first
2. Add "Body Measurement" option in mode selector UI
3. When selected, upload calls `/api/customer/<id>/measure_body` instead of `/api/upload_scan/<id>`
4. Parse response, show measurements in a results card
5. Add "View 3D" button → open measurement_viewer.html in WebView

**IMPORTANT:** This file is 1900+ lines. Always grep before reading. Only add minimum code.

### Test
```bash
cd companion_app
/c/Users/MiEXCITE/development/flutter/bin/flutter.bat build apk --debug
```

---

## Execution Order

```
Phase 1 (parallel):  T1 + T2
Phase 2 (parallel):  T3 + T7  (after T2)
Phase 3:             T4       (after T2)
Phase 4:             T5       (after T1, T2, T3, T4)
Phase 5:             T6       (after T5)
Phase 6 (parallel):  T8 + T9  (after T5, T6)
Phase 7:             T10      (after T8)
```

## Key Existing Files (DO NOT recreate these functions)

| Function | File | Purpose |
|----------|------|---------|
| `estimate_circumference_from_two_views()` | `core/circumference.py:29` | Ellipse circumference from 2 widths |
| `extract_silhouette()` | `core/silhouette_extractor.py:21` | Body mask from photo |
| `get_px_to_mm_ratio()` | `core/calibration.py:91` | Pixel to mm calibration |
| `get_pose_landmarks()` | `core/body_segmentation.py:78` | 10 pose landmarks |
| `estimate_body_composition()` | `core/body_composition.py:13` | BMI + body fat |
| `optimize_from_profile()` | `core/smpl_optimizer.py:432` | Fit SMPL to measurements |
| `smpl_forward()` | `core/smpl_optimizer.py:68` | SMPL forward pass |
| `extract_measurements()` | `core/smpl_optimizer.py:356` | Measure SMPL mesh |
| `render_silhouette()` | `core/smpl_optimizer.py:143` | 2D contour from mesh |
