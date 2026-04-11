# GTDdebug Requirements for GTD3D Autonomous Loops

## Status (2026-04-11)
- [x] G1: `gtd3d-web-start` — IMPLEMENTED
- [x] G2: `gtd3d-api-check` — IMPLEMENTED
- [x] G3: `gtd3d-apk-audit` — IMPLEMENTED
- [ ] G4: `gtd3d-web-audit` — DEFERRED (needs Playwright, after foundation battle-tested)
- [ ] G5: `gtd3d-loop` — DEFERRED (orchestrator, depends on G4)
- [x] G6: `gtd3d-web-stop` — IMPLEMENTED

## Context

GTD3D is a fitness body-composition tracker with:
- **APK** (`companion_app/`) — Flutter app with 5 tabs: camera, body_scan, live_scan, skin, multi_capture
- **Web Studio** (`apps/web_app/`) — py4web backend + JavaScript studio UI at `/web_app/studio_v2`
- **3D Pipeline** — RunPod GPU inference (LHM++ avatar generation)

GTDdebug already has `deploy`, `agent-cycle`, `agent-status`, and `bench-*` commands that work great for Baloot AI. GTD3D needs equivalent automation so Claude agents can run autonomous fix→build→test→deploy loops without human intervention.

**Profile**: `muscle-debug` (already configured in config.json)

---

## What Already Works (No Changes Needed)

These existing GTDdebug commands work for GTD3D today:
- `deploy muscle-debug` — builds Flutter APK + installs on device
- `agent-cycle muscle-debug --skip-build` — reinstall + screenshot + vision state
- `screen` / `screenshot` — ADB screencap
- `wake` — wake device screen
- `tap` / `swipe` — touch automation
- `perf muscle-debug` — CPU/MEM/battery monitoring
- `wifi-connect` — WiFi ADB connection
- `device-lock-status` / `acquire-device-lock` — device coordination
- `agent-boot` / `agent-end` / `agent-inbox` / `agent-send` — Tazjel protocol

---

## New Commands Needed

### 1. `gtd3d-web-start` — Start py4web + Seed Data + Verify
**What it does:** One command to get the backend running and ready for testing.

```bash
python gtddebug.py gtd3d-web-start --json
```

**Steps:**
1. Check if port 8000 is already bound → skip start if py4web is already running
2. If not running: start `py4web run apps --port 8000` in background (detached process)
3. Poll `GET /web_app/api/health` every 2s, max 30s timeout
4. Once healthy: `POST /web_app/api/seed_demo` to ensure test data exists
5. Acquire admin JWT: `POST /web_app/api/auth/admin_token` with `{"admin_secret":"dev-admin-secret"}`

**Output (JSON):**
```json
{
  "status": "ok",
  "server": "running",
  "port": 8000,
  "health": {"version": "4.0"},
  "seed": "ok",
  "token": "eyJ...",
  "url": "http://localhost:8000/web_app/studio_v2"
}
```

**Why:** Agents currently waste 5-10 tool calls starting py4web, waiting, seeding, and getting tokens. This collapses it to one call.

---

### 2. `gtd3d-web-audit` — Comprehensive Web Studio Health Check
**What it does:** Run all studio checks in one command using Playwright.

```bash
python gtddebug.py gtd3d-web-audit --json
```

**Steps:**
1. Ensure py4web is running (call `gtd3d-web-start` internally if needed)
2. Open `http://localhost:8000/web_app/studio_v2` in headless Chromium
3. Run these checks:
   - **Auth**: Verify no "Authentication required" errors in console
   - **Navigation**: Click each of the 8 nav tabs, verify panel switches
   - **API calls**: Switch to Live mode, verify `/api/customers` returns data
   - **Customer load**: Select first customer, verify profile populates
   - **Scan list**: Verify scan panel loads customer scans
   - **Viewport**: If customer has meshes, verify GLB loads in viewport (no WebGL errors)
   - **Console errors**: Capture all JS console.error entries
4. Screenshot each tab state

**Output (JSON):**
```json
{
  "status": "pass",
  "checks": {
    "auth": {"pass": true},
    "nav_tabs": {"pass": true, "tabs": 8, "all_switch": true},
    "api_live": {"pass": true, "customers": 5},
    "customer_load": {"pass": true, "name": "Demo User"},
    "scan_list": {"pass": true, "scans": 5},
    "viewport": {"pass": false, "error": "GLB fetch 404"},
    "console_errors": ["TypeError: Cannot read property..."]
  },
  "screenshots": ["captures/studio_tab_scan.png", ...],
  "pass_rate": "5/6"
}
```

**Why:** The existing `studio-v2-audit` in `scripts/browser/studio.py` is good but lives in gtd3d's repo, not GTDdebug. Moving this to GTDdebug means any agent can call it via the standard `gtddebug.py` interface without knowing gtd3d's internal scripts.

---

### 3. `gtd3d-apk-audit` — APK UI Regression Check
**What it does:** Launch app on device, navigate all 5 tabs, screenshot each, report issues.

```bash
python gtddebug.py gtd3d-apk-audit --json
```

**Steps:**
1. `svc power stayon true` + set 30min screen timeout (ALWAYS, first thing)
2. Launch app: `am start -n com.example.companion_app/.MainActivity`
3. Wait 3s for app to render
4. Screenshot home screen → save as `captures/apk_audit_home.png`
5. For each of 5 bottom tabs (indices 0-4):
   - Tap the tab coordinates (or use UIAutomator to find BottomNavigationBar items)
   - Wait 1s
   - Screenshot → save as `captures/apk_audit_tab_{name}.png`
6. Check for crash: `adb logcat -d | grep -i "FATAL\|AndroidRuntime\|flutter.*error"`
7. Capture device info: battery level, memory available

**Output (JSON):**
```json
{
  "status": "pass",
  "app_launched": true,
  "tabs_checked": 5,
  "crashes": [],
  "screenshots": [
    "captures/apk_audit_home.png",
    "captures/apk_audit_tab_camera.png",
    "captures/apk_audit_tab_body_scan.png",
    "captures/apk_audit_tab_live_scan.png",
    "captures/apk_audit_tab_skin.png",
    "captures/apk_audit_tab_multi_capture.png"
  ],
  "device": {"battery": 85, "memory_available_mb": 2048},
  "offline_banner": false
}
```

**Tab coordinates (Samsung A24, 1080x2340):**
The BottomNavigationBar has 5 items. Better to use UIAutomator text matching:
- "Camera" / "Body Scan" / "Live Scan" / "Skin" / "Multi Cap"

---

### 4. `gtd3d-api-check` — Backend Route Health
**What it does:** Hit all critical API endpoints and report status codes.

```bash
python gtddebug.py gtd3d-api-check --json
```

**Steps:**
1. Acquire admin token
2. Hit each endpoint category with a test request:
   - `GET /api/health` → expect 200
   - `GET /api/customers` → expect 200 with `status: success`
   - `GET /api/customer/1/scans` → expect 200
   - `GET /api/customer/1/health_logs` → expect 200
   - `GET /api/customer/1/body_profile` → expect 200
   - `GET /api/customer/1/quick_stats` → expect 200
   - `GET /api/customer/1/meshes` → expect 200
   - `POST /api/lhm/status/nonexistent` → expect 404 or error (not crash)
   - `GET /api/muscle_groups` → expect 200
   - `GET /studio_v2` → expect 200

**Output (JSON):**
```json
{
  "status": "pass",
  "total": 10,
  "passed": 9,
  "failed": 1,
  "results": [
    {"route": "/api/health", "method": "GET", "status": 200, "pass": true},
    {"route": "/api/customer/1/meshes", "method": "GET", "status": 500, "pass": false, "error": "table mesh_model..."}
  ]
}
```

---

### 5. `gtd3d-loop` — Autonomous Fix Cycle
**What it does:** The main loop command. Runs audit → identifies failures → agent fixes code → rebuilds → re-audits. Stops when all checks pass or max iterations reached.

```bash
python gtddebug.py gtd3d-loop --target web --max-iterations 5 --json
python gtddebug.py gtd3d-loop --target apk --max-iterations 3 --json
python gtddebug.py gtd3d-loop --target all --max-iterations 5 --json
```

**Steps (for `--target web`):**
1. `gtd3d-web-start` → ensure backend running
2. `gtd3d-api-check` → get baseline failures
3. `gtd3d-web-audit` → get UI failures
4. If all pass → exit with `{status: "all_pass", iterations: 0}`
5. If failures exist → output structured failure list for the calling agent
6. (Calling agent fixes code)
7. Agent calls `gtd3d-loop` again → it re-runs checks
8. Repeat until pass or max iterations

**Steps (for `--target apk`):**
1. `deploy muscle-debug` → build + install
2. `gtd3d-apk-audit` → check all tabs
3. If all pass → exit
4. If failures → output structured failure list
5. (Agent fixes code)
6. Agent calls `gtd3d-loop --target apk --skip-build` to reinstall only
7. Repeat

**Output (JSON):**
```json
{
  "status": "failures_found",
  "iteration": 2,
  "target": "web",
  "failures": [
    {
      "check": "api_check",
      "route": "/api/customer/1/meshes",
      "error": "OperationalError: no such column: mesh_model.lhm_used",
      "file_hint": "apps/web_app/mesh_controller.py",
      "line_hint": "grep for 'lhm_used' in mesh_controller.py"
    },
    {
      "check": "web_audit",
      "component": "viewport",
      "error": "GLB fetch returned 404",
      "file_hint": "apps/web_app/static/studio/viewport.js",
      "line_hint": "check mesh URL construction"
    }
  ],
  "passed": ["auth", "nav_tabs", "api_live", "customer_load", "scan_list"],
  "screenshots": ["captures/loop_iter2_viewport_fail.png"]
}
```

**Key design:** The `file_hint` and `line_hint` fields tell the agent WHERE to look, so it doesn't waste tokens exploring. This is the main token-saving feature.

---

### 6. `gtd3d-web-stop` — Clean shutdown
```bash
python gtddebug.py gtd3d-web-stop --json
```
Kill the py4web process on port 8000. Simple but needed for clean loops.

---

## Implementation Notes for GTDdebug Agent

### Where to add these commands
- Create `gtddebug/gtd3d.py` module (following the pattern of `gtddebug/agent.py`, `gtddebug/build.py`)
- Register commands in `gtddebug/cli.py` (or wherever the argparse dispatcher lives)
- All commands should accept `--json` flag for structured output

### Dependencies
- `requests` — for HTTP health checks and API calls
- `subprocess` — for py4web start/stop
- `playwright` — for web audit (already installed for baloot-ai)
- Standard ADB commands via existing `gtddebug/adb.py` or `gtddebug/device.py`

### Config needed in config.json
Add to the `muscle-debug` profile:
```json
{
  "web_port": 8000,
  "web_app_path": "apps",
  "py4web_path": "C:\\Users\\MiEXCITE\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\py4web.exe",
  "studio_url": "/web_app/studio_v2",
  "api_base": "/web_app",
  "admin_secret": "dev-admin-secret",
  "apk_tabs": ["Camera", "Body Scan", "Live Scan", "Skin", "Multi Cap"],
  "critical_api_routes": [
    {"method": "GET", "path": "/api/health"},
    {"method": "GET", "path": "/api/customers"},
    {"method": "GET", "path": "/api/customer/1/scans"},
    {"method": "GET", "path": "/api/customer/1/body_profile"},
    {"method": "GET", "path": "/api/customer/1/quick_stats"},
    {"method": "GET", "path": "/api/muscle_groups"},
    {"method": "GET", "path": "/studio_v2"}
  ]
}
```

### Error-to-file mapping (for `file_hint` in gtd3d-loop)
The loop command needs a mapping of common error patterns to likely source files:

```python
ERROR_FILE_MAP = {
    "OperationalError": "check models.py or the controller that queries this table",
    "no such column": "column missing — check models.py table definition",
    "ImportError": "check imports at top of the failing controller",
    "404": "route not registered — check __init__.py imports",
    "CORS": "check cors fixture in the @action.uses() decorator",
    "Authentication required": "check _auth_check() and token header",
    "GLB fetch": "check mesh_controller.py serve_mesh_glb()",
    "WebGL": "check viewport.js GLTFLoader setup",
    "Cannot read property": "JS null reference — check panel init order in studio.js",
    "flutter.*error": "check the Dart file referenced in the stack trace",
    "FATAL EXCEPTION": "check companion_app/lib/ — crash in native code",
}

ROUTE_TO_FILE = {
    "/api/customer/": {
        "scans": "body_scan_controller.py",
        "body_scan": "body_scan_controller.py",
        "live_scan": "body_scan_controller.py",
        "skin_texture": "texture_controller.py",
        "skin_region": "texture_controller.py",
        "pbr_textures": "texture_controller.py",
        "body_model": "body_model_controller.py",
        "update_deformation": "body_model_controller.py",
        "body_profile": "profile_controller.py",
        "profile_status": "profile_controller.py",
        "devices": "profile_controller.py",
        "health_log": "profile_controller.py",
        "meshes": "mesh_controller.py",
        "reconstruct_3d": "mesh_controller.py",
        "compare": "mesh_controller.py",
        "body_map": "dashboard_controller.py",
        "quick_stats": "dashboard_controller.py",
        "progress": "dashboard_controller.py",
        "session_report": "dashboard_controller.py",
        "export": "dashboard_controller.py",
        "upload_scan": "scan_upload_controller.py",
        "upload_session": "profile_controller.py",
        "render": "dashboard_controller.py",
        "room_texture": "texture_controller.py",
    },
    "/api/lhm/": "lhm_controller.py",
    "/api/auth/": "controllers.py",
    "/api/health": "controllers.py",
    "/api/customers": "controllers.py",
    "/studio": "studio_controller.py",
}
```

### Phone lock prevention
**CRITICAL:** Every command that touches ADB MUST start with:
```python
def _ensure_awake(serial):
    """Prevent phone from locking during automation."""
    subprocess.run(["adb", "-s", serial, "shell", "svc", "power", "stayon", "true"])
    subprocess.run(["adb", "-s", serial, "shell", "settings", "put", "system", "screen_off_timeout", "1800000"])
```

This is non-negotiable. The phone locks mid-test and wastes entire agent sessions.

---

## Priority Order

1. **`gtd3d-web-start`** — foundation for everything (easiest, most reused)
2. **`gtd3d-api-check`** — fast validation, no browser needed
3. **`gtd3d-apk-audit`** — requires device but simple ADB flow
4. **`gtd3d-web-audit`** — needs Playwright, can reuse `studio-v2-audit` logic
5. **`gtd3d-loop`** — orchestrator, depends on 1-4
6. **`gtd3d-web-stop`** — simple cleanup utility
