#!/usr/bin/env python3
"""
agent_browser.py — Playwright power tool for AI agents.

Gives agents eyes: screenshot, console logs, JS evaluation, 3D viewer inspection.
Designed for ZERO token waste — outputs are file paths and compact JSON, never raw blobs.

Usage:
    PY=C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe

    # Screenshot a URL (waits for network idle + 3D render)
    $PY scripts/agent_browser.py screenshot http://localhost:8000/viewer3d/index.html?model=demo.glb

    # Screenshot with custom output path
    $PY scripts/agent_browser.py screenshot http://localhost:8000/page --out captures/my_shot.png

    # Capture console logs (errors, warnings, info)
    $PY scripts/agent_browser.py console http://localhost:8000/page

    # Run JavaScript in page and get result
    $PY scripts/agent_browser.py eval http://localhost:8000/page "document.title"

    # Full audit: screenshot + console + JS metrics in one call (most token-efficient)
    $PY scripts/agent_browser.py audit http://localhost:8000/viewer3d/index.html?model=demo.glb

    # Wait for selector then screenshot
    $PY scripts/agent_browser.py screenshot http://localhost:8000/page --wait "canvas" --timeout 10

    # Multi-screenshot (capture N frames for animation review)
    $PY scripts/agent_browser.py filmstrip http://localhost:8000/page --frames 5 --interval 1000

    # Click, type, interact — then screenshot the result
    $PY scripts/agent_browser.py interact http://localhost:8000/page --actions '[{"click":"#start"},{"wait":2},{"screenshot":"after_click.png"}]'

    # --- NEW: Autonomous agent power tools ---

    # Visual diff: compare two screenshots (returns MATCH/MINOR_DIFF/MAJOR_DIFF + similarity %)
    $PY scripts/agent_browser.py diff captures/before.png captures/after.png

    # Assert: pass/fail checks on a page (NO screenshot needed — pure JSON verdict)
    $PY scripts/agent_browser.py assert http://localhost:8000/viewer3d/ --no-errors --canvas-rendered --min-meshes 1

    # Watch: retry assertions until pass (agent edits code, runs watch, gets result)
    $PY scripts/agent_browser.py watch http://localhost:8000/viewer3d/ --canvas-rendered --retries 5 --interval 3

    # ADB: capture Android device screen
    $PY scripts/agent_browser.py adb --serial R58W41RF6ZK

    # Describe: text-only page inspection (MOST token-efficient — no image read needed)
    $PY scripts/agent_browser.py describe http://localhost:8000/page
"""
import argparse
import json
import os
import sys
import time
import numpy as np
from pathlib import Path
from datetime import datetime

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAPTURES_DIR = PROJECT_ROOT / "captures"
CAPTURES_DIR.mkdir(exist_ok=True)


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _default_screenshot_path(prefix="screenshot"):
    return str(CAPTURES_DIR / f"{prefix}_{_timestamp()}.png")


def _launch_browser(headless=True):
    """Launch browser with optimal settings for 3D/WebGL content."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--enable-webgl",
            "--use-gl=angle",           # Better WebGL on Windows
            "--enable-gpu-rasterization",
            "--no-sandbox",
            "--disable-dev-shm-usage",  # Prevent /dev/shm issues
        ]
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=2,  # Retina-quality screenshots
    )
    return pw, browser, context


def _wait_for_page_ready(page, wait_selector=None, timeout_s=15):
    """Wait for page load + optional selector + 3D render settle."""
    # Wait for network idle
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
    except Exception:
        pass  # Some pages never fully idle (WebSocket, etc.)

    # Wait for specific selector if given
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=timeout_s * 1000)
        except Exception:
            pass

    # Detect Three.js / WebGL canvas and wait for render
    has_canvas = page.evaluate("""() => {
        const c = document.querySelector('canvas');
        return c !== null;
    }""")
    if has_canvas:
        # Wait for at least one animation frame to complete
        page.evaluate("""() => new Promise(resolve => {
            let frames = 0;
            function check() {
                frames++;
                if (frames >= 3) { resolve(true); return; }
                requestAnimationFrame(check);
            }
            requestAnimationFrame(check);
        })""")
        # Extra settle time for Three.js asset loading
        page.wait_for_timeout(1500)


def cmd_screenshot(args):
    """Take a screenshot. Returns file path only — agent reads the image separately."""
    out_path = args.out or _default_screenshot_path()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    pw, browser, context = _launch_browser()
    console_errors = []

    try:
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text)
                if msg.type in ("error", "warning") else None)

        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, args.wait, args.timeout)

        if args.selector:
            element = page.query_selector(args.selector)
            if element:
                element.screenshot(path=out_path)
            else:
                page.screenshot(path=out_path, full_page=args.full)
        else:
            page.screenshot(path=out_path, full_page=args.full)

        # Compact output — just what the agent needs
        result = {"screenshot": out_path, "size_kb": round(os.path.getsize(out_path) / 1024)}
        if console_errors:
            result["errors"] = console_errors[:5]  # Cap at 5 to save tokens
        print(json.dumps(result))

    finally:
        browser.close()
        pw.stop()


def cmd_console(args):
    """Capture console output. Returns structured JSON — no noise."""
    pw, browser, context = _launch_browser()
    logs = []

    try:
        page = context.new_page()

        def on_console(msg):
            logs.append({
                "type": msg.type,
                "text": msg.text[:300],  # Truncate long messages to save tokens
            })

        page.on("console", on_console)
        page.on("pageerror", lambda err: logs.append({"type": "exception", "text": str(err)[:300]}))

        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, timeout_s=args.timeout)

        # Wait extra time to catch async logs
        page.wait_for_timeout(2000)

        # Filter by level if requested
        if args.level:
            levels = args.level.split(",")
            logs = [l for l in logs if l["type"] in levels]

        # Cap total output
        if len(logs) > 50:
            result = {"logs": logs[:50], "truncated": len(logs)}
        else:
            result = {"logs": logs}

        print(json.dumps(result))

    finally:
        browser.close()
        pw.stop()


def cmd_eval(args):
    """Evaluate JS in page context. Returns the result as JSON."""
    pw, browser, context = _launch_browser()

    try:
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, timeout_s=args.timeout)

        result = page.evaluate(args.expression)

        # Ensure output is JSON-serializable and compact
        output = json.dumps({"result": result}, default=str)
        if len(output) > 2000:
            print(json.dumps({"result": str(result)[:2000], "truncated": True}))
        else:
            print(output)

    finally:
        browser.close()
        pw.stop()


def cmd_audit(args):
    """
    Full page audit in ONE call: screenshot + console + 3D scene info + performance.
    This is the most token-efficient command — one call gets everything.
    """
    out_path = args.out or _default_screenshot_path("audit")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    pw, browser, context = _launch_browser()
    logs = []

    try:
        page = context.new_page()

        def on_console(msg):
            if msg.type in ("error", "warning", "info"):
                logs.append({"type": msg.type, "text": msg.text[:200]})

        page.on("console", on_console)
        page.on("pageerror", lambda err: logs.append({"type": "exception", "text": str(err)[:200]}))

        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, args.wait, args.timeout)

        # Screenshot
        page.screenshot(path=out_path)

        # Gather page metrics
        metrics = page.evaluate("""() => {
            const result = {
                title: document.title,
                url: location.href,
                canvas_count: document.querySelectorAll('canvas').length,
                visible_text_length: document.body?.innerText?.length || 0,
            };

            // Three.js scene info (if available)
            if (window.scene || window.viewer?.scene) {
                const scene = window.scene || window.viewer.scene;
                result.threejs = {
                    objects: scene.children?.length || 0,
                    type: 'Three.js scene detected',
                };
                // Count meshes and get names
                const meshes = [];
                scene.traverse?.(obj => {
                    if (obj.isMesh) meshes.push(obj.name || obj.type);
                });
                result.threejs.meshes = meshes.slice(0, 10);
                result.threejs.mesh_count = meshes.length;
            }

            // WebGL info
            const canvas = document.querySelector('canvas');
            if (canvas) {
                try {
                    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                    if (gl) {
                        const dbg = gl.getExtension('WEBGL_debug_renderer_info');
                        result.webgl = {
                            renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'unknown',
                            canvas_size: [canvas.width, canvas.height],
                        };
                    }
                } catch(e) {}
            }

            // Performance timing
            const perf = performance.getEntriesByType('navigation')[0];
            if (perf) {
                result.load_time_ms = Math.round(perf.loadEventEnd - perf.startTime);
            }

            return result;
        }""")

        result = {
            "screenshot": out_path,
            "size_kb": round(os.path.getsize(out_path) / 1024),
            "metrics": metrics,
        }
        if logs:
            result["console"] = logs[:20]  # Cap to save tokens

        print(json.dumps(result, default=str))

    finally:
        browser.close()
        pw.stop()


def cmd_filmstrip(args):
    """Capture N frames over time — useful for animation/rotation review."""
    pw, browser, context = _launch_browser()

    try:
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, timeout_s=args.timeout)

        frames = []
        for i in range(args.frames):
            path = str(CAPTURES_DIR / f"frame_{_timestamp()}_{i:03d}.png")
            page.screenshot(path=path)
            frames.append(path)
            if i < args.frames - 1:
                page.wait_for_timeout(args.interval)

        print(json.dumps({"frames": frames, "count": len(frames)}))

    finally:
        browser.close()
        pw.stop()


def cmd_interact(args):
    """Execute a sequence of browser actions, then return screenshots/results."""
    pw, browser, context = _launch_browser()
    console_logs = []
    results = []

    try:
        page = context.new_page()
        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text[:200]})
                if msg.type in ("error", "warning") else None)

        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, timeout_s=args.timeout)

        actions = json.loads(args.actions)
        for action in actions:
            if "click" in action:
                page.click(action["click"], timeout=5000)
                results.append({"action": "click", "selector": action["click"]})

            elif "type" in action:
                page.fill(action.get("selector", "input"), action["type"])
                results.append({"action": "type", "text": action["type"][:50]})

            elif "wait" in action:
                page.wait_for_timeout(int(action["wait"]) * 1000)
                results.append({"action": "wait", "seconds": action["wait"]})

            elif "screenshot" in action:
                path = str(CAPTURES_DIR / action["screenshot"])
                page.screenshot(path=path)
                results.append({"action": "screenshot", "path": path})

            elif "eval" in action:
                val = page.evaluate(action["eval"])
                val_str = json.dumps(val, default=str)
                if len(val_str) > 500:
                    val_str = val_str[:500] + "..."
                results.append({"action": "eval", "result": val_str})

            elif "scroll" in action:
                page.evaluate(f"window.scrollBy(0, {action['scroll']})")
                results.append({"action": "scroll", "pixels": action["scroll"]})

        output = {"actions_completed": len(results), "results": results}
        if console_logs:
            output["errors"] = console_logs[:5]
        print(json.dumps(output, default=str))

    finally:
        browser.close()
        pw.stop()


def cmd_viewer3d(args):
    """
    Purpose-built for the gtd3d 3D viewer. One command to:
    - Load a GLB model in the viewer
    - Wait for Three.js to render
    - Screenshot from default + optional rotated angles
    - Extract scene stats (mesh count, vertices, materials)

    Usage:
        $PY scripts/agent_browser.py viewer3d demo_pbr.glb
        $PY scripts/agent_browser.py viewer3d /api/mesh/1.glb --rotate 0,90,180,270
    """
    model = args.model
    base_url = args.base_url.rstrip("/")

    # Build viewer URL
    if model.startswith("http"):
        url = model
    else:
        url = f"{base_url}/static/viewer3d/index.html?model={model}"

    pw, browser, context = _launch_browser()

    try:
        page = context.new_page()
        page.on("console", lambda msg: print(f"  [BROWSER] {msg.text}"))
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, "canvas", args.timeout)

        screenshots = []

        # Default front view
        path = str(CAPTURES_DIR / f"viewer3d_{_timestamp()}_front.png")
        page.screenshot(path=path)
        screenshots.append({"angle": "front", "path": path})

        # Rotate and capture additional angles if requested
        if args.rotate:
            angles = [int(a) for a in args.rotate.split(",")]
            for angle in angles:
                page.evaluate(f"""() => {{
                    if (window.controls || window.viewer?.controls) {{
                        const ctrl = window.controls || window.viewer.controls;
                        // Orbit camera to target angle
                        const rad = {angle} * Math.PI / 180;
                        if (ctrl.object) {{
                            const dist = ctrl.object.position.length();
                            ctrl.object.position.x = dist * Math.sin(rad);
                            ctrl.object.position.z = dist * Math.cos(rad);
                            ctrl.object.lookAt(ctrl.target || new THREE.Vector3());
                            ctrl.update();
                        }}
                    }}
                }}""")
                page.wait_for_timeout(800)  # Let render settle
                apath = str(CAPTURES_DIR / f"viewer3d_{_timestamp()}_{angle}deg.png")
                page.screenshot(path=apath)
                screenshots.append({"angle": f"{angle}deg", "path": apath})

        # Extract scene info
        scene_info = page.evaluate("""() => {
            const info = { loaded: false };
            const scene = window.scene || window.viewer?.scene;
            if (!scene) return info;
            info.loaded = true;
            let meshCount = 0, totalVerts = 0, materials = new Set();
            scene.traverse(obj => {
                if (obj.isMesh) {
                    meshCount++;
                    if (obj.geometry?.attributes?.position)
                        totalVerts += obj.geometry.attributes.position.count;
                    if (obj.material?.name) materials.add(obj.material.name);
                    if (obj.material?.type) materials.add(obj.material.type);
                }
            });
            info.meshes = meshCount;
            info.vertices = totalVerts;
            info.materials = [...materials].slice(0, 10);
            info.scene_children = scene.children.length;
            return info;
        }""")

        result = {
            "url": url,
            "screenshots": screenshots,
            "scene": scene_info,
        }
        print(json.dumps(result, default=str))

    finally:
        browser.close()
        pw.stop()


def cmd_diff(args):
    """
    Visual diff between two images. Returns:
    - similarity % (SSIM-based)
    - pixel diff count and highlighted diff image
    - Compact text verdict: MATCH / MINOR_DIFF / MAJOR_DIFF

    Use this to verify your changes actually improved the output.
    Agent reads the verdict string — never needs to open the diff image unless debugging.
    """
    from PIL import Image, ImageChops, ImageStat
    import math

    img_a = Image.open(args.image_a).convert("RGB")
    img_b = Image.open(args.image_b).convert("RGB")

    # Resize to same dimensions if needed (use the smaller)
    if img_a.size != img_b.size:
        target = (min(img_a.width, img_b.width), min(img_a.height, img_b.height))
        img_a = img_a.resize(target, Image.LANCZOS)
        img_b = img_b.resize(target, Image.LANCZOS)

    # Pixel-level diff
    diff_img = ImageChops.difference(img_a, img_b)
    stat = ImageStat.Stat(diff_img)
    # Mean diff per channel (0-255), averaged across RGB
    mean_diff = sum(stat.mean) / 3.0
    # RMS diff per channel
    rms_diff = math.sqrt(sum(c * c for c in stat.rms) / 3.0)

    # Count significantly different pixels (threshold: 30/255 per channel)
    threshold = 30
    diff_pixels = 0
    total_pixels = img_a.width * img_a.height
    for pixel in diff_img.get_flattened_data():
        if any(c > threshold for c in pixel):
            diff_pixels += 1
    diff_pct = (diff_pixels / total_pixels) * 100

    # Similarity score (100 = identical)
    similarity = max(0, 100 - (mean_diff / 255 * 100))

    # Verdict
    if similarity >= 99:
        verdict = "MATCH"
    elif similarity >= 90:
        verdict = "MINOR_DIFF"
    else:
        verdict = "MAJOR_DIFF"

    # Save highlighted diff image (amplified for visibility)
    diff_amplified = ImageChops.multiply(diff_img, Image.new("RGB", diff_img.size, (5, 5, 5)))
    diff_path = args.out or str(CAPTURES_DIR / f"diff_{_timestamp()}.png")
    diff_amplified.save(diff_path)

    result = {
        "verdict": verdict,
        "similarity_pct": round(similarity, 2),
        "diff_pixels_pct": round(diff_pct, 2),
        "rms_diff": round(rms_diff, 2),
        "diff_image": diff_path,
        "size": f"{img_a.width}x{img_a.height}",
    }
    print(json.dumps(result))


def cmd_assert(args):
    """
    Run visual/DOM assertions on a page. Returns pass/fail + reasons.
    Agent uses this instead of screenshot+manual-inspection to save tokens.

    Checks (all optional, combine as needed):
    --no-errors        : Fail if any console errors
    --has-selector     : Fail if CSS selector not found
    --no-selector      : Fail if CSS selector IS found (e.g., error banners)
    --text-contains    : Fail if page text doesn't contain string
    --text-absent      : Fail if page text contains this string
    --canvas-rendered  : Fail if canvas is blank (all-white or all-black)
    --min-meshes N     : Fail if Three.js scene has fewer than N meshes
    --js-truthy EXPR   : Fail if JS expression evaluates to falsy
    """
    pw, browser, context = _launch_browser()
    errors = []
    console_errors = []
    checks_passed = 0
    checks_total = 0

    try:
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text[:200])
                if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)[:200]))

        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, args.wait, args.timeout)

        # --no-errors
        if args.no_errors:
            checks_total += 1
            if console_errors:
                errors.append(f"CONSOLE_ERRORS: {console_errors[:3]}")
            else:
                checks_passed += 1

        # --has-selector
        if args.has_selector:
            checks_total += 1
            el = page.query_selector(args.has_selector)
            if el:
                checks_passed += 1
            else:
                errors.append(f"MISSING_SELECTOR: {args.has_selector}")

        # --no-selector
        if args.no_selector:
            checks_total += 1
            el = page.query_selector(args.no_selector)
            if el:
                errors.append(f"UNWANTED_SELECTOR_FOUND: {args.no_selector}")
            else:
                checks_passed += 1

        # --text-contains
        if args.text_contains:
            checks_total += 1
            body_text = page.evaluate("() => document.body?.innerText || ''")
            if args.text_contains.lower() in body_text.lower():
                checks_passed += 1
            else:
                errors.append(f"TEXT_NOT_FOUND: '{args.text_contains}'")

        # --text-absent
        if args.text_absent:
            checks_total += 1
            body_text = page.evaluate("() => document.body?.innerText || ''")
            if args.text_absent.lower() in body_text.lower():
                errors.append(f"UNWANTED_TEXT_FOUND: '{args.text_absent}'")
            else:
                checks_passed += 1

        # --canvas-rendered
        if args.canvas_rendered:
            checks_total += 1
            canvas_ok = page.evaluate("""() => {
                const c = document.querySelector('canvas');
                if (!c) return false;
                const ctx = c.getContext('2d', {willReadFrequently: true});
                if (ctx) {
                    const data = ctx.getImageData(0, 0, Math.min(c.width, 100), Math.min(c.height, 100)).data;
                    let nonZero = 0;
                    for (let i = 0; i < data.length; i += 4) {
                        if (data[i] !== 0 || data[i+1] !== 0 || data[i+2] !== 0) nonZero++;
                        if (data[i] !== 255 || data[i+1] !== 255 || data[i+2] !== 255) nonZero++;
                    }
                    return nonZero > 10;
                }
                // WebGL — just check it exists and has size
                const gl = c.getContext('webgl2') || c.getContext('webgl');
                return gl !== null && c.width > 0 && c.height > 0;
            }""")
            if canvas_ok:
                checks_passed += 1
            else:
                errors.append("CANVAS_BLANK: canvas appears blank or missing")

        # --min-meshes
        if args.min_meshes is not None:
            checks_total += 1
            mesh_count = page.evaluate("""() => {
                const scene = window.scene || window.viewer?.scene;
                if (!scene) return 0;
                let count = 0;
                scene.traverse(obj => { if (obj.isMesh) count++; });
                return count;
            }""")
            if mesh_count >= args.min_meshes:
                checks_passed += 1
            else:
                errors.append(f"TOO_FEW_MESHES: found {mesh_count}, need >= {args.min_meshes}")

        # --js-truthy
        if args.js_truthy:
            checks_total += 1
            val = page.evaluate(f"() => !!({args.js_truthy})")
            if val:
                checks_passed += 1
            else:
                errors.append(f"JS_FALSY: `{args.js_truthy}` evaluated to false")

        # Optional: capture screenshot on failure for debugging
        shot_path = None
        if errors and not args.no_screenshot:
            shot_path = str(CAPTURES_DIR / f"assert_fail_{_timestamp()}.png")
            page.screenshot(path=shot_path)

        passed = checks_passed == checks_total
        result = {
            "passed": passed,
            "checks": f"{checks_passed}/{checks_total}",
        }
        if errors:
            result["failures"] = errors
        if shot_path:
            result["failure_screenshot"] = shot_path
        print(json.dumps(result))

    finally:
        browser.close()
        pw.stop()


def cmd_watch(args):
    """
    Keep checking a URL until assertions pass OR max retries hit.
    This is the "iterate until correct" loop — agent edits code, calls watch,
    and gets a pass/fail without burning tokens on repeated screenshot+read cycles.

    Runs the same assertion checks as cmd_assert, retrying every --interval seconds.
    Returns on first success or after --retries attempts.
    """
    checks = {
        "no_errors": args.no_errors,
        "has_selector": args.has_selector,
        "text_contains": args.text_contains,
        "canvas_rendered": args.canvas_rendered,
        "min_meshes": args.min_meshes,
        "js_truthy": args.js_truthy,
    }

    for attempt in range(1, args.retries + 1):
        pw, browser, context = _launch_browser()
        console_errs = []
        failures = []
        checks_run = 0

        try:
            page = context.new_page()
            page.on("console", lambda msg: console_errs.append(msg.text[:200])
                    if msg.type == "error" else None)
            page.on("pageerror", lambda err: console_errs.append(str(err)[:200]))

            page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
            _wait_for_page_ready(page, args.wait, args.timeout)

            if checks["no_errors"]:
                checks_run += 1
                if console_errs:
                    failures.append(f"CONSOLE_ERRORS: {console_errs[:3]}")

            if checks["has_selector"]:
                checks_run += 1
                if not page.query_selector(checks["has_selector"]):
                    failures.append(f"MISSING: {checks['has_selector']}")

            if checks["text_contains"]:
                checks_run += 1
                text = page.evaluate("() => document.body?.innerText || ''")
                if checks["text_contains"].lower() not in text.lower():
                    failures.append(f"TEXT_NOT_FOUND: {checks['text_contains']}")

            if checks["canvas_rendered"]:
                checks_run += 1
                has_gl = page.evaluate("""() => {
                    const c = document.querySelector('canvas');
                    if (!c) return false;
                    const gl = c.getContext('webgl2') || c.getContext('webgl');
                    return gl !== null && c.width > 0 && c.height > 0;
                }""")
                if not has_gl:
                    failures.append("CANVAS_BLANK")

            if checks["min_meshes"] is not None:
                checks_run += 1
                mc = page.evaluate("""() => {
                    const s = window.scene || window.viewer?.scene;
                    if (!s) return 0;
                    let c = 0; s.traverse(o => { if (o.isMesh) c++; }); return c;
                }""")
                if mc < checks["min_meshes"]:
                    failures.append(f"MESHES: {mc} < {checks['min_meshes']}")

            if checks["js_truthy"]:
                checks_run += 1
                if not page.evaluate(f"() => !!({checks['js_truthy']})"):
                    failures.append(f"JS_FALSY: {checks['js_truthy']}")

        finally:
            browser.close()
            pw.stop()

        if not failures:
            print(json.dumps({
                "passed": True,
                "attempt": attempt,
                "checks": checks_run,
            }))
            return

        if attempt < args.retries:
            time.sleep(args.interval)

    # All retries exhausted
    shot_path = str(CAPTURES_DIR / f"watch_fail_{_timestamp()}.png")
    # One final screenshot for debugging
    pw2, br2, ctx2 = _launch_browser()
    try:
        pg = ctx2.new_page()
        pg.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(pg, args.wait, args.timeout)
        pg.screenshot(path=shot_path)
    finally:
        br2.close()
        pw2.stop()

    print(json.dumps({
        "passed": False,
        "attempts": args.retries,
        "last_failures": failures,
        "failure_screenshot": shot_path,
    }))


def cmd_adb(args):
    """
    Capture Android device screen via ADB. Works with Samsung A24 and MatePad Pro.
    Returns screenshot path — agent reads the image file to see the APK output.

    Usage:
        $PY scripts/agent_browser.py adb                          # Default device
        $PY scripts/agent_browser.py adb --serial R58W41RF6ZK     # Samsung A24
        $PY scripts/agent_browser.py adb --serial 192.168.100.33:5555  # MatePad
    """
    import subprocess

    out_path = args.out or str(CAPTURES_DIR / f"adb_{_timestamp()}.png")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    adb = "C:/Android/platform-tools/adb.exe"
    cmd = [adb]
    if args.serial:
        cmd += ["-s", args.serial]

    # Use exec-out screencap -p to get PNG bytes directly (avoids path mangling)
    cmd += ["exec-out", "screencap", "-p"]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")[:200]
            print(json.dumps({"error": f"adb failed: {err}"}))
            return

        with open(out_path, "wb") as f:
            f.write(result.stdout)

        size_kb = round(os.path.getsize(out_path) / 1024)
        print(json.dumps({"screenshot": out_path, "size_kb": size_kb}))

    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "adb screencap timed out (10s)"}))
    except FileNotFoundError:
        print(json.dumps({"error": f"adb not found at {adb}"}))


def cmd_describe(args):
    """
    Extract a structured text description of what's visible on a page.
    Returns compact JSON the agent can reason about WITHOUT reading a screenshot image.
    This is the MOST token-efficient way to understand page state.

    Extracts: headings, visible text summary, form states, button labels,
    error messages, image count, canvas state, layout info.
    """
    pw, browser, context = _launch_browser()
    console_errors = []

    try:
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text[:150])
                if msg.type == "error" else None)

        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, args.wait, args.timeout)

        desc = page.evaluate("""() => {
            const d = {};

            // Title
            d.title = document.title;

            // Headings
            d.headings = [...document.querySelectorAll('h1,h2,h3')]
                .slice(0, 10)
                .map(h => h.innerText.trim().substring(0, 100));

            // Visible error-like elements
            const errSelectors = '.error, .alert-danger, .alert-error, [role="alert"], .warning, .toast-error';
            d.errors_visible = [...document.querySelectorAll(errSelectors)]
                .slice(0, 5)
                .map(e => e.innerText.trim().substring(0, 150));

            // Buttons and their states
            d.buttons = [...document.querySelectorAll('button, [role="button"], input[type="submit"]')]
                .slice(0, 15)
                .map(b => ({
                    text: (b.innerText || b.value || b.title || '').trim().substring(0, 50),
                    disabled: b.disabled || false,
                }));

            // Form inputs summary
            d.inputs = [...document.querySelectorAll('input, select, textarea')]
                .slice(0, 15)
                .map(i => ({
                    type: i.type || i.tagName.toLowerCase(),
                    name: i.name || i.id || '',
                    value: (i.value || '').substring(0, 50),
                    placeholder: (i.placeholder || '').substring(0, 50),
                }));

            // Images
            d.images = document.querySelectorAll('img').length;

            // Canvas
            const canvases = document.querySelectorAll('canvas');
            d.canvas_count = canvases.length;
            if (canvases.length > 0) {
                const c = canvases[0];
                d.canvas_size = [c.width, c.height];
            }

            // Visible text summary (first 500 chars)
            const bodyText = document.body?.innerText || '';
            d.text_preview = bodyText.substring(0, 500).replace(/\\s+/g, ' ').trim();
            d.text_length = bodyText.length;

            // Three.js scene summary
            const scene = window.scene || window.viewer?.scene;
            if (scene) {
                let meshes = 0, lights = 0;
                scene.traverse(o => {
                    if (o.isMesh) meshes++;
                    if (o.isLight) lights++;
                });
                d.threejs = { meshes, lights, children: scene.children.length };
            }

            return d;
        }""")

        result = {"description": desc}
        if console_errors:
            result["console_errors"] = console_errors[:5]

        print(json.dumps(result, default=str))

    finally:
        browser.close()
        pw.stop()


def cmd_verify(args):
    """
    One-command GLB quality check: texture analysis + optional browser render.
    Combines glb_inspector (offline) with viewer3d render (if server is available).

    Usage:
        $PY scripts/agent_browser.py verify skin_densepose.glb
        $PY scripts/agent_browser.py verify meshes/skin_densepose.glb --render
    """
    glb_path = args.glb_path
    if not os.path.isabs(glb_path):
        glb_path = str(PROJECT_ROOT / glb_path)

    if not os.path.exists(glb_path):
        print(json.dumps({"error": f"GLB not found: {glb_path}"}))
        return

    # Tier 1: Offline texture analysis
    sys.path.insert(0, str(PROJECT_ROOT))
    from core.glb_inspector import score_glb
    result = score_glb(glb_path)

    # Tier 2: Browser render (optional)
    if args.render:
        model_name = os.path.basename(glb_path)
        try:
            pw, browser, context = _launch_browser()
            base_url = args.base_url.rstrip("/")
            url = f"{base_url}/web_app/static/viewer3d/index.html?model=meshes/{model_name}"
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _wait_for_page_ready(page, "canvas", 20)

            shot_path = str(CAPTURES_DIR / f"verify_{_timestamp()}.png")
            page.screenshot(path=shot_path)

            scene_info = page.evaluate("""() => {
                const scene = window.scene || window.viewer?.scene;
                if (!scene) return {loaded: false};
                let meshes = 0, verts = 0;
                scene.traverse(obj => {
                    if (obj.isMesh) {
                        meshes++;
                        if (obj.geometry?.attributes?.position)
                            verts += obj.geometry.attributes.position.count;
                    }
                });
                return {loaded: true, meshes, vertices: verts};
            }""")

            result["render"] = {
                "screenshot": shot_path,
                "scene": scene_info,
            }
            browser.close()
            pw.stop()
        except Exception as e:
            result["render"] = {"error": str(e)[:200]}

    print(json.dumps(result, indent=2))


def cmd_skin_check(args):
    """
    Render GLB in browser + analyze if output looks like human skin.
    Captures 4 angles, runs skin tone analysis on each, aggregates verdict.

    Usage:
        $PY scripts/agent_browser.py skin-check demo_pbr.glb
        $PY scripts/agent_browser.py skin-check meshes/skin_densepose.glb --base-url http://localhost:8000
    """
    glb_path = args.glb_path
    if not os.path.isabs(glb_path):
        glb_path = str(PROJECT_ROOT / glb_path)

    if not os.path.exists(glb_path):
        print(json.dumps({"error": f"GLB not found: {glb_path}"}))
        sys.exit(2)
        return

    # Copy GLB to static dir so viewer can load it
    model_name = os.path.basename(glb_path)
    static_meshes = PROJECT_ROOT / "web_app" / "static" / "viewer3d" / "meshes"
    static_meshes.mkdir(parents=True, exist_ok=True)
    dst = static_meshes / model_name
    if str(Path(glb_path).resolve()) != str(dst.resolve()):
        import shutil
        shutil.copy2(glb_path, dst)

    sys.path.insert(0, str(PROJECT_ROOT))
    from core.glb_inspector import analyze_skin_tone, detect_plastic_skin

    pw, browser, context = _launch_browser()

    try:
        base_url = args.base_url.rstrip("/")
        url = f"{base_url}/web_app/static/viewer3d/index.html?model=meshes/{model_name}"
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, "canvas", args.timeout)

        # Switch to skin mode for SSS material evaluation
        page.evaluate("() => { if (window.setViewMode) window.setViewMode('skin'); }")
        page.wait_for_timeout(500)

        # Hide all UI overlays so only the 3D canvas is captured
        page.evaluate("""() => {
            document.querySelectorAll('.card, #muscle-panel, #skin-upload-panel, .heatmap-legend, #card-toggle, #mesh-info, #status')
                .forEach(el => { if (el) el.style.display = 'none'; });
        }""")
        page.wait_for_timeout(300)

        angles = [int(a) for a in args.angles.split(",")]
        views = []
        screenshots = []

        for angle in angles:
            # Orbit camera to angle
            page.evaluate(f"""() => {{
                if (window.controls || window.viewer?.controls) {{
                    const ctrl = window.controls || window.viewer.controls;
                    const rad = {angle} * Math.PI / 180;
                    if (ctrl.object) {{
                        const dist = ctrl.object.position.length();
                        ctrl.object.position.x = dist * Math.sin(rad);
                        ctrl.object.position.z = dist * Math.cos(rad);
                        ctrl.object.lookAt(ctrl.target || new THREE.Vector3());
                        ctrl.update();
                    }}
                }}
            }}""")
            page.wait_for_timeout(800)

            shot_path = str(CAPTURES_DIR / f"skin_check_{_timestamp()}_{angle}deg.png")
            page.screenshot(path=shot_path)
            screenshots.append(shot_path)

            # Analyze skin tone + plastic detection
            skin_result = analyze_skin_tone(shot_path)
            skin_result["angle"] = angle
            plastic = detect_plastic_skin(shot_path)
            skin_result["plastic_score"] = plastic.get("plastic_score", 0)
            skin_result["edge_warmth"] = plastic.get("edge_warmth", 0)
            skin_result["issues"].extend(plastic.get("issues", []))
            views.append(skin_result)

        # Cross-view consistency
        hue_pcts = [v.get("skin_hue_pct", 0) for v in views if "skin_hue_pct" in v]
        sat_meds = [v.get("sat_median", 0) for v in views if "sat_median" in v]

        cross_view = {}
        cross_issues = []
        if len(hue_pcts) >= 2:
            hue_std = float(np.std(hue_pcts))
            cross_view["hue_std"] = round(hue_std, 1)
            cross_view["consistent"] = hue_std <= 15
            if hue_std > 15:
                cross_issues.append(
                    f"VIEW_INCONSISTENT: skin hue varies too much across views (std={hue_std:.1f})")
        if len(sat_meds) >= 2:
            sat_range = max(sat_meds) - min(sat_meds)
            cross_view["sat_range"] = round(sat_range, 1)
            if sat_range > 30:
                cross_issues.append(
                    f"VIEW_SAT_SHIFT: saturation varies {sat_range:.0f} across views (>30)")

        # Aggregate all issues
        all_issues = list(cross_issues)
        for v in views:
            for iss in v.get("issues", []):
                all_issues.append(f"{v.get('angle', '?')}deg: {iss}")

        # Score: weighted combination
        avg_hue = np.mean(hue_pcts) if hue_pcts else 0
        avg_sat = np.mean(sat_meds) if sat_meds else 0
        avg_lab_a = np.mean([v.get("lab_a_mean", 128) for v in views])
        avg_spec = np.mean([v.get("specular_pct", 0) for v in views])
        hue_std_val = cross_view.get("hue_std", 0)

        score_hue = min(100, avg_hue) * 0.4
        score_sat = max(0, 100 - abs(avg_sat - 70) * 1.5) * 0.2
        score_temp = min(100, max(0, (avg_lab_a - 120) * 10)) * 0.2
        score_consist = max(0, 100 - hue_std_val * 5) * 0.1
        score_spec = max(0, 100 - avg_spec * 12) * 0.1
        score = round(score_hue + score_sat + score_temp + score_consist + score_spec)
        score = max(0, min(100, score))

        # Verdict
        fail_codes = {"NON_SKIN_HUE", "DESATURATED", "TOO_DARK", "COOL_CAST", "RENDER_BLANK"}
        has_fail = any(
            any(code in iss for code in fail_codes)
            for v in views for iss in v.get("issues", [])
        )

        if has_fail or score < 45:
            verdict = "FAIL"
        elif score < 70:
            verdict = "WARN"
        else:
            verdict = "PASS"

        # Build suggestion
        suggestion = ""
        if "NON_SKIN_HUE" in str(all_issues):
            suggestion = "Most body pixels are outside human skin hue range — check material color or texture."
        elif "DESATURATED" in str(all_issues):
            suggestion = "Body looks gray — check lighting, material color, or missing texture."
        elif "COOL_CAST" in str(all_issues):
            suggestion = "Skin has green/blue cast — check light color or material tint."
        elif "TOO_SHINY" in str(all_issues):
            suggestion = "Excessive specular highlights — reduce clearcoat or increase roughness."
        elif "LOW_SKIN_HUE" in str(all_issues):
            suggestion = "Marginal skin tone — check texture coverage on flagged views."
        elif verdict == "PASS":
            suggestion = "Skin appearance looks good."

        output = {
            "verdict": verdict,
            "score": score,
            "views": [{
                "angle": v.get("angle"),
                "skin_hue_pct": v.get("skin_hue_pct"),
                "sat_median": v.get("sat_median"),
                "color_temp": v.get("color_temp"),
                "specular_pct": v.get("specular_pct"),
                "fitzpatrick_type": v.get("fitzpatrick_type"),
                "plastic_score": v.get("plastic_score"),
                "edge_warmth": v.get("edge_warmth"),
                "issues": v.get("issues", []),
            } for v in views],
            "cross_view": cross_view,
            "issues": all_issues,
            "suggestion": suggestion,
            "screenshots": screenshots,
        }

        print(json.dumps(output, indent=2))
        sys.exit(0 if verdict != "FAIL" else 2)

    except Exception as e:
        print(json.dumps({"error": str(e)[:300]}))
        sys.exit(2)
    finally:
        browser.close()
        pw.stop()


def cmd_cinematic_check(args):
    """
    Verify photorealistic 'Cinematic Scan' features:
    1. Load model in Skin mode
    2. Enable HDRI (Studio) and SSAO
    3. Set Muscle Definition to 80%
    4. Wait for EWR (Edge Warmth Ratio) audit to stabilize
    5. Screenshot + JSON report
    """
    model = args.model
    base_url = args.base_url.rstrip("/")
    url = f"{base_url}/static/viewer3d/index.html?model={model}"

    pw, browser, context = _launch_browser()

    try:
        page = context.new_page()
        page.on("console", lambda msg: print(f"  [BROWSER] {msg.text}"))
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_page_ready(page, "canvas", args.timeout)

        # 1. Setup Cinematic State via UI interaction
        page.evaluate("() => { if (window.setViewMode) window.setViewMode('skin'); }")
        page.wait_for_timeout(500)
        
        # Click the Scene tab if it's not active
        scene_tab = page.query_selector("button[data-tab='scene']")
        if scene_tab:
            scene_tab.click()
            page.wait_for_timeout(300)

        # Select HDRI via native Playwright method to trigger 'onchange'
        page.select_option("#hdri-select", "/static/hdris/studio_small_09_2k.hdr")
        
        # Set definition via slider
        def_slider = page.query_selector("#def-intensity")
        if def_slider:
            def_slider.fill("85") # 85%
            page.evaluate("() => { document.getElementById('def-intensity').dispatchEvent(new Event('input')); }")

        # Enable SSAO
        ssao_chk = page.query_selector("#chk-ssao")
        if ssao_chk:
            ssao_chk.set_checked(True)

        # Hide UI for clean capture
        page.evaluate("""() => {
            document.querySelectorAll('.card, #mobile-bar, .heatmap-legend, #card-toggle, #status')
                .forEach(el => { if (el) el.style.display = 'none'; });
        }""")
        
        # 2. Wait for HDRI and SSS Audit to settle
        # Wait specifically for EWR to become non-zero (max 15 attempts)
        ewr = 0
        for _ in range(15):
            ewr = page.evaluate("() => parseFloat(document.getElementById('audit-ewr-val')?.textContent || '0')")
            if ewr > 0:
                break
            page.wait_for_timeout(1000)

        # 3. Capture 2 angles (Front, 45deg)
        shots = []
        for angle in [0, 45]:
            page.evaluate(f"""() => {{
                if (window.controls || window.viewer?.controls) {{
                    const ctrl = window.controls || window.viewer.controls;
                    const rad = {angle} * Math.PI / 180;
                    const dist = ctrl.object.position.length();
                    ctrl.object.position.x = dist * Math.sin(rad);
                    ctrl.object.position.z = dist * Math.cos(rad);
                    ctrl.object.lookAt(ctrl.target || new THREE.Vector3());
                    ctrl.update();
                }}
            }}""")
            page.wait_for_timeout(1000)
            path = str(CAPTURES_DIR / f"cinematic_{_timestamp()}_{angle}deg.png")
            page.screenshot(path=path)
            shots.append({"angle": angle, "path": path})

        # 4. Extract Audit Metrics
        audit = page.evaluate("""() => {
            return {
                ewr: parseFloat(document.getElementById('audit-ewr-val')?.textContent || '0'),
                status: document.getElementById('audit-status')?.textContent || 'Unknown',
                hdri: document.getElementById('hdri-select')?.value || 'None'
            };
        }""")

        result = {
            "verdict": "PASS" if (audit['ewr'] > 1.1 and audit['ewr'] < 1.5) else "WARN",
            "audit": audit,
            "screenshots": shots,
            "suggestion": "SSS looking good" if audit['ewr'] > 1.1 else "SSS too low, check normal strength or attenuation"
        }
        print(json.dumps(result, indent=2))

    finally:
        browser.close()
        pw.stop()


def cmd_studio_audit(args):
    """
    Automated Studio health check:
    1. Open Studio URL
    2. Set Phone IP and Click Connect
    3. Wait for sensor data to populate
    4. Screenshot the dashboard
    5. Report console errors
    """
    base_url = args.base_url.rstrip("/")
    url = f"{base_url}/web_app/studio"
    phone_ip = args.phone_ip

    pw, browser, context = _launch_browser()
    logs = []

    try:
        page = context.new_page()
        page.on("console", lambda msg: logs.append({"type": msg.type, "text": msg.text[:200]})
                if msg.type in ("error", "warning") else None)

        print(f"Opening Studio: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Interact with the IP input and Connect button
        page.fill("#phone_ip", phone_ip)
        page.click("button:has-text('CONNECT')")
        
        print(f"Connecting to {phone_ip}...")
        page.wait_for_timeout(3000) # Wait for initial stream connect

        # Wait for real sensor data (non-zero or changed from --)
        sensor_active = False
        for _ in range(10):
            val = page.evaluate("() => document.getElementById('val_pitch').textContent")
            if val and "--" not in val:
                sensor_active = True
                break
            page.wait_for_timeout(1000)

        # Final state check
        status_text = page.evaluate("() => document.getElementById('conn_status').textContent")
        
        shot_path = str(CAPTURES_DIR / f"studio_audit_{_timestamp()}.png")
        page.screenshot(path=shot_path)

        result = {
            "studio_url": url,
            "phone_ip": phone_ip,
            "connection_status": status_text,
            "sensors_active": sensor_active,
            "screenshot": shot_path,
            "console_errors": logs[:5]
        }
        print(json.dumps(result, indent=2))

    finally:
        browser.close()
        pw.stop()


def cmd_studio_v2_audit(args):
    """Studio v2 health check: nav tabs, mock toggle, viewport, console errors."""
    base_url = args.base_url.rstrip("/")
    url = f"{base_url}/web_app/studio_v2"

    pw, browser, context = _launch_browser()
    logs = []

    try:
        page = context.new_page()
        page.on("console", lambda msg: logs.append({"type": msg.type, "text": msg.text[:200]})
                if msg.type in ("error", "warning") else None)

        print(f"Opening Studio v2: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Click each nav tab and record state
        tab_names = ["scan", "mesh", "texture", "render", "progress", "3dgs", "lhm", "multi-capture"]
        nav_results = []
        for name in tab_names:
            selector = f'a[data-nav="{name}"]'
            try:
                page.click(selector, timeout=5000)
                page.wait_for_timeout(500)
                is_active = page.evaluate(f'() => document.querySelector(\'a[data-nav="{name}"]\').classList.contains("active")')
                visible_panels = page.evaluate("() => [...document.querySelectorAll('.panel')].filter(p => p.offsetParent !== null).length")
                nav_results.append({"name": name, "active": is_active, "visible_panels": visible_panels})
            except Exception as e:
                nav_results.append({"name": name, "active": False, "visible_panels": 0, "error": str(e)[:100]})

        # Test MOCK_MODE toggle
        mock_initial = None
        mock_after = None
        button_text = ""
        mock_restored = False
        try:
            mock_initial = page.evaluate("() => Studio.MOCK_MODE")
            page.click("#mock-mode-toggle", timeout=5000)
            page.wait_for_timeout(1000)
            mock_after = page.evaluate("() => Studio.MOCK_MODE")
            button_text = page.evaluate("() => document.getElementById('mock-mode-toggle').textContent.trim()")
            page.click("#mock-mode-toggle", timeout=5000)
            page.wait_for_timeout(500)
            mock_restored = True
        except Exception as e:
            button_text = f"error: {str(e)[:100]}"

        # Check viewport canvas
        viewport = page.evaluate("() => { const c = document.querySelector('#viewport-container canvas'); return c ? {present: true, w: c.width, h: c.height} : {present: false} }")

        # Screenshot
        shot_path = str(CAPTURES_DIR / f"studio_v2_audit_{_timestamp()}.png")
        page.screenshot(path=shot_path)

        # Determine verdict
        js_errors = [l for l in logs if l["type"] == "error"]
        tabs_ok = all(t.get("active", False) for t in nav_results if "error" not in t)
        toggle_ok = mock_initial is not None and mock_after != mock_initial and mock_restored
        if js_errors or not tabs_ok or not toggle_ok:
            verdict = "FAIL"
        elif not viewport.get("present"):
            verdict = "WARN"
        else:
            verdict = "PASS"

        result = {
            "verdict": verdict,
            "url": url,
            "nav_tabs": nav_results,
            "mock_toggle": {
                "initial": mock_initial,
                "after_click": mock_after,
                "button_text": button_text,
                "restored": mock_restored,
            },
            "viewport": viewport,
            "console_errors": logs[:10],
            "screenshot": shot_path,
        }
        print(json.dumps(result, indent=2))

    finally:
        browser.close()
        pw.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Agent browser tool — gives AI agents eyes via Playwright",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- screenshot --
    p = sub.add_parser("screenshot", help="Capture page screenshot")
    p.add_argument("url")
    p.add_argument("--out", help="Output file path")
    p.add_argument("--wait", help="CSS selector to wait for before capture")
    p.add_argument("--selector", help="Screenshot only this element")
    p.add_argument("--full", action="store_true", help="Full page screenshot")
    p.add_argument("--timeout", type=int, default=15, help="Wait timeout seconds")
    p.set_defaults(func=cmd_screenshot)

    # -- console --
    p = sub.add_parser("console", help="Capture console logs")
    p.add_argument("url")
    p.add_argument("--level", help="Filter: error,warning,info,log (comma-separated)")
    p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(func=cmd_console)

    # -- eval --
    p = sub.add_parser("eval", help="Evaluate JavaScript in page")
    p.add_argument("url")
    p.add_argument("expression", help="JS expression to evaluate")
    p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(func=cmd_eval)

    # -- audit --
    p = sub.add_parser("audit", help="Full audit: screenshot + console + metrics (one call)")
    p.add_argument("url")
    p.add_argument("--out", help="Screenshot output path")
    p.add_argument("--wait", help="CSS selector to wait for")
    p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(func=cmd_audit)

    # -- filmstrip --
    p = sub.add_parser("filmstrip", help="Capture N frames over time")
    p.add_argument("url")
    p.add_argument("--frames", type=int, default=5, help="Number of frames")
    p.add_argument("--interval", type=int, default=1000, help="Interval between frames (ms)")
    p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(func=cmd_filmstrip)

    # -- interact --
    p = sub.add_parser("interact", help="Execute action sequence then capture")
    p.add_argument("url")
    p.add_argument("--actions", required=True, help='JSON array of actions')
    p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(func=cmd_interact)

    # -- viewer3d --
    p = sub.add_parser("viewer3d", help="3D viewer: load GLB, screenshot, extract scene info")
    p.add_argument("model", help="GLB filename, path, or full URL")
    p.add_argument("--rotate", help="Comma-separated angles to capture (e.g., 0,90,180,270)")
    p.add_argument("--base-url", default="http://192.168.100.16:8000", help="Server base URL")
    p.add_argument("--timeout", type=int, default=20)
    p.set_defaults(func=cmd_viewer3d)

    # -- diff --
    p = sub.add_parser("diff", help="Visual diff two images: similarity pct + highlighted diff")
    p.add_argument("image_a", help="First image (baseline/reference)")
    p.add_argument("image_b", help="Second image (current/test)")
    p.add_argument("--out", help="Output diff image path")
    p.set_defaults(func=cmd_diff)

    # -- assert --
    p = sub.add_parser("assert", help="Run DOM/visual assertions, returns pass/fail JSON")
    p.add_argument("url")
    p.add_argument("--wait", help="CSS selector to wait for")
    p.add_argument("--timeout", type=int, default=15)
    p.add_argument("--no-errors", action="store_true", help="Fail if console errors present")
    p.add_argument("--has-selector", help="Fail if this selector is missing")
    p.add_argument("--no-selector", help="Fail if this selector exists")
    p.add_argument("--text-contains", help="Fail if page text doesn't contain this")
    p.add_argument("--text-absent", help="Fail if page text contains this")
    p.add_argument("--canvas-rendered", action="store_true", help="Fail if canvas is blank")
    p.add_argument("--min-meshes", type=int, help="Fail if fewer Three.js meshes")
    p.add_argument("--js-truthy", help="Fail if JS expression is falsy")
    p.add_argument("--no-screenshot", action="store_true", help="Skip failure screenshot")
    p.set_defaults(func=cmd_assert)

    # -- watch --
    p = sub.add_parser("watch", help="Retry assertions until pass or max retries")
    p.add_argument("url")
    p.add_argument("--wait", help="CSS selector to wait for")
    p.add_argument("--timeout", type=int, default=15)
    p.add_argument("--retries", type=int, default=10, help="Max retries (default 10)")
    p.add_argument("--interval", type=float, default=3, help="Seconds between retries")
    p.add_argument("--no-errors", action="store_true")
    p.add_argument("--has-selector", help="Selector that must exist")
    p.add_argument("--text-contains", help="Text that must be present")
    p.add_argument("--canvas-rendered", action="store_true")
    p.add_argument("--min-meshes", type=int)
    p.add_argument("--js-truthy", help="JS expression that must be truthy")
    p.set_defaults(func=cmd_watch)

    # -- adb --
    p = sub.add_parser("adb", help="Capture Android device screen via ADB")
    p.add_argument("--serial", help="Device serial (e.g., R58W41RF6ZK)")
    p.add_argument("--out", help="Output file path")
    p.set_defaults(func=cmd_adb)

    # -- describe --
    p = sub.add_parser("describe", help="Extract text description of page (zero-screenshot audit)")
    p.add_argument("url")
    p.add_argument("--wait", help="CSS selector to wait for")
    p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(func=cmd_describe)

    # -- verify --
    p = sub.add_parser("verify", help="GLB quality check: texture analysis + optional render")
    p.add_argument("glb_path", help="Path to GLB file")
    p.add_argument("--render", action="store_true", help="Also render in browser")
    p.add_argument("--base-url", default="http://192.168.100.16:8000", help="Server base URL")
    p.set_defaults(func=cmd_verify)

    # -- skin-check --
    p = sub.add_parser("skin-check", help="Render GLB + check if output looks like human skin")
    p.add_argument("glb_path", help="Path to GLB file or model name")
    p.add_argument("--angles", default="0,90,180,270", help="Rotation angles (comma-separated)")
    p.add_argument("--base-url", default="http://192.168.100.16:8000", help="Server base URL")
    p.add_argument("--timeout", type=int, default=20, help="Page load timeout seconds")
    p.set_defaults(func=cmd_skin_check)

    # -- cinematic-check --
    p = sub.add_parser("cinematic-check", help="Verify Cinematic Scan: HDRI, SSS, Definition, EWR Audit")
    p.add_argument("model", help="GLB filename or model name")
    p.add_argument("--base-url", default="http://localhost:8000", help="Server base URL")
    p.add_argument("--timeout", type=int, default=20)
    p.set_defaults(func=cmd_cinematic_check)

    # -- studio-audit --
    p = sub.add_parser("studio-audit", help="Audit GTD3D Studio: stream status, sensor sync, UI state")
    p.add_argument("--base-url", default="http://localhost:8000", help="Server base URL")
    p.add_argument("--phone-ip", default="192.168.100.2", help="Phone/MatePad IP")
    p.add_argument("--timeout", type=int, default=20)
    p.set_defaults(func=cmd_studio_audit)

    # -- studio-v2-audit --
    p = sub.add_parser("studio-v2-audit", help="Audit Studio v2: nav tabs, mock toggle, viewport")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--phone-ip", default="192.168.100.6")
    p.add_argument("--timeout", type=int, default=20)
    p.set_defaults(func=cmd_studio_v2_audit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
