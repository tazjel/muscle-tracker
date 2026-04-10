"""
scripts/browser — Playwright power tool for AI agents.

Package structure:
  __init__.py  — shared utilities, adb command, CLI dispatcher (main)
  core.py      — general browser commands (screenshot, console, eval, audit,
                  filmstrip, interact, diff, assert, watch, describe)
  viewer.py    — 3D/GLB commands (viewer3d, verify, skin-check, cinematic-check)
  studio.py    — Studio automation commands (studio-audit, studio-v2-audit)
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CAPTURES_DIR = PROJECT_ROOT / "captures"
CAPTURES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ADB command (small enough to live here)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CLI dispatcher
# ---------------------------------------------------------------------------

def main():
    import argparse
    from browser.core import (
        cmd_screenshot, cmd_console, cmd_eval, cmd_audit,
        cmd_filmstrip, cmd_interact, cmd_diff, cmd_assert,
        cmd_watch, cmd_describe,
    )
    from browser.viewer import cmd_viewer3d, cmd_verify, cmd_skin_check, cmd_cinematic_check
    from browser.studio import cmd_studio_audit, cmd_studio_v2_audit

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
