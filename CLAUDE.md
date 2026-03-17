# Muscle Tracker — Agent Orientation

## What This Is
A fitness / body-composition tracking system.
- **Flutter companion app** (Android): runs on two devices (Samsung A24 + Huawei MatePad Pro), captures photos and video scans, uploads to server.
- **py4web server** (`web_app/`): REST API for scan upload, muscle volume analysis, body profile, 3D mesh generation.
- **Core vision pipeline** (`core/`): OpenCV / MediaPipe image processing, mesh generation, UV unwrapping, texture projection, silhouette matching.
- **3D body model viewer** (`web_app/static/viewer3d/`): Three.js r160, shows GLB body mesh, click-regions, sliders.

---

## Architecture

```
companion_app/          Flutter app (1900+ lines in main.dart)
core/
  body_segmentation.py  MediaPipe / GrabCut muscle ROI detection
  vision_medical.py     Muscle volume measurement from images
  smpl_fitting.py       Build 3D body mesh from 24 measurements
  uv_unwrap.py          Cylindrical UV atlas projection
  texture_projector.py  Camera photos → UV texture (vectorized)
  silhouette_extractor.py  Body contour from scan image → mm coords
  silhouette_matcher.py    Iterative mesh deformation to match silhouettes
  mesh_reconstruction.py   OBJ / GLB export (smooth normals, UVs, textures)
  frame_selector.py     Pick sharpest frame from burst capture
web_app/
  controllers.py        2200+ line REST API — grep before reading
  models.py             py4web DAL schema
  static/viewer3d/      Three.js viewer files
scripts/
  gtddebug.py           One-command dual-device scan CLI
  dual_captures/        Pulled JPEG images from devices
meshes/                 Generated GLB / OBJ files
uploads/                Temp images for API processing
```

---

## Key API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/login` | POST | Auth → JWT token |
| `/api/customer/<id>/body_model` | POST | Build GLB (+ optional images for silhouette + texture) |
| `/api/customer/<id>/body_profile` | POST | Update 24 body measurements |
| `/api/mesh/<id>.glb` | GET | Serve GLB for viewer |
| `/api/upload_quad_scan/<id>` | POST | 4-image dual scan upload |
| `/api/upload_scan/<id>` | POST | 2-image standard scan upload |

Viewer URL: `http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/api/mesh/<id>.glb`

---

## Quick-Start Commands

```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe

# Start server
cd C:/Users/MiEXCITE/Projects/muscle_tracker
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps \
  --host 0.0.0.0 --port 8000 > server.log 2>&1 &

# Check server
curl -s http://localhost:8000/web_app/api/login -X POST \
  -H "Content-Type: application/json" -d '{"email":"demo@muscle.com"}'

# Quick mesh test (no server needed)
$PY -c "from core.smpl_fitting import build_body_mesh; m=build_body_mesh(); print(m['num_vertices'], m['num_faces'])"

# Full dual scan + 3D body model
python scripts/gtddebug.py body3d --distance 100 --open

# Standard muscle scan
python scripts/gtddebug.py full --muscle quadricep --distance 100
```

---

## Devices

| Device | Serial | WiFi | Screen | SDK |
|---|---|---|---|---|
| Samsung A24 | `R58W41RF6ZK` | `192.168.100.8:5555` | 1080×2340 | 36 |
| MatePad Pro | — | `192.168.100.33:5555` | 1600×2560 | 29 |

Server: `192.168.100.16:8000`
Demo user: `demo@muscle.com` / `demo123`  Customer ID: 1

---

## Known Gotchas

- **py4web does NOT hot-reload** `core/*.py` or `web_app/*.py` — must kill and restart server after changes.
- **Default `python` in Git Bash is Inkscape's Python** — always use the full path `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`.
- **Do not `flutter run`** — use `flutter build apk --debug` then `adb install`.
- **Do not `adb push` in Git Bash** — path mangling breaks `/sdcard/` paths; use `adb exec-out` for binary files.
- **MatePad ADB install** — must uninstall before install (no `-r`), and disable package verifier first.
- **JWT secret rotates on server restart** — existing tokens invalidate; get a new token after restart.
- **Auto-capture fires once on app init** — to re-scan, force-stop + restart app via ADB.
- **`controllers.py` is 2200+ lines** — always `grep` before reading; key targets: `generate_body_model` (~2126), `upload_quad_scan`, `upload_scan`.
- **`main.dart` is 1900+ lines** — always `grep` first.

---

## 3D Pipeline Summary

`build_body_mesh(profile)` → `smpl_fitting.py`
→ `compute_uvs(...)` → `uv_unwrap.py`
→ `extract_silhouette(image, dist_cm)` → `silhouette_extractor.py`
→ `fit_mesh_to_silhouettes(verts, faces, views)` → `silhouette_matcher.py`
→ `project_texture(verts, faces, uvs, cam_views)` → `texture_projector.py`
→ `export_glb(verts, faces, path, uvs=..., texture_image=...)` → `mesh_reconstruction.py`

All wired together in `generate_body_model` in `controllers.py`.
