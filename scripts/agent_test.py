"""
agent_test.py — Server API + Viewer test suite for gtd3d.

Usage:
    PY=C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
    $PY scripts/agent_test.py server        # Test py4web API endpoints
    $PY scripts/agent_test.py viewer        # Test 3D viewer in browser
    $PY scripts/agent_test.py skin-upload   # Test skin region upload
    $PY scripts/agent_test.py full          # Run all tests
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PY = "C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe"
SERVER = "http://localhost:8000/web_app"
VIEWER_URL = f"http://localhost:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/1.glb&customer_id=1"


def _http(method, path, data=None, headers=None, timeout=5):
    """Simple HTTP helper using urllib. Returns (status_code, body_dict, error)."""
    url = f"{SERVER}{path}" if path.startswith("/") else path
    hdrs = headers or {}
    body = None
    if data:
        body = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json")

    try:
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw), None
            except json.JSONDecodeError:
                return resp.status, {"raw": raw[:200].decode(errors="replace")}, None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body, None
    except Exception as e:
        return 0, {}, str(e)


def cmd_server():
    """Test py4web health + core API endpoints."""
    t0 = time.time()
    tests = []
    token = None

    # Test 1: Login
    code, body, err = _http("POST", "/api/login",
                            data={"email": "demo@muscle.com", "password": "demo123"})
    ok = code == 200 and body.get("status") == "success"
    token = body.get("token") if ok else None
    tests.append({"name": "login", "ok": ok, "status_code": code,
                  "error": err or (None if ok else body.get("message"))})

    auth = {"Authorization": f"Bearer {token}"} if token else {}

    # Test 2: Body profile
    code, body, err = _http("GET", "/api/customer/1/body_profile", headers=auth)
    tests.append({"name": "body_profile", "ok": code == 200, "status_code": code, "error": err})

    # Test 3: Skin regions list
    code, body, err = _http("GET", "/api/customer/1/skin_regions", headers=auth)
    tests.append({"name": "skin_regions", "ok": code == 200, "status_code": code, "error": err})

    # Test 4: Mesh serve (404 OK if no mesh, 500 is bad)
    code, body, err = _http("GET", "/api/mesh/1.glb")
    tests.append({"name": "mesh_serve", "ok": code in (200, 404), "status_code": code, "error": err})

    passed = sum(1 for t in tests if t["ok"])
    failed = len(tests) - passed

    return {
        "command": "server",
        "status": "pass" if failed == 0 else "fail",
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "elapsed_s": round(time.time() - t0, 1),
    }


def cmd_viewer():
    """Load 3D viewer in browser, check console errors, verify scene loaded."""
    t0 = time.time()
    agent_browser = PROJECT_ROOT / "scripts" / "agent_browser.py"

    if not agent_browser.exists():
        return {"command": "viewer", "status": "error",
                "message": "agent_browser.py not found"}

    # Run browser audit
    try:
        r = subprocess.run(
            [PY, str(agent_browser), "audit", VIEWER_URL],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT))

        # Parse JSON output
        result = None
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass
        if not result:
            try:
                result = json.loads(r.stdout.strip())
            except json.JSONDecodeError:
                result = {"raw_output": r.stdout[:500]}

        console_errors = result.get("console_errors", [])
        screenshot_path = result.get("screenshot")

        return {
            "command": "viewer",
            "status": "pass" if not console_errors else "fail",
            "console_errors": console_errors,
            "screenshot_path": screenshot_path,
            "audit": result,
            "elapsed_s": round(time.time() - t0, 1),
        }
    except subprocess.TimeoutExpired:
        return {"command": "viewer", "status": "error", "message": "Browser audit timed out"}
    except Exception as e:
        return {"command": "viewer", "status": "error", "message": str(e)}


def cmd_skin_upload():
    """Test skin region upload API with a sample image."""
    t0 = time.time()

    # Find a sample image
    sample = None
    for d in [PROJECT_ROOT / "captures" / "skin_scan",
              PROJECT_ROOT / "captures",
              PROJECT_ROOT / "uploads"]:
        if d.exists():
            for ext in ("*.jpg", "*.png"):
                imgs = list(d.glob(ext))
                if imgs:
                    sample = imgs[0]
                    break
        if sample:
            break

    if not sample:
        return {"command": "skin-upload", "status": "skip",
                "message": "No sample image found in captures/ or uploads/"}

    # Get auth token
    _, body, _ = _http("POST", "/api/login",
                       data={"email": "demo@muscle.com", "password": "demo123"})
    token = body.get("token")
    if not token:
        return {"command": "skin-upload", "status": "error", "message": "Login failed"}

    # Upload via multipart (using urllib)
    import mimetypes
    boundary = "----AgentTestBoundary"
    content_type = mimetypes.guess_type(str(sample))[0] or "image/jpeg"

    body_parts = []
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(f'Content-Disposition: form-data; name="image"; filename="{sample.name}"\r\n'.encode())
    body_parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    body_parts.append(sample.read_bytes())
    body_parts.append(f"\r\n--{boundary}--\r\n".encode())

    multipart_body = b"".join(body_parts)
    url = f"{SERVER}/api/customer/1/skin_region/forearm"

    try:
        req = urllib.request.Request(url, data=multipart_body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("Authorization", f"Bearer {token}")

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            ok = result.get("status") == "success"
            return {
                "command": "skin-upload",
                "status": "pass" if ok else "fail",
                "upload_ok": ok,
                "status_code": resp.status,
                "response": result,
                "sample_image": str(sample),
                "elapsed_s": round(time.time() - t0, 1),
            }
    except Exception as e:
        return {"command": "skin-upload", "status": "error",
                "message": str(e), "elapsed_s": round(time.time() - t0, 1)}


def cmd_full():
    """Run all tests."""
    t0 = time.time()

    server = cmd_server()
    viewer = cmd_viewer()

    total_passed = server.get("passed", 0) + (1 if viewer.get("status") == "pass" else 0)
    total_failed = server.get("failed", 0) + (1 if viewer.get("status") not in ("pass", "error") else 0)

    status = "pass" if server.get("status") == "pass" and viewer.get("status") == "pass" else "fail"

    return {
        "command": "full",
        "status": status,
        "server": server,
        "viewer": viewer,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "elapsed_s": round(time.time() - t0, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="gtd3d API + viewer test suite")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("server", help="Test py4web API endpoints")
    sub.add_parser("viewer", help="Test 3D viewer in browser")
    sub.add_parser("skin-upload", help="Test skin region upload API")
    sub.add_parser("full", help="Run all tests")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "server":
        result = cmd_server()
    elif args.command == "viewer":
        result = cmd_viewer()
    elif args.command == "skin-upload":
        result = cmd_skin_upload()
    elif args.command == "full":
        result = cmd_full()
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("status") in ("ok", "pass", "skip") else 1)


if __name__ == "__main__":
    main()
