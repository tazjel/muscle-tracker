#!/usr/bin/env python3
"""
photo_preflight.py — Pre-flight check for skin scan photos BEFORE running pipeline.

Catches problems that waste 30s+ of DensePose + texture bake time:
- Uneven lighting (left-right / top-bottom brightness gradient)
- Overexposure / underexposure
- Too dark / too bright
- Photo resolution too low
- No body detected (using simple skin-color heuristic)
- Cross-photo exposure mismatch

Usage:
    PY=C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
    $PY scripts/photo_preflight.py                          # check captures/skin_scan/
    $PY scripts/photo_preflight.py --scan-dir path/to/photos
    $PY scripts/photo_preflight.py --fix                    # auto-fix exposure mismatch

Exit codes:
    0 = all photos OK
    1 = runtime error
    2 = photo quality issues detected (pipeline will produce bad results)

Run this BEFORE run_densepose_texture.py to avoid wasting 30+ seconds.
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCAN_DIR = os.path.join(PROJECT_ROOT, 'captures', 'skin_scan')


def check_photo(path, view_name):
    """Check a single photo for quality issues.

    Returns dict with metrics and issues list.
    """
    img = cv2.imread(path)
    if img is None:
        return {"view": view_name, "path": path, "error": "unreadable", "issues": ["UNREADABLE"]}

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0].astype(np.float64)

    issues = []
    metrics = {
        "view": view_name,
        "path": path,
        "resolution": f"{w}x{h}",
        "megapixels": round(w * h / 1e6, 1),
    }

    # ── Resolution check ──
    if w * h < 1_000_000:
        issues.append("LOW_RES: <1MP, DensePose needs at least 1MP for good IUV")

    # ── Overall brightness ──
    mean_brightness = float(l_channel.mean())
    metrics["mean_brightness"] = round(mean_brightness, 1)

    if mean_brightness < 60:
        issues.append(f"TOO_DARK: mean_L={mean_brightness:.0f} < 60 (DensePose misses body in dark photos)")
    elif mean_brightness > 200:
        issues.append(f"OVEREXPOSED: mean_L={mean_brightness:.0f} > 200 (skin tone washed out)")

    # ── Left-right lighting gradient (THE KEY CHECK) ──
    left_half = l_channel[:, :w // 2]
    right_half = l_channel[:, w // 2:]
    lr_diff = abs(float(left_half.mean()) - float(right_half.mean()))
    metrics["lr_brightness_diff"] = round(lr_diff, 1)

    if lr_diff > 15:
        issues.append(f"UNEVEN_LR: left-right brightness diff={lr_diff:.1f} > 15 (causes visible seam on body)")
    elif lr_diff > 8:
        issues.append(f"SLIGHT_UNEVEN_LR: diff={lr_diff:.1f} (may cause mild seam)")

    # ── Top-bottom gradient ──
    top_half = l_channel[:h // 2, :]
    bottom_half = l_channel[h // 2:, :]
    tb_diff = abs(float(top_half.mean()) - float(bottom_half.mean()))
    metrics["tb_brightness_diff"] = round(tb_diff, 1)

    if tb_diff > 20:
        issues.append(f"UNEVEN_TB: top-bottom brightness diff={tb_diff:.1f} > 20")

    # ── Contrast / dynamic range ──
    contrast = float(l_channel.std())
    metrics["contrast_std"] = round(contrast, 1)

    if contrast < 20:
        issues.append(f"LOW_CONTRAST: std={contrast:.1f} < 20 (flat lighting, poor texture detail)")
    elif contrast > 80:
        issues.append(f"HIGH_CONTRAST: std={contrast:.1f} > 80 (harsh shadows, DensePose may fail)")

    # ── Body detection (simple skin-color heuristic in HSV) ──
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Skin range in HSV: H=[0,25], S=[20,180], V=[50,255]
    skin_mask = ((hsv[:, :, 0] <= 25) | (hsv[:, :, 0] >= 165)) & \
                (hsv[:, :, 1] >= 20) & (hsv[:, :, 1] <= 180) & \
                (hsv[:, :, 2] >= 50)
    skin_pct = float(skin_mask.mean() * 100)
    metrics["skin_pixel_pct"] = round(skin_pct, 1)

    if skin_pct < 3:
        issues.append(f"NO_BODY: only {skin_pct:.1f}% skin-colored pixels (need >3%)")
    elif skin_pct < 8:
        issues.append(f"SMALL_BODY: {skin_pct:.1f}% skin pixels (body may be too far)")

    # ── Skin-region brightness (only skin pixels) ──
    if skin_pct > 3:
        skin_brightness = float(l_channel[skin_mask].mean())
        metrics["skin_brightness"] = round(skin_brightness, 1)

        # Check skin-area left-right gradient specifically
        skin_left = skin_mask[:, :w // 2]
        skin_right = skin_mask[:, w // 2:]
        if skin_left.sum() > 100 and skin_right.sum() > 100:
            skin_l_bright = float(l_channel[:, :w // 2][skin_left].mean())
            skin_r_bright = float(l_channel[:, w // 2:][skin_right].mean())
            skin_lr_diff = abs(skin_l_bright - skin_r_bright)
            metrics["skin_lr_diff"] = round(skin_lr_diff, 1)
            if skin_lr_diff > 12:
                issues.append(f"SKIN_UNEVEN_LR: body left-right brightness diff={skin_lr_diff:.1f} > 12 "
                              f"(L={skin_l_bright:.0f} R={skin_r_bright:.0f}) — WILL cause seam")

    metrics["issues"] = issues
    metrics["ok"] = len(issues) == 0
    return metrics


def check_cross_exposure(photos):
    """Check exposure consistency across all photos.

    Large differences cause color seams even after LAB harmonization.
    """
    issues = []
    brightnesses = {}
    for info in photos:
        if "error" not in info and "mean_brightness" in info:
            brightnesses[info["view"]] = info["mean_brightness"]

    if len(brightnesses) < 2:
        return issues

    values = list(brightnesses.values())
    max_diff = max(values) - min(values)
    brightest = max(brightnesses, key=brightnesses.get)
    darkest = min(brightnesses, key=brightnesses.get)

    if max_diff > 30:
        issues.append(f"EXPOSURE_MISMATCH: {brightest}={brightnesses[brightest]:.0f} vs "
                      f"{darkest}={brightnesses[darkest]:.0f} (diff={max_diff:.0f} > 30) — "
                      f"LAB harmonization can't fully fix this")
    elif max_diff > 15:
        issues.append(f"MILD_EXPOSURE_DIFF: {brightest} vs {darkest} (diff={max_diff:.0f}) — "
                      f"LAB harmonization should handle this")

    return issues


def main():
    parser = argparse.ArgumentParser(description='Pre-flight check for skin scan photos')
    parser.add_argument('--scan-dir', default=DEFAULT_SCAN_DIR, help='Photo directory')
    parser.add_argument('--views', nargs='+', default=['front', 'back', 'left', 'right'])
    parser.add_argument('--json', action='store_true', help='Output JSON instead of human-readable')
    args = parser.parse_args()

    photos = []
    all_issues = []

    for view in args.views:
        path = os.path.join(args.scan_dir, f'{view}.jpg')
        if not os.path.exists(path):
            path = os.path.join(args.scan_dir, f'{view}.png')
        if not os.path.exists(path):
            info = {"view": view, "error": "not found", "issues": ["MISSING"]}
            all_issues.append(f"MISSING: {view} photo not found")
        else:
            info = check_photo(path, view)
            all_issues.extend([f"{view}: {i}" for i in info.get("issues", [])])
        photos.append(info)

    # Cross-photo checks
    cross_issues = check_cross_exposure(photos)
    all_issues.extend(cross_issues)

    # Verdict
    has_fatal = any(i.startswith(("UNREADABLE", "NO_BODY", "MISSING", "TOO_DARK",
                                  "OVEREXPOSED", "EXPOSURE_MISMATCH", "SKIN_UNEVEN_LR"))
                    for info in photos for i in info.get("issues", []))
    has_fatal = has_fatal or any(i.startswith("EXPOSURE_MISMATCH") for i in cross_issues)

    verdict = "FAIL" if has_fatal else ("WARN" if all_issues else "PASS")

    result = {
        "verdict": verdict,
        "scan_dir": args.scan_dir,
        "photos": photos,
        "cross_issues": cross_issues,
        "all_issues": all_issues,
        "suggestion": _suggest(all_issues) if all_issues else "Photos look good for pipeline.",
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  PHOTO PRE-FLIGHT: {verdict}")
        print(f"{'='*60}")
        for info in photos:
            status = "OK" if info.get("ok") else "ISSUES" if "issues" in info else "ERROR"
            print(f"\n  {info['view']:>6}: {status}")
            if "resolution" in info:
                print(f"         res={info['resolution']} brightness={info.get('mean_brightness','?')}"
                      f" contrast={info.get('contrast_std','?')} skin={info.get('skin_pixel_pct','?')}%")
            if "lr_brightness_diff" in info:
                print(f"         LR_diff={info['lr_brightness_diff']} skin_LR={info.get('skin_lr_diff','?')}")
            for issue in info.get("issues", []):
                print(f"         ! {issue}")
        if cross_issues:
            print(f"\n  Cross-photo:")
            for i in cross_issues:
                print(f"         ! {i}")
        if all_issues:
            print(f"\n  Suggestion: {_suggest(all_issues)}")
        print()

    sys.exit(2 if verdict == "FAIL" else 0)


def _suggest(issues):
    """Map issues to actionable advice."""
    suggestions = []
    issue_text = " ".join(issues)

    if "UNEVEN_LR" in issue_text or "SKIN_UNEVEN_LR" in issue_text:
        suggestions.append("Retake photos with even lighting (face a window or use 2 symmetric lights).")
    if "TOO_DARK" in issue_text:
        suggestions.append("Photos are too dark — increase room lighting or use flash.")
    if "OVEREXPOSED" in issue_text:
        suggestions.append("Photos are overexposed — reduce lighting or lower camera exposure.")
    if "EXPOSURE_MISMATCH" in issue_text:
        suggestions.append("Lock camera exposure/white-balance before taking all 4 views.")
    if "LOW_CONTRAST" in issue_text:
        suggestions.append("Flat lighting — add directional light for skin detail.")
    if "NO_BODY" in issue_text or "SMALL_BODY" in issue_text:
        suggestions.append("Body not detected — check framing, stand closer, ensure skin is visible.")

    return " ".join(suggestions) if suggestions else "Minor issues — pipeline may still produce acceptable results."


if __name__ == '__main__':
    main()
