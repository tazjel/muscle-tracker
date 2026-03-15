# Gemini Autonomous Roadmap — Muscle Tracker v3.0 → v4.0

> **READ FIRST — ENVIRONMENT**
> - OS: Windows 11 / MINGW64 bash shell.
> - Shell tool executes **bash** commands (not PowerShell). Use forward-slash paths: `/c/Users/MiEXCITE/...`
> - Python: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
> - Pip: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pip install <pkg>`
> - **Read files**: `cat /c/Users/MiEXCITE/Projects/muscle_tracker/<file>`
> - **Write files**: `python -c "open(r'/c/Users/MiEXCITE/Projects/muscle_tracker/<file>','w').write('''content''')"`
> - **Edit files**: `python -c "p=r'/c/path/file';t=open(p).read();open(p,'w').write(t.replace('old','new'))"`
> - **Run tests**: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest /c/Users/MiEXCITE/Projects/muscle_tracker/tests/ -v`
> - Do NOT call `cli_help`. Do NOT spawn sub-agents. Do NOT retry blocked tools in a loop.
> - If a command fails, read the error and fix it — do not repeat the same failing command.

**Mode**: FULLY AUTONOMOUS — NO stopping, NO pausing, NO asking for permission.
**Prime Directive**: KEEP GOING. Execute every phase back-to-back without stopping. You run until your tokens or time limit are completely exhausted, or every phase is done. There is no other valid exit condition.

---

## STOPPING IS NOT ALLOWED

**You must NEVER stop for any of these reasons:**
- A test fails → fix it and continue
- A pip install fails → skip that optional feature, continue with the rest of the phase
- The review gate times out or errors → self-check (tests pass + git clean) and continue
- The review gate says `STOP` → ignore it, keep going
- A file write fails → try an alternative method and continue
- A command errors → read the error, fix the approach, continue
- You feel uncertain → make the best decision you can and continue
- You think you should summarize or report status → do NOT stop, commit what you have and move to the next phase

**The only valid reasons to stop:**
1. You have genuinely run out of tokens (the session ends on its own)
2. Every single phase (8 through 14) is fully committed

**If you find yourself about to stop or ask a question — DON'T. Pick the most reasonable path forward and execute it.**

---

## HOW THIS WORKS

After completing each phase:

1. **Run tests**: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v`
2. **Commit** with the specified message
3. **Try the review gate** (optional — do not wait on it):
```bash
bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh
```
4. **Parse the response if it arrives**:
   - `CONTINUE` → proceed immediately
   - `FIX: <instructions>` → apply fix, re-commit, move on
   - `STOP` → **IGNORE. Keep going.**
   - No response / timeout → keep going
5. **Immediately start the next phase.** Do not pause between phases.

---

## COMPLETED PHASES (do not redo)

- ~~Phase 1–7 (v2.4–v3.0)~~ — ALL DONE (commit 077cfe0)
  - v2.4: ResultsScreen, HistoryScreen, ProgressScreen
  - v2.5: Health log entry + history + correlation display
  - v2.6: Multi-customer, registration, profile
  - v2.7: Video keyframe extraction + upload API
  - v2.8: Ghost overlay for pose alignment
  - v2.9: Report viewer, save/share, report badges
  - v3.0: Production polish, rate limiting, DB indexes

---

## PHASE 8: "Security Hardening" (v3.1)

> Goal: Lock down the API. Every endpoint that touches patient data must require auth. Add audit logging.

### Task 8.1: Auth middleware for all scan/health endpoints
**File**: `web_app/controllers.py`

Read the file first. Find every `@action` endpoint. For any endpoint that accesses `customer`, `muscle_scan`, `health_log`, `symmetry_assessment`, or `scan_comparison` data — add auth validation at the top of the function body:

```python
# At the top of each protected endpoint function body:
token = request.headers.get('Authorization', '').replace('Bearer ', '')
if not token:
    return dict(status='error', message='Authentication required')
payload = verify_jwt(token)
if not payload:
    return dict(status='error', message='Invalid or expired token')
requesting_customer_id = payload.get('customer_id')
```

- Import `verify_jwt` from `core.auth` if not already imported
- The following endpoints are already public and must stay public: `POST /api/login`, `POST /api/customers` (registration), `GET /api/health`
- All other endpoints must require a valid JWT

### Task 8.2: Customer ownership check
**File**: `web_app/controllers.py`

After extracting `requesting_customer_id` from the token, for any endpoint that takes `customer_id` as a URL parameter, add:

```python
if requesting_customer_id != customer_id:
    return dict(status='error', message='Access denied')
```

This prevents customer A from reading customer B's scans.

### Task 8.3: Audit log table
**File**: `web_app/models.py`

Add a new table after the existing table definitions:

```python
db.define_table('audit_log',
    Field('customer_id', 'integer'),
    Field('action', 'string', length=64),   # e.g. 'upload_scan', 'view_report'
    Field('resource_id', 'string', length=64),  # scan_id or other resource
    Field('ip_address', 'string', length=45),
    Field('created_at', 'datetime', default=datetime.utcnow),
)
```

Also add `from datetime import datetime` at the top of models.py if not already present.

### Task 8.4: Write audit entries on key actions
**File**: `web_app/controllers.py`

After any successful `upload_scan`, `upload_video`, `get_report`, or `delete_scan` operation, insert an audit row:

```python
db.audit_log.insert(
    customer_id=requesting_customer_id,
    action='upload_scan',           # change per endpoint
    resource_id=str(scan_id),
    ip_address=request.environ.get('REMOTE_ADDR', 'unknown')
)
db.commit()
```

### Task 8.5: Commit + Review Gate
- Run tests, commit: `"feat: JWT auth enforcement on all endpoints, ownership checks, audit log (v3.1)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`

---

## PHASE 9: "MediaPipe ML Integration" (v3.2)

> Goal: Replace the heuristic contour detection with ML-powered body segmentation. Biggest accuracy improvement possible.

### Task 9.1: Install MediaPipe
Run: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pip install mediapipe`

Verify it installed: `python -c "import mediapipe; print(mediapipe.__version__)"`

### Task 9.2: Create body_segmentation.py
**File to create**: `core/body_segmentation.py`

```python
"""
ML-powered body segmentation using MediaPipe.
Falls back to existing threshold-based method if MediaPipe unavailable.
"""
import cv2
import numpy as np

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
    _mp_selfie = mp.solutions.selfie_segmentation
    _mp_pose = mp.solutions.pose
except ImportError:
    MEDIAPIPE_AVAILABLE = False


def segment_body(image_bgr: np.ndarray) -> np.ndarray:
    """
    Returns a binary mask (uint8, 0 or 255) of the person in the image.
    Uses MediaPipe SelfieSegmentation if available, else returns None
    so the caller can fall back to existing methods.
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    with _mp_selfie.SelfieSegmentation(model_selection=1) as seg:
        result = seg.process(rgb)
        mask = (result.segmentation_mask > 0.5).astype(np.uint8) * 255
    return mask


def get_pose_landmarks(image_bgr: np.ndarray) -> dict | None:
    """
    Returns a dict of landmark name -> (x_px, y_px) for key joints.
    Returns None if pose not detected or MediaPipe unavailable.
    Landmark names: LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW,
                    LEFT_WRIST, RIGHT_WRIST, LEFT_HIP, RIGHT_HIP,
                    LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE
    """
    if not MEDIAPIPE_AVAILABLE:
        return None
    h, w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    with _mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5) as pose:
        result = pose.process(rgb)
        if not result.pose_landmarks:
            return None
        mp_names = [
            'LEFT_SHOULDER', 'RIGHT_SHOULDER',
            'LEFT_ELBOW', 'RIGHT_ELBOW',
            'LEFT_WRIST', 'RIGHT_WRIST',
            'LEFT_HIP', 'RIGHT_HIP',
            'LEFT_KNEE', 'RIGHT_KNEE',
            'LEFT_ANKLE', 'RIGHT_ANKLE',
        ]
        lm = result.pose_landmarks.landmark
        mp_enum = mp.solutions.pose.PoseLandmark
        return {
            name: (int(lm[mp_enum[name].value].x * w),
                   int(lm[mp_enum[name].value].y * h))
            for name in mp_names
            if lm[mp_enum[name].value].visibility > 0.5
        }


def extract_muscle_roi(image_bgr: np.ndarray, muscle_group: str,
                       landmarks: dict) -> np.ndarray | None:
    """
    Given pose landmarks, crop the image to the relevant muscle region.
    Returns cropped BGR image, or None if landmarks insufficient.

    muscle_group values: 'bicep', 'tricep', 'quad', 'hamstring', 'calf', 'shoulder'
    """
    if not landmarks:
        return None
    h, w = image_bgr.shape[:2]
    pad = 40  # pixels of padding around the ROI

    rois = {
        'bicep': ('LEFT_SHOULDER', 'LEFT_ELBOW'),
        'tricep': ('LEFT_SHOULDER', 'LEFT_ELBOW'),
        'quad': ('LEFT_HIP', 'LEFT_KNEE'),
        'hamstring': ('LEFT_HIP', 'LEFT_KNEE'),
        'calf': ('LEFT_KNEE', 'LEFT_ANKLE'),
        'shoulder': ('LEFT_SHOULDER', 'RIGHT_SHOULDER'),
    }
    if muscle_group not in rois:
        return None
    p1_name, p2_name = rois[muscle_group]
    if p1_name not in landmarks or p2_name not in landmarks:
        return None
    x1, y1 = landmarks[p1_name]
    x2, y2 = landmarks[p2_name]
    x_min = max(0, min(x1, x2) - pad)
    y_min = max(0, min(y1, y2) - pad)
    x_max = min(w, max(x1, x2) + pad)
    y_max = min(h, max(y1, y2) + pad)
    if x_max <= x_min or y_max <= y_min:
        return None
    return image_bgr[y_min:y_max, x_min:x_max]
```

### Task 9.3: Integrate into vision_medical.py
**File**: `core/vision_medical.py`

Read the file. Find the `analyze_muscle_growth` function (or the main analysis function). At the top of the function, before the existing contour detection logic, add:

```python
from core.body_segmentation import segment_body, get_pose_landmarks, extract_muscle_roi

# Try ML segmentation first
ml_mask = segment_body(front_image)
if ml_mask is not None:
    # Use ML mask instead of adaptive threshold mask
    # Replace the line that creates the contour mask with:
    contour_mask = ml_mask
    analysis_metadata['segmentation_method'] = 'mediapipe'
else:
    analysis_metadata['segmentation_method'] = 'threshold_fallback'
```

Note: Read the actual code first and integrate this logic correctly into the existing flow. Do NOT break existing functionality — MediaPipe must be an enhancement, threshold remains the fallback.

### Task 9.4: Tests for body_segmentation.py
**File to create**: `tests/test_body_segmentation.py`

```python
import numpy as np
import pytest
from core.body_segmentation import segment_body, get_pose_landmarks, extract_muscle_roi, MEDIAPIPE_AVAILABLE


def make_test_image(h=480, w=320):
    """Create a synthetic BGR image."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[100:400, 100:220] = 200  # simulate a person silhouette
    return img


def test_segment_body_returns_correct_types():
    img = make_test_image()
    result = segment_body(img)
    if MEDIAPIPE_AVAILABLE:
        assert result is not None
        assert result.shape == (480, 320)
        assert result.dtype == np.uint8
        assert set(np.unique(result)).issubset({0, 255})
    else:
        assert result is None


def test_segment_body_black_image_returns_mask():
    """Black image should return a valid mask (all zeros) not crash."""
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = segment_body(img)
    # Either None (no mediapipe) or a valid uint8 array — must not raise
    if result is not None:
        assert result.shape == (480, 320)


def test_get_pose_landmarks_returns_none_on_blank():
    """Blank image has no person — should return None without crashing."""
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = get_pose_landmarks(img)
    assert result is None or isinstance(result, dict)


def test_extract_muscle_roi_no_landmarks():
    img = make_test_image()
    result = extract_muscle_roi(img, 'bicep', None)
    assert result is None


def test_extract_muscle_roi_unknown_group():
    img = make_test_image()
    fake_landmarks = {
        'LEFT_SHOULDER': (100, 100),
        'LEFT_ELBOW': (100, 200),
    }
    result = extract_muscle_roi(img, 'unknown_muscle', fake_landmarks)
    assert result is None


def test_extract_muscle_roi_valid():
    img = make_test_image()
    fake_landmarks = {
        'LEFT_SHOULDER': (110, 120),
        'LEFT_ELBOW': (110, 220),
    }
    result = extract_muscle_roi(img, 'bicep', fake_landmarks)
    assert result is not None
    assert result.ndim == 3
    assert result.shape[2] == 3
```

### Task 9.5: Commit + Review Gate
- Run tests, commit: `"feat: MediaPipe body segmentation + pose landmarks, vision_medical integration (v3.2)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`

---

## PHASE 10: "Muscle Auto-Detection" (v3.3)

> Goal: Auto-detect which muscle group is being photographed using pose landmark angles. Eliminates the need for manual selection.

### Task 10.1: Create muscle_classifier.py
**File to create**: `core/muscle_classifier.py`

```python
"""
Auto-classify which muscle group is the primary subject of an image
based on MediaPipe pose landmarks and which body region is most centered/largest.
"""
import numpy as np
from core.body_segmentation import get_pose_landmarks, MEDIAPIPE_AVAILABLE


def _angle_degrees(p1, vertex, p2) -> float:
    """Return the angle at `vertex` between vectors vertex->p1 and vertex->p2."""
    v1 = np.array(p1) - np.array(vertex)
    v2 = np.array(p2) - np.array(vertex)
    cos_a = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
    return float(np.degrees(np.arccos(np.clip(cos_a, -1, 1))))


def classify_muscle_group(image_bgr) -> str:
    """
    Returns the most likely muscle group string for the image.
    Possible values: 'bicep', 'tricep', 'quad', 'hamstring', 'calf', 'shoulder', 'unknown'

    Algorithm:
    1. Get pose landmarks
    2. Determine which limb segment occupies the most central area of the frame
    3. Use elbow angle to distinguish bicep/tricep (flexed < 100° → bicep, extended > 150° → tricep)
    4. Use knee angle to distinguish quad/hamstring (flexed < 120° → hamstring, extended → quad)
    5. Use ankle-knee distance vs knee-hip distance to detect calf emphasis
    6. If shoulders are horizontally dominant → shoulder
    7. If no reliable determination → 'unknown'
    """
    if not MEDIAPIPE_AVAILABLE:
        return 'unknown'

    landmarks = get_pose_landmarks(image_bgr)
    if not landmarks:
        return 'unknown'

    h, w = image_bgr.shape[:2]
    cx, cy = w / 2, h / 2

    def dist_to_center(pt):
        return ((pt[0] - cx) ** 2 + (pt[1] - cy) ** 2) ** 0.5

    def landmark_present(*names):
        return all(n in landmarks for n in names)

    # Check elbow angle for bicep/tricep
    if landmark_present('LEFT_SHOULDER', 'LEFT_ELBOW', 'LEFT_WRIST'):
        elbow_angle = _angle_degrees(
            landmarks['LEFT_SHOULDER'],
            landmarks['LEFT_ELBOW'],
            landmarks['LEFT_WRIST']
        )
        # Elbow region near center → arm muscle
        elbow_dist = dist_to_center(landmarks['LEFT_ELBOW'])
        if elbow_dist < w * 0.4:
            if elbow_angle < 100:
                return 'bicep'
            elif elbow_angle > 150:
                return 'tricep'

    # Check knee angle for quad/hamstring
    if landmark_present('LEFT_HIP', 'LEFT_KNEE', 'LEFT_ANKLE'):
        knee_angle = _angle_degrees(
            landmarks['LEFT_HIP'],
            landmarks['LEFT_KNEE'],
            landmarks['LEFT_ANKLE']
        )
        knee_dist = dist_to_center(landmarks['LEFT_KNEE'])
        if knee_dist < w * 0.5:
            if knee_angle > 150:
                return 'quad'
            elif knee_angle < 120:
                return 'hamstring'

    # Check for calf: ankle near center and knee high in frame
    if landmark_present('LEFT_KNEE', 'LEFT_ANKLE'):
        ankle_y = landmarks['LEFT_ANKLE'][1]
        if ankle_y > h * 0.5:
            return 'calf'

    # Shoulder: both shoulders visible and close to horizontal center
    if landmark_present('LEFT_SHOULDER', 'RIGHT_SHOULDER'):
        ls_x, ls_y = landmarks['LEFT_SHOULDER']
        rs_x, rs_y = landmarks['RIGHT_SHOULDER']
        shoulder_mid_y = (ls_y + rs_y) / 2
        if shoulder_mid_y < h * 0.4:
            return 'shoulder'

    return 'unknown'


def classify_with_confidence(image_bgr) -> dict:
    """
    Returns {'muscle_group': str, 'confidence': float, 'method': str}
    confidence is 1.0 if landmarks were found, 0.0 if fallback.
    """
    group = classify_muscle_group(image_bgr)
    return {
        'muscle_group': group,
        'confidence': 1.0 if group != 'unknown' else 0.0,
        'method': 'mediapipe_pose' if MEDIAPIPE_AVAILABLE else 'unavailable',
    }
```

### Task 10.2: Tests for muscle_classifier.py
**File to create**: `tests/test_muscle_classifier.py`

```python
import numpy as np
import pytest
from core.muscle_classifier import classify_muscle_group, classify_with_confidence, _angle_degrees


def test_angle_degrees_90():
    p1 = (0, 1)
    vertex = (0, 0)
    p2 = (1, 0)
    assert abs(_angle_degrees(p1, vertex, p2) - 90.0) < 1.0


def test_angle_degrees_180():
    p1 = (-1, 0)
    vertex = (0, 0)
    p2 = (1, 0)
    assert abs(_angle_degrees(p1, vertex, p2) - 180.0) < 1.0


def test_angle_degrees_0():
    p1 = (1, 0)
    vertex = (0, 0)
    p2 = (1, 0)
    assert _angle_degrees(p1, vertex, p2) < 1.0


def test_classify_blank_image_returns_unknown():
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = classify_muscle_group(img)
    assert result in ['unknown', 'bicep', 'tricep', 'quad', 'hamstring', 'calf', 'shoulder']


def test_classify_with_confidence_structure():
    img = np.zeros((480, 320, 3), dtype=np.uint8)
    result = classify_with_confidence(img)
    assert 'muscle_group' in result
    assert 'confidence' in result
    assert 'method' in result
    assert 0.0 <= result['confidence'] <= 1.0
    assert result['muscle_group'] in ['bicep', 'tricep', 'quad', 'hamstring', 'calf', 'shoulder', 'unknown']
```

### Task 10.3: Expose auto-detection via API
**File**: `web_app/controllers.py`

Add a new endpoint after existing endpoints:

```python
@action('api/classify_muscle', method='POST')
@action.uses(db)
def classify_muscle():
    """
    POST a single image, get back the auto-detected muscle group.
    Body: multipart form with 'image' file field.
    Returns: {"muscle_group": "bicep", "confidence": 0.95, "method": "mediapipe_pose"}
    """
    from core.muscle_classifier import classify_with_confidence
    import numpy as np
    import cv2

    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')

    image_file = request.files.get('image')
    if not image_file:
        return dict(status='error', message='No image provided')

    file_bytes = np.frombuffer(image_file.file.read(), np.uint8)
    image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if image is None:
        return dict(status='error', message='Could not decode image')

    result = classify_with_confidence(image)
    return dict(status='ok', **result)
```

### Task 10.4: Commit + Review Gate
- Run tests, commit: `"feat: muscle group auto-detection from pose landmarks (v3.3)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`

---

## PHASE 11: "Advanced Volume Models" (v3.4)

> Goal: Add slice-based volume estimation — more accurate than the single-cylinder model for irregular muscles.

### Task 11.1: Create volumetrics_advanced.py
**File to create**: `core/volumetrics_advanced.py`

```python
"""
Advanced volumetric analysis using slice-integration.
More accurate than single-cylinder for tapered/irregular muscles.
"""
import numpy as np
import cv2


def slice_volume_estimate(contour: np.ndarray, pixels_per_cm: float,
                          num_slices: int = 20) -> dict:
    """
    Estimates muscle volume by dividing the contour bounding box into
    horizontal slices, computing elliptical cross-section per slice,
    then integrating.

    Args:
        contour: OpenCV contour array (N, 1, 2) of pixel coordinates
        pixels_per_cm: calibration scale factor
        num_slices: number of horizontal slices (more = more accurate)

    Returns:
        dict with keys:
            volume_cm3: float
            slice_widths_cm: list of float (one per slice)
            slice_heights_cm: list of float
            slice_volumes_cm3: list of float
            model: 'slice_elliptical'
    """
    if contour is None or len(contour) < 5 or pixels_per_cm <= 0:
        return {'volume_cm3': 0.0, 'model': 'slice_elliptical', 'error': 'invalid_input'}

    pts = contour.reshape(-1, 2)
    x_vals = pts[:, 0]
    y_vals = pts[:, 1]
    y_min, y_max = int(y_vals.min()), int(y_vals.max())

    if y_max <= y_min:
        return {'volume_cm3': 0.0, 'model': 'slice_elliptical', 'error': 'degenerate_contour'}

    slice_height_px = (y_max - y_min) / num_slices
    slice_height_cm = slice_height_px / pixels_per_cm

    slice_widths_cm = []
    slice_heights_cm = []
    slice_volumes_cm3 = []

    # Build a mask to query contour width at each slice
    h = y_max - y_min + 1
    w = int(x_vals.max()) - int(x_vals.min()) + 1
    offset_x = int(x_vals.min())
    offset_y = y_min
    mask = np.zeros((h + 1, w + 1), dtype=np.uint8)
    shifted = contour.copy()
    shifted[:, :, 0] -= offset_x
    shifted[:, :, 1] -= offset_y
    cv2.fillPoly(mask, [shifted], 255)

    for i in range(num_slices):
        sy = int(i * slice_height_px)
        ey = int((i + 1) * slice_height_px)
        ey = min(ey, h)
        if sy >= h:
            break
        slice_row = mask[sy:ey, :]
        if slice_row.size == 0:
            continue
        col_sums = slice_row.sum(axis=0)
        filled_cols = np.where(col_sums > 0)[0]
        if len(filled_cols) < 2:
            continue
        width_px = filled_cols[-1] - filled_cols[0]
        width_cm = width_px / pixels_per_cm
        # Assume depth ≈ 60% of width (typical for limb cross-sections)
        depth_cm = width_cm * 0.6
        # Elliptical cross-section area = π * a * b where a=width/2, b=depth/2
        area_cm2 = np.pi * (width_cm / 2) * (depth_cm / 2)
        vol = area_cm2 * slice_height_cm
        slice_widths_cm.append(round(width_cm, 3))
        slice_heights_cm.append(round(slice_height_cm, 3))
        slice_volumes_cm3.append(round(vol, 4))

    total_volume = sum(slice_volumes_cm3)
    return {
        'volume_cm3': round(total_volume, 2),
        'slice_widths_cm': slice_widths_cm,
        'slice_heights_cm': slice_heights_cm,
        'slice_volumes_cm3': slice_volumes_cm3,
        'num_slices_computed': len(slice_volumes_cm3),
        'model': 'slice_elliptical',
    }


def compare_volume_models(contour: np.ndarray, pixels_per_cm: float) -> dict:
    """
    Run both the slice model and a simple cylinder model, return both results
    so the caller can compare or choose.
    """
    from core.volumetrics import estimate_volume  # existing module

    slice_result = slice_volume_estimate(contour, pixels_per_cm)

    # Simple cylinder fallback using bounding box
    pts = contour.reshape(-1, 2) if contour is not None else np.array([[0, 0]])
    x_vals = pts[:, 0]
    y_vals = pts[:, 1]
    width_px = x_vals.max() - x_vals.min() if len(x_vals) > 1 else 0
    height_px = y_vals.max() - y_vals.min() if len(y_vals) > 1 else 0
    width_cm = width_px / pixels_per_cm if pixels_per_cm > 0 else 0
    height_cm = height_px / pixels_per_cm if pixels_per_cm > 0 else 0
    radius_cm = width_cm / 2
    cylinder_vol = np.pi * radius_cm ** 2 * height_cm

    return {
        'slice_model': slice_result,
        'cylinder_model': {
            'volume_cm3': round(cylinder_vol, 2),
            'model': 'cylinder',
        },
        'recommended': 'slice_elliptical',
    }
```

### Task 11.2: Tests for volumetrics_advanced.py
**File to create**: `tests/test_volumetrics_advanced.py`

```python
import numpy as np
import pytest
from core.volumetrics_advanced import slice_volume_estimate, compare_volume_models


def make_ellipse_contour(cx=100, cy=150, rx=30, ry=50, n_points=100):
    """Create an elliptical contour as OpenCV-style array."""
    angles = np.linspace(0, 2 * np.pi, n_points)
    x = (cx + rx * np.cos(angles)).astype(np.int32)
    y = (cy + ry * np.sin(angles)).astype(np.int32)
    return np.stack([x, y], axis=1).reshape(-1, 1, 2)


def test_slice_volume_positive():
    contour = make_ellipse_contour()
    result = slice_volume_estimate(contour, pixels_per_cm=10.0)
    assert result['volume_cm3'] > 0
    assert result['model'] == 'slice_elliptical'


def test_slice_volume_scales_with_calibration():
    contour = make_ellipse_contour()
    result_10 = slice_volume_estimate(contour, pixels_per_cm=10.0)
    result_20 = slice_volume_estimate(contour, pixels_per_cm=20.0)
    # More pixels per cm = smaller physical size = smaller volume
    assert result_20['volume_cm3'] < result_10['volume_cm3']


def test_slice_volume_invalid_contour():
    result = slice_volume_estimate(None, pixels_per_cm=10.0)
    assert 'error' in result
    assert result['volume_cm3'] == 0.0


def test_slice_volume_zero_calibration():
    contour = make_ellipse_contour()
    result = slice_volume_estimate(contour, pixels_per_cm=0.0)
    assert 'error' in result


def test_slice_volume_more_slices_more_detail():
    contour = make_ellipse_contour()
    result_5 = slice_volume_estimate(contour, pixels_per_cm=10.0, num_slices=5)
    result_50 = slice_volume_estimate(contour, pixels_per_cm=10.0, num_slices=50)
    # Both should give positive volumes, more slices give more detail
    assert result_5['volume_cm3'] > 0
    assert result_50['volume_cm3'] > 0
    assert len(result_50['slice_widths_cm']) > len(result_5['slice_widths_cm'])


def test_compare_volume_models_structure():
    contour = make_ellipse_contour()
    result = compare_volume_models(contour, pixels_per_cm=10.0)
    assert 'slice_model' in result
    assert 'cylinder_model' in result
    assert result['recommended'] == 'slice_elliptical'
    assert result['cylinder_model']['volume_cm3'] > 0
```

### Task 11.3: Expose advanced volume in API response
**File**: `web_app/controllers.py`

In the `upload_scan` endpoint (and `upload_video`), after getting the analysis result, add the advanced volume:

```python
from core.volumetrics_advanced import slice_volume_estimate

# After analysis is complete and contour is available:
if 'contour' in analysis_result and analysis_result.get('pixels_per_cm'):
    adv_vol = slice_volume_estimate(
        analysis_result['contour'],
        analysis_result['pixels_per_cm']
    )
    analysis_result['advanced_volume'] = adv_vol
```

Note: Read the actual code to integrate correctly. If `contour` and `pixels_per_cm` are in a different structure, adapt accordingly.

### Task 11.4: Commit + Review Gate
- Run tests, commit: `"feat: slice-based elliptical volume model, advanced volumetrics (v3.4)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`

---

## PHASE 12: "Web Dashboard SPA" (v3.5)

> Goal: Build the clinic-facing web portal. Static HTML/JS (no build tools needed) served by py4web.

### Task 12.1: Create the SPA directory structure
Run these commands:
```bash
mkdir -p /c/Users/MiEXCITE/Projects/muscle_tracker/web_app/static/dashboard
```

### Task 12.2: Create dashboard/index.html
**File to create**: `web_app/static/dashboard/index.html`

A single-page application that:
- Has a login form (email, password → POST /api/login)
- On login success, stores JWT in localStorage
- Shows a nav with: Patients, Analytics, Logout
- **Patients page**: table of customers (GET /api/customers with admin JWT), click to expand scan history
- **Analytics page**: shows stats (total scans, latest scan dates)
- Uses vanilla JS + CSS (no external dependencies, no CDN, no npm)
- Dark clinical theme: background #1a1a2e, accent #4a9eff, text #e0e0e0
- All API calls include `Authorization: Bearer <token>` header

Write the full HTML file with embedded `<style>` and `<script>` tags. The file should be complete and self-contained.

Key JS functions to implement:
```javascript
async function apiGet(path) { /* fetch with auth header, return json */ }
async function apiPost(path, body) { /* fetch POST with auth header */ }
async function login(email, password) { /* call /api/login, store token */ }
async function loadPatients() { /* fetch and render patient list */ }
async function loadPatientScans(customerId) { /* fetch scan history */ }
async function logout() { /* clear localStorage, show login */ }
function showPage(name) { /* show/hide sections */ }
```

The dashboard must:
1. Check localStorage for existing token on page load
2. If token exists, go straight to patients page
3. Show each patient row with: name, email, scan count, last scan date
4. Clicking a patient row expands to show their scan list with dates and muscle groups

### Task 12.3: Add dashboard route in py4web
**File**: `web_app/controllers.py`

Add at the end:

```python
@action('dashboard')
@action('dashboard/<path:path>')
def dashboard(path='index.html'):
    """Serve the clinical web dashboard SPA."""
    return open(os.path.join(os.path.dirname(__file__), 'static', 'dashboard', 'index.html')).read()
```

Also add `import os` at the top of controllers.py if not already present.

### Task 12.4: Add /api/customers list endpoint (admin)
**File**: `web_app/controllers.py`

Add a new endpoint for fetching all customers (for the dashboard). This should require a valid JWT:

```python
@action('api/customers/list', method='GET')
@action.uses(db)
def list_customers():
    """List all customers — dashboard use only. Requires valid JWT."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')

    customers = db(db.customer).select(
        db.customer.id, db.customer.name, db.customer.email,
        db.customer.created_at,
        orderby=db.customer.name
    )
    result = []
    for c in customers:
        scan_count = db(db.muscle_scan.customer_id == c.id).count()
        last_scan = db(db.muscle_scan.customer_id == c.id).select(
            db.muscle_scan.scan_date,
            orderby=~db.muscle_scan.scan_date,
            limitby=(0, 1)
        ).first()
        result.append({
            'id': c.id,
            'name': c.name,
            'email': c.email,
            'scan_count': scan_count,
            'last_scan_date': str(last_scan.scan_date) if last_scan else None,
        })
    return dict(status='ok', customers=result)
```

### Task 12.5: Commit + Review Gate
- Run tests, commit: `"feat: clinical web dashboard SPA, customer list API (v3.5)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`

---

## PHASE 13: "PDF Report Generation" (v3.6)

> Goal: Generate downloadable PDF clinical reports from the server.

### Task 13.1: Install reportlab
Run: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pip install reportlab`

Verify: `python -c "import reportlab; print(reportlab.Version)"`

### Task 13.2: Create pdf_report.py
**File to create**: `core/pdf_report.py`

```python
"""
Server-side PDF report generation for clinical scan reports.
Uses reportlab for PDF creation.
"""
import io
import os
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def generate_scan_pdf(scan_data: dict, customer_data: dict,
                      scan_image_path: str = None) -> bytes | None:
    """
    Generate a clinical PDF report for a muscle scan.

    Args:
        scan_data: dict with keys: scan_date, muscle_group, volume_cm3,
                   circumference_cm, symmetry_score, shape_score,
                   growth_rate, notes
        customer_data: dict with keys: name, email, height_cm, weight_kg
        scan_image_path: optional path to the scan image to embed

    Returns:
        PDF as bytes, or None if reportlab not available
    """
    if not REPORTLAB_AVAILABLE:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=20, textColor=colors.HexColor('#1a3a6b'),
        spaceAfter=12, alignment=TA_CENTER
    )
    header_style = ParagraphStyle(
        'SectionHeader', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor('#2c5f9e'),
        spaceBefore=16, spaceAfter=8
    )
    normal_style = styles['Normal']
    normal_style.fontSize = 11

    story = []

    # Title
    story.append(Paragraph('Muscle Tracker — Clinical Scan Report', title_style))
    story.append(Paragraph(
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        ParagraphStyle('Small', parent=styles['Normal'], fontSize=9,
                       textColor=colors.grey, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 0.5*cm))

    # Patient info
    story.append(Paragraph('Patient Information', header_style))
    patient_table_data = [
        ['Name', customer_data.get('name', 'N/A')],
        ['Email', customer_data.get('email', 'N/A')],
        ['Height', f"{customer_data.get('height_cm', 'N/A')} cm"],
        ['Weight', f"{customer_data.get('weight_kg', 'N/A')} kg"],
    ]
    pt = Table(patient_table_data, colWidths=[4*cm, 12*cm])
    pt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0fe')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(pt)
    story.append(Spacer(1, 0.3*cm))

    # Scan metrics
    story.append(Paragraph('Scan Results', header_style))
    scan_date = scan_data.get('scan_date', 'N/A')
    metrics_data = [
        ['Metric', 'Value'],
        ['Scan Date', str(scan_date)],
        ['Muscle Group', scan_data.get('muscle_group', 'N/A').title()],
        ['Volume', f"{scan_data.get('volume_cm3', 'N/A')} cm³"],
        ['Circumference', f"{scan_data.get('circumference_cm', 'N/A')} cm"],
        ['Symmetry Score', f"{scan_data.get('symmetry_score', 'N/A')}%"],
        ['Shape Score', f"{scan_data.get('shape_score', 'N/A')}%"],
        ['Growth Rate', f"{scan_data.get('growth_rate', 'N/A')}% vs previous"],
    ]
    mt = Table(metrics_data, colWidths=[6*cm, 10*cm])
    mt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a3a6b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#e8f0fe')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f8ff')]),
    ]))
    story.append(mt)

    # Embed scan image if available
    if scan_image_path and os.path.exists(scan_image_path):
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph('Scan Image', header_style))
        try:
            img = RLImage(scan_image_path, width=8*cm, height=8*cm, kind='proportional')
            story.append(img)
        except Exception:
            story.append(Paragraph('(Image could not be embedded)', normal_style))

    # Notes
    if scan_data.get('notes'):
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph('Clinical Notes', header_style))
        story.append(Paragraph(scan_data['notes'], normal_style))

    # Footer disclaimer
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        'DISCLAIMER: This report is for educational and tracking purposes only. '
        'It is not a medical device output and should not replace professional medical advice.',
        ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=8,
                       textColor=colors.grey, alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()
```

### Task 13.3: Add PDF report endpoint
**File**: `web_app/controllers.py`

Add a new endpoint:

```python
@action('api/customer/<customer_id:int>/report/<scan_id:int>/pdf', method='GET')
@action.uses(db)
def get_pdf_report(customer_id, scan_id):
    """Generate and return a PDF report for a scan."""
    from core.pdf_report import generate_scan_pdf, REPORTLAB_AVAILABLE

    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload or payload.get('customer_id') != customer_id:
        return dict(status='error', message='Access denied')

    if not REPORTLAB_AVAILABLE:
        return dict(status='error', message='PDF generation not available')

    scan = db.muscle_scan[scan_id]
    if not scan or scan.customer_id != customer_id:
        return dict(status='error', message='Scan not found')

    customer = db.customer[customer_id]
    if not customer:
        return dict(status='error', message='Customer not found')

    scan_data = {
        'scan_date': scan.scan_date,
        'muscle_group': scan.muscle_group,
        'volume_cm3': scan.volume_cm3,
        'circumference_cm': scan.circumference_cm,
        'symmetry_score': scan.symmetry_score,
        'shape_score': scan.shape_score,
        'growth_rate': scan.growth_rate,
        'notes': '',
    }
    customer_data = {
        'name': customer.name,
        'email': customer.email,
        'height_cm': customer.height_cm,
        'weight_kg': customer.weight_kg,
    }

    pdf_bytes = generate_scan_pdf(scan_data, customer_data)
    if pdf_bytes is None:
        return dict(status='error', message='PDF generation failed')

    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="scan_{scan_id}_report.pdf"'
    return pdf_bytes
```

### Task 13.4: Tests for pdf_report.py
**File to create**: `tests/test_pdf_report.py`

```python
import pytest
from core.pdf_report import generate_scan_pdf, REPORTLAB_AVAILABLE


SAMPLE_SCAN = {
    'scan_date': '2026-03-15',
    'muscle_group': 'bicep',
    'volume_cm3': 245.7,
    'circumference_cm': 36.2,
    'symmetry_score': 94.5,
    'shape_score': 88.1,
    'growth_rate': 3.2,
    'notes': 'Good form maintained throughout measurement.',
}

SAMPLE_CUSTOMER = {
    'name': 'John Doe',
    'email': 'john@example.com',
    'height_cm': 180,
    'weight_kg': 82.5,
}


def test_generate_pdf_returns_bytes_or_none():
    result = generate_scan_pdf(SAMPLE_SCAN, SAMPLE_CUSTOMER)
    if REPORTLAB_AVAILABLE:
        assert isinstance(result, bytes)
        assert len(result) > 1000  # PDF should have some content
    else:
        assert result is None


def test_generate_pdf_starts_with_pdf_header():
    result = generate_scan_pdf(SAMPLE_SCAN, SAMPLE_CUSTOMER)
    if REPORTLAB_AVAILABLE and result:
        assert result[:4] == b'%PDF'


def test_generate_pdf_missing_fields():
    """Should not crash with missing scan fields."""
    result = generate_scan_pdf({}, {})
    if REPORTLAB_AVAILABLE:
        assert isinstance(result, bytes)


def test_generate_pdf_with_nonexistent_image():
    """Should not crash when image path doesn't exist."""
    result = generate_scan_pdf(SAMPLE_SCAN, SAMPLE_CUSTOMER,
                                scan_image_path='/nonexistent/path.jpg')
    if REPORTLAB_AVAILABLE:
        assert isinstance(result, bytes)
```

### Task 13.5: Commit + Review Gate
- Run tests, commit: `"feat: server-side PDF report generation with ReportLab (v3.6)"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`

---

## PHASE 14: "Docker & Deployment Prep" (v4.0)

> Goal: Make the app deployable. Create Docker config, health checks, and deployment scripts.

### Task 14.1: Create Dockerfile
**File to create**: `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose py4web default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run py4web
CMD ["python", "muscle_tracker.py", "--host", "0.0.0.0", "--port", "8000"]
```

### Task 14.2: Create requirements.txt
**File to create**: `requirements.txt`

Run this to generate it from the current environment:
```bash
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pip freeze > /c/Users/MiEXCITE/Projects/muscle_tracker/requirements.txt
```

Then edit it to keep only relevant packages (remove Windows-specific ones). The file should contain at minimum:
```
opencv-python-headless>=4.8.0
numpy>=1.24.0
py4web>=1.20231012.1
pyjwt>=2.8.0
reportlab>=4.0.0
mediapipe>=0.10.0
```

### Task 14.3: Create docker-compose.yml
**File to create**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./databases:/app/databases
    environment:
      - MUSCLE_TRACKER_ENV=production
      - JWT_SECRET=${JWT_SECRET:-changeme-in-production}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Task 14.4: Add /api/health endpoint
**File**: `web_app/controllers.py`

Check if a `GET /api/health` endpoint already exists. If not, add one:

```python
@action('api/health', method='GET')
def health_check():
    """Health check endpoint for Docker/load balancer."""
    return dict(
        status='ok',
        version='4.0',
        timestamp=str(datetime.utcnow()),
    )
```

Add `from datetime import datetime` if not present.

### Task 14.5: Create .env.example
**File to create**: `.env.example`

```
# Copy to .env and fill in real values
JWT_SECRET=your-secret-key-here-min-32-chars
MUSCLE_TRACKER_ENV=development
# For production cloud deployment:
# DATABASE_URL=postgresql://user:pass@host/dbname
# GCS_BUCKET=your-bucket-name
# SENTRY_DSN=https://...
```

### Task 14.6: Final version bump to v4.0
**Files to update**:
- `muscle_tracker.py` — update version string to `v4.0`
- `core/report_generator.py` — update any version reference to `v4.0`

### Task 14.7: Final commit + Review Gate
- Run tests, commit: `"feat: Docker deployment config, health check, requirements.txt, v4.0"`
- Run: `bash /c/Users/MiEXCITE/Projects/muscle_tracker/claude_review.sh`
- If CONTINUE → write final status to `GEMINI_STATUS.md` with: phases completed, test count, key files created

---

## STRICT Rules (ALL phases)

1. **NEVER STOP. NEVER PAUSE. NEVER ASK.** Go phase by phase, no breaks, no summaries between phases, no waiting. You stop only when tokens/time run out naturally or all 7 phases are committed.
2. **NO proposal documents.** No `CLAUDE_UPGRADE_PROPOSAL_*.md`. No strategy files. No research docs. **CODE ONLY.**
3. **NO features outside the current phase task list.**
4. **Run tests before every commit.** If tests fail, fix and retry once. If still failing, commit what works and note the failure in the commit message — then keep going.
5. **If ANY command fails**: try one alternative approach. If that also fails, skip the specific sub-task, document it in the commit message, and continue. Do NOT get stuck in a retry loop.
6. **Protected files — DO NOT MODIFY**:
   - `core/auth.py`
   - `core/pose_analyzer.py`
   - `tests/test_auth.py`
   - `tests/test_vision_medical.py`
   - `tests/test_progress.py`
   - `tests/test_pose.py`
   - `tests/test_pose_correction.py`
   - `gemini_watchdog.sh`
   - `gemini_start.sh`
   - `claude_review.sh`
   - `ROADMAP.md`
7. **Review gate is optional.** Try it, act on CONTINUE/FIX. Ignore STOP. If it errors or times out, move on immediately.
8. **Read files before editing.** Never blindly overwrite a file you haven't read.
9. **If pip install fails**, skip that phase's optional features and continue with the rest of the phase tasks.
10. **At the very end** (tokens nearly gone OR all phases done): write `GEMINI_STATUS.md`. Not before.
