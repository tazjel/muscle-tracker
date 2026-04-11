# GTDdebug Wave 4 Feedback from GTD3D (2026-04-11)

## Full Cycle Result: 23/25 API + 6/7 Web + 5/5 APK

Room_texture 500 was a real app bug (missing SQLite table) — now fixed.

## Remaining GTDdebug Bugs (4 items)

### Bug 1: api-check not sending auth token to some routes
**Routes affected:** `/api/lhm/status/nonexistent`, `/api/customer/1/progress_report`
**Proof:** Both routes work fine with curl + Bearer token:
- `lhm/status/nonexistent` returns `{"status":"error","message":"Job nonexistent not found"}` 
- `progress_report` returns full JSON with profile/meshes/volumes

**Root cause:** GTDdebug's `gtd3d-api-check` acquires a JWT token but may not be sending it on all route checks. Check if the Authorization header is included for every request, not just the first few.

**Fix:** Ensure every GET request in the extended route list includes `Authorization: Bearer {token}`.

### Bug 2: G12 perf-snapshot PSS/jank returns -1
**What happens:** `PSS=-1 MB`, `Jank=-1/-1 = -1.0%` — parsing fails silently.
**Likely cause:** 
- PSS: `dumpsys meminfo com.example.companion_app --short` output format may differ between Samsung devices. The parser probably expects specific line patterns.
- Jank: `dumpsys gfxinfo com.example.companion_app` may need `reset` first, or the Samsung output format includes extra lines.

**Fix:** Run these commands manually on the device and check the actual output format:
```bash
adb shell dumpsys meminfo com.example.companion_app --short
adb shell dumpsys gfxinfo com.example.companion_app
```
Then adjust the regex patterns to match Samsung A24's output.

### Bug 3: G4 customer_select fails despite customer_list PASS
**What happens:** `customer_list: PASS (1 rows)` but then `customer_select: FAIL — no customers to click`.
**Likely cause:** The selector used to find clickable customer rows doesn't match what the customer panel renders. The panel likely uses `<tr>` or `<div>` elements, but the click selector might be looking for a different element.

**Fix:** After `customer_list` passes, use the same selector that found the rows to click the first one:
```python
# Instead of looking for a different selector to click:
row = await page.query_selector('#panel-customer tr, [data-customer-id]')
if row:
    await row.click()
```

### Bug 4: Raw ADB output leaking to stdout before JSON
**What happens:** Lines like `Performing Streamed Install`, `Starting: Intent...`, `/sdcard/screenshot.png pulled...` appear before the JSON output.
**Impact:** Makes JSON parsing harder for agents. The `--json` flag should suppress all non-JSON output.

**Fix:** Redirect subprocess stdout/stderr to PIPE when running ADB commands, only include in JSON `data.lines[]` if relevant.

---

## App Bug Fixed This Session

**room_texture table missing from SQLite:**
- `models.py` defines `room_texture` table but `fake_migrate_all=True` skips actual table creation
- Manually ran `CREATE TABLE room_texture (...)` on `database.db`
- Route `/api/customer/1/room_textures` now returns 200

**Recommendation for GTDdebug:** Add to `gtd3d-seed-reset` (G15): check that all tables defined in models.py actually exist in SQLite, create any missing ones. This catches the `fake_migrate_all` gap.

---

## New Requirements

### G18: `gtd3d-db-check` — Schema Validation
Check that all tables defined in `models.py` exist in SQLite, and all columns match.

```bash
python gtddebug.py gtd3d-db-check --json
```

Steps:
1. Parse `apps/web_app/models.py` for `db.define_table('name', ...)` calls
2. Query `sqlite_master` for existing tables
3. For each defined table, check it exists AND has the expected columns
4. Report missing tables and missing columns

Output:
```json
{
  "status": "pass",
  "tables_defined": 13,
  "tables_exist": 13,
  "missing_tables": [],
  "column_mismatches": []
}
```

**Why:** The `fake_migrate_all=True` pattern means schema changes in models.py don't auto-apply. This command catches drift before it causes 500 errors.

### G19: `gtd3d-db-migrate` — Create Missing Tables
If `gtd3d-db-check` finds missing tables, create them:

```bash
python gtddebug.py gtd3d-db-migrate --json
```

Steps:
1. Run `gtd3d-db-check` to find missing tables
2. For each missing table, generate and execute `CREATE TABLE` SQL from the model definition
3. Re-run `gtd3d-db-check` to verify

### G20: `gtd3d-apk-camera-dispose` — Release Camera Resources
After apk-audit, tap a non-camera tab AND force-stop the app to release camera:

```bash
python gtddebug.py gtd3d-apk-camera-dispose --json
```

Steps:
1. Tap "Skin" tab (tab 4) — this navigates away from camera
2. Wait 1s
3. `am force-stop com.example.companion_app`
4. Report memory freed

**Why:** Camera eats 47-53% CPU + ~150MB RAM. After audit, release it.

### G21: `gtd3d-health-dashboard` — One-line Status Report
Quick health check of everything without running full tests:

```bash
python gtddebug.py gtd3d-health-dashboard --json
```

Steps (fast, <10s):
1. Check port 8000 (py4web running?)
2. Check ADB device connected
3. Check APK installed (`pm list packages | grep companion_app`)
4. Check battery level
5. Check available RAM
6. Check last build time of APK
7. Check git status (uncommitted changes?)

Output: one-line summary like:
```
[gtd3d] server=UP device=A24(76%,1.2GB) apk=installed(14m ago) git=clean
```
