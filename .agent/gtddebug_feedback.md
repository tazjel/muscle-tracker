# GTDdebug Feedback from GTD3D Testing (2026-04-11)

## G1: gtd3d-web-start — PASS
Works perfectly. Detects running server, starts fresh if needed, seeds, gets JWT.

## G2: gtd3d-api-check — PASS
7/7 routes pass. Clean structured output.

## G3: gtd3d-apk-audit — FAIL (needs fix)

### Bug 1: Tab detection fails — Flutter content-desc format
GTDdebug searches for tabs by text, but Flutter's BottomNavigationBar uses `content-desc` attributes with multiline format:

```xml
content-desc="Camera&#10;Tab 1 of 5"
content-desc="Body Scan&#10;Tab 2 of 5"
content-desc="Live Scan&#10;Tab 3 of 5"
content-desc="Skin&#10;Tab 4 of 5"
content-desc="Multi-Cap&#10;Tab 5 of 5"
```

**Fix:** When searching for a UI element by name (e.g., "Camera"), use substring match on `content-desc` attribute, not exact text match. The UIAutomator XPath should be:
```
//*[contains(@content-desc, 'Camera')]
```
Not:
```
//*[@text='Camera']
```

### Bug 2: Battery parsing returns -1
The battery dump output is present in the raw output but isn't being parsed. The format is:
```
Current Battery Service state:
  AC powered: false
  USB powered: true
  ...
  level: 85
```
**Fix:** Parse `level: (\d+)` from the battery dump output.

### Bug 3: Memory parsing returns -1
The `cat /proc/meminfo` output is present but MemAvailable isn't being extracted. Format:
```
MemAvailable:    2048000 kB
```
**Fix:** Parse `MemAvailable:\s+(\d+)\s+kB` and convert to MB.

### Bug 4: Output too verbose — raw XML dumps
The command dumps full UIAutomator XML hierarchies (>30KB) into stdout. This wastes tokens.
**Fix:** Don't include raw XML in the `--json` output. Parse it internally, only output the structured result JSON.

### Bug 5: Tab name mismatch
Config says `"Multi Cap"` but the actual content-desc is `"Multi-Cap"` (with hyphen).
**Fix:** Update the config tab names or use fuzzy matching.

## G6: gtd3d-web-stop — PASS
Works perfectly. Finds and kills processes, confirms port is free.

## Summary for GTDdebug Agent
Priority fixes:
1. **Content-desc substring matching** for Flutter tab detection (blocks all APK audit)
2. **Suppress raw XML** from JSON output (token waste)
3. **Battery/memory parsing** (minor but useful)
4. **Tab name: "Multi-Cap"** not "Multi Cap" in config
