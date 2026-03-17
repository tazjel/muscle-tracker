# SONNET ROOM 3D TASKS — Phase 1: 3D Room + Phase 2: Human in Room

> **Date**: 2026-03-18
> **Goal**: Build 3D room from user-provided dimensions, capture wall/floor textures via phone camera, then place the existing 3D body model inside the room. Use a 1m reference rod for body scale calibration.

---

## RULES — READ BEFORE STARTING

1. **DO NOT read `companion_app/lib/main.dart` or `web_app/controllers.py` in full** — grep first, read ±40 lines around match
2. **Verify after each task group** — run the test command listed in each task
3. **Commit after each task group** (R1, R2, R3, etc.)
4. **Reuse existing patterns** — study `core/smpl_fitting.py` and `web_app/static/viewer3d/body_viewer.js` for mesh + viewer conventions
5. **Coordinate system**: Z-up, X=width, Y=length, mm units in core/ (convert from meters at API boundary)
6. **Server restart required** after any `core/*.py` or `web_app/*.py` change — py4web does NOT hot-reload
7. **DO NOT modify** these files (they work): `smpl_fitting.py`, `silhouette_matcher.py`, `mesh_reconstruction.py`, `body_viewer.js`

### Key paths
```
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
SERVER=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe
PROJECT=C:/Users/MiEXCITE/Projects/muscle_tracker
```

### Room dimensions (hardcoded dev defaults)
```
Width  (X) = 4.0 m = 4000 mm
Length (Y) = 6.0 m = 6000 mm
Height (Z) = 3.0 m = 3000 mm
```

---

## PHASE 1 — 3D Room

### R1: Room Mesh Builder (`core/room_builder.py`) — NEW FILE

**What to build**: A function that generates a box mesh (inside-facing normals) from room dimensions. The viewer will be INSIDE the box looking at the walls.

```python
def build_room_mesh(
    width_mm: float = 4000,   # X
    length_mm: float = 6000,  # Y
    height_mm: float = 3000,  # Z
) -> dict:
    """
    Returns {
        'vertices': np.float32 (N, 3),   # 8 corners (or 24 for per-face UVs)
        'faces': np.uint32 (12, 3),       # 6 faces × 2 triangles
        'normals': np.float32 (N, 3),     # inward-facing
        'uvs': np.float32 (N, 2),         # per-vertex UV for texture mapping
        'face_labels': list[str],         # ['floor','ceiling','wall_north','wall_south','wall_east','wall_west']
        'face_ranges': dict,              # {'floor': (0,1), 'ceiling': (2,3), ...} face index ranges
        'width_mm': float,
        'length_mm': float,
        'height_mm': float,
    }
    """
```

**Key details**:
- Use 24 vertices (4 per face) so each face gets its own UV 0→1 mapping — this allows independent textures per wall
- Normals point INWARD (viewer is inside the room)
- Floor is at Z=0, ceiling at Z=height_mm
- Wall convention: North = +Y wall, South = −Y wall, East = +X wall, West = −X wall
- Origin at room center floor: X ∈ [−width/2, +width/2], Y ∈ [−length/2, +length/2], Z ∈ [0, height]

**Also add** `export_room_glb(room_data, texture_map=None, output_path=None) -> str`:
- Similar to existing `export_glb` in `mesh_reconstruction.py` — study that for the GLB binary format
- `texture_map` is optional dict: `{'floor': 'path/to/floor.jpg', 'wall_north': 'path/to/north.jpg', ...}`
- When textures provided: embed as separate materials per face group (multi-material GLB)
- When no textures: use a neutral gray material per surface (floor darker, walls lighter, ceiling lightest)

**Test**:
```bash
$PY -c "from core.room_builder import build_room_mesh; r=build_room_mesh(); print(r['vertices'].shape, r['faces'].shape, list(r['face_ranges'].keys()))"
# Expected: (24, 3) (12, 3) ['floor', 'ceiling', 'wall_north', 'wall_south', 'wall_east', 'wall_west']
```

**Commit**: `feat(3d): room mesh builder with per-face UVs and GLB export`

---

### R2: Room Viewer (`web_app/static/viewer3d/room_viewer.js` + `room.html`) — NEW FILES

**What to build**: A Three.js viewer for the room, similar to `body_viewer.js` but camera starts INSIDE the room.

**Study `body_viewer.js` first** (grep for `OrbitControls`, `GLTFLoader`, `scene.add`) to reuse the same patterns.

**`room.html`** — minimal HTML (copy structure from `index.html`):
- Canvas container
- Buttons: "Wireframe", "Textured", "Place Human" (disabled until Phase 2)
- Room dimensions display
- Load `room_viewer.js` as ES module

**`room_viewer.js`**:
- Load GLB via GLTFLoader (same CDN imports as body_viewer.js)
- Camera starts at room center (0, 0, 1500mm = eye height), looking toward +Y (north wall)
- OrbitControls with **constrained bounds**: camera cannot leave the room box
  - `controls.maxDistance` = min(width, length) / 2
  - Keep camera inside room bounds in the render loop: clamp camera.position to room extents ± 100mm margin
- Ambient light + point light at ceiling center (simulates room lamp)
- Wireframe toggle
- **Click wall to select** — raycaster hit → highlight face, show "Apply Texture" button
- Receive texture via URL param or POST: `?room_model=/api/room/1.glb`

**Test**: Open `room.html?room_model=test` in browser — should show gray box interior with orbit controls.

**Commit**: `feat(3d): room viewer with interior camera and wall selection`

---

### R3: Room API Endpoints (`web_app/controllers.py`) — MODIFY

**Grep target**: Find the `generate_body_model` endpoint. Add the new room endpoints AFTER it.

**Add these endpoints** (follow the same JWT auth pattern as `generate_body_model`):

#### `POST /api/customer/<id>/room`
```
Create/update room from dimensions.
Body JSON: { "width_m": 4.0, "length_m": 6.0, "height_m": 3.0, "name": "Bedroom" }
→ build_room_mesh() → export_room_glb() → save to meshes/room_{customer_id}_{timestamp}.glb
→ return { "status": "ok", "room_id": <id>, "glb_url": "/api/room/<id>.glb", "dimensions": {...} }
```

#### `POST /api/room/<room_id>/texture`
```
Upload texture image for one surface.
Multipart: surface=floor|ceiling|wall_north|wall_south|wall_east|wall_west, image=<file>
→ save image to uploads/room_{room_id}_{surface}.jpg
→ rebuild GLB with new texture map → return { "status": "ok", "glb_url": "..." }
```

#### `GET /api/room/<id>.glb`
```
Serve room GLB file (same pattern as existing mesh GLB serving).
```

**DB table needed in `web_app/models.py`** — add BEFORE `db.commit()`:
```python
db.define_table('room_model',
    Field('customer_id', 'reference customer'),
    Field('name', 'string', length=128, default='My Room'),
    Field('width_mm', 'double'),
    Field('length_mm', 'double'),
    Field('height_mm', 'double'),
    Field('glb_path', 'string', length=512),
    Field('texture_floor', 'string', length=512),
    Field('texture_ceiling', 'string', length=512),
    Field('texture_wall_north', 'string', length=512),
    Field('texture_wall_south', 'string', length=512),
    Field('texture_wall_east', 'string', length=512),
    Field('texture_wall_west', 'string', length=512),
    Field('created_on', 'datetime', default=lambda: datetime.now()),
    Field('is_active', 'boolean', default=True),
)
```

**Test**:
```bash
# Start server, get token (see handoff), then:
curl -s -X POST http://localhost:8000/web_app/api/customer/1/room \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"width_m":4,"length_m":6,"height_m":3}' | python -m json.tool
# Expected: { "status": "ok", "room_id": 1, "glb_url": "/api/room/1.glb" }
```

**Commit**: `feat(api): room creation endpoint with GLB generation and texture upload`

---

### R4: Room Texture Capture in App (`companion_app/lib/main.dart`) — MODIFY

**Grep targets in main.dart**: `CameraScreen`, `_captureImage`, `scanMode`

**What to add**: A new scan mode `ROOM_TEXTURE` accessible from the camera screen.

**UI flow**:
1. Add a "Room" button/chip next to existing mode chips (AUTO/MANUAL/DUAL)
2. When ROOM mode active, show overlay text: "Point at FLOOR and tap" → capture → "Point at NORTH WALL and tap" → capture → ... cycle through all 6 surfaces
3. Each capture: save image locally, upload to `POST /api/room/{room_id}/texture` with surface label
4. After all 6 captured (or user skips), show "Room complete" → option to open room viewer URL

**Hardcode in dev mode**:
- `room_id = 1` (same dev customer)
- Surface capture order: `['floor', 'wall_north', 'wall_east', 'wall_south', 'wall_west', 'ceiling']`
- Allow skip (some surfaces like ceiling may be hard to photograph)

**Keep it simple**: Reuse existing camera infrastructure. No special framing needed — just point and tap for each surface.

**Test**: Build APK, capture floor texture on phone, verify texture appears at `uploads/room_1_floor.jpg` on server.

**Commit**: `feat(app): room texture capture mode with guided surface prompts`

---

### R5: Reference Rod for Scale Calibration (`core/reference_detector.py`) — NEW FILE

**What to build**: Detect a known-length object (1 meter rod) in a photo to compute accurate px→mm scale.

```python
def detect_reference_rod(
    image_path: str,
    known_length_mm: float = 1000,  # 1 meter rod
) -> dict | None:
    """
    Detect a vertical rod/stick in the image using edge detection + Hough lines.
    Returns {
        'px_per_mm': float,        # calibration factor
        'rod_length_px': float,    # detected rod length in pixels
        'rod_endpoints': tuple,    # ((x1,y1), (x2,y2)) in pixel coords
        'confidence': float,       # 0-1 detection confidence
    } or None if rod not detected.
    """
```

**Algorithm** (keep simple):
1. Convert to grayscale → Canny edge detection
2. HoughLinesP → find longest near-vertical line (angle within 10° of vertical)
3. If longest vertical line > 20% of image height → assume it's the rod
4. `px_per_mm = rod_length_px / known_length_mm`
5. Return None if no qualifying line found (fallback to distance-based calibration)

**Integration point**: The `analyze_muscle_growth` function in `vision_medical.py` already accepts `px_per_mm` — this gives a second calibration source alongside distance-based.

**Test**:
```bash
$PY -c "from core.reference_detector import detect_reference_rod; print(detect_reference_rod.__doc__[:50])"
# Just verify import works. Real testing needs a photo with the rod.
```

**Commit**: `feat(3d): reference rod detection for px→mm scale calibration`

---

## PHASE 2 — Human in Room

### R6: Composite Scene — Body Model Inside Room

**Modify `room_viewer.js`**: Enable the "Place Human" button.

When clicked:
1. Fetch body model GLB: `GET /api/mesh/{latest_mesh_id}.glb`
2. Load into same Three.js scene as room
3. Position body at room center floor: `body.position.set(0, 0, 0)` (feet on floor, Z-up)
4. Body model is in mm, room is in mm — scales match automatically
5. Make body draggable within room bounds (Three.js DragControls or simple click-to-place)
6. Add reference rod object: a thin cylinder mesh, 1000mm tall, placed near the body for visual scale check

**New API endpoint** in controllers.py:

#### `GET /api/customer/<id>/room_scene`
```
Return composite scene data:
{
  "room_glb_url": "/api/room/1.glb",
  "body_glb_url": "/api/mesh/5.glb",
  "body_height_mm": 1680,
  "reference_rod_mm": 1000,
  "room_dimensions_mm": { "width": 4000, "length": 6000, "height": 3000 }
}
```

**Visual reference rod in viewer**:
```javascript
// Add 1m rod as thin cylinder
const rodGeom = new THREE.CylinderGeometry(5, 5, 1000, 8);
const rodMat = new THREE.MeshStandardMaterial({ color: 0xff0000 });
const rod = new THREE.Mesh(rodGeom, rodMat);
rod.position.set(500, 0, 500); // 500mm to the right of body, standing on floor
scene.add(rod);
```

**Scale validation**: If body model height doesn't match the rod proportionally (body should be ~1.68× rod height), display a warning: "Body height (168cm) vs rod (100cm) — ratio 1.68:1 ✓"

**Test**: Open room viewer → click "Place Human" → body appears standing on floor beside red rod.

**Commit**: `feat(3d): composite room scene with body model and reference rod`

---

### R7: Rod-Calibrated Body Scan

**Modify** the scan workflow so when a reference rod is visible alongside the user:

1. In `web_app/controllers.py` `upload_scan` / `upload_quad_scan`:
   - After receiving image, call `detect_reference_rod(image_path)`
   - If rod detected with confidence > 0.6: use rod's `px_per_mm` instead of distance-based calibration
   - Store calibration source in scan record: `calibration_method = 'rod' | 'distance'`

2. In `companion_app/lib/main.dart`:
   - When ROOM mode has been set up, add instruction overlay: "Stand beside the 1m rod for best accuracy"
   - No code change needed for the actual calibration — that happens server-side

**Test**:
```bash
# Capture photo with user standing beside rod
# Upload via API
# Check response: calibration_method should be 'rod' if rod detected
```

**Commit**: `feat: rod-based calibration for body scans with reference object detection`

---

## EXECUTION ORDER

```
R1 → R2 → R3 → R4 → R5 → R6 → R7
 │         │         │         │
 │         │         │         └─ Rod calibration (needs R5 + R3)
 │         │         └─ Reference detector (independent)
 │         └─ API + DB (needs R1)
 └─ Viewer (needs R1)
```

**Parallelizable**: R1 and R5 have no dependencies — can be done simultaneously.
**Phase 1 complete at**: R4 done (room with textures, viewable)
**Phase 2 complete at**: R7 done (human in room, rod-calibrated)

---

## FILES TOUCHED (summary)

| Task | New Files | Modified Files |
|------|-----------|----------------|
| R1 | `core/room_builder.py` | — |
| R2 | `web_app/static/viewer3d/room_viewer.js`, `room.html` | — |
| R3 | — | `web_app/controllers.py`, `web_app/models.py` |
| R4 | — | `companion_app/lib/main.dart` |
| R5 | `core/reference_detector.py` | — |
| R6 | — | `web_app/static/viewer3d/room_viewer.js`, `web_app/controllers.py` |
| R7 | — | `web_app/controllers.py`, `companion_app/lib/main.dart` |

**DO NOT MODIFY** (protected files — working code):
- `core/smpl_fitting.py`
- `core/silhouette_matcher.py`
- `core/silhouette_extractor.py`
- `core/mesh_reconstruction.py`
- `web_app/static/viewer3d/body_viewer.js`
