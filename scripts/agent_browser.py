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
"""
import argparse
import json
import os
import sys
import time
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
        url = f"{base_url}/web_app/static/viewer3d/index.html?model={model}"

    pw, browser, context = _launch_browser()

    try:
        page = context.new_page()
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


def main():
    parser = argparse.ArgumentParser(
        description="Agent browser tool — gives AI agents eyes via Playwright",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
