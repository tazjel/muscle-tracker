"""
browser/viewer.py — 3D viewer and GLB inspection commands.

Commands: viewer3d, verify, skin-check, cinematic-check
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

from browser import (
    CAPTURES_DIR,
    PROJECT_ROOT,
    _launch_browser,
    _timestamp,
    _wait_for_page_ready,
)


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
