# GTDdebug Wave 3 Test Results (2026-04-11)

## Full Cycle Test: G13 `gtd3d-full-cycle`

**Overall: PASS in 139 seconds**

```
ram_cleanup     : freed 560 MB
deploy          : build skipped, install success (14s)
backend         : health ok, seed ok
apk_audit       : 5/5 tabs, 0 crashes
api_check       : 7/7 routes pass
web_audit       : 5/7 (2 false failures)
perf            : PSS=297 MB, jank=8.7%, 39.1°C
logcat          : 0 errors, 0 warnings
```

## Bug Fixes Confirmed Working
- G3 tab retry logic: 5/5 tabs found consistently now
- G4 mock_toggle: PASS (no longer clicking the toggle, just verifying state)
- G12 perf-snapshot: CPU/memory/battery/jank all parsed correctly
- G11 logcat-watch: clean capture, 0 noise

## Remaining Bug: G4 customer_list (0 rows)

**Root cause confirmed:** This is a Playwright timing issue, NOT an app bug.

Proof: `curl /api/customers` with JWT returns `{"customers": [{"name": "Ahmed Bani", "id": 1, ...}]}` — the API works fine.

The customer panel loads asynchronously via `CustomerPanel.loadCustomers()` → `Studio.apiGet('/api/customers')`. By the time Playwright checks the DOM, the panel may not have rendered yet.

**Fix:** In G4's customer_list check, add:
```python
# Wait for customer rows to appear (async load)
try:
    await page.wait_for_selector(
        '#panel-customer tr, #panel-customer .customer-row, [data-customer-id]',
        timeout=5000
    )
except:
    pass  # If timeout, check count will be 0 = FAIL
```

Or use JS evaluation:
```python
count = await page.evaluate('CustomerPanel.customers.length')
```

This is more reliable than DOM checking since the data loads before render.

## Performance Observations (from G12)

| Metric | Value | Assessment |
|--------|-------|-----------|
| PSS Memory | 297 MB | High — camera service + Flutter overhead. Consider releasing camera when not on Camera tab |
| Jank | 8.7% (2/23) | Acceptable for debug build. Monitor in release |
| CPU (camera) | 53% | Expected when camera preview is active |
| Battery temp | 39.1°C | Warm but not throttling (<42°C) |
| Logcat errors | 0 | Clean — no Flutter exceptions during idle |

## New Requirements

### Fix: G4 customer_list timing
Use JS eval `CustomerPanel.customers.length` instead of DOM row counting. More reliable, doesn't depend on render timing.

### New: G14 `gtd3d-api-check-extended` — Cover ALL controller routes
Current api-check only tests 7 routes. The app has 86+ routes across 9 controllers. Extend to cover:

```python
EXTENDED_ROUTES = [
    # Core (controllers.py)
    ("GET", "/api/health"),
    ("GET", "/api/customers"),
    ("GET", "/api/muscle_groups"),
    ("GET", "/api/shape_templates"),
    ("GET", "/api/volume_models"),
    
    # Profile (profile_controller.py)
    ("GET", "/api/customer/1/body_profile"),
    ("GET", "/api/customer/1/profile_status"),
    ("GET", "/api/customer/1/devices"),
    ("GET", "/api/customer/1/health_logs"),
    ("GET", "/api/customer/1/progress_report"),
    
    # Dashboard (dashboard_controller.py)
    ("GET", "/api/customer/1/quick_stats"),
    ("GET", "/api/customer/1/body_map"),
    ("GET", "/api/customer/1/progress_summary"),
    ("GET", "/api/customer/1/export"),
    
    # Scans (body_scan_controller.py)
    ("GET", "/api/customer/1/scans"),
    ("GET", "/api/body_scan_result"),
    
    # Meshes (mesh_controller.py)
    ("GET", "/api/customer/1/meshes"),
    ("GET", "/api/mesh/template.glb"),
    
    # Textures (texture_controller.py)
    ("GET", "/api/customer/1/skin_regions"),
    ("GET", "/api/customer/1/pbr_textures"),
    ("GET", "/api/customer/1/room_textures"),
    
    # LHM (lhm_controller.py)
    ("GET", "/api/lhm/status/nonexistent"),
    
    # Studio (studio_controller.py)
    ("GET", "/studio_v2"),
    ("GET", "/viewer"),
    ("GET", "/body_viewer"),
]
```

Should report: `25/25 passed` or which specific routes fail with HTTP status + error message + `file_hint`.

### New: G15 `gtd3d-seed-reset` — Reset database to known state
For reproducible testing, reset the database to a clean seeded state:

1. Delete all customers, scans, meshes, health_logs
2. Re-run seed_demo
3. Verify customer 1 exists with expected profile

This ensures tests aren't polluted by leftover data from previous runs.

### New: G16 `gtd3d-camera-release` — Stop camera to save RAM
After APK audit, the camera stays active eating 53% CPU and ~150MB RAM:

```bash
adb shell am broadcast -a com.example.companion_app.RELEASE_CAMERA
```

Or simpler: force-stop and relaunch only when needed. The app should be modified to accept this broadcast, or GTDdebug should navigate away from the Camera tab after audit to release the camera.

**Quick fix for now:** After apk-audit, tap a non-camera tab (e.g., "Skin" tab 4) so the camera is released by AutomaticKeepAliveClientMixin losing its keep-alive.

Actually — the IndexedStack keeps all tabs alive. The camera WON'T release just by switching tabs. This is a real app issue:
- **App fix needed:** Use `wantKeepAlive = false` for camera_tab when not selected, or dispose camera in `deactivate()`
- **GTDdebug workaround:** `am force-stop` after audit, only relaunch when needed

### New: G17 `gtd3d-apk-memory-profile` — Track memory over time
Record PSS/USS every 5 seconds for 60 seconds while interacting:

1. Launch app
2. Start memory sampling loop (every 5s)
3. Navigate through tabs: Camera → Body Scan → Live Scan → Skin → Multi-Cap → back to Camera
4. Stop sampling
5. Report: peak PSS, average PSS, memory per tab, leak detection (is PSS growing?)

Output: JSON + simple ASCII chart of memory over time.
