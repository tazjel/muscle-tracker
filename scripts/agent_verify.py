#!/usr/bin/env python3
"""
agent_verify.py — CLI for Claude to verify GLB quality after generation.

Three tiers:
  Tier 1: Offline texture analysis (~1-2s, no server needed)
  Tier 2: + Browser render screenshots (~8s, needs server)
  Tier 3: + Compare against reference GLB

Usage:
    PY=C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe

    # Tier 1: Offline analysis only
    $PY scripts/agent_verify.py meshes/skin_densepose.glb

    # Tier 2: + Browser render
    $PY scripts/agent_verify.py meshes/skin_densepose.glb --render

    # Tier 3: + Reference comparison
    $PY scripts/agent_verify.py meshes/skin_densepose.glb --reference meshes/known_good.glb

Exit codes:
    0 = PASS or WARN
    1 = runtime error
    2 = quality FAIL
"""
import sys
import os
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join("C:", os.sep, "Users", "MiEXCITE", "AppData", "Local",
                   "Programs", "Python", "Python312", "python.exe")


def tier1_texture_analysis(glb_path):
    """Offline GLB texture extraction + quality scoring."""
    from core.glb_inspector import score_glb
    return score_glb(glb_path)


def tier2_render_analysis(glb_path):
    """Browser render screenshots + per-angle quality analysis.

    Now uses analyze_render_screenshot() for seam/asymmetry detection on each view.
    """
    from core.glb_inspector import analyze_render_screenshot

    model_name = os.path.basename(glb_path)
    agent_browser = os.path.join(PROJECT_ROOT, "scripts", "agent_browser.py")

    # Copy GLB to static dir so viewer can load it
    static_glb = os.path.join(PROJECT_ROOT, "web_app", "static", "viewer3d", model_name)
    if not os.path.exists(static_glb):
        import shutil
        shutil.copy2(glb_path, static_glb)

    cmd = [PY, agent_browser, "viewer3d", model_name,
           "--rotate", "0,90,180,270"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if proc.returncode != 0:
            return {"error": f"viewer3d failed: {proc.stderr[:200]}"}
        browser_result = json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "viewer3d timed out (45s)"}
    except json.JSONDecodeError:
        return {"error": f"viewer3d invalid JSON: {proc.stdout[:200]}"}

    # Analyze each screenshot with full quality checks
    render_scores = []
    render_issues = []
    for shot in browser_result.get("screenshots", []):
        path = shot.get("path", "")
        if not os.path.exists(path):
            render_scores.append({"angle": shot.get("angle"), "error": "file not found"})
            continue

        analysis = analyze_render_screenshot(path)
        analysis["angle"] = shot.get("angle", "unknown")
        render_scores.append(analysis)

        for issue in analysis.get("issues", []):
            render_issues.append(f"{analysis['angle']}: {issue}")

    return {
        "scene": browser_result.get("scene", {}),
        "renders": render_scores,
        "render_issues": render_issues,
    }


def tier3_reference_comparison(glb_path, reference_path):
    """Compare albedo textures between two GLBs using SSIM."""
    import cv2
    import numpy as np
    from core.glb_inspector import extract_textures

    tex_a = extract_textures(glb_path)
    tex_b = extract_textures(reference_path)

    if tex_a["albedo"] is None:
        return {"error": "test GLB has no albedo"}
    if tex_b["albedo"] is None:
        return {"error": "reference GLB has no albedo"}

    a = tex_a["albedo"]
    b = tex_b["albedo"]

    # Resize to same dimensions
    if a.shape != b.shape:
        h = min(a.shape[0], b.shape[0])
        w = min(a.shape[1], b.shape[1])
        a = cv2.resize(a, (w, h))
        b = cv2.resize(b, (w, h))

    # Convert to grayscale for SSIM
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float64)

    # Manual SSIM (avoids skimage dependency)
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    mu_a = cv2.GaussianBlur(ga, (11, 11), 1.5)
    mu_b = cv2.GaussianBlur(gb, (11, 11), 1.5)
    mu_a_sq = mu_a ** 2
    mu_b_sq = mu_b ** 2
    mu_ab = mu_a * mu_b

    sigma_a_sq = cv2.GaussianBlur(ga ** 2, (11, 11), 1.5) - mu_a_sq
    sigma_b_sq = cv2.GaussianBlur(gb ** 2, (11, 11), 1.5) - mu_b_sq
    sigma_ab = cv2.GaussianBlur(ga * gb, (11, 11), 1.5) - mu_ab

    ssim_map = ((2 * mu_ab + C1) * (2 * sigma_ab + C2)) / \
               ((mu_a_sq + mu_b_sq + C1) * (sigma_a_sq + sigma_b_sq + C2))
    ssim = float(np.mean(ssim_map))

    return {
        "ssim": round(ssim, 4),
        "match": "MATCH" if ssim > 0.9 else ("SIMILAR" if ssim > 0.7 else "DIFFERENT"),
    }


def main():
    parser = argparse.ArgumentParser(description="Verify GLB output quality")
    parser.add_argument("glb_path", help="Path to GLB file to verify")
    parser.add_argument("--render", action="store_true",
                        help="Tier 2: also render in browser and analyze screenshots")
    parser.add_argument("--reference",
                        help="Tier 3: compare against reference GLB (SSIM)")
    args = parser.parse_args()

    if not os.path.exists(args.glb_path):
        print(json.dumps({"error": f"File not found: {args.glb_path}"}))
        sys.exit(1)

    # ── Tier 1: Always run ──
    result = tier1_texture_analysis(args.glb_path)

    # ── Tier 2: Browser render ──
    if args.render:
        render = tier2_render_analysis(args.glb_path)
        result["render"] = render

        # Downgrade verdict if render shows problems
        if "renders" in render:
            for r in render["renders"]:
                if r.get("non_black_pct", 100) < 5:
                    if result["verdict"] != "FAIL":
                        result["verdict"] = "FAIL"
                        result["issues"].append(f"RENDER_BLANK: {r['angle']} is nearly all black")

    # ── Tier 3: Reference comparison ──
    if args.reference:
        if os.path.exists(args.reference):
            ref = tier3_reference_comparison(args.glb_path, args.reference)
            result["reference"] = ref
        else:
            result["reference"] = {"error": f"Reference not found: {args.reference}"}

    # ── Output ──
    print(json.dumps(result, indent=2))

    # ── Exit code ──
    if result["verdict"] == "FAIL":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
