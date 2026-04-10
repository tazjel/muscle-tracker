"""
browser/studio.py — GTD3D Studio automation commands.

Commands: studio-audit, studio-v2-audit
"""
import json

from browser import (
    CAPTURES_DIR,
    _launch_browser,
    _timestamp,
    _wait_for_page_ready,
)


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
