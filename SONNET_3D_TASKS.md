# 3D Human View — Sonnet Task Sheet

**Project**: Upgrade muscle_tracker from basic ellipsoid mesh to a professional 3D human viewer.
**Agent**: Claude Sonnet (primary — owns all integration work)
**Date**: 2026-03-17

---

## RULES

- **DO NOT** read `companion_app/lib/main.dart` or `web_app/controllers.py` in full. Grep first, read ±50 lines.
- **DO NOT** modify any file that Jules/Gemini are assigned to (see BOUNDARIES below).
- **DO NOT** add features not listed in this task sheet.
- After each task, run a quick sanity check (load viewer in browser, or run `python -c "from core.mesh_reconstruction import *"`)
- Commit after completing each task group.

## BOUNDARIES — File Ownership

| File/Dir | Owner | Notes |
|----------|-------|-------|
| `web_app/static/viewer3d/*` | **Sonnet** | Core viewer rewrite |
| `core/mesh_reconstruction.py` | **Sonnet** | glTF export, SMPL integration |
| `core/mesh_comparison.py` | **Sonnet** | Vertex color heatmap in glTF |
| `core/mesh_volume.py` | **Sonnet** | Volume from new mesh format |
| `core/smpl_fitting.py` | **Sonnet** | NEW file — SMPL body model fitting |
| `core/video_capture.py` | **Sonnet** | NEW file — video frame extraction (Phase 3) |
| `web_app/controllers.py` | **Sonnet** | 3D API endpoints (grep only, edit targeted lines) |
| `web_app/models.py` | **Sonnet** | DB schema changes for profiles |
| `companion_app/lib/main.dart` | **Sonnet** | Dev mode + profile setup (grep only, edit targeted) |
| `web_app/static/viewer3d/body_viewer.js` | **Sonnet** | NEW file — upgraded viewer |
| `scripts/quality_gate.py` | **Jules** | DO NOT TOUCH |
| `core/frame_selector.py` | **Jules** | DO NOT TOUCH |
| `web_app/static/viewer3d/measurement_overlay.js` | **Gemini** | DO NOT TOUCH |
| `web_app/static/viewer3d/styles.css` | **Gemini** | DO NOT TOUCH |

---

## TASK GROUP 0: Human Profile + Device Profile + Dev Mode (PRE-REQUISITE)

> This group must be done FIRST. All other tasks depend on the profile data being available.

### T0.1 — Extend the database schema with body measurements and device profiles

**Goal**: Store the human's actual body measurements and device setup so the system has ground truth instead of guessing.

**Current state** (`web_app/models.py`):
- `customer` table has: `height_cm`, `weight_kg` (lines 23-24) — that's ALL
- No body part measurements, no device profile table
- `muscle_scan` table has `device_info` (string, line 65) — just a text field

**What to add to `models.py`**:

1. **Extend `customer` table** — add these fields after `weight_kg` (line 24):
```python
    # Segment lengths (user provides during profile setup)
    Field('shoulder_width_cm', 'double'),         # edge to edge
    Field('neck_to_shoulder_cm', 'double'),       # each side, neck to shoulder edge
    Field('shoulder_to_head_cm', 'double'),       # shoulder top to head top
    Field('arm_length_cm', 'double'),             # finger to shoulder
    Field('upper_arm_length_cm', 'double'),       # shoulder to elbow
    Field('forearm_length_cm', 'double'),         # elbow to fingertip
    Field('torso_length_cm', 'double'),           # belly to shoulder
    Field('inseam_cm', 'double'),                 # crotch to ankle
    Field('floor_to_knee_cm', 'double'),          # ground to knee top
    Field('knee_to_belly_cm', 'double'),          # knee to belly start
    Field('back_buttock_to_knee_cm', 'double'),   # rear: buttock to knee
    # Circumferences
    Field('head_circumference_cm', 'double'),
    Field('neck_circumference_cm', 'double'),
    Field('chest_circumference_cm', 'double'),
    Field('bicep_circumference_cm', 'double'),
    Field('forearm_circumference_cm', 'double'),
    Field('hand_circumference_cm', 'double'),     # palm
    Field('waist_circumference_cm', 'double'),
    Field('hip_circumference_cm', 'double'),      # buttock level
    Field('thigh_circumference_cm', 'double'),    # upper thigh
    Field('quadricep_circumference_cm', 'double'),
    Field('calf_circumference_cm', 'double'),
    Field('profile_completed', 'boolean', default=False),
```

2. **Create NEW `device_profile` table**:
```python
db.define_table('device_profile',
    Field('customer_id', 'reference customer'),
    Field('device_name', 'string', length=128),          # "Samsung A24", "MatePad Pro"
    Field('device_serial', 'string', length=64),         # ADB serial
    Field('role', 'string', length=16),                  # "front", "back", "left", "right"
    Field('camera_height_from_ground_cm', 'double'),     # tripod/shelf height
    Field('distance_to_subject_cm', 'double'),           # how far from human
    Field('sensor_width_mm', 'double'),                  # camera sensor size
    Field('focal_length_mm', 'double'),                  # camera focal length
    Field('screen_width_px', 'integer'),
    Field('screen_height_px', 'integer'),
    Field('tap_x', 'integer'),                           # center tap coordinate for ADB
    Field('tap_y', 'integer'),
    Field('orientation', 'string', length=16, default='portrait'),  # portrait/landscape
    Field('is_active', 'boolean', default=True),
    Field('created_on', 'datetime', default=lambda: datetime.now()),
    Field('notes', 'text'),
)
```

3. **Create NEW `scan_setup` table** (per-session calibration snapshot):
```python
db.define_table('scan_setup',
    Field('customer_id', 'reference customer'),
    Field('session_date', 'datetime', default=lambda: datetime.now()),
    Field('human_distance_from_wall_cm', 'double'),     # background distance
    Field('floor_type', 'string', length=32),            # "tile", "carpet", "wood"
    Field('lighting', 'string', length=32),              # "natural", "fluorescent", "ring_light"
    Field('clothing', 'string', length=64),              # "shirtless", "tight_shirt", "shorts"
    Field('notes', 'text'),
)
```

**Why these measurements matter**:
- `shoulder_width_cm` + `arm_length_cm` → constrains SMPL shape parameters
- `circumference` values → directly validate volume calculations
- `camera_height_from_ground_cm` → corrects perspective distortion (camera looking up/down at subject)
- `distance_to_subject_cm` → replaces the manual distance picker, stored per-device

**Acceptance**: Server starts without errors. New tables exist in database.db.

---

### T0.2 — Create profile setup API endpoints

**Goal**: REST API for the app to submit and retrieve human/device profiles.

**What to add to `controllers.py`**:

```python
# --- HUMAN PROFILE ---

@action('api/customer/<customer_id:int>/body_profile', method=['GET'])
@action.uses(db, cors)
def get_body_profile(customer_id):
    """Return all body measurements for a customer."""
    # Auth check (copy pattern from existing endpoints)
    customer = db.customer[customer_id]
    if not customer: return dict(status='error', message='Customer not found')
    return dict(
        status='success',
        profile={
            'height_cm': customer.height_cm,
            'weight_kg': customer.weight_kg,
            'shoulder_width_cm': customer.shoulder_width_cm,
            'arm_length_cm': customer.arm_length_cm,
            # ... all fields ...
            'profile_completed': customer.profile_completed,
        }
    )

@action('api/customer/<customer_id:int>/body_profile', method=['POST'])
@action.uses(db, cors)
def update_body_profile(customer_id):
    """Update body measurements. Accepts partial updates."""
    # Auth check
    customer = db.customer[customer_id]
    data = request.json
    update_fields = {}
    for field in ['height_cm', 'weight_kg',
                  'shoulder_width_cm', 'neck_to_shoulder_cm', 'shoulder_to_head_cm',
                  'arm_length_cm', 'upper_arm_length_cm', 'forearm_length_cm',
                  'torso_length_cm', 'inseam_cm', 'floor_to_knee_cm',
                  'knee_to_belly_cm', 'back_buttock_to_knee_cm',
                  'head_circumference_cm', 'neck_circumference_cm',
                  'chest_circumference_cm', 'bicep_circumference_cm',
                  'forearm_circumference_cm', 'hand_circumference_cm',
                  'waist_circumference_cm', 'hip_circumference_cm',
                  'thigh_circumference_cm', 'quadricep_circumference_cm',
                  'calf_circumference_cm']:
        if field in data and data[field] is not None:
            update_fields[field] = float(data[field])
    # Mark complete if at least height + weight + 3 circumferences provided
    filled = sum(1 for v in update_fields.values() if v and v > 0)
    update_fields['profile_completed'] = filled >= 5
    customer.update_record(**update_fields)
    return dict(status='success', profile_completed=update_fields['profile_completed'])

# --- DEVICE PROFILE ---

@action('api/customer/<customer_id:int>/devices', method=['GET'])
@action.uses(db, cors)
def get_devices(customer_id):
    """Return all device profiles for a customer."""
    devices = db(db.device_profile.customer_id == customer_id).select()
    return dict(status='success', devices=[row.as_dict() for row in devices])

@action('api/customer/<customer_id:int>/devices', method=['POST'])
@action.uses(db, cors)
def add_or_update_device(customer_id):
    """Add or update a device profile. If device_serial matches, update."""
    data = request.json
    serial = data.get('device_serial', '')
    existing = db(
        (db.device_profile.customer_id == customer_id) &
        (db.device_profile.device_serial == serial)
    ).select().first()
    fields = {
        'customer_id': customer_id,
        'device_name': data.get('device_name', ''),
        'device_serial': serial,
        'role': data.get('role', 'front'),
        'camera_height_from_ground_cm': float(data.get('camera_height_from_ground_cm', 0)),
        'distance_to_subject_cm': float(data.get('distance_to_subject_cm', 100)),
        'sensor_width_mm': float(data.get('sensor_width_mm', 0)),
        'focal_length_mm': float(data.get('focal_length_mm', 0)),
        'screen_width_px': int(data.get('screen_width_px', 0)),
        'screen_height_px': int(data.get('screen_height_px', 0)),
        'tap_x': int(data.get('tap_x', 0)),
        'tap_y': int(data.get('tap_y', 0)),
        'orientation': data.get('orientation', 'portrait'),
    }
    if existing:
        existing.update_record(**fields)
        return dict(status='success', device_id=existing.id, action='updated')
    else:
        device_id = db.device_profile.insert(**fields)
        return dict(status='success', device_id=device_id, action='created')

# --- SCAN SETUP ---

@action('api/customer/<customer_id:int>/scan_setup', method=['POST'])
@action.uses(db, cors)
def save_scan_setup(customer_id):
    """Save scan environment setup before a session."""
    data = request.json
    setup_id = db.scan_setup.insert(
        customer_id=customer_id,
        human_distance_from_wall_cm=float(data.get('human_distance_from_wall_cm', 0)),
        floor_type=data.get('floor_type', ''),
        lighting=data.get('lighting', ''),
        clothing=data.get('clothing', ''),
        notes=data.get('notes', ''),
    )
    return dict(status='success', setup_id=setup_id)
```

**Wire device distance into scan upload**: In the existing `upload_scan` and `upload_quad_scan` endpoints, when `camera_distance_cm` is NOT provided in the request, fall back to the device_profile's `distance_to_subject_cm` for that device serial.

**Acceptance**:
```bash
curl -X POST http://localhost:8000/web_app/api/customer/1/body_profile \
  -H "Content-Type: application/json" \
  -d '{"height_cm": 175, "weight_kg": 80, "shoulder_width_cm": 48, "bicep_circumference_cm": 35}'
# Returns: {"status": "success", "profile_completed": false}
```

---

### T0.3 — Dev Mode in Flutter app

**Goal**: APK starts in dev mode to make testing easy. Dev mode enables:
1. ADB-invocable actions (scan, upload, set profile)
2. On-screen dev panel showing current state
3. Interactive questions to user for profile/calibration refinement
4. No kiosk mode (status bar visible for debugging)

**Current state** (`main.dart`):
- App starts in immersive kiosk mode (line 53)
- Auto-login with demo@muscle.com (lines 57-73)
- Goes directly to CameraLevelScreen (line 83)
- `_cameraDistanceCm` hardcoded default 100.0 (line 221)

**What to change in `main.dart`**:

1. **Add dev mode flag** — read from file at startup (like dual role):
```dart
// In AppConfig class (line 17):
static bool devMode = false;
static Map<String, dynamic> devConfig = {};

// In main() after line 55 (_cameras = await availableCameras()):
try {
  final devFile = File('/data/local/tmp/muscle_tracker_dev.json');
  if (await devFile.exists()) {
    final devJson = jsonDecode(await devFile.readAsString());
    AppConfig.devMode = devJson['dev_mode'] == true;
    AppConfig.devConfig = devJson;
  }
} catch (_) {}

// If dev mode, DON'T use immersive sticky:
if (!AppConfig.devMode) {
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
}
```

GTDdebug enables dev mode via:
```bash
adb shell 'echo "{\"dev_mode\":true,\"auto_scan\":false}" > /data/local/tmp/muscle_tracker_dev.json'
adb shell am force-stop com.example.companion_app
adb shell am start -n com.example.companion_app/.MainActivity
```

2. **Add profile setup screen** — shown on first launch or when profile_completed is false:

```dart
class ProfileSetupScreen extends StatefulWidget { ... }

class _ProfileSetupScreenState extends State<ProfileSetupScreen> {
  // Text controllers for each measurement
  final _heightCtrl = TextEditingController();
  final _weightCtrl = TextEditingController();
  final _shoulderCtrl = TextEditingController();
  final _armLengthCtrl = TextEditingController();
  final _chestCtrl = TextEditingController();
  final _waistCtrl = TextEditingController();
  final _hipCtrl = TextEditingController();
  final _thighCtrl = TextEditingController();
  final _calfCtrl = TextEditingController();
  final _bicepCtrl = TextEditingController();
  final _neckCtrl = TextEditingController();
  final _inseamCtrl = TextEditingController();

  // Step-by-step guided flow:
  // Step 1: Height + Weight (required)
  // Step 2: Upper body — shoulder width, chest, neck, bicep (with diagram)
  // Step 3: Lower body — waist, hip, thigh, calf, inseam (with diagram)
  // Step 4: Review & submit

  // Each step shows:
  // - Simple body diagram highlighting what to measure
  // - Text field with unit (cm)
  // - "How to measure" hint text
  // - Skip button (measurements are optional except height/weight)

  Future<void> _submitProfile() async {
    final body = {
      'height_cm': double.tryParse(_heightCtrl.text),
      'weight_kg': double.tryParse(_weightCtrl.text),
      'shoulder_width_cm': double.tryParse(_shoulderCtrl.text),
      // ... all fields ...
    };
    body.removeWhere((k, v) => v == null);
    await http.post(
      Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/body_profile'),
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $_jwtToken'},
      body: jsonEncode(body),
    );
    // Navigate to camera screen
  }
}
```

3. **Add device setup screen** — shown after profile, or accessible from dev panel:

```dart
class DeviceSetupScreen extends StatefulWidget { ... }

class _DeviceSetupScreenState extends State<DeviceSetupScreen> {
  double _cameraHeightCm = 100.0;  // height of phone/tablet from floor
  double _distanceCm = 100.0;       // distance to subject
  String _role = 'front';           // front/back/left/right

  // Shows:
  // - Side-view diagram: stick figure with phone on tripod
  // - Slider: "Camera height from floor" (30cm - 200cm)
  // - Slider: "Distance to subject" (50cm - 300cm)
  // - Role picker: front/back/left/right
  // - Auto-detect button: reads device model + serial, camera specs

  Future<void> _autoDetect() async {
    // Read device model, screen size from Flutter
    // Read focal length from camera controller
    // Post to /api/customer/$_customerId/devices
  }

  Future<void> _submitDevice() async {
    await http.post(
      Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/devices'),
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $_jwtToken'},
      body: jsonEncode({
        'device_name': 'Auto-detected',
        'device_serial': '', // read from build info
        'role': _role,
        'camera_height_from_ground_cm': _cameraHeightCm,
        'distance_to_subject_cm': _distanceCm,
        'screen_width_px': MediaQuery.of(context).size.width.toInt(),
        'screen_height_px': MediaQuery.of(context).size.height.toInt(),
        'orientation': 'portrait',
      }),
    );
  }
}
```

4. **Dev panel overlay** (only visible in dev mode):
```dart
// Floating dev panel — toggled with a small [D] button in corner
Widget _buildDevPanel() {
  if (!AppConfig.devMode) return const SizedBox.shrink();
  return Positioned(
    top: 40, right: 10,
    child: Container(
      padding: EdgeInsets.all(8),
      color: Colors.black87,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('DEV MODE', style: TextStyle(color: Colors.amber, fontWeight: FontWeight.bold)),
        Text('Customer: $_customerId', style: TextStyle(color: Colors.white70, fontSize: 10)),
        Text('Distance: ${_cameraDistanceCm}cm', style: TextStyle(color: Colors.white70, fontSize: 10)),
        Text('JWT: ${_jwtToken?.substring(0, 8)}...', style: TextStyle(color: Colors.white70, fontSize: 10)),
        Text('Profile: ${_profileCompleted ? "OK" : "INCOMPLETE"}', style: TextStyle(color: _profileCompleted ? Colors.green : Colors.red, fontSize: 10)),
        SizedBox(height: 4),
        // Quick action buttons
        ElevatedButton(onPressed: _openProfileSetup, child: Text('Edit Profile', style: TextStyle(fontSize: 10))),
        ElevatedButton(onPressed: _openDeviceSetup, child: Text('Device Setup', style: TextStyle(fontSize: 10))),
        ElevatedButton(onPressed: _triggerScan, child: Text('Force Scan', style: TextStyle(fontSize: 10))),
      ]),
    ),
  );
}
```

5. **App launch flow change**:
```
main() →
  if dev mode file exists → set AppConfig.devMode = true, skip kiosk
  auto-login →
  check profile_completed →
    if false → ProfileSetupScreen → DeviceSetupScreen → CameraLevelScreen
    if true → CameraLevelScreen (current behavior)
```

6. **ADB-invocable profile setup** (for GTDdebug):
The app should also accept profile data pushed via file, just like dual role:
```bash
# GTDdebug pushes profile before launching app:
adb shell 'echo "{
  \"height_cm\": 168,
  \"shoulder_width_cm\": 37,
  \"arm_length_cm\": 80,
  \"upper_arm_length_cm\": 35,
  \"forearm_length_cm\": 45,
  \"torso_length_cm\": 50,
  \"floor_to_knee_cm\": 52,
  \"chest_circumference_cm\": 97,
  \"bicep_circumference_cm\": 32,
  \"waist_circumference_cm\": 90,
  \"hip_circumference_cm\": 92,
  \"thigh_circumference_cm\": 53,
  \"calf_circumference_cm\": 34,
  \"camera_height_from_ground_cm\": 65
}" > /data/local/tmp/muscle_tracker_profile.json'
```
App reads this file at startup and auto-submits to server if found.

**Acceptance**:
```bash
# Enable dev mode
adb shell 'echo "{\"dev_mode\":true}" > /data/local/tmp/muscle_tracker_dev.json'
# Push profile data (real user measurements)
adb shell 'echo "{\"height_cm\":168,\"shoulder_width_cm\":37,\"bicep_circumference_cm\":32,\"chest_circumference_cm\":97,\"calf_circumference_cm\":34}" > /data/local/tmp/muscle_tracker_profile.json'
# Launch app — shows dev panel, submits profile, goes to camera
adb shell am force-stop com.example.companion_app
adb shell am start -n com.example.companion_app/.MainActivity
```

---

### T0.4 — Interactive calibration questions (ask user in chat)

**Goal**: When Sonnet is running a test session via GTDdebug, the system can ask the user specific questions to improve accuracy.

**What to create**: A calibration questionnaire endpoint that returns the next question to ask.

```python
@action('api/customer/<customer_id:int>/calibration_questions', method=['GET'])
@action.uses(db, cors)
def calibration_questions(customer_id):
    """Return the next calibration question based on missing data."""
    customer = db.customer[customer_id]
    devices = db(db.device_profile.customer_id == customer_id).select()

    questions = []

    # Priority 1: Must-have measurements
    if not customer.height_cm:
        questions.append({
            'id': 'height_cm', 'type': 'number', 'unit': 'cm',
            'question': 'How tall are you? (cm)',
            'hint': 'Stand against a wall, mark top of head, measure from floor.',
            'priority': 'required',
        })
    if not customer.weight_kg:
        questions.append({
            'id': 'weight_kg', 'type': 'number', 'unit': 'kg',
            'question': 'What is your weight? (kg)',
            'priority': 'required',
        })

    # Priority 2: Device setup
    if not devices:
        questions.append({
            'id': 'device_height', 'type': 'number', 'unit': 'cm',
            'question': 'How high is the phone/tablet camera from the floor? (cm)',
            'hint': 'Measure from floor to the camera lens. If on a table, measure table height + device position.',
            'priority': 'important',
        })
        questions.append({
            'id': 'device_distance', 'type': 'number', 'unit': 'cm',
            'question': 'How far is the phone from where you stand? (cm)',
            'hint': 'Measure straight line from camera to your standing position.',
            'priority': 'important',
        })

    # Priority 3: Body measurements for target muscle
    latest_scan = db(db.muscle_scan.customer_id == customer_id).select(
        orderby=~db.muscle_scan.scan_date, limitby=(0,1)).first()
    target = latest_scan.muscle_group if latest_scan else 'bicep'

    measurement_map = {
        'bicep': ('bicep_circumference_cm', 'What is your relaxed bicep circumference? (cm)',
                  'Wrap tape measure around the widest part of your upper arm, arm at side.'),
        'quadricep': ('thigh_circumference_cm', 'What is your thigh circumference? (cm)',
                     'Wrap tape around the widest part of your thigh, standing upright.'),
        'calf': ('calf_circumference_cm', 'What is your calf circumference? (cm)',
                'Wrap tape around the widest part of your calf.'),
        'chest': ('chest_circumference_cm', 'What is your chest circumference? (cm)',
                 'Wrap tape around chest at nipple height, arms at sides.'),
    }

    if target in measurement_map:
        field, q, h = measurement_map[target]
        if not getattr(customer, field, None):
            questions.append({
                'id': field, 'type': 'number', 'unit': 'cm',
                'question': q, 'hint': h, 'priority': 'helpful',
            })

    return dict(status='success', questions=questions, profile_completed=customer.profile_completed)
```

**How Sonnet uses this during a test session**:
1. Sonnet calls GET `/api/customer/1/calibration_questions`
2. If questions remain, Sonnet asks the user in chat: *"Quick calibration question: How tall are you? (cm)"*
3. User answers: *"175"*
4. Sonnet POSTs to `/api/customer/1/body_profile` with `{"height_cm": 175}`
5. Repeat until no questions left

**Acceptance**: Endpoint returns prioritized list of missing measurements.

---

## TASK GROUP 1: Viewer Engine Upgrade (Phase 1)

### T1.1 — Upgrade Three.js and add glTF support

**Goal**: Replace the r128 OBJ-only viewer with a modern glTF-capable engine.

**Current state** (`web_app/static/viewer3d/index.html`):
- Three.js r128 loaded from CDN
- OBJLoader, OrbitControls loaded from CDN
- Single `viewer.js` file (109 lines)

**What to do**:
1. Create `web_app/static/viewer3d/body_viewer.js` (new file — do NOT overwrite `viewer.js`, keep it as fallback)
2. Update `index.html`:
   - Upgrade Three.js CDN to r160+ (use ES module imports or addons bundle)
   - Add GLTFLoader import
   - Add `<script src="body_viewer.js">` after viewer.js
   - Add `<link rel="stylesheet" href="styles.css">` (Gemini creates this)
   - Add `<script src="measurement_overlay.js">` (Gemini creates this)
3. In `body_viewer.js`, implement:
   - `initBodyViewer()` — creates scene, camera, renderer, OrbitControls
   - Support loading both OBJ (legacy) and glTF/GLB (new) via URL param `?model=path.glb` (falls back to `?obj=` for OBJ)
   - **Tone mapping**: `renderer.toneMapping = THREE.ACESFilmicToneMapping`
   - **Environment lighting**: Use `PMREMGenerator` with a simple gradient environment
   - Keep existing buttons: wireframe toggle, reset camera, screenshot
   - **Expose** `window.bodyViewer` global for Gemini's measurement_overlay.js:
     ```javascript
     window.bodyViewer = { scene, camera, renderer, mesh, getMeshIntersection(event) { /*raycaster*/ } };
     ```

**Acceptance**: Browser opens `viewer3d/index.html?model=test.glb` and renders with realistic lighting.

---

### T1.2 — Add PBR skin material for human mesh

**Goal**: Apply a realistic skin-like material to human body meshes.

**What to do in `body_viewer.js`**:
1. Default PBR material matching user's light brown skin tone:
   ```javascript
   const skinMaterial = new THREE.MeshStandardMaterial({
       color: 0xC4956A, roughness: 0.65, metalness: 0.0, side: THREE.DoubleSide
   });
   ```
2. Add hemisphere light: `new THREE.HemisphereLight(0xffeedd, 0x334455, 0.4)`
3. Second directional light from below-left for definition shadows

**Acceptance**: Human mesh looks like a body, not a blue wireframe.

---

### T1.3 — Add vertex color heatmap rendering

**Goal**: Growth/change visualization as color gradient on mesh.

**What to do in `body_viewer.js`**:
1. `applyHeatmap(mesh, colorData)` — maps per-vertex values to blue→green→red
2. Toggle button: "Show Growth Heatmap" / "Show Solid"
3. HTML legend overlay (uses CSS classes from Gemini's `styles.css`: `.heatmap-legend`, `.heatmap-gradient`, `.heatmap-labels`)

**Acceptance**: Mesh toggles between solid skin and rainbow heatmap.

---

### T1.4 — Add HDRI environment map

**Goal**: Realistic reflections and ambient lighting.

**What to do**: Generate gradient environment with `PMREMGenerator` or use a free small HDR (< 500KB).

**Acceptance**: Mesh has soft ambient reflections.

---

## TASK GROUP 2: glTF Export Pipeline (Phase 1-2 bridge)

### T2.1 — Add glTF/GLB export to mesh_reconstruction.py

**Goal**: Export reconstructed mesh as GLB (binary glTF).

**Current state** (`core/mesh_reconstruction.py`):
- `export_obj()` (lines 82-87), `export_stl()` (lines 89-101)

**What to do**:
1. Add `export_glb(vertices, faces, output_path, vertex_colors=None)` function
2. Use `pygltflib>=1.16` (add to requirements.txt)
3. Default PBR material: `baseColorFactor=[0.83, 0.65, 0.45, 1.0]`, `roughnessFactor=0.65`
4. If vertex_colors provided, add COLOR_0 accessor

**Acceptance**: `export_glb(verts, faces, "test.glb")` produces valid GLB.

---

### T2.2 — Wire glTF export into controllers.py

**Goal**: `/api/customer/<id>/reconstruct_3d` produces GLB alongside OBJ.

**What to do**:
1. Grep for `reconstruct_3d` in controllers.py
2. After `export_obj()`, add `export_glb()` call
3. Add `glb_path` to mesh_model DB record (add Field to mesh_model table)
4. Add endpoint: `@action('api/mesh/<mesh_id>.glb')` to serve GLB files
5. **Use device_profile and body_profile data**: When reconstructing, pull the customer's measurements and device distance from profiles instead of requiring them per-request

**Acceptance**: POST reconstruct_3d returns both `obj_url` and `glb_url`.

---

## TASK GROUP 3: SMPL Body Model Integration (Phase 2)

### T3.1 — Create core/smpl_fitting.py

**Goal**: Fit a parametric human body model to the user's profile measurements.

**Key advantage of profiles**: With shoulder_width, arm_length, circumferences known, SMPL beta parameters can be solved directly instead of guessing from images.

**What to do**:
1. Create `core/smpl_fitting.py`
2. **Lightweight approach** (no PyTorch):
   - Use a pre-computed SMPL mean template mesh (6890 verts, 13776 faces) as NPZ
   - Scale by height_cm
   - Apply shape deformation using known circumferences → PCA shape coefficients
   - Apply muscle-specific displacement for target group
3. Input: customer's body_profile measurements dict
4. Output: `{vertices, faces, joints, volume_cm3, body_params}`

**Acceptance**: `fit_smpl_to_measurements({'height_cm': 175, 'shoulder_width_cm': 48, 'bicep_circumference_cm': 35})` returns a human-shaped mesh.

---

### T3.2 — Integrate SMPL mesh into reconstruction endpoint

**Goal**: `reconstruct_3d` with `model_type=body` produces full human mesh.

**What to do**:
1. Add `model_type` param to reconstruct_3d: `"tube"` (default) or `"body"` (SMPL)
2. When `body`: pull customer's body_profile, call `fit_smpl_to_measurements()`, export GLB
3. Keep tube as fallback

**Acceptance**: POST `reconstruct_3d?model_type=body` returns human-shaped GLB.

---

## TASK GROUP 4: Video Capture Backend (Phase 3)

### T4.1 — Create core/video_capture.py

**Goal**: Frame-accurate extraction with PyAV (NOT OpenCV).

Add `av` to requirements.txt. Implement:
- `extract_frames_at_timestamps(video_path, timestamps_ms, output_dir)`
- `extract_frames_uniform(video_path, num_frames, output_dir)`
- `get_video_metadata(video_path)` — duration, fps, resolution, is_vfr
- Handle VFR video (common on mobile)

**Acceptance**: Extract 20 frames, timestamps match PTS within 1ms.

---

### T4.2 — Create video upload endpoint

**Goal**: Accept video + IMU JSON, extract frames, store session.

1. Add `video_scan_session` table to models.py
2. Add `upload_video_scan` endpoint with streamed 1MB-chunk writes
3. **Import Jules's modules** — use `quality_gate.check_video_quality()` as pre-filter, `frame_selector.select_best_frames()` for frame selection
4. Pull device_profile for camera intrinsics when available

**Acceptance**: Upload test video → session created → frames extracted → quality report returned.

---

## DEPENDENCY GRAPH

```
T0.1 (DB schema)    ─── DO FIRST
T0.2 (profile API)  ─── needs T0.1
T0.3 (dev mode)     ─── needs T0.2 (profile endpoints must exist)
T0.4 (questions)    ─── needs T0.2
          │
T1.1-T1.4 (viewer)  ── can start after T0.1 (independent of app changes)
          │
T2.1 (glTF export)  ── needs T1.1
T2.2 (wire API)     ── needs T0.1 + T2.1
          │
T3.1 (SMPL)         ── needs T0.1 (uses profile measurements)
T3.2 (SMPL API)     ── needs T2.2 + T3.1
          │
T4.1 (video)        ── independent
T4.2 (video API)    ── needs T0.1 + T4.1
```

**Recommended order**: T0.1 → T0.2 → T0.3 → T0.4 → T1.1 → T1.2 → T1.4 → T2.1 → T1.3 → T2.2 → T3.1 → T3.2 → T4.1 → T4.2

---

## FILES TO NEVER READ IN FULL

- `companion_app/lib/main.dart` — 1878 lines. Grep first.
- `web_app/controllers.py` — 1855 lines. Grep first.

## KEY COMMANDS

```bash
# Start server
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/Scripts/py4web.exe run apps --host 0.0.0.0 --port 8000

# Test viewer in browser
# http://localhost:8000/web_app/static/viewer3d/index.html

# Install new Python deps
/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe -m pip install pygltflib av

# Build APK
cd companion_app && flutter build apk --debug --target-platform android-arm64

# Install on phone
adb -s R58W41RF6ZK install -r build/app/outputs/flutter-apk/app-debug.apk

# Enable dev mode
adb -s R58W41RF6ZK shell 'echo "{\"dev_mode\":true}" > /data/local/tmp/muscle_tracker_dev.json'

# Push profile via ADB
adb -s R58W41RF6ZK shell 'echo "{\"height_cm\":175,\"weight_kg\":80}" > /data/local/tmp/muscle_tracker_profile.json'

# Force restart
adb -s R58W41RF6ZK shell "am force-stop com.example.companion_app && sleep 1 && am start -n com.example.companion_app/.MainActivity"
```

## USER'S REAL MEASUREMENTS (confirmed 2026-03-17)

### Body Profile — hardcode these as defaults
```
height_cm: 168
weight_kg: 63

# Segment lengths
shoulder_width_cm: 37              # edge to edge
neck_to_shoulder_cm: 15            # each side
shoulder_to_head_cm: 25
arm_length_cm: 80                  # finger to shoulder
upper_arm_length_cm: 35            # shoulder to elbow (derived: 80-45)
forearm_length_cm: 45              # finger to elbow
torso_length_cm: 50                # belly to shoulder
inseam_cm: 92                      # estimated (floor-to-knee 52 + knee-to-belly 40)
floor_to_knee_cm: 52
knee_to_belly_cm: 40
back_buttock_to_knee_cm: 61.6

# Circumferences
head_circumference_cm: 56
neck_circumference_cm: 35
chest_circumference_cm: 97
bicep_circumference_cm: 32
forearm_circumference_cm: 29
hand_circumference_cm: 21          # palm
waist_circumference_cm: 90         # below belly
hip_circumference_cm: 92           # buttock level
thigh_circumference_cm: 53         # upper thigh
quadricep_circumference_cm: 52
calf_circumference_cm: 34
```

### Device Setup — hardcode these as defaults
```
# Both devices sit on identical chairs
chair_height_cm: 50

# Samsung A24 — PORTRAIT (standing vertical on chair)
a24_camera_height_cm: 65           # chair 50 + device 15
a24_orientation: portrait
a24_serial: R58W41RF6ZK
a24_role: front
a24_distance_to_subject_cm: 100    # first scan; 50 for close-up second scan

# MatePad Pro — LANDSCAPE (lying on chair, better in landscape)
matepad_camera_height_cm: 65       # chair 50 + device 15
matepad_orientation: landscape
matepad_serial: 192.168.100.33:5555
matepad_role: back
matepad_distance_to_subject_cm: 100 # first scan; 50 for close-up second scan
```

### Environment
```
lighting: overhead_lamp             # powerful lamp directly above subject
clothing: small white shorts only (shirtless)
skin_tone: light brown (~#C4956A)
scan_strategy: two scans per session — 100cm (full body) then 50cm (close-up detail)
```

### All questions answered — profile complete!

### Dual-distance scan strategy:
- **Scan 1 at 100cm**: Full body framing, better for pose detection + proportions
- **Scan 2 at 50cm**: Close-up detail, better for muscle definition + circumference accuracy
- Compare both to find optimal distance for each measurement type
- Camera height is 65cm vs subject height 168cm → camera looks UP ~35 degrees at 100cm, ~50 degrees at 50cm
- Consider: the 50cm scan won't capture full body — only the region near camera height (roughly knee to chest)

### Skin tone for PBR material:
- Light brown (~#C4956A) — use this in T1.2 skin material instead of generic 0xd4a574
- White shorts will appear in body segmentation — need to handle: only shorts, light color, may confuse skin detection

### Pre-built dev profile files:
- `scripts/dev_profiles/default_human_profile.json` — all body measurements
- `scripts/dev_profiles/default_device_setup.json` — both device configs

These files are pushed to devices via ADB as `/data/local/tmp/muscle_tracker_profile.json`
