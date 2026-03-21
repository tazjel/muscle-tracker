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
| Check video quality before 3D recon | `quality_gate.py` | ~5s |
| Save a visual baseline | `$GTD aiart-save-baseline` | ~2s |
| Regression test against baseline | `$GTD aiart-batch-audit` | ~10s |
| Device screenshot + state | `$GTD agent-status --json` | ~5s |
| Compare two screenshots (pixel diff) | `$GTD agent-diff` | ~5s |
| Deploy Flutter app + verify | `$GTD agent-cycle --json` | ~70s |

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

### After Modifying Flutter App (companion_app/)
```bash
$GTD agent-cycle dev --json        # Build + deploy + screenshot + state
$GTD agent-status --json           # Quick: screenshot + state only
```

### Regression Check (before/after comparison)
```bash
# Save baseline BEFORE your change
$PY scripts/agent_browser.py viewer3d skin_densepose.glb  # saves screenshots
# ... make your change ...
# Compare AFTER
$PY scripts/agent_browser.py diff captures/before.png captures/after.png
```

---

## D. GTDdebug Integration

**Path:** `python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py`
**Always add:** `--json` flag for machine-readable output

### Discovery (run once per session if needed)
```bash
$GTD agent-help --json                    # All agent commands
$GTD agent-vision-help --compact --json   # Vision commands (<3KB)
```

### Key Commands for gtd3d
| Command | Purpose | When |
|---------|---------|------|
| `$GTD agent-status --json` | Screenshot + app state | After Flutter changes |
| `$GTD agent-diff before.png after.png --json` | Pixel diff + zones | Before/after comparison |
| `$GTD vision-compare img_a.png img_b.png --json` | Detailed pixel comparison | Texture quality comparison |
| `$GTD aiart-save-baseline folder/ label --json` | Save baseline | Before risky changes |
| `$GTD aiart-batch-audit folder/ --json` | Regression vs baseline | After changes, batch check |
| `$GTD vision-golden current.png --json` | Golden image comparison | Regression gate |
| `$GTD agent-cycle dev --json` | Full deploy + verify | After Flutter build |

### When to Use GTDdebug vs Local Scripts
- **Device/Flutter work** → GTDdebug (it handles ADB, deploy, device screenshots)
- **GLB/texture work** → Local scripts (agent_verify, agent_browser, photo_preflight)
- **Image comparison** → Either works; GTDdebug has zone-aware diff, local has SSIM-based diff

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
