# GTD3D — Sonnet Task Updates

> Sonnet updates this file after each completed task.
> Opus reads this to track progress and plan next waves.

<!-- Updates will appear below, newest first -->

## [2026-04-10] Wave 3B Update

### Task 3B.1 — Implement api_service.dart
- Status: done
- Files changed: `services/api_service.dart`
- Notes: Singleton with `get()`, `post()`, `uploadImage()`, `uploadMultipart()`, `getRaw()`, `postRaw()`. Uses `AppConfig.serverBaseUrl` and `jwtToken` from config.dart. Mirrors MultipartRequest patterns found in tabs/.

### Task 3B.2 — Implement camera_service.dart + sensor_service.dart
- Status: done
- Files changed: `services/camera_service.dart`, `services/sensor_service.dart`
- Notes: CameraService: singleton owning CameraController, `initialize()`, `capture()`, `toggleTorch()`, `dispose()`. SensorService: singleton with `ValueNotifier<double> pitch/roll`, `latestValues` map, `start()`/`stop()`/`dispose()`. Both mirror patterns from main.dart HomeScreen.

### Task 3B.3 — Wire services into HomeScreen + verify build
- Status: done
- Files changed: `companion_app/lib/main.dart`
- Notes: HomeScreen now delegates camera init to `CameraService.instance` and sensors to `SensorService.instance`. `_latestSensor` replaced with `_sensorService.latestValues`. Tabs still receive CameraController as param (passed from service). Build verified: `✓ Built build/app/outputs/flutter-apk/app-debug.apk`

## [2026-04-10] Wave 3A Update

### Task 3A.1 — Extract simple screens (6 classes)
- Status: done
- Files changed: `screens/review_screen.dart`, `screens/report_viewer_screen.dart`, `screens/profile_progress_screen.dart`, `screens/register_screen.dart`, `screens/health_log_screen.dart`
- Notes: RegisterScreen uses `Navigator.pushNamedAndRemoveUntil(context, '/home', ...)` to avoid circular import with main.dart. Both HealthLogScreen and HealthLogListScreen in one file.

### Task 3A.2 — Extract medium screens (4 classes)
- Status: done
- Files changed: `screens/login_screen.dart`, `screens/results_screen.dart`, `screens/progress_screen.dart`, `screens/history_screen.dart`
- Notes: LoginScreen uses named route `/home` instead of direct HomeScreen import. ResultsScreen imports its cross-screen dependencies (LivePreviewScreen, HistoryScreen, etc.) from the screens/ folder.

### Task 3A.3 — Extract complex screens (3 classes)
- Status: done
- Files changed: `screens/profile_setup_screen.dart`, `screens/live_preview_screen.dart`, `screens/model_viewer_screen.dart`
- Notes: ProfileSetupScreen and LivePreviewScreen use named route `/home`. LivePreviewScreen initializes its own camera via `availableCameras()` (independent of global `_cameras`).

### Task 3A.4 — Extract BodyScanReview + RegionRecapture
- Status: done
- Files changed: `screens/body_scan_review_screen.dart`
- Notes: Both classes in one file. `_RegionRecaptureScreen` renamed to `RegionRecaptureScreen` (public). Internal reference in BodyScanReviewScreen updated to use `RegionRecaptureScreen`.

### Task 3A.5 — Update imports + verify build
- Status: done
- Files changed: `companion_app/lib/main.dart`
- Notes: main.dart reduced from 2,074 lines to 275 lines. All 14 screen imports added. Named routes map added (`/home`). Build succeeded: `✓ Built build/app/outputs/flutter-apk/app-debug.apk`

## [2026-04-10] Wave 3C Update

### Task 3C.1 — Add MOCK_MODE toggle UI
- Status: done
- Files changed: `apps/web_app/templates/studio_v2.html`, `apps/web_app/static/studio/studio.js`
- Notes: Added toggle button in topbar (top-right area). `toggleMockMode()` flips `Studio.MOCK_MODE`, updates button appearance (text Mock/Live, accent color on Live), logs mode change, re-inits CustomerPanel and RenderPanel. `MOCK_MODE: true` remains default.

### Task 3C.2 — Harden panels for MOCK_MODE=false
- Status: done
- Files changed: `customer-panel.js`, `body-scan-panel.js`, `report-panel.js`, `3dgs-panel.js`, `lhm-panel.js`, `multi-capture-panel.js`, `studio_v2.html`
- Notes:
  - `customer-panel.js`: added mock fallback with 2 demo customers; `select()` skips profile fetch in mock mode; error message improved.
  - `body-scan-panel.js`: `loadSessions` shows mock empty state; `startNewSession` logs error and bails in mock mode; `!ok` message improved.
  - `report-panel.js`: improved error message on `!ok`.
  - Mock-only panels (`3dgs-panel.js`, `lhm-panel.js`, `multi-capture-panel.js`): added `_renderModeBanner()` with red "Requires backend — enable Live mode and start py4web" banner; banner div IDs added to HTML.

### Task 3C.3 — Wire viewport
- Status: done (already implemented)
- Files changed: none
- Notes: `render-panel.js` `viewMesh()` already calls `Studio.showInViewport('glb', url)`. `studio.js` already has `showInViewport()` dispatching `CustomEvent('viewport-load')`. `viewport.js` already listens for `viewport-load` and calls `handleLoad()` which dispatches to `loadGLB()`. Full pipeline was already wired.
