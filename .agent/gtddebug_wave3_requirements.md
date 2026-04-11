# GTDdebug Wave 3 Requirements for GTD3D

## Testing Results (2026-04-11)

### Wave 2 Command Status
| # | Command | Status | Issue |
|---|---------|--------|-------|
| G4 | `gtd3d-web-audit` | Works but 3 false failures | mock_toggle check logic inverted, customer_list timing |
| G5 | `gtd3d-loop` | Works end-to-end | Correctly chains sub-commands, reports failures with file_hint |
| G7 | `gtd3d-apk-clean-ram` | PASS | Freed 558-575 MB consistently |
| G8 | `gtd3d-deploy-smart` | PASS | Correctly skips build, installs in 14s |

### Bugs Found

#### Bug 1: G4 mock_toggle check is inverted
**Problem:** Studio now starts in live mode (`MOCK_MODE: false`). The G4 check clicks the toggle and expects `MOCK_MODE` to be false, but clicking it switches it TO mock (true).

**Fix:** The check should verify:
1. `Studio.MOCK_MODE === false` BEFORE clicking (confirms live mode auto-detected)
2. Don't click the toggle at all — just verify the current state
3. Or: click toggle, verify it's true, click again, verify it's back to false

#### Bug 2: G4 customer_list shows 0 rows
**Problem:** The customer panel loads asynchronously. By the time Playwright checks, the DOM may not have rendered the customer rows yet.

**Fix:** After the page loads and auth succeeds, wait for customer rows to appear:
```python
await page.wait_for_selector('#panel-customer tr, #panel-customer .customer-row', timeout=5000)
```
Or evaluate `Studio.customer` via JS to confirm data loaded.

#### Bug 3: G3 tab detection race condition (intermittent)
**Problem:** UIAutomator dump sometimes misses tabs if the app hasn't fully rendered. First run found 5/5, second run found 2/5. The Camera/Body Scan/Live Scan tabs use camera initialization which is slow.

**Fix:** Add a longer wait before the first UIAutomator dump. Currently it waits 3s after launch — increase to 5s. Or: retry the UI dump up to 3 times if expected tabs aren't found.

#### Bug 4: G3 status says PASS even when tabs are missing
**Problem:** The audit said `Status: PASS` but only found 2/5 tabs. If tabs are missed, status should be FAIL.

**Fix:** Status should be FAIL if `tabs_found < tabs_expected`. Currently it seems to only check for crashes.

---

## New Commands Needed

### G10: `gtd3d-apk-flow` — Automated UI Interaction Sequence
**What it does:** Go beyond tab checking — actually interact with the app's UI flows.

```bash
python gtddebug.py gtd3d-apk-flow --flow profile-setup --json
python gtddebug.py gtd3d-apk-flow --flow camera-capture --json
python gtddebug.py gtd3d-apk-flow --flow scan-review --json
```

**Flows:**

**`profile-setup`:**
1. Launch app
2. If on Camera tab (home), check if dev profile auto-submitted
3. Tap settings/profile icon (if exists)
4. Screenshot profile screen
5. Verify profile fields are populated (UIAutomator text check)

**`camera-capture`:**
1. Ensure on Camera tab
2. Tap "PHOTO" mode button (content-desc="PHOTO")
3. Wait 2s for camera preview
4. Tap capture button (center bottom area)
5. Wait 3s
6. Screenshot result
7. Check for error dialogs

**`scan-review`:**
1. Tap "Body Scan" tab
2. Wait for scan list or "Start Scan" button
3. Screenshot the state
4. If scans exist, tap first scan row
5. Screenshot review screen

**Output:** JSON with pass/fail per step, screenshots, and any error dialogs found.

### G11: `gtd3d-logcat-watch` — Filtered Log Capture During Test
**What it does:** Capture only Flutter/app logs during a test window, filter out noise.

```bash
python gtddebug.py gtd3d-logcat-watch --seconds 30 --json
```

**Steps:**
1. Clear logcat buffer: `adb logcat -c`
2. Start logcat in background with filter: `adb logcat -s flutter,AndroidRuntime,System.err`
3. Wait N seconds
4. Kill logcat
5. Parse output for:
   - `E/flutter`: Flutter errors (CRITICAL)
   - `E/AndroidRuntime`: Crashes (CRITICAL)
   - `W/flutter`: Flutter warnings (INFO)
   - `I/flutter`: Flutter prints (DEBUG)
6. Dedup repeated lines, count occurrences

**Output (JSON):**
```json
{
  "status": "ok",
  "duration_seconds": 30,
  "errors": [
    {"level": "E", "tag": "flutter", "message": "SocketException: Connection refused", "count": 3}
  ],
  "warnings": [
    {"level": "W", "tag": "flutter", "message": "Image provider failed", "count": 1}
  ],
  "debug": 12,
  "total_lines": 45
}
```

### G12: `gtd3d-perf-snapshot` — Quick Performance Check
**What it does:** Capture CPU/memory/battery in one shot during app use.

```bash
python gtddebug.py gtd3d-perf-snapshot --json
```

**Steps:**
1. `dumpsys cpuinfo | head -20` → top CPU consumers
2. `dumpsys meminfo com.example.companion_app --short` → PSS/USS memory
3. `dumpsys battery` → level, temperature, charging
4. `dumpsys gfxinfo com.example.companion_app` → janky frames count

**Output (JSON):**
```json
{
  "status": "ok",
  "cpu_top3": [
    {"process": "com.example.companion_app", "cpu_pct": 12.5},
    {"process": "surfaceflinger", "cpu_pct": 3.2}
  ],
  "memory": {"pss_mb": 85, "private_dirty_mb": 62},
  "battery": {"level": 85, "temp_c": 32.1, "charging": true},
  "jank": {"total_frames": 500, "janky_frames": 12, "jank_pct": 2.4}
}
```

### G13: `gtd3d-full-cycle` — The Complete Autonomous Pipeline
**What it does:** Everything in one command. The ultimate loop for agents.

```bash
python gtddebug.py gtd3d-full-cycle --json
```

**Steps:**
1. `gtd3d-apk-clean-ram`
2. `gtd3d-deploy-smart` (or `--force-build` to always rebuild)
3. `gtd3d-web-start` (ensure backend)
4. `gtd3d-apk-audit` (all 5 tabs)
5. `gtd3d-api-check` (all routes)
6. `gtd3d-web-audit` (Playwright studio)
7. `gtd3d-perf-snapshot` (performance)
8. `gtd3d-logcat-watch --seconds 10` (error capture)
9. Aggregate all results into single report

**Output (JSON):**
```json
{
  "status": "pass",
  "components": {
    "ram_cleanup": {"freed_mb": 550},
    "deploy": {"build": "skipped", "install": "success"},
    "backend": {"health": "ok", "routes": "7/7"},
    "apk_audit": {"tabs": "5/5", "crashes": 0},
    "web_audit": {"checks": "7/7"},
    "perf": {"pss_mb": 85, "jank_pct": 2.4},
    "logcat": {"errors": 0, "warnings": 1}
  },
  "overall": "PASS",
  "elapsed_ms": 95000
}
```

**Why:** One command for agents to run after every code change. No need to remember which commands to chain.

---

## Bug Fixes Required (Priority Order)

1. **G3 tab detection retry** — if < 5 tabs found, wait 2s and retry UIAutomator dump (up to 3 times)
2. **G3 status logic** — FAIL if tabs_found < tabs_expected
3. **G4 mock_toggle** — don't click the toggle, just verify `Studio.MOCK_MODE === false`
4. **G4 customer_list wait** — `wait_for_selector` on customer rows with 5s timeout
5. **G3 raw output suppression** — UIAutomator XML still leaking to stdout outside JSON (36KB of noise)

## New Commands Priority

1. **G13: `gtd3d-full-cycle`** — highest value, one command for everything
2. **G12: `gtd3d-perf-snapshot`** — quick, useful for monitoring
3. **G11: `gtd3d-logcat-watch`** — catches Flutter errors agents would miss
4. **G10: `gtd3d-apk-flow`** — deeper UI testing, can wait
