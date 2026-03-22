"""
agent_device.py — Device automation bridge for gtd3d.

Wraps Flutter build, ADB install/launch, screenshot capture, logcat parsing,
and GTDdebug vision tools into single-command workflows.

Usage:
    PY=C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
    $PY scripts/agent_device.py deploy                    # Build + install + screenshot + logcat
    $PY scripts/agent_device.py deploy --skip-build       # Install only (faster)
    $PY scripts/agent_device.py deploy --device matpad    # Deploy to MatePad
    $PY scripts/agent_device.py status                    # Quick screenshot + error check
    $PY scripts/agent_device.py check-server              # Test py4web endpoints
    $PY scripts/agent_device.py diff --before prev.png    # Visual before/after
    $PY scripts/agent_device.py logs                      # Flutter-filtered logcat
    $PY scripts/agent_device.py devices                   # List devices + connection status
    $PY scripts/agent_device.py full-cycle                # Everything in one call
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPANION_APP = PROJECT_ROOT / "companion_app"
APK_PATH = COMPANION_APP / "build" / "app" / "outputs" / "flutter-apk" / "app-debug.apk"
CAPTURES_DIR = PROJECT_ROOT / "captures" / "device"
PROFILES_PATH = Path(__file__).resolve().parent / "device_profiles.json"

FLUTTER = "C:/Users/MiEXCITE/development/flutter/bin/flutter.bat"
ADB = "C:/Android/platform-tools/adb.exe"
PY = "C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe"
GTDDEBUG = f"{PY} C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py"
SERVER_LOCAL = "http://localhost:8000/web_app"


# ═══════════════════════════════════════════════════════════════════════════════
#  Device Profile Management
# ═══════════════════════════════════════════════════════════════════════════════

def _load_profiles():
    """Load device_profiles.json."""
    with open(PROFILES_PATH) as f:
        return json.load(f)


def _load_profile(device_key=None):
    """Load a specific device profile. Returns (profile_dict, config)."""
    cfg = _load_profiles()
    key = device_key or cfg.get("default_device", "a24")
    if key not in cfg["devices"]:
        return None, cfg
    profile = cfg["devices"][key]
    profile["_key"] = key
    profile.setdefault("platform", "android")
    profile.setdefault("quirks", [])
    profile.setdefault("install_flags", [])
    return profile, cfg


def _resolve_device(profile):
    """Find a working ADB target for the device. Returns target string or None."""
    if profile.get("platform") != "android":
        return None

    # Try WiFi first
    wifi_target = None
    if profile.get("wifi_ip") and profile.get("adb_port"):
        wifi_target = f"{profile['wifi_ip']}:{profile['adb_port']}"
        rc = _run_raw_adb("-s", wifi_target, "get-state")
        if rc[2] == 0 and "device" in rc[0]:
            return wifi_target
        # Try connecting
        rc = _run_raw_adb("connect", wifi_target)
        if rc[2] == 0 and ("connected" in rc[0] or "already" in rc[0]):
            time.sleep(1)
            rc2 = _run_raw_adb("-s", wifi_target, "get-state")
            if rc2[2] == 0 and "device" in rc2[0]:
                return wifi_target

    # Try USB serial
    if profile.get("serial"):
        rc = _run_raw_adb("-s", profile["serial"], "get-state")
        if rc[2] == 0 and "device" in rc[0]:
            return profile["serial"]

    # Scan connected devices for matching serial
    rc = _run_raw_adb("devices")
    if rc[2] == 0 and profile.get("serial"):
        for line in rc[0].splitlines():
            if profile["serial"] in line and "device" in line:
                return profile["serial"]

    # Last resort: try wifi connect one more time with fresh IP
    if wifi_target:
        _run_raw_adb("connect", wifi_target)
        time.sleep(2)
        rc = _run_raw_adb("-s", wifi_target, "get-state")
        if rc[2] == 0 and "device" in rc[0]:
            return wifi_target

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Low-level helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _timestamp():
    return time.strftime("%Y%m%d_%H%M%S")


def _run_raw_adb(*args, timeout=30):
    """Run ADB command, return (stdout, stderr, returncode)."""
    cmd = [ADB] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return "", str(e), 1


def _run_adb(target, *args, timeout=30):
    """Run ADB command against a specific device target."""
    return _run_raw_adb("-s", target, *args, timeout=timeout)


def _run_flutter(*args, timeout=300):
    """Run Flutter command in companion_app dir."""
    cmd = [FLUTTER] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(COMPANION_APP), timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "Flutter build timed out", 1
    except FileNotFoundError:
        return "", f"Flutter not found at {FLUTTER}", 1


def _run_gtddebug(cmd, *args):
    """Run GTDdebug command, parse JSON output."""
    full_cmd = f"{GTDDEBUG} {cmd} {' '.join(args)} --json"
    try:
        r = subprocess.run(full_cmd, capture_output=True, text=True,
                          timeout=60, shell=True)
        if r.returncode == 0 and r.stdout.strip():
            # Find JSON in output (may have non-JSON prefix)
            for line in r.stdout.strip().splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
            # Try full output
            try:
                return json.loads(r.stdout.strip())
            except json.JSONDecodeError:
                pass
        return {"status": "error", "message": r.stderr or r.stdout or "no output"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _screenshot(target, name=None, device_key="default"):
    """Take screenshot via ADB exec-out, save to captures/device/{device_key}/."""
    out_dir = CAPTURES_DIR / device_key
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{name or 'screen'}_{_timestamp()}.png"
    out_path = out_dir / fname

    cmd = [ADB, "-s", target, "exec-out", "screencap", "-p"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15)
        if r.returncode == 0 and len(r.stdout) > 1000:
            out_path.write_bytes(r.stdout)
            return str(out_path)
    except Exception:
        pass
    return None


def _parse_logcat(text):
    """Parse logcat text for Flutter errors, crashes, and warnings."""
    flutter_errors = []
    dart_exceptions = []
    warnings = []
    crash_log = None

    lines = text.splitlines()
    crash_lines = []
    in_crash = False

    for line in lines:
        # Fatal crash
        if "FATAL EXCEPTION" in line or "AndroidRuntime" in line:
            in_crash = True
            crash_lines.append(line)
            continue
        if in_crash:
            if line.strip() and not line.startswith("-----"):
                crash_lines.append(line)
            else:
                in_crash = False

        # Flutter errors
        if "E/flutter" in line:
            flutter_errors.append(line.strip())

        # Dart exceptions
        if "Unhandled Exception" in line or "DartError" in line:
            dart_exceptions.append(line.strip())

        # Warnings
        if "W/flutter" in line:
            warnings.append(line.strip())

    if crash_lines:
        crash_log = "\n".join(crash_lines)

    return {
        "flutter_errors": flutter_errors[-20:],  # last 20
        "dart_exceptions": dart_exceptions[-10:],
        "warnings": warnings[-10:],
        "crash_log": crash_log,
    }


def _install_apk(target, profile, apk_path):
    """Install APK with device-specific quirk handling."""
    cfg = _load_profiles()
    package = cfg.get("app_package", "com.example.companion_app")
    quirks = profile.get("quirks", [])
    errors = []

    # Quirk: disable package verifier (MatePad)
    if "disable_package_verifier" in quirks:
        _run_adb(target, "shell", "settings", "put", "global",
                "verifier_verify_adb_installs", "0")

    # Quirk: must uninstall before install (MatePad)
    if "uninstall_before_install" in quirks:
        _run_adb(target, "uninstall", package)
        time.sleep(1)

    # Install with device-specific flags (120s timeout for WiFi ADB)
    flags = profile.get("install_flags", [])
    install_args = ["install"] + flags + [str(apk_path)]
    stdout, stderr, rc = _run_adb(target, *install_args, timeout=120)

    if rc != 0:
        # Retry: uninstall then clean install
        if "INSTALL_FAILED" in (stdout + stderr) or "timed out" in (stdout + stderr):
            errors.append(f"First install failed: {stdout} {stderr}")
            _run_adb(target, "uninstall", package, timeout=15)
            time.sleep(1)
            stdout2, stderr2, rc2 = _run_adb(target, "install", str(apk_path), timeout=120)
            if rc2 == 0:
                return {"status": "ok", "retry": True, "errors": errors}
            return {"status": "error",
                    "message": f"Install failed after retry: {stdout2} {stderr2}",
                    "errors": errors}
        return {"status": "error", "message": f"{stdout} {stderr}"}

    return {"status": "ok", "retry": False, "errors": []}


# ═══════════════════════════════════════════════════════════════════════════════
#  Commands
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_deploy(device_key=None, skip_build=False, wait_secs=10):
    """Build APK -> install -> launch -> screenshot -> check logcat."""
    t0 = time.time()
    result = {"command": "deploy", "status": "ok", "steps": {}, "errors": []}

    profile, cfg = _load_profile(device_key)
    if not profile:
        return {"command": "deploy", "status": "error",
                "message": f"Unknown device: {device_key}"}
    if profile.get("platform") != "android":
        return {"command": "deploy", "status": "error",
                "message": f"{profile['name']} is {profile.get('platform')} — Android only for now"}

    result["device"] = profile["name"]
    package = cfg.get("app_package", "com.example.companion_app")
    activity = cfg.get("app_activity", ".MainActivity")

    # Step 1: Resolve device
    target = _resolve_device(profile)
    if not target:
        result["status"] = "error"
        result["errors"].append(f"Cannot connect to {profile['name']} "
                               f"(WiFi: {profile.get('wifi_ip')}, Serial: {profile.get('serial')})")
        result["steps"]["connect"] = {"status": "error"}
        return result
    result["steps"]["connect"] = {"status": "ok", "target": target}

    # Step 2: Build APK
    if skip_build:
        result["steps"]["build"] = {"status": "skipped"}
        if not APK_PATH.exists():
            result["status"] = "error"
            result["errors"].append(f"No APK found at {APK_PATH}")
            return result
    else:
        stdout, stderr, rc = _run_flutter("build", "apk", "--debug",
                                           "--target-platform", "android-arm64")
        if rc != 0:
            # Extract dart error from stderr
            dart_err = ""
            for line in (stderr + "\n" + stdout).splitlines():
                if "Error:" in line or "error:" in line or "lib/" in line:
                    dart_err += line + "\n"
            result["steps"]["build"] = {"status": "error", "error": dart_err or stderr}
            result["status"] = "error"
            result["errors"].append(f"Build failed: {dart_err[:500]}")
            result["elapsed_s"] = round(time.time() - t0, 1)
            return result
        result["steps"]["build"] = {"status": "ok", "apk_path": str(APK_PATH)}

    # Step 3: Force-stop existing app
    _run_adb(target, "shell", "am", "force-stop", package)

    # Step 4: Install
    install_result = _install_apk(target, profile, APK_PATH)
    result["steps"]["install"] = install_result
    if install_result["status"] != "ok":
        result["status"] = "error"
        result["errors"].append(install_result.get("message", "Install failed"))
        result["elapsed_s"] = round(time.time() - t0, 1)
        return result

    # Step 5: Launch
    stdout, stderr, rc = _run_adb(target, "shell", "am", "start",
                                   "-n", f"{package}/{activity}")
    if rc != 0 or "Error" in stdout:
        result["steps"]["launch"] = {"status": "error", "error": stdout + stderr}
        result["errors"].append(f"Launch failed: {stdout}")
    else:
        result["steps"]["launch"] = {"status": "ok"}

    # Step 6: Wait for app to stabilize
    time.sleep(wait_secs)

    # Step 7: Screenshot
    screenshot_path = _screenshot(target, "deploy", profile["_key"])
    result["steps"]["screenshot"] = {
        "status": "ok" if screenshot_path else "error",
        "path": screenshot_path
    }
    result["screenshot_path"] = screenshot_path

    # Step 8: Logcat check
    stdout, _, _ = _run_adb(target, "logcat", "-d", "-t", "200")
    logcat_result = _parse_logcat(stdout)
    result["steps"]["logcat"] = {"status": "ok", **logcat_result}
    if logcat_result["crash_log"]:
        result["errors"].append("App crashed!")
        result["crash_log"] = logcat_result["crash_log"]
        result["status"] = "error"
    elif logcat_result["flutter_errors"]:
        result["errors"].extend(logcat_result["flutter_errors"][:5])

    result["elapsed_s"] = round(time.time() - t0, 1)
    return result


def cmd_status(device_key=None):
    """Quick screenshot + error check without building."""
    t0 = time.time()
    profile, cfg = _load_profile(device_key)
    if not profile:
        return {"command": "status", "status": "error", "message": f"Unknown device: {device_key}"}

    target = _resolve_device(profile)
    if not target:
        return {"command": "status", "status": "error",
                "message": f"Cannot connect to {profile['name']}"}

    package = cfg.get("app_package", "com.example.companion_app")

    # Check if app is running
    stdout, _, _ = _run_adb(target, "shell", "pidof", package)
    app_running = bool(stdout.strip())

    # Screenshot
    screenshot_path = _screenshot(target, "status", profile["_key"])

    # Recent logcat
    stdout, _, _ = _run_adb(target, "logcat", "-d", "-t", "100")
    logcat = _parse_logcat(stdout)

    return {
        "command": "status",
        "status": "ok",
        "device": profile["name"],
        "app_running": app_running,
        "screenshot_path": screenshot_path,
        "flutter_errors": logcat["flutter_errors"],
        "crash_log": logcat["crash_log"],
        "elapsed_s": round(time.time() - t0, 1),
    }


def cmd_check_server():
    """Verify py4web is running and test key API endpoints."""
    t0 = time.time()
    endpoints = {}
    errors = []
    token = None

    # Test login
    try:
        data = json.dumps({"email": "demo@muscle.com", "password": "demo123"}).encode()
        req = urllib.request.Request(
            f"{SERVER_LOCAL}/api/login", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            ok = body.get("status") == "success"
            token = body.get("token")
            endpoints["login"] = {"status_code": resp.status, "ok": ok}
    except Exception as e:
        endpoints["login"] = {"status_code": 0, "ok": False, "error": str(e)}
        errors.append(f"Login failed: {e}")

    # Test skin_regions (needs auth)
    try:
        req = urllib.request.Request(
            f"{SERVER_LOCAL}/api/customer/1/skin_regions",
            headers={"Authorization": f"Bearer {token}"} if token else {})
        with urllib.request.urlopen(req, timeout=5) as resp:
            endpoints["skin_regions"] = {"status_code": resp.status, "ok": resp.status == 200}
    except Exception as e:
        endpoints["skin_regions"] = {"status_code": 0, "ok": False, "error": str(e)}

    # Test mesh serve
    try:
        req = urllib.request.Request(f"{SERVER_LOCAL}/api/mesh/1.glb")
        with urllib.request.urlopen(req, timeout=5) as resp:
            endpoints["mesh"] = {"status_code": resp.status, "ok": True}
    except urllib.error.HTTPError as e:
        endpoints["mesh"] = {"status_code": e.code, "ok": e.code == 404}  # 404 is ok (no mesh yet)
    except Exception as e:
        endpoints["mesh"] = {"status_code": 0, "ok": False, "error": str(e)}

    server_running = endpoints.get("login", {}).get("ok", False)
    return {
        "command": "check-server",
        "status": "ok" if server_running else "error",
        "server_running": server_running,
        "endpoints": endpoints,
        "errors": errors,
        "elapsed_s": round(time.time() - t0, 1),
    }


def cmd_diff(device_key=None, before_path=None):
    """Before/after visual comparison using GTDdebug agent-diff."""
    t0 = time.time()
    profile, _ = _load_profile(device_key)
    if not profile:
        return {"command": "diff", "status": "error", "message": f"Unknown device: {device_key}"}

    target = _resolve_device(profile)
    if not target:
        return {"command": "diff", "status": "error",
                "message": f"Cannot connect to {profile['name']}"}

    # Take "after" screenshot
    after_path = _screenshot(target, "diff_after", profile["_key"])
    if not after_path:
        return {"command": "diff", "status": "error", "message": "Screenshot failed"}

    # Find "before" — use provided path or most recent deploy screenshot
    if not before_path:
        dev_dir = CAPTURES_DIR / profile["_key"]
        if dev_dir.exists():
            pngs = sorted(dev_dir.glob("deploy_*.png"), key=lambda p: p.stat().st_mtime)
            if pngs:
                before_path = str(pngs[-1])

    if not before_path:
        return {"command": "diff", "status": "error",
                "message": "No before screenshot found. Run deploy first or pass --before."}

    # Call GTDdebug agent-diff
    gtd_result = _run_gtddebug("agent-diff", before_path, after_path)

    return {
        "command": "diff",
        "status": "ok",
        "before": before_path,
        "after": after_path,
        "gtddebug_result": gtd_result,
        "elapsed_s": round(time.time() - t0, 1),
    }


def cmd_baseline(device_key=None, action="save", label="gtd3d"):
    """Save or check visual regression baseline via GTDdebug vision-golden."""
    t0 = time.time()
    profile, _ = _load_profile(device_key)
    if not profile:
        return {"command": "baseline", "status": "error", "message": f"Unknown device: {device_key}"}

    target = _resolve_device(profile)
    if not target:
        return {"command": "baseline", "status": "error",
                "message": f"Cannot connect to {profile['name']}"}

    screenshot_path = _screenshot(target, f"baseline_{action}", profile["_key"])
    if not screenshot_path:
        return {"command": "baseline", "status": "error", "message": "Screenshot failed"}

    if action == "save":
        gtd_result = _run_gtddebug("vision-golden", "save", label, screenshot_path)
    else:
        gtd_result = _run_gtddebug("vision-golden", "check", label, screenshot_path)

    return {
        "command": "baseline",
        "status": "ok",
        "action": action,
        "label": label,
        "screenshot_path": screenshot_path,
        "gtddebug_result": gtd_result,
        "elapsed_s": round(time.time() - t0, 1),
    }


def cmd_logs(device_key=None, seconds=10):
    """Get Flutter-filtered logcat."""
    t0 = time.time()
    profile, _ = _load_profile(device_key)
    if not profile:
        return {"command": "logs", "status": "error", "message": f"Unknown device: {device_key}"}

    target = _resolve_device(profile)
    if not target:
        return {"command": "logs", "status": "error",
                "message": f"Cannot connect to {profile['name']}"}

    # Get recent logcat lines (approximate: ~15 lines per second)
    count = max(50, seconds * 15)
    stdout, _, _ = _run_adb(target, "logcat", "-d", "-t", str(count))

    # Filter for Flutter/app-relevant lines
    relevant = []
    for line in stdout.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in ["flutter", "dart", "companion_app",
                                       "fatal", "androidruntime", "exception"]):
            relevant.append(line.strip())

    parsed = _parse_logcat(stdout)

    return {
        "command": "logs",
        "status": "ok",
        "device": profile["name"],
        "total_lines": len(stdout.splitlines()),
        "relevant_lines": relevant[-50:],
        **parsed,
        "elapsed_s": round(time.time() - t0, 1),
    }


def cmd_devices():
    """List known device profiles and their connection status."""
    t0 = time.time()
    cfg = _load_profiles()
    devices = []

    for key, dev in cfg["devices"].items():
        entry = {
            "key": key,
            "name": dev.get("name", key),
            "platform": dev.get("platform", "android"),
            "connected": False,
            "adb_target": None,
            "is_default": key == cfg.get("default_device"),
        }

        if dev.get("platform") == "android":
            dev["_key"] = key
            target = _resolve_device(dev)
            if target:
                entry["connected"] = True
                entry["adb_target"] = target

        devices.append(entry)

    return {
        "command": "devices",
        "status": "ok",
        "devices": devices,
        "default": cfg.get("default_device"),
        "elapsed_s": round(time.time() - t0, 1),
    }


def cmd_full_cycle(device_key=None, skip_build=False):
    """Full automation: check-server -> deploy -> aggregate pass/fail."""
    t0 = time.time()

    # Check server (non-blocking — warn but continue)
    server = cmd_check_server()

    # Deploy
    deploy = cmd_deploy(device_key=device_key, skip_build=skip_build)

    # Aggregate
    all_errors = []
    if not server.get("server_running"):
        all_errors.append("Server not running")
    all_errors.extend(deploy.get("errors", []))

    status = "pass" if deploy.get("status") == "ok" else "fail"
    summary_parts = []
    if server.get("server_running"):
        summary_parts.append("server OK")
    else:
        summary_parts.append("server DOWN")
    if deploy.get("status") == "ok":
        summary_parts.append("deploy OK")
    else:
        summary_parts.append(f"deploy FAILED: {'; '.join(deploy.get('errors', [])[:2])}")

    return {
        "command": "full-cycle",
        "status": status,
        "device": deploy.get("device", "unknown"),
        "server": server,
        "deploy": deploy,
        "screenshot_path": deploy.get("screenshot_path"),
        "errors": all_errors,
        "summary": " | ".join(summary_parts),
        "elapsed_s": round(time.time() - t0, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="gtd3d device automation")
    sub = parser.add_subparsers(dest="command")

    # deploy
    p = sub.add_parser("deploy", help="Build + install + launch + screenshot + logcat")
    p.add_argument("--device", "-d", help="Device profile key (default: from profiles)")
    p.add_argument("--skip-build", action="store_true", help="Skip flutter build")
    p.add_argument("--wait", type=int, default=10, help="Seconds to wait after launch")

    # status
    p = sub.add_parser("status", help="Quick screenshot + error check")
    p.add_argument("--device", "-d")

    # check-server
    sub.add_parser("check-server", help="Verify py4web + test endpoints")

    # diff
    p = sub.add_parser("diff", help="Before/after visual comparison")
    p.add_argument("--device", "-d")
    p.add_argument("--before", help="Path to before screenshot")

    # baseline
    p = sub.add_parser("baseline", help="Save or check visual regression baseline")
    p.add_argument("action", choices=["save", "check"], nargs="?", default="save")
    p.add_argument("--device", "-d")
    p.add_argument("--label", default="gtd3d")

    # logs
    p = sub.add_parser("logs", help="Flutter-filtered logcat")
    p.add_argument("--device", "-d")
    p.add_argument("--seconds", type=int, default=10)

    # devices
    sub.add_parser("devices", help="List devices + connection status")

    # full-cycle
    p = sub.add_parser("full-cycle", help="check-server -> deploy -> report")
    p.add_argument("--device", "-d")
    p.add_argument("--skip-build", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "deploy":
        result = cmd_deploy(args.device, args.skip_build, args.wait)
    elif args.command == "status":
        result = cmd_status(args.device)
    elif args.command == "check-server":
        result = cmd_check_server()
    elif args.command == "diff":
        result = cmd_diff(args.device, args.before)
    elif args.command == "baseline":
        result = cmd_baseline(args.device, args.action, args.label)
    elif args.command == "logs":
        result = cmd_logs(args.device, args.seconds)
    elif args.command == "devices":
        result = cmd_devices()
    elif args.command == "full-cycle":
        result = cmd_full_cycle(args.device, args.skip_build)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("status") in ("ok", "pass") else 1)


if __name__ == "__main__":
    main()
