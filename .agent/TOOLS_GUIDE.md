# Agent Tools Guide — gtd3d

Read this ONCE at session start. Do NOT read the script source files — this guide has everything you need.

```
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
GTD="python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py"
```

---

## A. Decision Tree — What Tool Do I Use?

| Situation | Tool | Time |
|-----------|------|------|
| Check photo quality before pipeline | `photo_preflight.py` | ~1s |
| Run full texture pipeline | `run_densepose_texture.py --verify` | ~35s |
| Check GLB quality (offline, no server) | `agent_verify.py` tier 1 | ~2s |
| Check GLB visually (needs server) | `agent_verify.py --render` tier 2 | ~10s |
| Compare GLB against reference | `agent_verify.py --reference` tier 3 | ~5s |
| See the 3D model from multiple angles | `agent_browser.py viewer3d` | ~8s |
| Compare two images (before/after) | `agent_browser.py diff` | ~3s |
| Read browser console errors | `agent_browser.py console` | ~3s |
| Full browser audit (screenshot+console+scene) | `agent_browser.py audit` | ~5s |
| Text-only page inspection (saves tokens) | `agent_browser.py describe` | ~3s |
| Pass/fail assertions (pure JSON) | `agent_browser.py assert` | ~3s |
| **Check if 3D body looks like real skin** | **`agent_browser.py skin-check`** | **~12s** |
| Check video quality before 3D recon | `quality_gate.py` | ~5s |
| Save a visual baseline | `$GTD aiart-save-baseline` | ~2s |
| Regression test against baseline | `$GTD aiart-batch-audit` | ~10s |
| **Build + deploy + test Flutter app** | **`agent_device.py deploy`** | **~80s** |
| **Quick device screenshot + error check** | **`agent_device.py status`** | **~5s** |
| **Full deploy + server check cycle** | **`agent_device.py full-cycle`** | **~90s** |
| **Check py4web server health** | **`agent_device.py check-server`** | **~3s** |
| **Before/after device visual diff** | **`agent_device.py diff`** | **~8s** |
| **Flutter-filtered device logs** | **`agent_device.py logs`** | **~3s** |
| **List devices + connection status** | **`agent_device.py devices`** | **~2s** |
| **Test server API endpoints** | **`agent_test.py server`** | **~5s** |
| **Test 3D viewer in browser** | **`agent_test.py viewer`** | **~8s** |
| **Run all web tests** | **`agent_test.py full`** | **~15s** |

---

## B. Tool Reference Cards

### 1. photo_preflight.py — Photo Quality Gate
```bash
$PY scripts/photo_preflight.py                        # Default: captures/skin_scan/
$PY scripts/photo_preflight.py --scan-dir /path/to/photos
```
**Output:** JSON with per-photo metrics + cross-photo checks
**Key fields:** `ok`, `issues[]`, `mean_brightness`, `lr_brightness_diff`, `skin_pixel_pct`
**Exit codes:** 0=PASS, 2=FAIL
**Act on result:**
- PASS → proceed to pipeline
- FAIL → tell user to retake photos (report which metric failed)
**Do NOT:** Run the pipeline if preflight fails — it wastes 30+ seconds

---

### 2. agent_verify.py — GLB Quality Verification (3 tiers)
```bash
# Tier 1: Offline texture analysis (no server needed)
$PY scripts/agent_verify.py meshes/skin_densepose.glb

# Tier 2: + Browser render + visual analysis (needs py4web running)
$PY scripts/agent_verify.py meshes/skin_densepose.glb --render

# Tier 3: + Reference comparison (SSIM)
$PY scripts/agent_verify.py meshes/skin_densepose.glb --reference meshes/known_good.glb
```
**Output:** JSON `{verdict, score, issues[], suggestion}`
**Verdict values:** PASS (score 80+), WARN (60-79), FAIL (<60)
**Exit codes:** 0=PASS/WARN, 1=error, 2=FAIL
**Key issues detected:** UNIFORM_BLOB, LOW_VARIANCE, BLUE_SHIFT, SEAM, MILD_ASYMMETRY, NON_SKIN_TONE
**Act on result:**
- PASS → done, ship it
- WARN → read `suggestion` field, decide if acceptable
- FAIL → read `issues[]`, fix the root cause (usually bad input photos or code bug)
**Do NOT:** Use tier 2/3 for quick checks — tier 1 is enough for most iterations

---

### 3. agent_browser.py — Browser Automation (12 commands)

**Token-efficient commands (use these first):**
```bash
# Text-only page inspection — NO screenshot, minimal tokens
$PY scripts/agent_browser.py describe http://localhost:8000/web_app/static/viewer3d/index.html

# Pure JSON assertions — pass/fail, no images
$PY scripts/agent_browser.py assert http://localhost:8000/... --checks "title:contains:Viewer" "canvas:exists"

# Console logs only
$PY scripts/agent_browser.py console http://localhost:8000/...
```

**Visual commands (use when you need to see):**
```bash
# 3D viewer multi-angle screenshots (default: 0,90,180,270°)
$PY scripts/agent_browser.py viewer3d skin_densepose.glb

# Custom rotation angles
$PY scripts/agent_browser.py viewer3d skin_densepose.glb --rotate 0,45,90,135,180

# Visual diff between two images
$PY scripts/agent_browser.py diff before.png after.png

# Full audit: screenshot + console + Three.js scene info + perf
$PY scripts/agent_browser.py audit http://localhost:8000/...

# Single screenshot
$PY scripts/agent_browser.py screenshot http://localhost:8000/...

# Run JS in page
$PY scripts/agent_browser.py eval http://localhost:8000/... "scene.children.length"
```

**Advanced commands:**
```bash
# Watch (retry assertions until pass)
$PY scripts/agent_browser.py watch http://localhost:8000/... --checks "canvas:exists" --max-attempts 5

# Filmstrip (N frames over time)
$PY scripts/agent_browser.py filmstrip http://localhost:8000/... --frames 5 --interval 1000

# Android device screenshot
$PY scripts/agent_browser.py adb
```

**All commands return JSON.** Screenshot commands return file paths — read the image separately if needed.

---

### 4. run_densepose_texture.py — Full Pipeline
```bash
$PY scripts/run_densepose_texture.py                          # Default run
$PY scripts/run_densepose_texture.py --verify                 # + quality gate after
$PY scripts/run_densepose_texture.py --views front back --atlas 2048 --output meshes/my.glb
$PY scripts/run_densepose_texture.py --debug                  # Save intermediate images
```
**Stages:** Find photos → DensePose IUV → Texture bake (LAB + CLAHE) → GLB export → (optional verify)
**Exit codes:** 0=success, 2=FAIL (when --verify detects issues)
**Do NOT:** Run without checking preflight first

---

### 5. quality_gate.py — Video Quality Pre-Filter
```bash
$PY scripts/quality_gate.py video.mp4
$PY scripts/quality_gate.py video.mp4 --tracking-json poses.json --strict
```
**Output:** JSON `{passed, score, rejection_reasons[]}`
**Checks:** Frame rate (≥15fps), motion blur, person presence, arc coverage, jank
**Exit codes:** 0=pass, non-zero=fail

---

### 6. core/glb_inspector.py — Low-Level GLB Analysis (library, not CLI)
**Do NOT read this file (469 lines).** Use `agent_verify.py` which wraps it.
Only use directly if you need programmatic access in Python:
```python
from core.glb_inspector import score_glb, extract_textures, detect_seams, check_symmetry
result = score_glb("meshes/skin_densepose.glb")
# result: {verdict, score, scores{}, mesh{}, symmetry{}, seams{}, issues[], suggestion}
```

---

## C. Verification Workflows

### After Modifying Texture Code (core/texture_bake.py, core/densepose_texture.py)
```bash
$PY scripts/photo_preflight.py && \
$PY scripts/run_densepose_texture.py --verify && \
echo "PIPELINE PASS" || echo "PIPELINE FAIL"
```
If FAIL: check if it's a photo issue (preflight) or code issue (verify issues[]).

### After Modifying Mesh Code (core/smpl_fitting.py, core/mesh_reconstruction.py)
```bash
$PY -c "from core.smpl_fitting import build_body_mesh; m=build_body_mesh(); print(m['num_vertices'], m['num_faces'])"
$PY scripts/agent_verify.py meshes/skin_densepose.glb
```

### After Modifying Viewer JS (web_app/static/viewer3d/*.js)
```bash
# Quick: text-only check
$PY scripts/agent_browser.py describe http://localhost:8000/web_app/static/viewer3d/index.html
# Thorough: full audit
$PY scripts/agent_browser.py audit http://localhost:8000/web_app/static/viewer3d/index.html?model=/api/mesh/1.glb
```

### After Modifying Skin Material / Procedural Skin Code
```bash
$PY scripts/agent_browser.py skin-check demo_pbr.glb
# PASS → done, do not re-run for marginal improvements
# WARN → read issues[] for guidance, fix if actionable
# FAIL → read issues[] for specific problem (too shiny, blue cast, gray, etc.)
```
**Issue codes:** `NON_SKIN_HUE`, `DESATURATED`, `COOL_CAST`, `TOO_SHINY`, `LOW_SKIN_HUE`, `ZONE_COLOR_SHIFT`, `VIEW_INCONSISTENT`
**Output:** JSON with `verdict`, `score` (0-100), per-view metrics, `suggestion`

### After Modifying Flutter App (companion_app/)
```bash
$PY scripts/agent_device.py full-cycle                  # Build + deploy + check server + logcat
$PY scripts/agent_device.py deploy --skip-build         # Re-deploy without rebuild
$PY scripts/agent_device.py deploy --device matpad      # Deploy to MatePad
$PY scripts/agent_device.py status                      # Quick screenshot + error check
$PY scripts/agent_device.py logs                        # Flutter-filtered logcat
```

### Regression Check (before/after comparison)
```bash
# Save baseline BEFORE your change
$PY scripts/agent_device.py baseline save --label before_fix
# ... make your change ...
$PY scripts/agent_device.py deploy
# Compare AFTER
$PY scripts/agent_device.py diff --before captures/device/a24/deploy_PREV.png
$PY scripts/agent_device.py baseline check --label before_fix
```

### Test Server + Viewer
```bash
$PY scripts/agent_test.py server          # Test all API endpoints
$PY scripts/agent_test.py viewer          # Browser audit of 3D viewer
$PY scripts/agent_test.py full            # All tests combined
```

---

## D. agent_device.py Reference Card

**The go-to tool for ALL Flutter device work.** Replaces manual flutter/adb calls.

| Command | What | Time | Key Output |
|---------|------|------|------------|
| `deploy` | Build + install + launch + screenshot + logcat | ~80s | `{screenshot_path, errors[], crash_log}` |
| `deploy --skip-build` | Install + launch (no rebuild) | ~20s | Same |
| `deploy --device matpad` | Deploy to specific device | ~80s | Same |
| `status` | Screenshot + app running check | ~5s | `{app_running, flutter_errors[]}` |
| `check-server` | Test py4web API endpoints | ~3s | `{server_running, endpoints:{}}` |
| `diff --before img.png` | Before/after visual diff (GTDdebug) | ~8s | `{verdict, zones}` |
| `baseline save` | Save regression golden | ~3s | `{label, screenshot_path}` |
| `baseline check` | Compare vs saved golden | ~3s | `{diff_pct}` |
| `logs --seconds 10` | Flutter-filtered logcat | ~3s | `{flutter_errors[], crash_log}` |
| `devices` | List profiles + connection status | ~2s | `{devices: [{connected}]}` |
| `full-cycle` | check-server + deploy | ~90s | `{status:"pass"/"fail", summary}` |

**Device profiles:** `scripts/device_profiles.json` — add new devices there, no code changes needed.

**Failure recovery (automatic):**
- Build fail → dart error in `steps.build.error`
- Install fail → auto-uninstall + retry
- Device offline → auto-reconnect WiFi ADB
- App crash → full stacktrace in `crash_log`
- MatePad → auto-handles uninstall-first + package verifier quirks

**Act on result:**
- `status == "ok"` + empty `errors[]` → App deployed successfully
- `crash_log` present → Read it, fix the Dart code, run `deploy --skip-build`
- `flutter_errors[]` → Non-fatal errors to investigate
- `status == "error"` in `steps.build` → Compilation error, fix code first

---

## E. GTDdebug Integration (Advanced)

**Path:** `python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py`
**Always add:** `--json` flag for machine-readable output

**Note:** For most Flutter/device work, use `agent_device.py` instead — it wraps GTDdebug.
Use GTDdebug directly only for advanced vision analysis not covered by agent_device.py.

### Direct GTDdebug Commands (when agent_device.py is insufficient)
| Command | Purpose | When |
|---------|---------|------|
| `$GTD vision-compare img_a.png img_b.png --json` | Detailed pixel comparison | Texture quality analysis |
| `$GTD aiart-save-baseline folder/ label --json` | Save perf baseline | Before risky perf changes |
| `$GTD aiart-batch-audit folder/ --json` | Regression vs baseline | After changes, batch check |
| `$GTD agent-audit --json` | Combined quality audit | Deep device inspection |

### When to Use What
- **Flutter build/deploy/test** → `agent_device.py` (one command does everything)
- **Server API testing** → `agent_test.py server`
- **3D viewer testing** → `agent_test.py viewer` or `agent_browser.py audit`
- **GLB/texture quality** → `agent_verify.py`, `agent_browser.py`
- **Advanced vision analysis** → GTDdebug direct (vision-compare, aiart-*)

---

## E. Token-Saving Rules

1. **NEVER read these files** — use this guide instead:
   - `scripts/agent_browser.py` (1138 lines)
   - `core/glb_inspector.py` (469 lines)
   - `scripts/photo_preflight.py` (262 lines)
   - `scripts/quality_gate.py` (262 lines)

2. **Use the cheapest command first:**
   - `describe` before `screenshot` (text vs image)
   - `assert` before `audit` (JSON vs full report)
   - tier 1 before tier 2 `agent_verify` (offline vs browser)

3. **Use exit codes in shell** to avoid parsing JSON:
   ```bash
   $PY scripts/agent_verify.py meshes/x.glb && echo "QUALITY OK" || echo "QUALITY FAIL"
   ```

4. **Don't iterate blindly** — if preflight FAIL says `lr_brightness_diff=46`, the fix is retaking photos, not tweaking code.

5. **One verification per change** — don't run all tools after every edit. Match the tool to what you changed (see Section C).
