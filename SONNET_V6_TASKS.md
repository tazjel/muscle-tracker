# V6 Task Sheet — Lighting Normalization, Normal Maps, Flutter WebView, Touch Gestures

> **For Sonnet execution only.** Read the full task before writing any code.
> Static files (JS/CSS/HTML) do NOT need server restart.
> Python changes (core/*.py, controllers.py) NEED server restart.

---

## P1 — Lighting Normalization for Texture Projection

### P1.1 — White Balance + Histogram Equalization per Camera View

**File**: `core/texture_projector.py` (149 lines)

**Goal**: Normalize each camera photo before sampling to reduce color shifts between views (e.g., warm front-light vs cool side-light).

**Where to edit**: Add a helper function before `project_texture()` (~line 17), then call it at the top of the per-view loop (~line 43).

**Code** — add after the imports (line 15):

```python
def _normalize_lighting(img):
    """White-balance + CLAHE on each camera view for consistent skin tone."""
    # Convert to LAB for perceptual uniformity
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # CLAHE on luminance only — preserves color, evens brightness
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)

    # Simple grey-world white balance on a/b channels
    a = cv2.add(a, int(128 - a.mean()))
    b = cv2.add(b, int(128 - b.mean()))

    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
```

**Where to call it**: Inside the `for view in camera_views:` loop, right after `img = view['image']` (line 43), add:

```python
        img = _normalize_lighting(img)
```

**Verification**:
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
import cv2, numpy as np
from core.texture_projector import _normalize_lighting
img = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
out = _normalize_lighting(img)
print('Shape:', out.shape, 'dtype:', out.dtype)
assert out.shape == img.shape
print('OK — lighting normalization works')
"
```

**Pitfalls**:
- `cv2.add` clamps to 0–255 automatically (no overflow risk)
- CLAHE clipLimit > 3.0 creates artifacts on skin
- This is applied BEFORE projection so it affects the final texture atlas

**Needs restart**: YES (Python change)

---

## P2 — Normal Map Export + Viewer Support

### P2.1 — Generate Normal Map in Python

**File**: `core/mesh_reconstruction.py` (304 lines)

**Goal**: Compute a tangent-space normal map from mesh geometry and embed it in the GLB alongside the color texture.

**Where to edit**: Add a new function after `_compute_smooth_normals()` (~line 117), before `export_glb()`.

**Code** — add after line 117:

```python
def _generate_normal_map(vertices, faces, uvs, atlas_size=1024):
    """
    Generate a tangent-space normal map from mesh geometry.
    Returns (atlas_size, atlas_size, 3) uint8 RGB image.
    """
    normal_map = np.full((atlas_size, atlas_size, 3), 128, dtype=np.uint8)  # flat normal = (128,128,255)
    normal_map[:, :, 2] = 255  # Z always up in tangent space

    normals = _compute_smooth_normals(vertices, faces)

    for fi in range(len(faces)):
        f = faces[fi]
        for vi in f:
            if uvs is None:
                continue
            uv = uvs[vi]
            tx = int(np.clip(uv[0] * (atlas_size - 1), 0, atlas_size - 1))
            ty = int(np.clip((1 - uv[1]) * (atlas_size - 1), 0, atlas_size - 1))
            n = normals[vi]
            # Tangent-space encoding: map [-1,1] → [0,255]
            normal_map[ty, tx, 0] = int(np.clip((n[0] * 0.5 + 0.5) * 255, 0, 255))  # R = X
            normal_map[ty, tx, 1] = int(np.clip((n[1] * 0.5 + 0.5) * 255, 0, 255))  # G = Y
            normal_map[ty, tx, 2] = int(np.clip((n[2] * 0.5 + 0.5) * 255, 0, 255))  # B = Z

    return normal_map
```

**Verification**:
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
import numpy as np
from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.mesh_reconstruction import _generate_normal_map
mesh = build_body_mesh()
uvs = compute_uvs(mesh['vertices'], mesh['body_part_ids'], DEFAULT_ATLAS)
nmap = _generate_normal_map(mesh['vertices'], mesh['faces'], uvs, atlas_size=256)
print('Normal map shape:', nmap.shape, 'dtype:', nmap.dtype)
print('Center pixel (should be ~128,128,255):', nmap[128, 128])
print('OK')
"
```

**Needs restart**: YES

---

### P2.2 — Embed Normal Map in GLB Export

**File**: `core/mesh_reconstruction.py` — `export_glb()` function (line 120)

**Goal**: Add `normal_map` parameter to `export_glb()`. When provided, embed it as a second PNG image and set it as the material's `normalTexture`.

**Where to edit**: Modify `export_glb()` signature and body.

**Step 1** — Change function signature (line 120):

```python
def export_glb(vertices, faces, output_path, normals=True,
               uvs=None, texture_image=None, normal_map=None):
```

**Step 2** — After the texture PNG block (after line 167), add normal map encoding:

```python
    # ── Normal map PNG ──────────────────────────────────────────────────────
    nmap_binary = b''
    if normal_map is not None and uvs is not None:
        success_n, enc_n = cv2.imencode('.png', normal_map)
        if success_n:
            nmap_binary = enc_n.tobytes()
            pad_n = (4 - len(nmap_binary) % 4) % 4
            nmap_binary += b'\x00' * pad_n
```

**Step 3** — Append `nmap_binary` to blob (line 170):

Change:
```python
    blob  = tris_binary + verts_binary + norms_binary + uvs_binary + png_binary
```
To:
```python
    blob  = tris_binary + verts_binary + norms_binary + uvs_binary + png_binary + nmap_binary
```

**Step 4** — After the color texture bufferView block (after line 241), add normal map bufferView:

```python
    if nmap_binary:
        buf_views.append(pygltflib.BufferView(
            buffer=0, byteOffset=offset, byteLength=len(nmap_binary),
        ))
        images.append(pygltflib.Image(
            mimeType='image/png', bufferView=len(buf_views) - 1,
        ))
        # Reuse sampler 0 if it exists, else add one
        if not samplers:
            samplers.append(pygltflib.Sampler(
                magFilter=pygltflib.LINEAR, minFilter=pygltflib.LINEAR_MIPMAP_LINEAR,
                wrapS=pygltflib.CLAMP_TO_EDGE, wrapT=pygltflib.CLAMP_TO_EDGE,
            ))
        textures.append(pygltflib.Texture(source=len(images) - 1, sampler=0))
        offset += len(nmap_binary)
```

**Step 5** — In the material section (~line 244), when building the PBR block for textured meshes, add `normalTexture`:

Change the material creation (line 264) to:

```python
    mat_kwargs = dict(pbrMetallicRoughness=pbr, doubleSided=True)
    if nmap_binary and len(textures) >= 2:
        mat_kwargs['normalTexture'] = pygltflib.NormalMaterialTexture(
            index=len(textures) - 1, scale=1.0
        )

    # ... then in the GLTF2 construction:
    materials=[pygltflib.Material(**mat_kwargs)],
```

**Verification**:
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY -c "
import numpy as np
from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.mesh_reconstruction import export_glb, _generate_normal_map
mesh = build_body_mesh()
uvs = compute_uvs(mesh['vertices'], mesh['body_part_ids'], DEFAULT_ATLAS)
nmap = _generate_normal_map(mesh['vertices'], mesh['faces'], uvs, atlas_size=256)
# Create a dummy texture
tex = np.full((256, 256, 3), 180, dtype=np.uint8)
export_glb(mesh['vertices'], mesh['faces'], 'meshes/test_normal.glb',
           uvs=uvs, texture_image=tex, normal_map=nmap)
import os
sz = os.path.getsize('meshes/test_normal.glb')
print(f'GLB with normal map: {sz} bytes')
assert sz > 50000
print('OK')
os.remove('meshes/test_normal.glb')
"
```

**Pitfalls**:
- Buffer offsets MUST stay 4-byte aligned — the pad calculation handles this
- `normalTexture` uses `NormalMaterialTexture` (not `TextureInfo`) — it has a `scale` field
- The texture index for the normal map is `len(textures) - 1` (second texture), not hardcoded `1`
- **Do NOT change** the non-textured material path (the `else` branch at line 250)

**Needs restart**: YES

---

### P2.3 — Wire Normal Map into generate_body_model

**File**: `web_app/controllers.py` — `generate_body_model()` at ~line 2229

**Goal**: Generate and pass normal map when texture is being projected.

**Where to edit**: Inside the texture projection block (~line 2344–2350), after `texture_image` is created.

**After** line 2348 (`logger.info('Texture projected from %d view(s)', len(cam_views))`), add:

```python
                    # Generate normal map for enhanced viewer lighting
                    try:
                        from core.mesh_reconstruction import _generate_normal_map
                        normal_map = _generate_normal_map(verts, faces, uvs_for_glb, atlas_size=1024)
                        logger.info('Normal map generated (1024x1024)')
                    except Exception:
                        normal_map = None
                        logger.warning('Normal map generation failed')
```

**Then** modify the export call at ~line 2359:

Change:
```python
                export_glb(verts, faces, glb_path,
                           uvs=uvs_for_glb, texture_image=texture_image)
```
To:
```python
                export_glb(verts, faces, glb_path,
                           uvs=uvs_for_glb, texture_image=texture_image,
                           normal_map=normal_map if 'normal_map' in dir() else None)
```

**Pitfalls**:
- `normal_map` variable may not exist if texture projection failed — use the `if 'normal_map' in dir()` guard or define `normal_map = None` before the `if silhouette_views:` block
- Better approach: define `normal_map = None` right after `uvs_for_glb = None` at line 2326

**Needs restart**: YES

---

### P2.4 — Viewer Normal Map Support (automatic)

**File**: `web_app/static/viewer3d/body_viewer.js` (1052 lines)

**Goal**: Three.js GLTFLoader automatically applies `normalTexture` from glTF materials — **no viewer code changes needed**. The `MeshStandardMaterial` created by GLTFLoader already supports normal maps out of the box.

**What to verify**: Load a GLB with normal map in the viewer and confirm the surface shows micro-detail shading.

**Verification**: After generating a textured model with normal map, open:
```
http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/api/mesh/<id>.glb
```
Toggle between Solid (no normals visible) and Textured (normal map active) to see the difference.

**No code changes. No restart.**

---

## P3 — Flutter WebView for In-App 3D Viewer

### P3.1 — Add webview_flutter Dependency

**File**: `companion_app/pubspec.yaml` (95 lines)

**Goal**: Add `webview_flutter` package for embedding the 3D viewer inside the app.

**Where to edit**: Under `dependencies:` section, after `share_plus: 10.1.0` (line 41).

**Add**:
```yaml
  webview_flutter: ^4.10.0
```

**Then run**:
```bash
cd C:/Users/MiEXCITE/Projects/muscle_tracker/companion_app && flutter pub get
```

**Pitfalls**:
- WebView requires `minSdkVersion 19` — MatePad Pro SDK 29 and A24 SDK 36 are both fine
- `webview_flutter` v4.x uses platform views (no external Chrome dependency)

---

### P3.2 — Add Android Internet Permission (if missing)

**File**: `companion_app/android/app/src/main/AndroidManifest.xml`

**Goal**: Ensure `<uses-permission android:name="android.permission.INTERNET"/>` is present. Flutter apps usually have it, but verify.

**Verification**:
```bash
grep -c "INTERNET" companion_app/android/app/src/main/AndroidManifest.xml
# Should print 1 or more
```

---

### P3.3 — Create ModelViewerScreen Widget

**File**: `companion_app/lib/main.dart` (~line 2136, after `LivePreviewScreen`)

**Goal**: Add a new `ModelViewerScreen` stateful widget that loads the 3D viewer URL in a WebView.

**Where to add**: After the `LivePreviewScreen` class (find `class LivePreviewScreen` at ~line 2005, its `State` class ends around ~line 2136). Add the new class after it.

**Code**:

```dart
class ModelViewerScreen extends StatefulWidget {
  final int meshId;
  final String? title;
  const ModelViewerScreen({super.key, required this.meshId, this.title});

  @override
  State<ModelViewerScreen> createState() => _ModelViewerScreenState();
}

class _ModelViewerScreenState extends State<ModelViewerScreen> {
  late final WebViewController _controller;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageFinished: (_) => setState(() => _loading = false),
      ))
      ..loadRequest(Uri.parse(
        '${AppConfig.serverBaseUrl}/static/viewer3d/index.html'
        '?model=/api/mesh/${widget.meshId}.glb'
        '&customer=${_customerId ?? "1"}'
      ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        title: Text(widget.title ?? '3D Body Model',
            style: const TextStyle(fontSize: 16)),
        backgroundColor: const Color(0xFF161B22),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_loading)
            const Center(child: CircularProgressIndicator(
              color: AppTheme.primaryTeal,
            )),
        ],
      ),
    );
  }
}
```

**Also add import** at the top of main.dart (after line 11):
```dart
import 'package:webview_flutter/webview_flutter.dart';
```

**Pitfalls**:
- `_customerId` is a file-level variable in main.dart (defined near login logic) — confirm it's accessible
- `WebViewController` must be created in `initState`, NOT in `build()`
- The viewer URL uses the same path as the desktop viewer — no special mobile endpoint needed
- Three.js WebGL works in Android WebView on SDK 29+ (both devices qualify)

**Needs server restart**: NO (Flutter change only)

---

### P3.4 — Navigate to ModelViewerScreen from ResultsScreen

**File**: `companion_app/lib/main.dart` — `ResultsScreen` class

**Goal**: Add a "View 3D" button in the results screen that opens the 3D viewer for the generated mesh.

**Where to edit**: In `_ResultsScreenState` (~line 1445), find the action buttons row. Grep for `View 3D` or `ReportViewerScreen` to find the buttons area (~line 1605).

**Near line 1605**, where there's already a "View Report" button, add another button:

```dart
              FilledButton.icon(
                onPressed: () {
                  final meshId = widget.result['mesh_id'];
                  if (meshId != null) {
                    Navigator.push(context, MaterialPageRoute(
                      builder: (_) => ModelViewerScreen(meshId: int.parse(meshId.toString())),
                    ));
                  }
                },
                icon: const Icon(Icons.view_in_ar, size: 18),
                label: const Text('VIEW 3D'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF1B5E20),
                  foregroundColor: Colors.white,
                ),
              ),
```

**Pitfalls**:
- `mesh_id` may not be in the scan result — only body_model endpoint returns it. Guard with null check.
- Use `int.parse(meshId.toString())` to handle both int and String from JSON

**Needs server restart**: NO

---

### P3.5 — Build and Install Updated APK

**Verification** (do NOT use `flutter run`):
```bash
cd C:/Users/MiEXCITE/Projects/muscle_tracker/companion_app
flutter build apk --debug

# Install on Samsung A24 (USB)
adb -s R58W41RF6ZK install -r build/app/outputs/flutter-apk/app-debug.apk

# Install on MatePad Pro (WiFi) — must uninstall first
adb -s 192.168.100.33:5555 uninstall com.example.companion_app
adb -s 192.168.100.33:5555 install build/app/outputs/flutter-apk/app-debug.apk
```

---

## P4 — Mobile Touch Gestures in 3D Viewer

### P4.1 — OrbitControls Already Supports Touch

**File**: `web_app/static/viewer3d/body_viewer.js` (1052 lines)

**Important**: Three.js `OrbitControls` already handles:
- **1-finger drag** = rotate
- **2-finger pinch** = zoom
- **2-finger drag** = pan

These work out of the box on mobile. **No code changes needed for basic touch.**

---

### P4.2 — Add Touch-Friendly UI Adjustments

**File**: `web_app/static/viewer3d/styles.css` (257 lines)

**Goal**: Make the UI overlay more touch-friendly on mobile (larger buttons, collapsible panel).

**Where to edit**: Add a `@media` block at the end of `styles.css`.

**Code** — append to end of file:

```css
/* ── Mobile touch optimizations ───────────────────────────────────────────── */
@media (max-width: 768px), (pointer: coarse) {
  #ui-overlay .card {
    max-width: 180px;
    padding: 8px;
    font-size: 11px;
    max-height: 70vh;
    overflow-y: auto;
  }

  .view-modes {
    flex-wrap: wrap;
    gap: 3px;
  }

  .view-mode-btn {
    min-width: 44px;
    min-height: 44px;
    font-size: 11px;
    padding: 6px 8px;
  }

  .controls button {
    min-width: 44px;
    min-height: 44px;
    font-size: 11px;
    padding: 6px;
  }

  #adjust-panel input[type="range"] {
    width: 70px;
    height: 28px;
  }

  .heatmap-legend {
    bottom: 10px;
    right: 10px;
    padding: 6px 10px;
    font-size: 10px;
  }

  #section-panel input[type="range"] {
    width: 80px;
  }

  #compare-panel select {
    width: 100px !important;
  }
}
```

**Verification**: Open the viewer URL on a phone browser or resize desktop browser to < 768px width. Buttons should be 44×44px minimum (Apple HIG touch target).

**Needs restart**: NO (static CSS file)

---

### P4.3 — Add Viewport Meta Tag

**File**: `web_app/static/viewer3d/index.html` (line 4)

**Goal**: Ensure the existing viewport meta tag disables user scaling (prevents browser zoom interfering with Three.js pinch-zoom).

**Where to edit**: Line 4 already has a viewport tag. Change it to:

```html
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
```

**Needs restart**: NO

---

### P4.4 — Prevent Default Touch on Canvas (Avoid Scroll Conflicts)

**File**: `web_app/static/viewer3d/body_viewer.js`

**Goal**: Prevent the browser from scrolling/zooming when the user touches the 3D canvas.

**Where to edit**: In `init()` function, after `renderer.domElement.addEventListener('click', _onMeshClick);` (~line 120).

**Add**:

```javascript
  // Prevent browser default touch behaviors (scroll, pinch-zoom) on the 3D canvas
  renderer.domElement.addEventListener('touchstart', (e) => e.preventDefault(), { passive: false });
  renderer.domElement.addEventListener('touchmove',  (e) => e.preventDefault(), { passive: false });
```

**Pitfalls**:
- Must use `{ passive: false }` — Chrome defaults to passive touch listeners on the document
- This only prevents defaults on the canvas element, not the UI overlay — so sliders/buttons still work
- OrbitControls adds its own touch listeners internally — this doesn't conflict

**Needs restart**: NO (static JS file)

---

### P4.5 — Double-Tap to Reset Camera

**File**: `web_app/static/viewer3d/body_viewer.js`

**Goal**: Add double-tap gesture to reset camera (mobile equivalent of pressing R).

**Where to edit**: In `init()`, after the touch prevention listeners from P4.4.

**Add**:

```javascript
  // Double-tap to reset camera (mobile convenience)
  let _lastTap = 0;
  renderer.domElement.addEventListener('touchend', (e) => {
    const now = Date.now();
    if (now - _lastTap < 300 && e.changedTouches.length === 1) {
      window.resetCamera();
    }
    _lastTap = now;
  });
```

**Pitfalls**:
- 300ms threshold is standard for double-tap detection
- Check `changedTouches.length === 1` to avoid triggering on pinch release
- Don't prevent default on `touchend` — it would break click events

**Needs restart**: NO

---

## Dependency Order

```
P1.1 — standalone Python (restart server after)
P2.1 → P2.2 → P2.3 — sequential Python (restart server once after P2.3)
P2.4 — verify only (no code change)
P3.1 → P3.2 → P3.3 → P3.4 → P3.5 — sequential Flutter
P4.1 — verify only
P4.2 + P4.3 + P4.4 + P4.5 — independent static file changes (no restart)
```

**Optimal execution order**:
1. P1.1 + P2.1 + P2.2 (Python core)
2. P2.3 (controllers.py — needs P2.1 + P2.2)
3. Restart server ONCE
4. P4.2 + P4.3 + P4.4 + P4.5 (static files, parallel)
5. P3.1 → P3.3 → P3.4 → P3.5 (Flutter, sequential)
6. Test everything
