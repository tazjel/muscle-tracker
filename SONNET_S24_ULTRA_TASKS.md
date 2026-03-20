# Sonnet Tasks — Samsung S24 Ultra Integration

**Agent:** Sonnet | **Date:** 2026-03-20
**When done:** Commit with descriptive message.

## Context

Upgrading from Samsung A24 (SM-A245, 50MP, 6.4mm sensor) to S24 Ultra (SM-S928B, 200MP, 9.8mm sensor).
The S24 Ultra has: 200MP main + Laser AF + ARCore Depth API (software) + Snapdragon 8 Gen 3.
No hardware ToF/LiDAR — uses ARCore software depth estimation.

**Camera intrinsics already partially handled:**
- `core/calibration.py:18` already has `SM-S92: 9.8` in sensor DB
- S24 Ultra model string is `SM-S928B` — matches `SM-S92` prefix
- Main camera: 200MP, f/1.7, 6.3mm focal length, 1/1.3" sensor (9.8mm width)

---

## T1 — Add S24 Ultra Device Profile

**File:** `core/calibration.py`
**Location:** Line 18

**Current:**
```python
'SM-S92':   9.8,   # Samsung Galaxy S24 Ultra
```

**Change to (more precise + add S24 base models):**
```python
'SM-S928':  9.8,   # Samsung Galaxy S24 Ultra — 200MP 1/1.3" sensor
'SM-S926':  7.2,   # Samsung Galaxy S24+
'SM-S921':  7.2,   # Samsung Galaxy S24
'SM-S92':   9.8,   # Samsung Galaxy S24 series fallback
```

**Also update** `core/smpl_direct.py` lines 19-20. Current defaults are A24 values:
```python
DEFAULT_FOCAL_MM = 4.0
DEFAULT_SENSOR_W_MM = 6.4
```

These defaults are fine as fallbacks — but add a device profile lookup. After line 20, add:
```python
# Device-specific camera profiles (focal_mm, sensor_width_mm)
_DEVICE_CAMERAS = {
    'SM-A245': (4.0, 6.4),    # Samsung A24 — 50MP f/1.8
    'SM-S928': (6.3, 9.8),    # Samsung S24 Ultra — 200MP f/1.7
    'SM-S926': (6.3, 7.2),    # Samsung S24+
    'SM-S921': (6.3, 7.2),    # Samsung S24
}

def get_camera_profile(device_model=None):
    """Return (focal_mm, sensor_width_mm) for known device, or defaults."""
    if device_model:
        for key, vals in _DEVICE_CAMERAS.items():
            if key in device_model:
                return vals
    return (DEFAULT_FOCAL_MM, DEFAULT_SENSOR_W_MM)
```

---

## T2 — Send Device Model from Companion App

**Why:** The server needs to know which device took the photo to select correct camera intrinsics. Currently hardcoded to A24 defaults.

**File:** `companion_app/lib/main.dart`
**Location:** Line 854 (upload_scan), line 1032 (upload_session), line 890 (video upload)

**What to do:**

1. At the top of the `_CaptureScreenState` class (around line 616), add a device model field:
```dart
String _deviceModel = '';
```

2. In `initState()` (line 658), after `_initCamera()`, add:
```dart
_getDeviceModel();
```

3. Add the method:
```dart
Future<void> _getDeviceModel() async {
  try {
    final info = await DeviceInfoPlugin().androidInfo;
    _deviceModel = info.model ?? '';
  } catch (_) {}
}
```

4. Add `device_info_plus` to `pubspec.yaml` dependencies (line 42):
```yaml
device_info_plus: ^11.0.0
```

5. Add import at top of main.dart:
```dart
import 'package:device_info_plus/device_info_plus.dart';
```

6. In every upload request, add the device model field. At lines 854, 890, 1032:
```dart
request.fields['device_model'] = _deviceModel;
```

---

## T3 — Server: Use Device Model for Camera Intrinsics

**Why:** Once the app sends `device_model`, the server should use it to pick the right focal length and sensor width instead of hardcoded A24 defaults.

**File:** `web_app/controllers.py`
**Location:** Line 2862-2864 (inside `generate_body_model()`)

**Current code:**
```python
camera_distance_cm = float(
    request.forms.get('camera_distance_cm', '0') or '100'
)
cam_h_mm = float(profile.get('camera_height_from_ground_cm', 65)) * 10
```

**Add after line 2865:**
```python
_device_model = request.forms.get('device_model', '')
```

**Then at line 2892** (the `generate_direct_smpl` call), pass it:
```python
smpl_result = generate_direct_smpl(
    {d: v['img'] for d, v in loaded_images.items()},
    profile=profile,
    dist_mm=_dist_mm,
    cam_h_mm=cam_h_mm,
    device_model=_device_model,
)
```

**File:** `core/smpl_direct.py`
**Location:** `generate_direct_smpl()` function signature (grep for `def generate_direct_smpl`)

Add `device_model=None` parameter, and use it to select camera profile:
```python
def generate_direct_smpl(images_dict, profile=None, dist_mm=2300.0,
                          cam_h_mm=650.0, device_model=None):
    focal_mm, sensor_w_mm = get_camera_profile(device_model)
    logger.info("Camera profile: %s → focal=%.1fmm, sensor=%.1fmm",
                device_model or 'default', focal_mm, sensor_w_mm)
```

Then use these values instead of the DEFAULT_ constants throughout the function.

**Also update** the Anny path in controllers.py. At line 3058-3059:
```python
# CURRENT (hardcoded A24 values):
'focal_mm':        4.0,
'sensor_width_mm': 6.4,

# CHANGE TO:
'focal_mm':        _focal_mm,
'sensor_width_mm': _sensor_w_mm,
```

Add before the Anny texture projection block:
```python
from core.smpl_direct import get_camera_profile
_focal_mm, _sensor_w_mm = get_camera_profile(_device_model)
```

---

## T4 — ARCore Depth Capture in Companion App

**Why:** S24 Ultra supports ARCore Depth API. Capturing a depth map alongside each photo gives the server a real depth image for better mesh fitting — replacing the software `estimate_depth()` call on the server.

**File:** `companion_app/pubspec.yaml`
**Add dependency:**
```yaml
arcore_flutter_plugin: ^0.1.0
```

**File:** `companion_app/lib/main.dart`
**Location:** After the burst capture (`_burstCaptureBest`) at line 915

**What to do:** This is the most complex task. Add an optional depth capture mode:

1. Add a flag to detect ARCore depth support:
```dart
bool _depthSupported = false;

Future<void> _checkDepthSupport() async {
  try {
    // ARCore depth is available on S24 Ultra via software stereo
    // Check if ARCore is available on this device
    _depthSupported = await ArCoreController.checkArCoreAvailability();
  } catch (_) {
    _depthSupported = false;
  }
}
```

2. After each photo capture, if depth is supported, capture a depth frame:
```dart
Future<Uint8List?> _captureDepthMap() async {
  if (!_depthSupported) return null;
  // ARCore depth capture returns a 16-bit depth image
  // This gets uploaded alongside the photo
  try {
    // Implementation depends on arcore_flutter_plugin API
    // Returns PNG-encoded depth map or null
    return null; // TODO: wire ARCore depth session
  } catch (_) {
    return null;
  }
}
```

3. In upload requests, add the depth map as an additional file:
```dart
if (depthData != null) {
  request.files.add(http.MultipartFile.fromBytes(
    '${direction}_depth', depthData,
    filename: '${direction}_depth.png',
  ));
}
```

**NOTE:** ARCore depth integration is non-trivial — the `arcore_flutter_plugin` may need a custom platform channel. This task is a scaffold; the full ARCore session management will need a follow-up task. For now, add the infrastructure (flag, upload field, server acceptance) so it works when wired.

---

## T5 — Server: Accept Device Depth Maps

**Why:** When the app sends `front_depth`, `back_depth` etc., the server should use them instead of running `estimate_depth()` on the server (which uses Depth Anything V2 — slower and less accurate than on-device ARCore depth).

**File:** `web_app/controllers.py`
**Location:** Line 2867-2880 (where `loaded_images` dict is built)

**After the image loading loop, add depth map loading:**
```python
for _dir in loaded_images:
    _depth_file = request.files.get(f'{_dir}_depth')
    if _depth_file:
        _depth_tmp = os.path.join('uploads', f'depth_{customer_id}_{_dir}_{int(time.time())}.png')
        try:
            _depth_file.save(_depth_tmp)
            _depth_img = _cv2.imread(_depth_tmp, _cv2.IMREAD_UNCHANGED)
            if _depth_img is not None:
                loaded_images[_dir]['depth'] = _depth_img
                logger.info('Device depth map loaded for %s: %s', _dir, _depth_img.shape)
        except Exception:
            logger.warning('Failed to load depth map for %s', _dir)
```

**Then at line 3017-3034** (depth estimation block), prefer device depth over server estimation:
```python
depth_maps = []
if silhouette_views:
    for sv in silhouette_views:
        _dir = sv['direction']
        if _dir in loaded_images and 'depth' in loaded_images[_dir]:
            # Use device-captured depth (ARCore) — more accurate
            depth_maps.append({
                'depth': loaded_images[_dir]['depth'],
                'direction': _dir,
                'source': 'device_arcore',
            })
            logger.info('Using device depth for %s', _dir)
            continue
        # Fallback: server-side depth estimation
        if _dir in loaded_images:
            try:
                from core.depth_estimator import estimate_depth
                depth_result = estimate_depth(
                    loaded_images[_dir]['img'],
                    camera_distance_mm=sv['distance_mm'],
                    body_mask=sv.get('mask'),
                )
                if depth_result:
                    depth_result['direction'] = _dir
                    depth_result['source'] = 'server_estimated'
                    depth_maps.append(depth_result)
            except Exception:
                pass
```

---

## T6 — Higher Resolution Texture Pipeline

**Why:** S24 Ultra 200MP = 16384x12288 images. The current pipeline downscales aggressively. With better source images, we should keep more resolution.

**File:** `core/cloud_gpu.py`
**Location:** `_encode_image()` function at line 34

**Current:**
```python
def _encode_image(img_bgr, max_dim=1024, quality=85):
```

**Change to:**
```python
def _encode_image(img_bgr, max_dim=2048, quality=85):
```

This lets cloud GPU inference (HMR, rembg, DSINE) work with 2048px inputs instead of 1024px — better detail for the S24 Ultra's high-res images. The A24's 50MP images will also benefit but less dramatically.

**File:** `core/smpl_direct.py`
**Location:** `_rasterize_texture()` function — grep for `atlas_size`

**Current default:** `atlas_size=2048`

For S24 Ultra, the native resolution can support 4096px atlas without upscaling. Add logic:
```python
# Auto-select atlas size based on input resolution
max_input_dim = max(img.shape[0] for img in images_dict.values())
if max_input_dim > 8000:  # 200MP = ~12000px tall
    atlas_size = 4096
else:
    atlas_size = 2048
```

---

## Files Reference

| What | File | Lines |
|------|------|-------|
| Sensor DB | `core/calibration.py` | 14-24 |
| Default focal/sensor | `core/smpl_direct.py` | 19-20 |
| generate_direct_smpl() | `core/smpl_direct.py` | grep `def generate_direct_smpl` |
| _rasterize_texture() | `core/smpl_direct.py` | grep `def _rasterize_texture` |
| _encode_image() cloud | `core/cloud_gpu.py` | 34-42 |
| Camera init | `companion_app/lib/main.dart` | 660-677 |
| Upload scan | `companion_app/lib/main.dart` | 846-866 |
| Upload session | `companion_app/lib/main.dart` | 1025-1060 |
| Video upload | `companion_app/lib/main.dart` | 880-899 |
| generate_body_model() | `web_app/controllers.py` | 2782-2979 |
| Depth estimation block | `web_app/controllers.py` | 3017-3034 |
| Anny texture cam_views | `web_app/controllers.py` | 3050-3059 |
| pubspec.yaml | `companion_app/pubspec.yaml` | 30-42 |
