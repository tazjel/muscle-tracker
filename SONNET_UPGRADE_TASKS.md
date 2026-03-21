# Sonnet Upgrade Tasks — Photorealism & Pipeline Quality

**Agent:** Sonnet | **Date:** 2026-03-22
**Server restart:** YES after Python changes | **Port:** 8000
**Python:** `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
**When done:** Commit with descriptive message to master branch.

> Goal: Upgrade gtd3d visual quality and pipeline defaults based on Phase 3 research
> findings. Six tightly scoped tasks — do them in order.

---

## CRITICAL RULES — READ BEFORE ANY TASK

1. **`onBeforeCompile` is BANNED** — body_viewer.js:628 says it breaks `MeshPhysicalMaterial`'s transmission/IOR shader code. The viewer uses canvas compositing instead.
2. **Do NOT use `transmission` or `thickness`** on the skin material — these make the mesh transparent (glass effect), NOT subsurface scattering. Skin is opaque.
3. **Always grep before reading** — `controllers.py` is 3200+ lines, `body_viewer.js` is 3800+ lines, `main.dart` is 2300+ lines.
4. **Test commands use `$PY`** — always set `PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe` first.
5. **Read `.agent/TOOLS_GUIDE.md`** for all verification tool usage.

---

## T1 — Default Atlas Resolution 1024 → 2048

**Effort:** 15 min | **Depends on:** Nothing | **Risk:** Low

### What to read
```bash
grep -n 'default=1024\|atlas_size.*1024\|texture_size.*1024' scripts/run_densepose_texture.py core/densepose_texture.py core/texture_factory.py
```

### What to do
1. Open `scripts/run_densepose_texture.py` line 36:
   ```python
   # BEFORE:
   parser.add_argument('--atlas', type=int, default=1024, help='Atlas resolution')
   # AFTER:
   parser.add_argument('--atlas', type=int, default=2048, help='Atlas resolution')
   ```

2. Check `core/densepose_texture.py` — if any function has `texture_size=1024` as default, change to `texture_size=2048`.

3. Check `core/texture_factory.py` — if any function has `atlas_size=1024` as default, change to `atlas_size=2048`.

4. Do NOT change any other defaults (e.g., in `core/texture_bake.py` or `controllers.py` — those are set per-call).

### Test
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY scripts/run_densepose_texture.py --help 2>&1 | grep atlas
# Should show: default=2048
```

### DO NOT
- Change body_viewer.js
- Change export_glb
- Change any resolution that's passed as a function argument (only change defaults)

---

## T2 — Wrap-Lighting SSS via Additive Overlay Mesh

**Effort:** 2 hours | **Depends on:** Nothing | **Risk:** Medium

### Context
The skin currently looks "plastic" because there's no subsurface light scattering. We can't use `onBeforeCompile` (banned) or `transmission` (wrong effect). Instead, we add a SECOND transparent mesh that renders a warm glow at shadow edges.

### What to read
```bash
grep -n 'SKIN_MATERIAL\|realSkinMat\|pbrMat\|bodyMesh\|loadModel' web_app/static/viewer3d/body_viewer.js | head -20
```
Focus on:
- `SKIN_MATERIAL` definition (line ~602)
- Where the GLB mesh is loaded and material applied (~line 1280-1310)
- The `init()` function (~line 698)

### What to do
1. After the GLB mesh is loaded and `SKIN_MATERIAL` applied, add a subsurface overlay:

```javascript
// ── Subsurface Scattering Overlay ────────────────────────────────────────
// Second-pass mesh with additive blending for warm glow at shadow edges.
// Does NOT modify the main MeshPhysicalMaterial.
function _addSSSOverlay(mesh) {
  const sssUniforms = {
    uLightDir:    { value: new THREE.Vector3(0.5, 1.0, 0.3).normalize() },
    uSSSColor:    { value: new THREE.Color(0.8, 0.25, 0.15) }, // warm red
    uSSSStrength: { value: 0.35 },
    uWrap:        { value: 0.4 },
  };

  const sssMaterial = new THREE.ShaderMaterial({
    uniforms: sssUniforms,
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vWorldPos;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uLightDir;
      uniform vec3 uSSSColor;
      uniform float uSSSStrength;
      uniform float uWrap;
      varying vec3 vNormal;
      varying vec3 vWorldPos;
      void main() {
        float NdotL = dot(normalize(vNormal), uLightDir);
        // Wrap lighting: light bleeds into shadow side
        float wrapDiffuse = max(0.0, (NdotL + uWrap) / (1.0 + uWrap));
        // SSS is strongest where light is just below the surface (shadow edge)
        float sss = (1.0 - wrapDiffuse) * smoothstep(-0.3, 0.3, NdotL);
        vec3 color = uSSSColor * sss * uSSSStrength;
        gl_FragColor = vec4(color, sss * uSSSStrength * 0.6);
      }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.FrontSide,
  });

  mesh.traverse(child => {
    if (child.isMesh) {
      const overlay = new THREE.Mesh(child.geometry, sssMaterial);
      overlay.renderOrder = child.renderOrder + 1;
      overlay.name = 'sss_overlay';
      child.parent.add(overlay);
    }
  });

  // Expose for UI sliders
  window.setSSSStrength = (val) => { sssUniforms.uSSSStrength.value = val; };
  window.setSSSColor = (hex) => { sssUniforms.uSSSColor.value.set(hex); };
}
```

2. Call `_addSSSOverlay(bodyMesh)` right after the GLB model is loaded and added to the scene.

3. Find where `bodyMesh` is set (grep for `bodyMesh =` or `bodyMesh=`). Add the call after the mesh is positioned.

4. Sync the `uLightDir` uniform with the scene's directional light. Find the main directional light (grep `DirectionalLight`) and update `uLightDir` in the render loop or when light changes.

### Test
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY scripts/agent_browser.py viewer3d skin_densepose.glb --rotate 0,90,180,270
# Compare: shadow edges should have warm red-ish glow
```

### DO NOT
- Use `onBeforeCompile` (breaks MeshPhysicalMaterial)
- Modify `SKIN_MATERIAL` or `realSkinMat` or `pbrMat` properties
- Use `transmission` or `thickness` (glass effect, wrong for skin)
- Delete any existing code

---

## T3 — Improve Pore Normal Tiling Quality

**Effort:** 1 hour | **Depends on:** Nothing | **Risk:** Low

### What to read
```bash
grep -n '_applyPoreNormalPatch\|_poreNormal\|poreSize\|tilesX' web_app/static/viewer3d/body_viewer.js
```
Focus on function `_applyPoreNormalPatch` at line 652.

### What to do
The current pore tiling stamps a uniform 256px tile everywhere. This causes visible repetition. Upgrade:

1. **In `_applyPoreNormalPatch` (line 652):** Replace the uniform tiling loop with rotation-randomized tiling:

```javascript
// Replace the simple tile loop (lines 678-684) with:
const tileW = 192; // smaller tiles = less visible repetition
const tilesX = Math.ceil(size / tileW) + 1;
const tilesY = Math.ceil(size / tileW) + 1;

for (let y = 0; y < tilesY; y++) {
  for (let x = 0; x < tilesX; x++) {
    ctx.save();
    const cx = x * tileW + tileW / 2;
    const cy = y * tileW + tileW / 2;
    // Pseudo-random rotation per tile (deterministic from position)
    const angle = ((x * 7 + y * 13) % 4) * Math.PI / 2; // 0, 90, 180, 270°
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.drawImage(_poreNormalImg, -tileW / 2, -tileW / 2, tileW, tileW);
    ctx.restore();
  }
}
```

2. **Vary intensity by region:** After the tiling loop, optionally darken the pore overlay in regions that should be smoother (lips, eyelids). This is optional and can be done by drawing a semi-transparent rectangle over those UV regions.

### Test
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY scripts/agent_browser.py viewer3d skin_densepose.glb --rotate 0,45
# Zoom in close — pore pattern should NOT show visible grid repetition
```

### DO NOT
- Use `onBeforeCompile`
- Change material type
- Change `_poreNormalStrength` default (keep 0.3)

---

## T4 — Add Displacement Map to GLB Export

**Effort:** 1 hour | **Depends on:** Nothing | **Risk:** Low

### What to read
```bash
grep -n 'def export_glb\|displacement\|ao_map' core/mesh_reconstruction.py | head -15
grep -n 'displacement\|generate_displacement' core/texture_factory.py | head -10
grep -n 'displacement' scripts/run_densepose_texture.py
```

### What to do
1. **In `core/mesh_reconstruction.py` function `export_glb` (line 142):**
   Add `displacement_map=None` parameter alongside existing `ao_map=None`.

   After the AO map encoding block (~line 194-195), add:
   ```python
   disp_buf_idx = None
   if displacement_map is not None and uvs is not None:
       success_d, enc_d = cv2.imencode('.png', displacement_map)
       if success_d:
           disp_buf_idx = len(gltf['buffers'][0]['uri_data'])
           # ... same pattern as normal_map/roughness_map/ao_map encoding
   ```

   Note: glTF 2.0 does NOT have a standard displacement map extension. Store it as an extra texture in `material.extensions` or as `material.extras.displacementMap`. The viewer can read it from extras.

2. **In `scripts/run_densepose_texture.py`:**
   After generating the AO map, check if `texture_factory` produces a displacement map. If so, pass it to `export_glb(..., displacement_map=disp)`.

3. **In the viewer (`body_viewer.js`):** After loading a GLB, check for `material.extras.displacementMap` and apply it:
   ```javascript
   if (mat.userData && mat.userData.displacementMap) {
     mat.displacementMap = mat.userData.displacementMap;
     mat.displacementScale = 0.5;
   }
   ```

### Test
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY scripts/agent_verify.py meshes/skin_densepose.glb
# Should still PASS — displacement doesn't affect quality score
```

### DO NOT
- Modify vertex positions in the mesh
- Change existing normal_map/roughness_map/ao_map encoding
- Use KHR_materials_displacement (not widely supported)

---

## T5 — Ensure Canonical SMPL UV Is Default Everywhere

**Effort:** 1 hour | **Depends on:** Nothing | **Risk:** Medium

### What to read
```bash
grep -n 'canonical\|cylindrical\|uv_mode\|compute_uvs\|_load_canonical' core/smpl_direct.py core/uv_unwrap.py core/uv_canonical.py scripts/run_densepose_texture.py | head -30
```

### Context
- `core/smpl_direct.py` (line 27-33) already loads canonical SMPL UVs from `smpl_canonical_vert_uvs.npy`
- `core/uv_canonical.py` has `get_canonical_uvs()` that extracts UVs from `SMPL_NEUTRAL.pkl`
- `core/uv_unwrap.py` has cylindrical UV fallback
- `scripts/run_densepose_texture.py` may use cylindrical UVs from uv_unwrap
- SMPLitex (our next texture upgrade) REQUIRES canonical SMPL UVs

### What to do
1. **In `scripts/run_densepose_texture.py`:**
   - Add `--uv-mode` argument:
     ```python
     parser.add_argument('--uv-mode', choices=['canonical', 'cylindrical'],
                         default='canonical', help='UV layout (canonical for SMPLitex compat)')
     ```
   - Where UVs are computed, check `args.uv_mode`:
     ```python
     if args.uv_mode == 'canonical':
         from core.uv_canonical import get_canonical_uvs
         uvs = get_canonical_uvs()
         if uvs is None:
             logger.warning("Canonical UVs unavailable, falling back to cylindrical")
             from core.uv_unwrap import compute_uvs
             uvs = compute_uvs(verts)
     else:
         from core.uv_unwrap import compute_uvs
         uvs = compute_uvs(verts)
     ```

2. **Verify `core/smpl_direct.py`** already defaults to canonical (it does — line 340-343). No changes needed there.

3. **Verify `SMPL_NEUTRAL.pkl` exists** at `runpod/SMPL_NEUTRAL.pkl`. If not, the fallback to cylindrical must work silently.

### Test
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY scripts/run_densepose_texture.py --uv-mode canonical --atlas 2048 --help
# Verify the flag is listed

# If SMPL_NEUTRAL.pkl exists:
$PY -c "from core.uv_canonical import get_canonical_uvs; uvs=get_canonical_uvs(); print(f'Canonical UVs: {uvs.shape}' if uvs is not None else 'FALLBACK')"
```

### DO NOT
- Delete cylindrical UV support (keep as fallback)
- Modify `core/uv_canonical.py` (it works correctly)
- Remove the SMPL_NEUTRAL.pkl path from any file

---

## T6 — Photo Preflight Feedback in Flutter App

**Effort:** 2 hours | **Depends on:** Nothing | **Risk:** Medium

### What to read
```bash
grep -n 'CameraPreview\|StreamBuilder\|_cameraController\|_buildPreview\|captureImage' companion_app/lib/main.dart | head -20
```

### Context
Current photos FAIL preflight with LR brightness diff 25-46. Users have no idea their lighting is bad until after upload. Adding a real-time indicator during camera preview prevents bad captures.

### What to do
1. **In `main.dart`, find the camera preview widget** (grep for `CameraPreview` or the widget that shows the live camera feed).

2. **Add a periodic brightness checker** that runs every 500ms during preview:
   ```dart
   Timer? _lightnessTimer;

   void _startLightnessCheck() {
     _lightnessTimer = Timer.periodic(Duration(milliseconds: 500), (_) async {
       if (_cameraController == null || !_cameraController!.value.isInitialized) return;
       try {
         final image = await _cameraController!.takePicture();
         final bytes = await File(image.path).readAsBytes();
         final decoded = img.decodeImage(bytes);
         if (decoded == null) return;

         // Split into left and right halves
         final w = decoded.width;
         final h = decoded.height;
         double leftSum = 0, rightSum = 0;
         int leftCount = 0, rightCount = 0;

         for (int y = 0; y < h; y += 4) {  // sample every 4th pixel for speed
           for (int x = 0; x < w; x += 4) {
             final pixel = decoded.getPixel(x, y);
             final lum = (0.299 * pixel.r + 0.587 * pixel.g + 0.114 * pixel.b);
             if (x < w ~/ 2) { leftSum += lum; leftCount++; }
             else { rightSum += lum; rightCount++; }
           }
         }

         final leftAvg = leftSum / leftCount;
         final rightAvg = rightSum / rightCount;
         final diff = (leftAvg - rightAvg).abs();

         setState(() {
           _lightingQuality = diff < 15 ? 'good' : (diff < 25 ? 'warn' : 'bad');
           _lightingDiff = diff;
         });

         // Clean up temp file
         File(image.path).deleteSync();
       } catch (e) {
         // Silently ignore — preview check is best-effort
       }
     });
   }
   ```

3. **Add an overlay indicator** on the camera preview:
   ```dart
   Widget _buildLightingIndicator() {
     final color = _lightingQuality == 'good' ? Colors.green
                 : _lightingQuality == 'warn' ? Colors.orange
                 : Colors.red;
     final text = _lightingQuality == 'good' ? 'Lighting OK'
                : _lightingQuality == 'warn' ? 'Uneven lighting'
                : 'Bad lighting — face the light';
     return Positioned(
       top: 16, left: 16, right: 16,
       child: Container(
         padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
         decoration: BoxDecoration(
           color: color.withOpacity(0.8),
           borderRadius: BorderRadius.circular(8),
         ),
         child: Text(text, style: TextStyle(color: Colors.white, fontSize: 14)),
       ),
     );
   }
   ```

4. **Wire it up:** Call `_startLightnessCheck()` when camera preview starts, cancel `_lightnessTimer` when navigating away.

5. **Add `image` package** to `pubspec.yaml` if not already present:
   ```yaml
   dependencies:
     image: ^4.0.0
   ```

### Test
```bash
# Build and deploy
GTD="python C:/Users/MiEXCITE/Desktop/GTDdebug/gtddebug.py"
cd companion_app
/c/Users/MiEXCITE/development/flutter/bin/flutter.bat build apk --debug
$GTD agent-cycle dev --json
```

### DO NOT
- Run `flutter analyze`
- Use `flutter run` (use `flutter build apk --debug` + `adb install`)
- Modify server code
- Block the UI thread (the brightness check MUST be async)
- Take full-resolution photos for the check (use `takePicture` but sample sparsely)

---

## Task Dependencies & Order

```
T1 (15 min) ──→ independent, do first (quick win)
T2 (2 hours) ──→ independent (biggest visual impact)
T3 (1 hour) ──→ independent (improves close-up detail)
T4 (1 hour) ──→ independent (adds displacement to GLB)
T5 (1 hour) ──→ independent (unblocks SMPLitex)
T6 (2 hours) ──→ independent (prevents bad photo captures)
```

Recommended order: T1 → T5 → T3 → T2 → T4 → T6
(Quick wins first, then viewer upgrades, then Flutter)

## Verification After All Tasks

```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe

# 1. Atlas default is 2048
$PY scripts/run_densepose_texture.py --help 2>&1 | grep -i 'atlas.*2048'

# 2. Canonical UVs work
$PY -c "from core.uv_canonical import get_canonical_uvs; u=get_canonical_uvs(); print(u.shape if u is not None else 'NONE')"

# 3. Viewer loads (needs server running)
$PY scripts/agent_browser.py audit http://localhost:8000/web_app/static/viewer3d/index.html

# 4. GLB quality check
$PY scripts/agent_verify.py meshes/skin_densepose.glb
```
