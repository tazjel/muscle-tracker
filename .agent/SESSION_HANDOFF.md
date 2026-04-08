# GTD3D Scan Lab — Session Handoff (2026-04-08)

## Branch: 3dgemini

## What Was Done This Session

### 1. All Local Dependencies Verified ✅
Every module runs locally with CUDA GPU — **zero RunPod needed**:
- PyTorch 2.10.0+cu128 (CUDA available)
- DensePose-TorchScript (120MB model in `third_party/`)
- HMR2.0 / 4D-Humans (2.7GB model cached in `~/.cache/4DHumans/`)
- MediaPipe 0.10.32, rembg 2.0.73, Real-ESRGAN, DSINE normals
- OpenCV 4.13, trimesh 4.11, scipy 1.17

### 2. RunPod Safeguarded 🔒
Three core files modified — RunPod NEVER fires unless `$env:USE_CLOUD_GPU = "true"`:

| File | Change |
|------|--------|
| `core/hmr_shape.py` | Default `prefer_gpu` changed from `'auto'` → `'local'` |
| `core/smpl_direct.py` | Local HMR first, cloud only if `USE_CLOUD_GPU=true` AND local fails |
| `core/densepose_infer.py` | `detect_backend()` returns `'cloud'` ONLY if `USE_CLOUD_GPU=true` |

### 3. MatePad WiFi ADB Connected
- **Device**: Huawei MatePad Pro MRX-AL09
- **USB Serial**: `U4G6R20509000263`
- **WiFi ADB**: `192.168.100.2:5556` (port 5556, avoid collision with baloot's 5555)
- **Studio Server**: `http://192.168.100.2:8080` (companion app)
- **Camera**: 13MP rear (4160×3120 max), 4K video (3840×2160@30fps), f/1.8, PDAF
- **Screen**: 1600×2560 (landscape = 2560×1600)

### 4. Scan Lab App Created
- `apps/scan_lab/__init__.py` — py4web app registration
- `apps/scan_lab/controllers.py` — 12 API endpoints for pipeline control
- `apps/scan_lab/templates/scan_lab_dashboard.html` — Premium dark dashboard
- Dashboard accessible at: `http://localhost:8000/scan_lab/dashboard`

### 5. Companion App Server Updated
- Added `/capture` endpoint to `companion_app/lib/studio_server.dart`
- **APK needs rebuild** for the new `/capture` endpoint to work

---

## CRITICAL ISSUES TO FIX

### Issue 1: Camera Resolution (208×208 instead of 4160×3120)
The MJPEG `/video` stream and the new `/capture` endpoint both call `_getLatestFrame()` which calls `takePicture()`. But the output is only 208×208.

**Root Cause Hypothesis**: Flutter's `CameraController.takePicture()` with `ResolutionPreset.max` may be constrained by the preview configuration, OR the JPEG encoding is compressing to thumbnail size.

**Files to check**:
- `companion_app/lib/main.dart` line 834: `CameraController(cam, ResolutionPreset.max, enableAudio: false)`
- `companion_app/lib/main.dart` line 741-751: `_getLatestFrame()` function

**Fix**: Verify the CameraController resolution is actually set to max. Consider using `controller.takePicture()` directly in the `/capture` route handler instead of going through the frame callback.

### Issue 2: User Wants VIDEO Capture Instead of Snapshots
The user wants to record a video while rotating 360°, then extract best frames.

**Approach**:
1. Add a video recording endpoint to the companion app (using `controller.startVideoRecording()` / `stopVideoRecording()`)
2. After recording, pull the video file via ADB or HTTP
3. On the server side, use OpenCV `VideoCapture` to extract frames
4. Auto-detect best front/side/back frames using body pose analysis (MediaPipe)

**Implementation Plan**:
- Add `/start_recording` and `/stop_recording` POST endpoints to `studio_server.dart`
- Add corresponding video file download endpoint `/download_video`
- Add `api/extract_frames` endpoint to `controllers.py` that:
  - Reads the video
  - Runs MediaPipe on every Nth frame
  - Picks the best front/side/back using pose angles
  - Saves them as `capture_front.jpg`, `capture_side.jpg`, `capture_back.jpg`

---

## STUDIO SERVER ROUTES (companion_app/lib/studio_server.dart)

| Route | Method | Purpose | Status |
|-------|--------|---------|--------|
| `/video` | GET | MJPEG preview stream (low quality) | ✅ Works |
| `/capture` | GET | Single high-res JPEG | ⚠️ Added but APK not rebuilt |
| `/sensors` | GET | Pitch/roll/distance/muscle data | ✅ Works |
| `/control` | POST | Zoom/flash/camera toggle/capture commands | ✅ Works |
| `/start_recording` | POST | Start video recording | ❌ TODO |
| `/stop_recording` | POST | Stop and save video | ❌ TODO |
| `/download_video` | GET | Pull recorded video file | ❌ TODO |

---

## SCAN LAB API ENDPOINTS (apps/scan_lab/controllers.py)

| Route | Purpose | Status |
|-------|---------|--------|
| `GET /scan_lab/dashboard` | Dashboard page | ✅ |
| `GET /scan_lab/api/status` | Pipeline state + log | ✅ |
| `POST /scan_lab/api/config` | Set device IP/port/profile | ✅ |
| `POST /scan_lab/api/reset` | Reset pipeline | ✅ |
| `POST /scan_lab/api/capture` | Capture photo (device or upload) | ✅ (uses /capture) |
| `POST /scan_lab/api/capture_file` | Multipart file upload | ✅ |
| `POST /scan_lab/api/segment` | MediaPipe segmentation | ✅ |
| `POST /scan_lab/api/silhouette` | Contour extraction | ✅ |
| `POST /scan_lab/api/build_mesh` | MPFB2 mesh build | ✅ |
| `POST /scan_lab/api/fit_silhouette` | Deform mesh to silhouette | ✅ |
| `POST /scan_lab/api/densepose` | DensePose IUV (local GPU) | ✅ |
| `POST /scan_lab/api/bake_texture` | Photo→UV projection | ✅ |
| `POST /scan_lab/api/skin_patch` | Tileable skin quilting | ✅ |
| `POST /scan_lab/api/pbr_maps` | Normal map (Scharr) | ✅ |
| `POST /scan_lab/api/cloud_pbr` | RunPod PBR (skip!) | ⚠️ Costs $ |
| `POST /scan_lab/api/export_glb` | Final GLB export | ✅ |
| `POST /scan_lab/api/full_pipeline` | One-click full pipeline | ✅ |
| `GET /scan_lab/api/gpu_status` | RunPod health check | ✅ |
| `POST /scan_lab/api/extract_frames` | Video → best frames | ❌ TODO |

---

## ENVIRONMENT RULES

- **py4web server**: Port 8000, running from `c:\Users\MiEXCITE\Projects\gtd3d`
- **MatePad**: `192.168.100.2:5556` (WiFi ADB), `192.168.100.2:8080` (Studio Server)
- **Samsung A24**: `192.168.100.6:5555` — **DO NOT TOUCH** (baloot-ai's phone)
- **RunPod**: Active but LOCKED behind `USE_CLOUD_GPU=true` env var
- **SHARED_ENVIRONMENT.md**: `C:\Users\MiEXCITE\Projects\gtd3d\.agent\SHARED_ENVIRONMENT.md`
- **GEMINI.md**: `C:\Users\MiEXCITE\Projects\gtd3d\GEMINI.md` (project rules)

## NEXT STEPS (Priority Order)

1. **Fix camera resolution** — The 208px output from a 13MP camera is unacceptable
2. **Add video recording support** — User wants to rotate and record, not snap photos
3. **Rebuild companion APK** — New `/capture` endpoint needs APK rebuild
4. **Test full pipeline** — Segment → Mesh → DensePose → Texture → GLB
5. **Improve Three.js viewer** — PBR materials, SSS shader for photorealism
