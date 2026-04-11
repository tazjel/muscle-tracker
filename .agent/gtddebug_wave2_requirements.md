# GTDdebug Wave 2 Requirements for GTD3D

## Context

Wave 1 commands (G1-G3, G6) are battle-tested and working. All bugs from `.agent/gtddebug_feedback.md` are fixed. Time for the next layer: Playwright web audit, the autonomous loop orchestrator, and device health management.

---

## G4: `gtd3d-web-audit` — Playwright Studio Health Check

**What it does:** Open studio_v2 in headless Chromium, check all 8 tabs, verify live API, report pass/fail.

```bash
python gtddebug.py gtd3d-web-audit --json
```

**Steps:**
1. Call `gtd3d-web-start` internally (ensure backend running + JWT)
2. Launch headless Chromium via Playwright
3. Navigate to `http://localhost:8000/web_app/studio_v2`
4. Wait for page load (check for `Studio.init()` completion — look for nav tabs rendered)
5. Collect all `console.error` entries throughout the test
6. Run these checks:

| Check | How | Pass Criteria |
|-------|-----|--------------|
| `page_load` | Wait for `#nav-tabs` visible | Rendered within 5s |
| `mock_toggle` | Click Mock/Live button, check `Studio.MOCK_MODE` via JS eval | Toggles to false |
| `auth` | Check `Studio._token` via JS eval after live mode | Token is non-null |
| `nav_tabs` | Click each of 8 nav links, verify panel switches | All 8 panels show/hide correctly |
| `customer_list` | In live mode, check customer-panel has rows | At least 1 customer loaded |
| `customer_select` | Click first customer row | `Studio.customerId` is set |
| `scan_list` | After customer select, check scan-panel | Scans loaded (count >= 0, no error) |
| `viewport` | If customer has meshes, check viewport canvas | No WebGL errors |
| `console_errors` | Collect all console.error from entire run | Report them (don't fail on warnings) |

7. Screenshot each tab: save to `captures/web_audit_{tab_name}.png`

**Output (JSON):**
```json
{
  "status": "pass",
  "checks": {
    "page_load": {"pass": true, "ms": 1200},
    "mock_toggle": {"pass": true},
    "auth": {"pass": true, "token_len": 167},
    "nav_tabs": {"pass": true, "count": 8},
    "customer_list": {"pass": true, "count": 5},
    "customer_select": {"pass": true, "id": 1},
    "scan_list": {"pass": true, "count": 5},
    "viewport": {"pass": false, "error": "GLB 404"},
    "console_errors": ["TypeError: x is null at lhm-panel.js:42"]
  },
  "screenshots": ["captures/web_audit_scan.png", ...],
  "pass_rate": "7/8"
}
```

**Implementation note:** GTD3D already has Playwright logic in `scripts/browser/studio.py` (`studio-v2-audit` command). Reuse that logic — it already knows the nav tab selectors, mock toggle, and viewport checks. The key difference: this version runs through GTDdebug's CLI, returns structured JSON with `file_hint` on failures, and integrates with the loop.

**Existing selectors to reuse (from scripts/browser/studio.py):**
- Nav tabs: `a[data-nav]` links in the sidebar
- Mock toggle: button with "Mock" or "Live" text
- Customer panel: `#panel-customer` or similar
- Viewport: `#viewport canvas` or Three.js container

---

## G5: `gtd3d-loop` — Autonomous Fix Cycle Orchestrator

**What it does:** Run all audits → report failures with file hints → wait for agent to fix → re-run. The loop controller.

```bash
python gtddebug.py gtd3d-loop --target web --max-iterations 5 --json
python gtddebug.py gtd3d-loop --target apk --max-iterations 3 --json
python gtddebug.py gtd3d-loop --target all --max-iterations 5 --json
```

**Steps for `--target web`:**
1. `gtd3d-web-start` → ensure backend
2. `gtd3d-api-check` → route health
3. `gtd3d-web-audit` → UI health
4. Merge results → output structured failure list with `file_hint` per failure
5. Exit with status `all_pass` or `failures_found`

**Steps for `--target apk`:**
1. `gtd3d-apk-clean-ram` → free memory first
2. `deploy muscle-debug` → build + install (or `--skip-build` for reinstall only)
3. `gtd3d-apk-audit` → tab check + screenshots
4. Merge results → output failure list with `file_hint`

**Steps for `--target all`:**
1. Run web checks first (no device needed)
2. Then run APK checks
3. Merge all results

**Output (JSON):**
```json
{
  "status": "failures_found",
  "target": "web",
  "iteration": 1,
  "max_iterations": 5,
  "failures": [
    {
      "check": "api_check",
      "route": "/api/customer/1/meshes",
      "error": "OperationalError: no such column: mesh_model.lhm_used",
      "file_hint": "apps/web_app/mesh_controller.py",
      "grep_hint": "lhm_used"
    },
    {
      "check": "web_audit",
      "component": "viewport",
      "error": "GLB fetch returned 404",
      "file_hint": "apps/web_app/static/studio/viewport.js",
      "grep_hint": "mesh_url"
    },
    {
      "check": "web_audit",
      "component": "console_error",
      "error": "TypeError: x is null at lhm-panel.js:42",
      "file_hint": "apps/web_app/static/studio/lhm-panel.js",
      "grep_hint": "line 42"
    }
  ],
  "passed": ["page_load", "auth", "nav_tabs", "customer_list", "scan_list"],
  "next_action": "fix failures and re-run: gtd3d-loop --target web --iteration 2"
}
```

**Error-to-file mapping** (include in GTDdebug):
```python
ROUTE_TO_FILE = {
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
    "lhm": "lhm_controller.py",
    "auth": "controllers.py",
    "health": "controllers.py",
    "customers": "controllers.py",
    "studio": "studio_controller.py",
    "seed_demo": "profile_controller.py",
}

JS_FILE_MAP = {
    "studio.js": "apps/web_app/static/studio/studio.js",
    "customer-panel": "apps/web_app/static/studio/customer-panel.js",
    "scan-panel": "apps/web_app/static/studio/scan-panel.js",
    "body-scan-panel": "apps/web_app/static/studio/body-scan-panel.js",
    "render-panel": "apps/web_app/static/studio/render-panel.js",
    "device-panel": "apps/web_app/static/studio/device-panel.js",
    "progress-panel": "apps/web_app/static/studio/progress-panel.js",
    "texture-panel": "apps/web_app/static/studio/texture-panel.js",
    "report-panel": "apps/web_app/static/studio/report-panel.js",
    "3dgs-panel": "apps/web_app/static/studio/3dgs-panel.js",
    "lhm-panel": "apps/web_app/static/studio/lhm-panel.js",
    "multi-capture-panel": "apps/web_app/static/studio/multi-capture-panel.js",
    "viewport": "apps/web_app/static/studio/viewport.js",
}

ERROR_PATTERN_MAP = {
    "OperationalError": "check models.py table definition",
    "no such column": "column missing in models.py",
    "ImportError": "check imports at top of controller",
    "404": "route not registered — check __init__.py",
    "CORS": "check cors in @action.uses()",
    "Authentication required": "check _auth_check() and token",
    "WebGL": "check viewport.js GLTFLoader",
}
```

---

## G7: `gtd3d-apk-clean-ram` — Device Memory Cleanup

**What it does:** Free RAM on the phone between test cycles. Always run before deploy.

```bash
python gtddebug.py gtd3d-apk-clean-ram --json
```

**Steps:**
1. `svc power stayon true` + screen timeout 30min (always, first thing)
2. Force-stop the app: `am force-stop com.example.companion_app`
3. Kill background processes: `am kill-all`
4. Drop filesystem caches: `echo 3 > /proc/sys/vm/drop_caches` (may need root, skip if fails)
5. Trim memory: `am send-trim-memory com.example.companion_app COMPLETE` (skip if app not running)
6. Report memory before/after:
   - `cat /proc/meminfo | grep MemAvailable`
   - `dumpsys meminfo --summary com.example.companion_app` (if running)

**Output (JSON):**
```json
{
  "status": "ok",
  "mem_before_mb": 1200,
  "mem_after_mb": 2100,
  "freed_mb": 900,
  "app_killed": true,
  "cache_dropped": false
}
```

**Integration:** `gtd3d-loop --target apk` should call this automatically before each deploy cycle.

---

## G8: `gtd3d-deploy-smart` — Skip Rebuild If Unchanged

**What it does:** Check if Dart source files changed since last build. If not, skip `flutter build` and just reinstall the existing APK. Saves 40-90 seconds per cycle.

```bash
python gtddebug.py gtd3d-deploy-smart --json
```

**Steps:**
1. Check `companion_app/build/app/outputs/flutter-apk/app-debug.apk` exists and note its mtime
2. Check `git diff --name-only HEAD` for any `.dart` or `pubspec.yaml` changes in `companion_app/`
3. Also check `git diff --cached` for staged changes
4. If no Dart/pubspec changes since last APK build:
   - Skip build, just `adb install -r` the existing APK
   - Log: `"build": "skipped (no dart changes)"`
5. If changes exist:
   - Run `flutter clean && flutter build apk --debug`
   - Install the new APK
6. Launch the app after install

**Output (JSON):**
```json
{
  "status": "ok",
  "build": "skipped",
  "reason": "no dart changes since last build (app-debug.apk mtime: 2026-04-11T00:30:00)",
  "install": "success",
  "launched": true,
  "elapsed_ms": 8500
}
```

or:

```json
{
  "status": "ok",
  "build": "rebuilt",
  "reason": "3 dart files changed: api_service.dart, main.dart, connectivity_service.dart",
  "install": "success",
  "launched": true,
  "elapsed_ms": 95000
}
```

---

## G9: `gtd3d-screenshot-diff` — Visual Regression Detection

**What it does:** Compare current APK screenshots against golden baselines. Detect UI regressions.

```bash
python gtddebug.py gtd3d-screenshot-diff --json
python gtddebug.py gtd3d-screenshot-diff --save-baseline --json  # save current as golden
```

**Steps (compare mode):**
1. Run `gtd3d-apk-audit` to get fresh screenshots of all 5 tabs
2. Compare each screenshot against baselines in `captures/baselines/gtd3d/`
3. Use SSIM or pixel diff (GTDdebug already has `compare` command)
4. Report similarity % per tab, flag any below 85% threshold

**Steps (save-baseline mode):**
1. Run `gtd3d-apk-audit` to get fresh screenshots
2. Copy them to `captures/baselines/gtd3d/` with tab names
3. Record device info (model, resolution, Android version) in a metadata JSON

**Output (JSON):**
```json
{
  "status": "regression",
  "results": [
    {"tab": "camera", "similarity": 0.97, "pass": true},
    {"tab": "body_scan", "similarity": 0.92, "pass": true},
    {"tab": "live_scan", "similarity": 0.71, "pass": false, "diff_image": "captures/diff_live_scan.png"},
    {"tab": "skin", "similarity": 0.95, "pass": true},
    {"tab": "multi_cap", "similarity": 0.93, "pass": true}
  ],
  "regressions": ["live_scan"],
  "baseline_date": "2026-04-11",
  "device": "SM-A245F"
}
```

---

## Priority Order

1. **G7: `gtd3d-apk-clean-ram`** — quick win, prevents OOM in cycles
2. **G8: `gtd3d-deploy-smart`** — saves 40-90s per cycle, huge for loops
3. **G4: `gtd3d-web-audit`** — Playwright checks, enables G5
4. **G5: `gtd3d-loop`** — the main orchestrator, depends on G4+G7+G8
5. **G9: `gtd3d-screenshot-diff`** — visual regression, nice-to-have after loop works

## Integration: How the Full Loop Works

```
Agent detects bug or gets task
    │
    ▼
Agent fixes code (Edit tool)
    │
    ▼
gtd3d-apk-clean-ram          ← G7: free RAM
    │
    ▼
gtd3d-deploy-smart            ← G8: skip build if no dart changes
    │
    ▼
gtd3d-loop --target all       ← G5: runs G2 + G3 + G4
    │
    ├─ PASS → commit + done
    │
    └─ FAIL → failures[] with file_hint
         │
         ▼
    Agent reads file_hint, fixes code
         │
         ▼
    Re-run gtd3d-loop --target all --skip-build
         │
         └─ repeat until PASS or max iterations
```
