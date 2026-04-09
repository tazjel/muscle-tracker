# Next Session Brief — GTD3D (2026-04-10)

## Just Completed: Wave 2 — APK Tabs + Web Panel Upgrades
Commits: `6672202` (merge), `93c1159` (APK), `2f68f6b` (web stubs), `2f3f0f7` (web enhance)

**APK**: main.dart 3,562→2,074 lines. 5 real tab files (camera 549, body_scan 278, live_scan 378, skin 183, multi_capture 379).
**Web**: 5 panels upgraded from stubs to real API integration (scan 262, render 259, device 184, progress 489, texture 519).
Detailed handoff: memory `handoff_next_agent.md`

## Next Up: Wave 3 — Screen Extraction + Services + Live Mode

### Wave 3 Sonnet Agent Tasks (ready to dispatch)

**Agent 1 — APK Screen Extraction (worktree, ~20 min)**
Extract 15 screen classes from main.dart (2,074 lines) to `companion_app/lib/screens/`.
Target: main.dart → ~800 lines after extraction.
Screens to extract (grep for `^class` to find current line numbers):
- ProfileSetupScreen, LoginScreen, ReviewScreen, ResultsScreen
- ProfileProgressScreen, HistoryScreen, ProgressScreen
- HealthLogScreen, HealthLogListScreen, RegisterScreen
- ReportViewerScreen, LivePreviewScreen, ModelViewerScreen
- BodyScanReviewScreen, _RegionRecaptureScreen
Rules: remove `_` prefix on private classes, update imports in main.dart, `flutter.bat build apk --debug` to verify.

**Agent 2 — APK Services Implementation (worktree, ~15 min)**
Implement 3 stub services in `companion_app/lib/services/`:
- `api_service.dart` (6→~200 lines) — centralize all HTTP calls: GET/POST with JWT auth header from config.dart `jwtToken`, base URL from `AppConfig.serverBaseUrl`, response parsing. Extract repeated `http.get/post` patterns from tabs/ and screens/.
- `camera_service.dart` (6→~100 lines) — singleton owning CameraController init, frame capture (`takePicture`), torch toggle, resolution switching. Currently HomeScreen owns controller directly.
- `sensor_service.dart` (6→~80 lines) — singleton owning accelerometer/gyro/magnetometer streams, expose pitch/roll as ValueNotifier or Stream. Currently HomeScreen subscribes directly.
Rules: Use singleton pattern (already scaffolded). Don't add Provider/Riverpod. Wire into HomeScreen, update tabs to use services instead of passed params.

**Agent 3 — Web Studio Live Mode (worktree, ~10 min)**
- Set `Studio.MOCK_MODE = false` in studio.js line 12
- Add a `MOCK_MODE` toggle button in the top bar (so developers can switch)
- Verify all panels handle `MOCK_MODE=false` gracefully (no crashes when backend is down)
- Wire viewport.js to render-panel.js: when "View 3D" is clicked in mesh list, call `Studio.showInViewport('glb', url)` — this dispatches `viewport-load` event that viewport.js listens to
- Test: start py4web (`py4web run apps --port 8000`), seed data, open studio_v2, verify customer list loads, scan upload works
- `git add -f` for all `apps/` files

### Agent Dependency Map
```
Agent 1 (screens) ──┐
                     ├──→ Merge + verify build
Agent 2 (services) ──┘    (Agent 2 depends on Agent 1 if services
                           reference screen classes — safer to run
                           sequentially or merge Agent 1 first)
Agent 3 (web live) ─────→ Independent, can run in parallel
```

### Quick Start
```bash
cd C:/Users/MiEXCITE/Projects/gtd3d
py4web run apps --port 8000
curl -X POST http://localhost:8000/web_app/api/seed_demo
# APK: cd companion_app && flutter.bat clean && flutter.bat run
# Studio: http://localhost:8000/web_app/studio_v2
```

### Key Technical Notes
- `.gitignore` matches `apps/` — ALWAYS `git add -f`
- Grep for class/function names, never trust line numbers from memory
- Sequential bash calls only (Windows)
- Services: singleton with ValueNotifier, NOT Provider/Riverpod
- Tab pattern: AutomaticKeepAliveClientMixin, shared CameraController

## Also Pending (lower priority)
- Docker/RunPod LHM++ deployment (handler_v2.py v8, Dockerfile with CUDA fixes)
- Rename GitHub repo muscle-tracker → gtd3d
- 3dgs-panel.js, lhm-panel.js, multi-capture-panel.js still mock-only
