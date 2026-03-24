"""Test the region adjustment Apply/Reset flow via Playwright."""
import json
from playwright.sync_api import sync_playwright

URL = "http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/17.glb"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(4000)  # let Three.js fully load

    # Capture console
    logs = []
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))

    # 1. Before state
    before = json.loads(page.evaluate("JSON.stringify(window._adjustDebug())"))
    print("BEFORE:", json.dumps(before, indent=2))

    # 2. Select glutes + set width=20 + Apply
    page.evaluate("""
        window.selectMuscleRegion('glutes');
        document.getElementById('adj-width').value = 20;
        window.applyAdjustment();
    """)
    after_apply = json.loads(page.evaluate("JSON.stringify(window._adjustDebug())"))
    print("\nAFTER APPLY:", json.dumps(after_apply, indent=2))

    # 3. Take screenshot
    page.screenshot(path="captures/test_after_apply.png")

    # 4. Reset
    page.evaluate("window.resetAdjustment()")
    after_reset = json.loads(page.evaluate("JSON.stringify(window._adjustDebug())"))
    print("\nAFTER RESET:", json.dumps(after_reset, indent=2))

    # 5. Screenshot after reset
    page.screenshot(path="captures/test_after_reset.png")

    # 6. Verify
    print("\n--- Console logs ---")
    for l in logs:
        print(l)

    # Compare hip verts
    if before.get('hipVerts') and after_apply.get('hipVerts'):
        b = before['hipVerts'][0]
        a = after_apply['hipVerts'][0]
        print(f"\nHip vert[0] before: {b}")
        print(f"Hip vert[0] after:  {a}")
        changed = any(abs(b[i] - a[i]) > 0.001 for i in range(3))
        print(f"Changed: {changed}")

    browser.close()
