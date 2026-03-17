#!/usr/bin/env python3
"""
GTDdebug — Dual-Device Muscle Scanner CLI
==========================================
One-command orchestration of the full dual-device scan pipeline.

Usage:
    python scripts/gtddebug.py <command> [options]

Commands:
    setup       Force-stop apps, push roles, launch both, wait for camera init
    capture     ADB-tap both devices simultaneously (repeat for side view)
    pull        Pull captured JPEGs from both devices
    upload      Upload pulled images to server, print results
    full        setup → front-capture → rotate-wait → side-capture → pull → upload
    install     Build APK (optional) and install on both devices
    logs        Tail the py4web server log

Options:
    --phone SERIAL      Phone serial (default: R58W41RF6ZK)
    --tablet SERIAL     Tablet serial / IP:port (default: 192.168.100.33:5555)
    --muscle GROUP      Muscle group (default: quadricep)
    --distance CM       Camera distance in cm (default: 100)
    --customer ID       Customer ID (default: 1)
    --server URL        Server base URL (default: http://192.168.100.16:8000/web_app)
    --no-voice          Disable TTS voice prompts
    --apk PATH          APK path for install command
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from threading import Thread

# ── Defaults ──────────────────────────────────────────────────────────────────
PHONE_SERIAL   = "R58W41RF6ZK"
TABLET_SERIAL  = "192.168.100.33:5555"
APP_PACKAGE    = "com.example.companion_app"
SERVER_URL     = "http://192.168.100.16:8000/web_app"
CUSTOMER_ID    = 1
MUSCLE_GROUP   = "quadricep"
CAMERA_DIST_CM = 100
ROLE_FILE      = "/data/local/tmp/muscle_tracker_role.json"
DUAL_DIR_CACHE = "cache/muscle_dual"

PULL_DIR = os.path.join(os.path.dirname(__file__), "dual_captures")
APK_PATH = os.path.join(os.path.dirname(__file__), "..",
                        "companion_app", "build", "app", "outputs",
                        "flutter-apk", "app-debug.apk")


# ── ADB helpers ───────────────────────────────────────────────────────────────

def adb(serial, *args, timeout=15):
    cmd = ["adb", "-s", serial] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"  [WARN] ADB timeout: {' '.join(args)}")
        return ""
    except FileNotFoundError:
        print("[ERROR] adb not found in PATH"); sys.exit(1)


def adb_shell(serial, cmd_str, timeout=15):
    return adb(serial, "shell", cmd_str, timeout=timeout)


def parallel(fn_a, fn_b):
    results = [None, None]
    def ra(): results[0] = fn_a()
    def rb(): results[1] = fn_b()
    ta, tb = Thread(target=ra), Thread(target=rb)
    ta.start(); tb.start()
    ta.join(timeout=30); tb.join(timeout=30)
    return results


def speak(text, enabled=True):
    if not enabled:
        print(f"  [{text}]"); return
    try:
        import pyttsx3
        e = pyttsx3.init(); e.say(text); e.runAndWait()
    except Exception:
        print(f"  [{text}]")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_setup(args):
    """Force-stop apps, push role files, launch both, wait for camera init."""
    print("\n=== SETUP ===")

    # Connect tablet over WiFi if needed
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    if args.tablet not in out:
        print(f"  Connecting to tablet {args.tablet} via WiFi...")
        subprocess.run(["adb", "connect", args.tablet], capture_output=True)
        time.sleep(2)
        out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
        if args.tablet not in out:
            print(f"  [ERROR] Tablet {args.tablet} not reachable"); return False

    def setup_device(serial, role):
        adb_shell(serial, f"am force-stop {APP_PACKAGE}")
        adb_shell(serial, f"run-as {APP_PACKAGE} rm -rf {DUAL_DIR_CACHE}")
        adb_shell(serial, f'echo \'{json.dumps({"role": role})}\' > {ROLE_FILE} && chmod 666 {ROLE_FILE}')
        adb_shell(serial, "rm -f /data/local/tmp/muscle_tracker_trigger")
        adb_shell(serial, "settings put global stay_on_while_plugged_in 3")
        adb_shell(serial, "settings put global window_animation_scale 0")
        adb_shell(serial, "settings put global transition_animation_scale 0")
        adb_shell(serial, "settings put global animator_duration_scale 0")
        if role == "back":
            adb_shell(serial, "settings put system screen_brightness 10")
        print(f"  {role} ({serial}): role set")

    parallel(lambda: setup_device(args.phone, "front"),
             lambda: setup_device(args.tablet, "back"))

    print("  Launching apps...")
    parallel(
        lambda: adb_shell(args.phone,  f"am start -n {APP_PACKAGE}/.MainActivity"),
        lambda: adb_shell(args.tablet, f"am start -n {APP_PACKAGE}/.MainActivity"),
    )
    print("  Waiting 8s for cameras to initialize...")
    time.sleep(8)
    print("  Setup complete — both devices ready")
    return True


def cmd_capture(args):
    """Tap both devices simultaneously to trigger DUAL capture."""
    print("\n=== CAPTURE ===")
    speak("Stand still. Capturing.", args.voice)
    parallel(
        lambda: adb_shell(args.phone,  "input tap 540 1100"),
        lambda: adb_shell(args.tablet, "input tap 800 1280"),
    )
    print("  Waiting 5s for burst to complete...")
    time.sleep(5)
    print("  Capture done")


def cmd_pull(args):
    """Pull captured JPEGs from both devices. Returns (phone_files, tablet_files)."""
    print("\n=== PULL ===")
    os.makedirs(PULL_DIR, exist_ok=True)

    def pull_device(serial, role):
        raw = adb_shell(serial, f"run-as {APP_PACKAGE} ls {DUAL_DIR_CACHE}/")
        files = [f.strip() for f in raw.split("\n")
                 if f.strip().endswith(".jpg")]
        print(f"  {role} ({serial}): {len(files)} images found")
        pulled = []
        for fname in sorted(files):
            local = os.path.join(PULL_DIR, f"{role}_{fname}")
            cmd = ["adb", "-s", serial, "exec-out",
                   "run-as", APP_PACKAGE, "cat", f"{DUAL_DIR_CACHE}/{fname}"]
            try:
                with open(local, "wb") as f:
                    subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=15)
                size = os.path.getsize(local)
                if size > 5000:
                    pulled.append(local)
                    print(f"    {fname}: {size} bytes OK")
                else:
                    print(f"    {fname}: {size} bytes — too small, skipping")
                    os.remove(local)
            except Exception as e:
                print(f"    {fname}: pull failed — {e}")
        return pulled

    phone_files, tablet_files = parallel(
        lambda: pull_device(args.phone, "front"),
        lambda: pull_device(args.tablet, "back"),
    )
    return phone_files or [], tablet_files or []


def cmd_upload(phone_files, tablet_files, args):
    """Rename captures and upload quad scan to server."""
    print("\n=== UPLOAD ===")
    try:
        import requests
    except ImportError:
        print("  [ERROR] requests not installed: pip install requests"); return None

    # Map to standard names
    images = {}
    if len(phone_files) >= 1:  images["front"]      = phone_files[0]
    if len(phone_files) >= 2:  images["left_side"]  = phone_files[1]
    if len(tablet_files) >= 1: images["back"]       = tablet_files[0]
    if len(tablet_files) >= 2: images["right_side"] = tablet_files[1]

    if len(images) < 2:
        print(f"  [ERROR] Need at least 2 images, got {len(images)}: {list(images.keys())}")
        return None

    # Copy to named files for inspection
    for name, src in images.items():
        dest = os.path.join(PULL_DIR, f"{name}.jpg")
        shutil.copy2(src, dest)

    # Auth token
    try:
        r = requests.post(f"{args.server}/api/auth/token",
                          json={"email": "demo@muscle.com"}, timeout=5)
        token = r.json().get("token", "demo")
    except Exception:
        token = "demo"

    url = f"{args.server}/api/upload_quad_scan/{args.customer}"
    print(f"  POST {url}")
    files = {k: open(v, "rb") for k, v in images.items()}
    data  = {"muscle_group": args.muscle,
             "camera_distance_cm": str(args.distance)}
    try:
        r = requests.post(url, files=files, data=data,
                          headers={"Authorization": f"Bearer {token}"}, timeout=60)
        result = r.json()
    except Exception as e:
        result = {"status": "error", "message": str(e)}
    finally:
        for f in files.values(): f.close()

    return result


def cmd_full(args):
    """Full pipeline: setup → front capture → rotate → side capture → pull → upload."""
    print("\n" + "=" * 60)
    print("  DUAL SCAN — FULL PIPELINE")
    print(f"  Muscle: {args.muscle} | Distance: {args.distance}cm | Customer: {args.customer}")
    print("=" * 60)

    if not cmd_setup(args): sys.exit(1)

    # Front + back capture
    print("\n=== FRONT + BACK ===")
    speak("Stand still. Capturing front and back.", args.voice)
    cmd_capture(args)

    # Rotation countdown
    print("\n=== ROTATE ===")
    speak("Turn 90 degrees to your left now.", args.voice)
    for i in range(10, 0, -1):
        print(f"  Turn 90° to your LEFT — {i}s...", end="\r")
        time.sleep(1)
    print()
    speak("Stand still.", args.voice)

    # Side capture
    print("\n=== SIDES ===")
    speak("Stand still. Capturing sides.", args.voice)
    cmd_capture(args)

    phone_files, tablet_files = cmd_pull(args)

    if len(phone_files) < 2 or len(tablet_files) < 2:
        print(f"\n  [WARN] Short capture: phone={len(phone_files)}, tablet={len(tablet_files)}")
        print("  Proceeding with available images...")

    result = cmd_upload(phone_files, tablet_files, args)

    print("\n=== RESULTS ===")
    if result and result.get("status") == "success":
        print(f"  Volume:        {result.get('volume_cm3', 'N/A')} cm³")
        if result.get("volume_front_cm3"):
            print(f"    Front pair:  {result['volume_front_cm3']} cm³")
        if result.get("volume_back_cm3"):
            print(f"    Back pair:   {result['volume_back_cm3']} cm³")
        print(f"  Circumference: {result.get('circumference_cm', 'N/A')} cm")
        print(f"  Shape:         {result.get('shape_grade', 'N/A')} ({result.get('shape_score', 'N/A')}/100)")
        growth = result.get("growth_pct")
        print(f"  Growth:        {round(growth, 1)}%" if growth is not None else "  Growth:        — (first calibrated scan)")
        print(f"  Calibrated:    {result.get('calibrated', False)}")
        speak("Scan complete.", args.voice)
    else:
        msg = result.get("message", "Unknown error") if result else "No response"
        print(f"  [FAILED] {msg}")
        speak("Scan failed.", args.voice)

    print("\n" + "=" * 60)


def cmd_install(args):
    """Build APK (if --build) and install on both devices."""
    apk = args.apk or APK_PATH
    apk = os.path.normpath(apk)

    if args.build:
        print("=== BUILD APK ===")
        app_dir = os.path.join(os.path.dirname(__file__), "..", "companion_app")
        r = subprocess.run(
            ["flutter", "build", "apk", "--debug", "--target-platform", "android-arm64"],
            cwd=app_dir
        )
        if r.returncode != 0:
            print("[ERROR] Build failed"); sys.exit(1)

    if not os.path.exists(apk):
        print(f"[ERROR] APK not found: {apk}"); sys.exit(1)

    print(f"\n=== INSTALL ===\n  APK: {apk}")

    def install(serial, label):
        print(f"  Installing on {label} ({serial})...")
        r = subprocess.run(["adb", "-s", serial, "install", "-r", apk],
                           capture_output=True, text=True, timeout=120)
        ok = "Success" in r.stdout or "success" in r.stdout.lower()
        print(f"  {label}: {'OK' if ok else 'FAILED'}")
        if not ok: print(f"    {r.stdout.strip() or r.stderr.strip()}")

    parallel(lambda: install(args.phone,  "Phone"),
             lambda: install(args.tablet, "Tablet"))


def cmd_body3d(args):
    """Capture front+back, generate 3D body model, print viewer URL."""
    try:
        import requests
    except ImportError:
        print("[ERROR] requests not installed: pip install requests"); return

    print("\n" + "=" * 60)
    print("  BODY 3D — CAPTURE + GENERATE MESH")
    print(f"  Distance: {args.distance}cm | Customer: {args.customer}")
    print("=" * 60)

    print("\n[body3d] Setting up devices...")
    cmd_setup(args)

    print("\n[body3d] Triggering capture on both devices...")
    cmd_capture(args)

    print("\n[body3d] Pulling images...")
    phone_files, tablet_files = cmd_pull(args)

    front_path = phone_files[0]  if phone_files  else None
    back_path  = tablet_files[0] if tablet_files else None

    if not front_path or not back_path:
        print(f"[body3d] FAILED — missing images: front={front_path} back={back_path}")
        return

    print(f"\n[body3d] front: {os.path.basename(front_path)}")
    print(f"[body3d] back:  {os.path.basename(back_path)}")

    print("\n[body3d] Logging in...")
    try:
        r = requests.post(f"{args.server}/api/login",
                          json={"email": "demo@muscle.com"}, timeout=5)
        token = r.json().get("token", "demo")
    except Exception as e:
        print(f"[body3d] Auth failed: {e}"); token = "demo"

    print("[body3d] Generating body model...")
    try:
        with open(front_path, 'rb') as fh, open(back_path, 'rb') as bh:
            r = requests.post(
                f"{args.server}/api/customer/{args.customer}/body_model",
                headers={"Authorization": f"Bearer {token}"},
                files={"front_image": fh, "back_image": bh},
                data={"camera_distance_cm": str(args.distance)},
                timeout=120,
            )
        result = r.json()
    except Exception as e:
        print(f"[body3d] Request failed: {e}"); return

    if result.get("status") == "success":
        glb_url = result.get("glb_url", "")
        host = args.server.rsplit("/", 1)[0]  # strip /web_app
        viewer = f"{host}/web_app/static/viewer3d/index.html?model={glb_url}"
        print(f"\n[body3d] mesh_id={result['mesh_id']}  "
              f"verts={result['num_vertices']}  "
              f"silhouette_views_used={result.get('silhouette_views_used', 0)}")
        print(f"[body3d] Viewer URL:\n  {viewer}")
        if args.open:
            import webbrowser; webbrowser.open(viewer)
    else:
        print(f"[body3d] FAILED: {result}")


def cmd_logs(args):
    """Tail the server log."""
    log = os.path.join(os.path.dirname(__file__), "..", "server.log")
    log = os.path.normpath(log)
    if not os.path.exists(log):
        print(f"[ERROR] server.log not found at {log}"); return
    subprocess.run(["tail", "-f", "-n", "50", log])


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="GTDdebug — Dual-Device Scan CLI",
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command",
                   choices=["setup", "capture", "pull", "upload", "full", "install", "logs",
                            "body3d"])
    p.add_argument("--phone",    default=PHONE_SERIAL,   help="Phone ADB serial")
    p.add_argument("--tablet",   default=TABLET_SERIAL,  help="Tablet ADB serial/IP:port")
    p.add_argument("--muscle",   default=MUSCLE_GROUP,   help="Muscle group")
    p.add_argument("--distance", type=int, default=CAMERA_DIST_CM, help="Camera distance (cm)")
    p.add_argument("--customer", type=int, default=CUSTOMER_ID,    help="Customer ID")
    p.add_argument("--server",   default=SERVER_URL,     help="Server base URL")
    p.add_argument("--apk",      default=None,           help="APK path (for install)")
    p.add_argument("--build",    action="store_true",    help="Build APK before install")
    p.add_argument("--no-voice", dest="voice", action="store_false", default=True,
                   help="Disable TTS voice prompts")
    p.add_argument("--open", action="store_true",
                   help="Open viewer URL in browser after body3d")

    args = p.parse_args()

    if   args.command == "setup":   cmd_setup(args)
    elif args.command == "capture": cmd_capture(args)
    elif args.command == "pull":
        pf, tf = cmd_pull(args)
        print(f"\n  Pulled {len(pf)} phone + {len(tf)} tablet images → {PULL_DIR}")
    elif args.command == "upload":
        # Find most-recent pulled files
        pf = sorted([f for f in os.listdir(PULL_DIR) if f.startswith("front_")],
                    reverse=True)
        tf = sorted([f for f in os.listdir(PULL_DIR) if f.startswith("back_")],
                    reverse=True)
        pf = [os.path.join(PULL_DIR, f) for f in pf[:2]]
        tf = [os.path.join(PULL_DIR, f) for f in tf[:2]]
        result = cmd_upload(pf, tf, args)
        if result: print(json.dumps(result, indent=2))
    elif args.command == "full":    cmd_full(args)
    elif args.command == "install": cmd_install(args)
    elif args.command == "body3d":  cmd_body3d(args)
    elif args.command == "logs":    cmd_logs(args)


if __name__ == "__main__":
    main()
