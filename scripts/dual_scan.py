#!/usr/bin/env python3
"""
Dual-Device Synchronized Muscle Scanning — Desktop Orchestrator

Controls two Android devices (phone + tablet) via ADB to capture
front/back/left/right views simultaneously, then uploads to server.

Usage:
    python scripts/dual_scan.py
    python scripts/dual_scan.py --phone R58W41RF6ZK --tablet 192.168.100.33:5555
"""

import subprocess
import sys
import os
import time
import json
import argparse
import glob
import shutil
from threading import Thread

# --- Configuration ---

SERVER_URL = "http://192.168.100.16:8000/web_app"
CUSTOMER_ID = 1
MUSCLE_GROUP = "quadricep"
CAMERA_DISTANCE_CM = 120

PHONE_SERIAL = "R58W41RF6ZK"
TABLET_SERIAL = "192.168.100.33:5555"
APP_PACKAGE = "com.example.companion_app"

DUAL_DIR_CACHE = "cache/muscle_dual"  # inside app sandbox (run-as required)
ROLE_FILE = "/data/local/tmp/muscle_tracker_role.json"
TRIGGER_FILE = "/data/local/tmp/muscle_tracker_trigger"

LOCAL_PULL_DIR = os.path.join(os.path.dirname(__file__), "dual_captures")


def adb(serial, *args):
    """Run an ADB command and return stdout."""
    cmd = ["adb", "-s", serial] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"  [WARN] ADB timeout: {' '.join(cmd)}")
        return ""
    except FileNotFoundError:
        print("[ERROR] adb not found in PATH")
        sys.exit(1)


def adb_shell(serial, cmd_str):
    """Run an ADB shell command."""
    return adb(serial, "shell", cmd_str)


def parallel(fn_a, fn_b):
    """Run two functions in parallel, return their results."""
    results = [None, None]
    def run_a(): results[0] = fn_a()
    def run_b(): results[1] = fn_b()
    ta, tb = Thread(target=run_a), Thread(target=run_b)
    ta.start(); tb.start()
    ta.join(timeout=30); tb.join(timeout=30)
    return results


def speak(text):
    """Text-to-speech via pyttsx3 (desktop speakers)."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except ImportError:
        print(f"  [TTS not available] {text}")
    except Exception as e:
        print(f"  [TTS error: {e}] {text}")


# --- Phase 0: Setup ---

def check_devices(phone, tablet):
    """Verify both devices are connected."""
    print("\n=== PHASE 0: SETUP ===")
    output = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    print(f"  Connected devices:\n{output}")

    if phone not in output:
        print(f"  [ERROR] Phone {phone} not connected")
        return False

    if tablet not in output:
        print(f"  Tablet {tablet} not found — attempting WiFi connect...")
        subprocess.run(["adb", "connect", tablet], capture_output=True, text=True)
        time.sleep(2)
        output = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
        if tablet not in output:
            print(f"  [ERROR] Tablet {tablet} still not connected")
            return False
        print(f"  Tablet connected via WiFi")

    return True


def setup_device(serial, role):
    """Configure a device for dual scanning."""
    print(f"  Setting up {role} device ({serial})...")

    # Kill old app instance
    adb_shell(serial, f"am force-stop {APP_PACKAGE}")

    # Clear old captures (inside app sandbox)
    adb_shell(serial, f"run-as {APP_PACKAGE} rm -rf {DUAL_DIR_CACHE}")

    # Push role config to /data/local/tmp (world-readable)
    role_json = json.dumps({"role": role})
    adb_shell(serial, f'echo \'{role_json}\' > {ROLE_FILE} && chmod 666 {ROLE_FILE}')

    # Remove any stale trigger
    adb_shell(serial, f"rm -f {TRIGGER_FILE}")

    # Developer optimizations
    adb_shell(serial, "settings put global stay_on_while_plugged_in 3")
    adb_shell(serial, "settings put global window_animation_scale 0")
    adb_shell(serial, "settings put global transition_animation_scale 0")
    adb_shell(serial, "settings put global animator_duration_scale 0")

    # Dim screen for tablet (reduce false-touch visual feedback)
    if role == "back":
        adb_shell(serial, "settings put system screen_brightness 10")

    print(f"  {role} device ready")


def launch_app(serial):
    """Launch the companion app."""
    adb_shell(serial, f"am start -n {APP_PACKAGE}/.MainActivity")


def setup_all(phone, tablet):
    """Full setup for both devices."""
    if not check_devices(phone, tablet):
        return False

    parallel(
        lambda: setup_device(phone, "front"),
        lambda: setup_device(tablet, "back"),
    )

    print("  Launching app on both devices...")
    parallel(
        lambda: launch_app(phone),
        lambda: launch_app(tablet),
    )

    print("  Waiting 6s for cameras to initialize...")
    time.sleep(6)
    return True


# --- Phase 1 & 3: Capture ---

def trigger_phone(phone):
    """Trigger capture on phone via screen tap (center of screen)."""
    # Samsung A24 portrait: ~1080x2340, center tap
    adb_shell(phone, "input tap 540 1170")
    return True


def trigger_tablet(tablet):
    """Trigger capture on tablet via ADB tap (center of 1600x2560 screen)."""
    # File trigger has permission issues; ADB tap works reliably
    # MatePad Pro 1600x2560 portrait, center = 800,1280
    adb_shell(tablet, "input tap 800 1280")
    return True


def capture_phase(phone, tablet, phase_name):
    """Trigger simultaneous capture on both devices."""
    print(f"\n  >>> {phase_name} — CAPTURING <<<")
    parallel(
        lambda: trigger_phone(phone),
        lambda: trigger_tablet(tablet),
    )
    print("  Waiting 4s for burst capture to complete...")
    time.sleep(4)
    print(f"  {phase_name} capture done")


# --- Phase 4: Collect & Upload ---

def pull_images(serial, role, local_dir):
    """Pull captured images from device app sandbox using exec-out run-as."""
    device_files = adb_shell(serial, f"run-as {APP_PACKAGE} ls {DUAL_DIR_CACHE}/").split("\n")
    device_files = [f.strip() for f in device_files if f.strip() and f.strip().endswith(".jpg")]
    print(f"  Found {len(device_files)} images on {role} device")

    pulled = []
    for fname in sorted(device_files):
        local = os.path.join(local_dir, f"{role}_{fname}")
        # Binary-safe pull: exec-out + run-as cat (adb shell cat corrupts on Windows)
        cmd = ["adb", "-s", serial, "exec-out", "run-as", APP_PACKAGE, "cat", f"{DUAL_DIR_CACHE}/{fname}"]
        try:
            with open(local, "wb") as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=15)
            if os.path.exists(local) and os.path.getsize(local) > 0:
                pulled.append(local)
                print(f"    Pulled {fname} ({os.path.getsize(local)} bytes)")
        except Exception as e:
            print(f"    Failed to pull {fname}: {e}")
    return pulled


def rename_captures(phone_files, tablet_files, local_dir):
    """
    Rename captures to standard names:
    Phone capture 1 → front.jpg, Phone capture 2 → left_side.jpg
    Tablet capture 1 → back.jpg, Tablet capture 2 → right_side.jpg
    """
    mapping = {}

    if len(phone_files) >= 1:
        mapping["front"] = phone_files[0]
    if len(phone_files) >= 2:
        mapping["left_side"] = phone_files[1]
    if len(tablet_files) >= 1:
        mapping["back"] = tablet_files[0]
    if len(tablet_files) >= 2:
        mapping["right_side"] = tablet_files[1]

    renamed = {}
    for name, src in mapping.items():
        dest = os.path.join(local_dir, f"{name}.jpg")
        shutil.copy2(src, dest)
        renamed[name] = dest

    return renamed


def upload_quad_scan(images, customer_id, muscle_group, camera_distance_cm):
    """Upload 4 images to server."""
    import requests

    url = f"{SERVER_URL}/api/upload_quad_scan/{customer_id}"
    print(f"\n  Uploading to {url}...")

    files = {}
    for key in ("front", "back", "left_side", "right_side"):
        if key in images:
            files[key] = open(images[key], "rb")

    data = {
        "muscle_group": muscle_group,
        "camera_distance_cm": str(camera_distance_cm),
    }

    # Get auth token
    try:
        auth_res = requests.post(
            f"{SERVER_URL}/api/auth/token",
            json={"email": "demo@muscle.com"},
            timeout=5,
        )
        token = auth_res.json().get("token", "demo")
    except Exception:
        token = "demo"

    headers = {"Authorization": f"Bearer {token}"}

    try:
        res = requests.post(url, files=files, data=data, headers=headers, timeout=60)
        result = res.json()
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        for f in files.values():
            f.close()


def collect_and_upload(phone, tablet):
    """Pull images from both devices and upload."""
    print("\n=== PHASE 4: COLLECT & UPLOAD ===")

    os.makedirs(LOCAL_PULL_DIR, exist_ok=True)

    phone_files, tablet_files = parallel(
        lambda: pull_images(phone, "front", LOCAL_PULL_DIR),
        lambda: pull_images(tablet, "back", LOCAL_PULL_DIR),
    )

    phone_files = phone_files or []
    tablet_files = tablet_files or []

    print(f"  Phone images: {len(phone_files)}, Tablet images: {len(tablet_files)}")

    if len(phone_files) < 2 or len(tablet_files) < 2:
        print("  [ERROR] Expected at least 2 captures per device")
        print(f"  Phone files: {phone_files}")
        print(f"  Tablet files: {tablet_files}")
        return None

    images = rename_captures(phone_files, tablet_files, LOCAL_PULL_DIR)
    print(f"  Renamed: {list(images.keys())}")

    result = upload_quad_scan(images, CUSTOMER_ID, MUSCLE_GROUP, CAMERA_DISTANCE_CM)
    return result


# --- Main Flow ---

def main():
    parser = argparse.ArgumentParser(description="Dual-device muscle scan orchestrator")
    parser.add_argument("--phone", default=PHONE_SERIAL, help="Phone ADB serial")
    parser.add_argument("--tablet", default=TABLET_SERIAL, help="Tablet ADB serial (WiFi)")
    parser.add_argument("--muscle", default=MUSCLE_GROUP, help="Muscle group to scan")
    parser.add_argument("--distance", type=int, default=CAMERA_DISTANCE_CM, help="Camera distance in cm")
    parser.add_argument("--customer", type=int, default=CUSTOMER_ID, help="Customer ID")
    args = parser.parse_args()

    global MUSCLE_GROUP, CAMERA_DISTANCE_CM, CUSTOMER_ID
    MUSCLE_GROUP = args.muscle
    CAMERA_DISTANCE_CM = args.distance
    CUSTOMER_ID = args.customer

    print("=" * 60)
    print("  DUAL-DEVICE MUSCLE SCAN")
    print(f"  Muscle: {MUSCLE_GROUP} | Distance: {CAMERA_DISTANCE_CM}cm")
    print(f"  Phone: {args.phone} | Tablet: {args.tablet}")
    print("=" * 60)

    # Phase 0: Setup
    if not setup_all(args.phone, args.tablet):
        print("\n[FAILED] Device setup failed. Check connections and retry.")
        sys.exit(1)

    # Phase 1: Front + Back capture
    print("\n=== PHASE 1: FRONT + BACK ===")
    speak("Stand still. Capturing front and back.")
    print("  >>> STAND STILL — CAPTURING FRONT + BACK <<<")
    capture_phase(args.phone, args.tablet, "FRONT + BACK")

    # Phase 2: Rotation
    print("\n=== PHASE 2: ROTATE ===")
    print("  >>> TURN 90 DEGREES NOW <<<")
    speak("Turn 90 degrees now")
    time.sleep(5)

    # Phase 3: Left + Right side capture
    print("\n=== PHASE 3: LEFT + RIGHT SIDES ===")
    speak("Stand still. Capturing sides.")
    print("  >>> STAND STILL — CAPTURING SIDES <<<")
    capture_phase(args.phone, args.tablet, "LEFT + RIGHT SIDES")

    # Phase 4: Collect & Upload
    result = collect_and_upload(args.phone, args.tablet)

    # Phase 5: Results
    print("\n=== PHASE 5: RESULTS ===")
    if result and result.get("status") == "success":
        print(f"  Volume:        {result.get('volume_cm3', 'N/A')} cm3")
        if result.get("volume_front_cm3"):
            print(f"    Front pair:  {result['volume_front_cm3']} cm3")
        if result.get("volume_back_cm3"):
            print(f"    Back pair:   {result['volume_back_cm3']} cm3")
        print(f"  Circumference: {result.get('circumference_cm', 'N/A')} cm")
        print(f"  Shape:         {result.get('shape_grade', 'N/A')} ({result.get('shape_score', 'N/A')}/100)")
        print(f"  Growth:        {result.get('growth_pct', 'N/A')}%")
        print(f"  Calibrated:    {result.get('calibrated', False)}")
        speak("Scan complete. Check results on screen.")
    else:
        msg = result.get("message", "Unknown error") if result else "No result"
        print(f"  [FAILED] {msg}")
        speak("Scan failed. Check the terminal.")

    print("\n" + "=" * 60)
    print("  SCAN COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
