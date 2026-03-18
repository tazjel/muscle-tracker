# V7 Verification Sheet — Real Human in Real Room

> **For Sonnet execution only.** All V7 code is already written by Opus.
> Your job: verify each feature works, fix bugs if found.
> Static files (JS/CSS/HTML) do NOT need server restart.
> Python changes (models.py, controllers.py) NEED server restart.

---

## How to Use This Sheet

1. Work top-to-bottom, one task at a time
2. Each task has: what to check, how to check it, what to fix if broken
3. Do NOT read files listed here unless the verification step fails
4. Do NOT refactor, add features, or "improve" anything — verify only
5. Mark each task DONE or FIXED after completing it

---

## T1 — Verify Room Shell (P1)

**Files if needed**: `web_app/static/viewer3d/body_viewer.js` lines 1118-1180

**Check**: Open the viewer in browser and press `6` (or click "Room" button).

**Verify**:
```bash
# Serve viewer (if server not running)
cd C:/Users/MiEXCITE/Projects/gtd3d
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps --host 0.0.0.0 --port 8000 >> server.log 2>&1 &
```
- Open: `http://localhost:8000/web_app/static/viewer3d/index.html?model=/api/mesh/1.glb`
- Press `6` → floor appears under body, walls surround it, ceiling above
- Body shadow visible on floor
- Press `6` again → room disappears, dark background returns
- Orbit camera still works inside the room

**Quick JS syntax check** (run in browser console):
```javascript
// Should not throw — room group exists and has 6 children
console.log('Room children:', bodyViewer.scene.getObjectByName('room_floor') ? 'OK' : 'MISSING');
```

**Common bugs to fix**:
- If no shadow on floor: check `body_viewer.js:255` — shadow camera frustum must be ±400
- If walls face wrong way: check rotation values in `_buildRoom()`
- If background stays dark when room on: check `toggleRoom()` sets `scene.background = null`

**Needs restart**: NO

---

## T2 — Verify Lighting Swap (P3)

**Files if needed**: `body_viewer.js` lines 216-260

**Check**: With room ON (key 6), lighting should feel like an overhead lamp, not studio.

**Verify**:
- Room OFF → body lit from front-top (studio key light), side fill, back rim
- Press `6` (room ON) → single warm overhead light, dimmer ambient, body lit from above
- Press `6` (room OFF) → studio lights restored, exact same as before
- Toggle rapidly 5x → no duplicate lights accumulating (scene shouldn't get brighter)

**Quick check for light leak** (browser console):
```javascript
// Count lights — should be 3 (room) or 5 (studio), never more
let n = 0; bodyViewer.scene.traverse(c => { if (c.isLight) n++; }); console.log('Lights:', n);
```

**Common bugs to fix**:
- Lights accumulate: `_clearLights()` not removing all items — check array `.length = 0`
- Room too dark: PointLight intensity too low, try 2.0 instead of 1.5
- No contact shadow blob: check `_contactShadow.visible` toggles with `_roomOn`

**Needs restart**: NO

---

## T3 — Verify Props (P6)

**Files if needed**: `body_viewer.js` lines 1302-1357

**Check**: Press `8` (or click "Props" button) to toggle reference objects.

**Verify**:
- Press `8` → red rod appears beside body, camera stands front/back, door outline on left wall
- Use Measure tool (M) → click top and bottom of red rod → should read ~1000mm
- Stands positioned at Z=±178 (1m from body center)
- Press `8` → all props disappear

**Common bugs to fix**:
- Rod not 1m: check `rodH = 178.6` (1000mm × 0.17857 scale)
- Door on wrong wall: should be on left wall (X = -357)
- Props not casting shadow: verify `castShadow = true` on each mesh

**Needs restart**: NO

---

## T4 — Verify Mirror (P4)

**Files if needed**: `body_viewer.js` lines 1204-1248

**Check**: Press `7` to cycle mirror through walls.

**Verify**:
- Press `7` once → back wall becomes reflective, body reflection visible
- Rotate camera → reflection updates in real-time
- Press `7` again → mirror moves to left wall
- Press `7` → right wall, then front wall, then off
- After cycling off → wall materials restored (no permanent silver walls)
- If room was off, pressing `7` should auto-enable room first

**Common bugs to fix**:
- No reflection visible: CubeCamera not updating — check `_updateMirror()` called in `_animate()`
- Self-reflection recursion (infinite mirrors): check `_mirrorWallMesh.visible = false` before `_cubeCamera.update()`
- Material not restored: check `_preMirrorMat` saved before override

**Needs restart**: NO

---

## T5 — Verify Walk Mode (P5)

**Files if needed**: `body_viewer.js` lines 1250-1299

**Check**: Press `5` to enter walk mode.

**Verify**:
- Press `5` → pointer locks (cursor disappears), camera jumps to room corner at eye height
- WASD moves → camera walks around the room
- Can't walk through walls (clamped 20 units from edges)
- Camera Y stays at 300 (eye height) regardless of mouse look
- S key moves backward (not screenshot) while in walk mode
- Escape → exits walk mode, orbit controls restored
- If room was off, pressing `5` should auto-enable room first

**Known issue**: PointerLockControls requires user gesture (click) before `lock()` works in some browsers. If pointer doesn't lock on first press of `5`, that's a browser security restriction — Sonnet can add a fallback:

**Fix if pointer lock fails** — in `toggleWalkMode()`, wrap the lock call:
```javascript
// Replace: _pointerControls.lock();
// With:
renderer.domElement.requestPointerLock();
```
Only apply this fix if the CDN PointerLockControls doesn't handle it.

**Needs restart**: NO

---

## T6 — Verify Room Textures API (P2)

**Files if needed**: `web_app/controllers.py` lines 1282-1340, `web_app/models.py` line 208

**IMPORTANT**: This task requires server restart. Do T1-T5 first.

**Step 1 — Restart server**:
```bash
ps aux | grep py4web | grep -v grep | awk '{print $1}' | xargs kill
sleep 2
cd C:/Users/MiEXCITE/Projects/gtd3d
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps --host 0.0.0.0 --port 8000 >> server.log 2>&1 &
sleep 3
```

**Step 2 — Get fresh JWT** (old one invalidated by restart):
```bash
TOKEN=$(curl -s http://localhost:8000/web_app/api/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@muscle.com"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")
echo "Token: $TOKEN"
```

**Step 3 — Upload a test texture**:
```bash
# Create a simple test image
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
import numpy as np, cv2
img = np.full((256, 256, 3), [180, 160, 140], dtype=np.uint8)
cv2.putText(img, 'FLOOR', (60, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (80, 80, 80), 3)
cv2.imwrite('uploads/test_floor.jpg', img)
print('Test floor image created')
"

# Upload it
curl -s http://localhost:8000/web_app/api/customer/1/room_texture \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "surface=floor" \
  -F "image=@uploads/test_floor.jpg"
```

**Step 4 — Verify GET endpoints**:
```bash
# List textures
curl -s http://localhost:8000/web_app/api/customer/1/room_textures \
  -H "Authorization: Bearer $TOKEN"

# Should return: {"status": "success", "textures": [{"surface": "floor", "url": "..."}]}

# Serve the image (should return image bytes, not 404)
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/web_app/api/customer/1/room_texture/floor
# Should print: 200
```

**Step 5 — Verify in viewer**:
- Open viewer with room on (key 6) → floor should show the test texture

**Common bugs to fix**:
- `room_texture` table not created: check `models.py` has `db.define_table('room_texture', ...)` before `db.commit()`
- 404 on upload: check `@action` decorator path matches `/api/customer/<customer_id:int>/room_texture`
- Image not showing in viewer: check `_loadRoomTextures()` maps surface names correctly (the API returns `wall_front` but viewer uses `front`)

**Needs restart**: YES

---

## T7 — HTML Button Row Verification

**File if needed**: `web_app/static/viewer3d/index.html` lines 29-39

**Check**: All 4 new buttons visible and functional.

**Verify** (visual inspection in browser):
- Second row of buttons exists: Walk, Room, Mirror, Props
- Each button highlights blue when active
- Keyboard hints show: `5 walk · 6 room · 7 mirror · 8 props` and `WASD move`
- On mobile viewport (DevTools 375px width) buttons don't overflow

**Common bugs to fix**:
- Buttons overflow on mobile: add `flex-wrap: wrap` to the new `.view-modes` div
- Button IDs wrong: must be `btn-walk`, `btn-room`, `btn-mirror`, `btn-props`

**Needs restart**: NO

---

## Execution Order

| Order | Task | Server Restart | Time Est |
|-------|------|----------------|----------|
| 1 | T1 (Room) | No | 2 min |
| 2 | T2 (Lights) | No | 2 min |
| 3 | T3 (Props) | No | 2 min |
| 4 | T4 (Mirror) | No | 3 min |
| 5 | T5 (Walk) | No | 3 min |
| 6 | T7 (HTML) | No | 1 min |
| 7 | T6 (Textures API) | YES | 5 min |

Do T1-T5 and T7 in one session (no restart). Do T6 last (requires restart).

---

## Files Modified by V7 (Reference Only — Do Not Read Unless Fixing a Bug)

| File | Lines Changed | What |
|------|--------------|------|
| `body_viewer.js` | +350 lines | Room, lights, mirror, walk, props, room textures |
| `index.html` | +15 lines | Walk/Room/Mirror/Props buttons, key hints |
| `models.py` | +8 lines | `room_texture` table |
| `controllers.py` | +55 lines | 3 room texture endpoints |

## Keyboard Map After V7
| Key | Action |
|-----|--------|
| 1-4 | View modes (solid/wire/heat/textured) |
| 5 | Walk mode (first-person) |
| 6 | Room toggle |
| 7 | Mirror cycle (back→left→right→front→off) |
| 8 | Props toggle |
| L | Labels |
| M | Measure |
| R | Reset camera |
| S | Screenshot (or backward in walk mode) |
| WASD | Move (walk mode only) |
| Escape | Exit walk mode / exit measure |
