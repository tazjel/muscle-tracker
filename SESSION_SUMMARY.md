# GTD3D Studio Upgrade - Session Summary (2026-04-07)

## DONE
- **APK Extraction**: Analyzed IP Webcam Pro for feature parity.
- **Companion App (v3.0.0)**:
    - Integrated `shelf` web server.
    - Implemented `/video` (MJPEG), `/sensors` (JSON), and `/control` (Remote) endpoints.
    - Defaulted to back camera for high-res capture.
    - Metadata burst capture logic added.
- **Desktop Studio (Cinematic v5.5)**:
    - Premium dashboard UI with sensor overlays.
    - Sidebar for recent capture previews.
    - Automated Scan Sequence (Front/Side/Back).
    - Server-side processing trigger for MPFB2 pipeline.
    - **FIXED**: Studio 500 error resolved by correcting py4web `URL()` positional syntax.
    - **FIXED**: Sensors/Controls bypass CORS via server-side proxying (`api/studio/sensors`, `api/studio/control`).
- **Windows & Py4web Compatibility**:
    - Unified database connection in `models.py` and `common.py`.
    - Standardized absolute path resolution using `PROJECT_ROOT` and `_abs_path`.
    - Fixed `Auth` import path for Windows branch.
- **Tools**:
    - `scripts/agent_device.py`: Huawei/MatePad auto-clicker for ADB installs.
    - `scripts/agent_browser.py`: Added `studio-audit` for Playwright validation.
    - Fixed `apps/_default` junction for root routing.

## COMMANDS & DISCOVERIES
- **Run Server**: `py4web run --port 8000 apps`
- **Audit Studio**: `python scripts/agent_browser.py studio-audit --phone-ip 192.168.100.2`
- **Discovery**: Py4web on Windows requires `Auth` from `py4web.utils.auth`.
- **Discovery**: Path parameters in py4web templates MUST be positional: `URL('action', id)`.
- **Discovery**: SQLite URIs on Windows need 3 slashes: `sqlite:///C:/path/to/db`.

## PENDING
- **End-to-End Test**: Verify "Capture -> Save -> Process -> View" cycle with physical MatePad.
- **Phase 4**: Implement live mesh morphing based on sensor distance.

## CONNECTION DATA
- **MatePad**: 192.168.100.2 (Port 8080)
- **Desktop**: 192.168.100.7 (Port 8000)
