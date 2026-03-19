# Photorealistic Rendering Pipeline — Implementation Plan

**Status:** Draft
**Date:** 2026-03-19
**Scope:** Frontend viewer (`body_viewer.js`) + Backend texture pipeline (`core/`)

---

## Problem Statement

The 3D body model currently looks plastic/waxy despite having:
- MeshPhysicalMaterial with SSS, sheen, clearcoat
- Real-ESRGAN 4x upscaled textures (up to 4096px)
- Procedural skin normal/roughness maps
- ACES tone mapping + studio lighting presets

**Root causes:**
1. **Double-lit textures** — phone photos contain baked room lighting; Three.js lights the mesh again, creating conflicting shadows and highlights
2. **No micro-geometry** — procedural normal map has pore noise but at wrong scale (1024px tiled 5×5); real skin has multi-frequency detail that breaks up specular highlights
3. **Flat procedural environment** — PMREMGenerator builds a grey box with white planes; real skin needs complex high-frequency reflections to look convincing
4. **No ambient occlusion** — crevices (armpits, fingers, neck crease) have no contact shadows, making the mesh look like a floating mannequin

---

## Phase 1: Frontend Quick Wins (No Backend Changes)

**Impact:** High — immediately reduces plastic look
**Effort:** ~4 hours total
**Files:** `web_app/static/viewer3d/body_viewer.js`, `web_app/static/viewer3d/index.html`

### Task 1.1: HDRI Environment Map

**What:** Replace the procedural PMREMGenerator environment with a real studio HDRI.

**Why:** The current environment is 6 grey planes + 5 white rectangles. Human skin is a translucent, rough dielectric — its appearance is dominated by environment reflections at grazing angles. A real HDRI with complex light variation (soft gradients, bright spots, dark zones) makes the specular response look natural instead of uniformly smooth.

**How:**

1. Download a free studio HDRI from Poly Haven (e.g., `studio_small_09_1k.hdr` — neutral, no color cast):
   ```
   web_app/static/viewer3d/hdri/studio_small_09_1k.hdr  (~1.5 MB)
   ```

2. Add `RGBELoader` to the import map in `index.html` (line ~48):
   ```javascript
   // Already available via three/addons/ — no new dependency
   import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
   ```

3. Replace the procedural env generation (body_viewer.js lines 817-880) with:
   ```javascript
   function _buildEnvironment() {
       const pmrem = new THREE.PMREMGenerator(renderer);
       pmrem.compileEquirectangularShader();

       new RGBELoader()
           .setPath('./hdri/')
           .load('studio_small_09_1k.hdr', (hdrTexture) => {
               const envMap = pmrem.fromEquirectangular(hdrTexture).texture;
               scene.environment = envMap;
               // Don't set scene.background — keep dark UI background
               hdrTexture.dispose();
               pmrem.dispose();
           });
   }
   ```

4. Keep the procedural env as fallback if HDRI fails to load.

5. Add a "Neutral" lighting preset option that uses only the HDRI (no directional lights) for the most realistic look.

**Validation:** Load any GLB, switch to Studio preset. Specular highlights on shoulders and cheeks should show soft gradient transitions instead of uniform white dots.

---

### Task 1.2: Tiled Micro-Normal Map (Skin Pores)

**What:** Add a secondary, high-frequency tiled normal map that simulates skin pore micro-geometry.

**Why:** The current procedural normal (1024px, tiled 5×5) has pore-sized noise but it tiles visibly and lacks the characteristic cross-hatch pattern of real skin. A dedicated micro-normal breaks up specular highlights into thousands of tiny sparkles — the single most effective anti-plastic technique.

**How:**

1. Source a tileable skin pore normal map (256×256 or 512×512 PNG, tangent-space):
   - Free option: generate from a Perlin noise + Voronoi cell pattern
   - Better: use a CC0 skin pore texture from FreePBR or TextureCan
   - Save to: `web_app/static/viewer3d/textures/skin_pore_normal.png`

2. Load and apply as a detail normal in the material setup. Three.js r160 `MeshPhysicalMaterial` does NOT support a second normal map natively, so use a custom `onBeforeCompile` shader patch:

   ```javascript
   // In SKIN_MATERIAL creation (body_viewer.js ~line 452)
   const poreNormalTex = new THREE.TextureLoader().load('./textures/skin_pore_normal.png');
   poreNormalTex.wrapS = poreNormalTex.wrapT = THREE.RepeatWrapping;
   poreNormalTex.repeat.set(40, 56);  // High tile count for pore scale on 300-unit body

   SKIN_MATERIAL.userData.poreNormal = poreNormalTex;
   SKIN_MATERIAL.userData.poreNormalStrength = 0.3;

   SKIN_MATERIAL.onBeforeCompile = (shader) => {
       shader.uniforms.poreNormalMap = { value: poreNormalTex };
       shader.uniforms.poreNormalScale = { value: 0.3 };

       // Add uniform declarations after existing ones
       shader.fragmentShader = shader.fragmentShader.replace(
           '#include <normalmap_pars_fragment>',
           `#include <normalmap_pars_fragment>
           uniform sampler2D poreNormalMap;
           uniform float poreNormalScale;`
       );

       // Blend pore normal with base normal after normal map application
       shader.fragmentShader = shader.fragmentShader.replace(
           '#include <normal_fragment_maps>',
           `#include <normal_fragment_maps>
           {
               vec3 poreN = texture2D(poreNormalMap, vNormalMapUv * 8.0).xyz * 2.0 - 1.0;
               poreN.xy *= poreNormalScale;
               normal = normalize(normal + poreN);
           }`
       );
   };
   ```

3. Also apply this patch in the `_applyDefaultMaterial` function (line ~997) and the `_loadRealSkinTexture` material builder (line ~386) so real-texture mode also gets micro-pores.

4. Add a slider in the Scene tab for "Skin Detail" (0.0–1.0) that controls `poreNormalScale`.

**Validation:** Zoom into shoulder or forearm. Specular highlights should break into a granular pattern instead of a smooth white blob.

---

### Task 1.3: Tune SSS and Material Parameters

**What:** Adjust existing MeshPhysicalMaterial properties for more convincing skin.

**Why:** Current values are close but some are off:
- `transmission: 0.08` causes the mesh to be slightly see-through (visible on thin areas like ears)
- `clearcoat: 0.03` is too low to see any effect — either remove it or raise to 0.08+ for oily skin zones
- `sheen: 0.15` is good but `sheenRoughness: 0.7` is too rough (real skin peach fuzz is ~0.4)

**How:**

Update the SKIN_MATERIAL definition (body_viewer.js ~line 452):

```javascript
// BEFORE (current)                    // AFTER (tuned)
transmission:       0.08,              transmission:       0.02,      // Less transparency
thickness:          0.5,               thickness:          2.0,       // Thicker = more color absorption
attenuationColor:   (0.8, 0.25, 0.15), attenuationColor:  (0.85, 0.3, 0.18),  // Warmer blood tone
attenuationDistance: 0.5,              attenuationDistance: 3.0,      // Light travels further in skin
ior:                1.4,               ior:                1.38,      // Skin IOR (literature value)
sheen:              0.15,              sheen:              0.2,       // Slightly more fuzz
sheenRoughness:     0.7,               sheenRoughness:     0.4,      // Tighter fuzz highlights
clearcoat:          0.03,              clearcoat:          0.06,     // Visible oil layer
clearcoatRoughness: 0.4,              clearcoatRoughness: 0.3,      // Slightly sharper oil reflection
specularIntensity:  0.5,              specularIntensity:  0.4,      // Reduce direct specular
```

Also update the real-skin material builder (~line 386) with the same values.

**Validation:** Ears and thin areas should no longer look semi-transparent. Skin should have a subtle warm glow at grazing angles.

---

### Task 1.4: SSAO Post-Processing Pass

**What:** Add Screen Space Ambient Occlusion to darken crevices and contact areas.

**Why:** Without AO, the underside of arms, neck creases, inner thighs, and armpit areas are lit identically to exposed surfaces. This flatness screams "CG." SSAO adds depth cues that ground the body in 3D space.

**Effort:** Medium — requires refactoring the render loop to use EffectComposer.

**How:**

1. Import required modules (body_viewer.js top):
   ```javascript
   import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
   import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
   import { SSAOPass } from 'three/addons/postprocessing/SSAOPass.js';
   import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
   ```

2. Initialize composer after renderer setup (~line 503):
   ```javascript
   let composer;

   function _initPostProcessing() {
       composer = new EffectComposer(renderer);

       const renderPass = new RenderPass(scene, camera);
       composer.addPass(renderPass);

       const ssaoPass = new SSAOPass(scene, camera, window.innerWidth, window.innerHeight);
       ssaoPass.kernelRadius = 24;        // World-space radius (body is 300 units tall)
       ssaoPass.minDistance = 0.001;
       ssaoPass.maxDistance = 0.15;
       ssaoPass.output = SSAOPass.OUTPUT.Default;  // Blended
       composer.addPass(ssaoPass);

       const outputPass = new OutputPass();
       composer.addPass(outputPass);
   }
   ```

3. Replace `renderer.render(scene, camera)` in `_animate()` (line ~3236):
   ```javascript
   // OLD:
   renderer.render(scene, camera);

   // NEW:
   if (composer && _ssaoEnabled) {
       composer.render();
   } else {
       renderer.render(scene, camera);
   }
   ```

4. Handle resize — update composer size in the window resize handler:
   ```javascript
   if (composer) composer.setSize(window.innerWidth, window.innerHeight);
   ```

5. Add a toggle checkbox in the Scene tab: "Ambient Occlusion" (default: ON for Studio/Outdoor presets, OFF for Clinical).

**Caveats:**
- EffectComposer requires `preserveDrawingBuffer: true` (already set)
- The mirror CubeCamera render must still use `renderer.render()` directly (not composer) — no change needed since `_updateMirror()` already calls renderer directly
- SSAO adds ~2-4ms per frame on GPU; disable on mobile or low-end by checking `renderer.capabilities.maxTextureSize < 4096`
- SSAOPass needs a depth texture — may need `renderer.capabilities.isWebGL2` check

**Validation:** Switch to Studio preset. Armpits, neck crease, inner elbows, and where thighs meet torso should darken naturally.

---

## Phase 2: Backend Texture Improvements

**Impact:** High — fixes the fundamental double-lighting problem
**Effort:** ~8 hours total
**Files:** `core/texture_enhance.py`, `core/texture_projector.py`, `core/skin_texture.py`

### Task 2.1: Delighting Pass (Remove Baked Lighting from Photos)

**What:** Add a high-pass delighting filter that removes low-frequency lighting gradients from projected photo textures, leaving only the intrinsic skin color (albedo).

**Why:** Phone photos taken at 1m distance contain room lighting — overhead lights create a bright forehead/dark chin gradient, side windows create left/right imbalance. When this baked-in lighting gets projected onto the mesh and then lit again by Three.js, you get double shadows (one from the photo, one from the 3D light). The result is either washed out (conflicting fill) or uncannily dark in shadow areas.

**How:**

Add a `delight_texture()` function to `core/texture_enhance.py`:

```python
def delight_texture(texture: np.ndarray, coverage_mask: np.ndarray = None,
                    sigma_ratio: float = 0.15) -> np.ndarray:
    """
    Remove low-frequency lighting from projected photo texture.

    Uses homomorphic filtering:
      1. Convert to log-space (separates illumination × reflectance)
      2. High-pass filter removes illumination (smooth gradients)
      3. Convert back — remaining signal is surface reflectance (albedo)

    Args:
        texture:       (H, W, 3) uint8 BGR
        coverage_mask: (H, W) float32, 0=gap, >0=covered (optional)
        sigma_ratio:   blur radius as fraction of image size (0.15 = good default)

    Returns:
        (H, W, 3) uint8 BGR — delighted albedo
    """
    import cv2
    import numpy as np

    h, w = texture.shape[:2]
    sigma = int(max(h, w) * sigma_ratio) | 1  # Ensure odd

    # Work in float LAB space to preserve color
    lab = cv2.cvtColor(texture, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]

    # Log-space high-pass on luminance only (preserve chrominance)
    L_log = np.log1p(L)
    L_blur = cv2.GaussianBlur(L_log, (sigma, sigma), 0)
    L_highpass = L_log - L_blur

    # Rescale to target mean luminance (128 = middle grey in LAB)
    L_new = np.expm1(L_highpass)
    L_new = (L_new - L_new.min()) / (L_new.max() - L_new.min() + 1e-6) * 200 + 28

    # Blend: 70% delighted + 30% original (preserve some natural variation)
    lab[:, :, 0] = L_new * 0.7 + L * 0.3

    # Slight desaturation of extreme chrominance (removes colored light tints)
    ab_center = 128.0
    lab[:, :, 1] = (lab[:, :, 1] - ab_center) * 0.85 + ab_center
    lab[:, :, 2] = (lab[:, :, 2] - ab_center) * 0.85 + ab_center

    result = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)

    # Only apply to covered regions
    if coverage_mask is not None:
        mask = (coverage_mask > 0).astype(np.float32)[:, :, None]
        result = (result * mask + texture * (1 - mask)).astype(np.uint8)

    return result
```

**Integration point** in `controllers.py` `generate_body_model()` (~line 2652), BEFORE the enhance call:

```python
# After project_texture, before enhance_texture_atlas:
from core.texture_enhance import delight_texture
texture = delight_texture(texture, coverage_mask=coverage)
texture = enhance_texture_atlas(texture, coverage, upscale=True, ...)
```

**Validation:** Compare GLB output with/without delighting. The delighted version should have uniform brightness across front-lit and side-lit regions. Skin color should be preserved.

---

### Task 2.2: Per-Region Roughness Map

**What:** Generate a roughness map that varies by body region instead of the current uniform 0.6 ± noise approach.

**Why:** Real skin roughness varies significantly:
- Forehead/nose: 0.3–0.4 (oily, glossy T-zone)
- Lips: 0.2–0.3 (wet, very glossy)
- Elbows/knees: 0.7–0.8 (dry, rough)
- Palms/soles: 0.8–0.9 (very rough, thick skin)
- Standard skin: 0.55–0.65

A uniform roughness value is one of the most obvious tells of CG skin.

**How:**

Add to `core/skin_texture.py`:

```python
# Roughness values per SMPL body part ID
REGION_ROUGHNESS = {
    0: 0.60,   # torso
    1: 0.55,   # upper arms
    2: 0.65,   # forearms
    3: 0.75,   # hands
    4: 0.55,   # upper legs
    5: 0.65,   # lower legs
    6: 0.80,   # feet
    7: 0.45,   # head/face (oilier)
    8: 0.70,   # neck
}

def generate_regional_roughness_map(vertices, faces, uvs, body_part_ids,
                                     atlas_size=1024):
    """
    Rasterize a roughness map where each texel gets the roughness
    value of its corresponding body region, with smooth transitions.
    """
    import cv2
    import numpy as np

    roughness = np.full((atlas_size, atlas_size), 155, dtype=np.uint8)  # 0.6 default

    # Rasterize each triangle with its body part roughness
    for fi in range(len(faces)):
        v0, v1, v2 = faces[fi]
        part = body_part_ids[v0]
        r_val = int(REGION_ROUGHNESS.get(part, 0.6) * 255)

        uv_tri = (uvs[[v0, v1, v2]] * atlas_size).astype(np.int32)
        cv2.fillConvexPoly(roughness, uv_tri, r_val)

    # Smooth transitions between regions (no hard edges)
    roughness = cv2.GaussianBlur(roughness, (31, 31), 0)

    # Add micro-variation noise
    noise = np.random.randint(-8, 9, roughness.shape, dtype=np.int16)
    roughness = np.clip(roughness.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return roughness
```

**Integration:** Call in `generate_body_model()` after UV computation, embed as a separate texture in the GLB (roughnessMetallicTexture channel).

---

### Task 2.3: Improved Normal Map from Depth

**What:** Use Depth Anything V2 output (already computed in pipeline step 4) to generate a higher-quality normal map that captures body-scale surface variation.

**Why:** The current normal map (`mesh_reconstruction.py` lines 120-144) is computed from mesh geometry alone — it captures facet normals but misses photo-derived surface detail. The depth maps already exist in the pipeline but are only used for silhouette matching, not texture generation.

**How:**

```python
def depth_to_normal_map(depth_map, uvs, vertices, faces, atlas_size=1024):
    """
    Convert a metric depth map into a tangent-space normal map
    and bake it into UV atlas space.
    """
    import cv2
    import numpy as np

    h, w = depth_map.shape[:2]

    # Sobel gradients on depth
    dx = cv2.Sobel(depth_map, cv2.CV_32F, 1, 0, ksize=3)
    dy = cv2.Sobel(depth_map, cv2.CV_32F, 0, 1, ksize=3)

    # Normal from depth gradient: n = normalize(-dx, -dy, 1)
    normals = np.dstack([-dx, -dy, np.ones_like(dx)])
    norm = np.linalg.norm(normals, axis=2, keepdims=True)
    normals = normals / (norm + 1e-8)

    # Encode to tangent-space: [-1,1] -> [0,255]
    normal_img = ((normals * 0.5 + 0.5) * 255).astype(np.uint8)

    return normal_img  # (H, W, 3)
```

**Integration:** Blend depth-derived normals with geometry normals (50/50 weight) before embedding in GLB. This captures both macro shape (from mesh) and meso-scale surface detail (from depth estimation).

---

## Phase 3: Advanced Pipeline (Future)

**Impact:** Highest — AAA-quality skin
**Effort:** 20+ hours
**Prerequisite:** Phases 1 & 2 complete

### Task 3.1: Standardized SMPL UV Layout

**What:** Replace cylindrical projection UVs with the canonical SMPL UV layout.

**Why:** Anny already outputs 21,334 UV coordinates (line ~553 in smpl_fitting.py) from the MakeHuman topology. The current pipeline IGNORES these and recomputes cylindrical UVs in `uv_unwrap.py`. The Anny UVs have proper seam placement (hidden in armpits, inner legs, back of head) and uniform texel density. Switching to them would:
- Eliminate visible UV seams on the torso
- Enable pre-authored anatomical masks (fixed UV = fixed texel locations)
- Improve texture projection quality (less distortion)

**How:**

1. In `generate_body_model()` (~line 2633), check if Anny UVs exist in the mesh output:
   ```python
   if 'uvs' in mesh_data and mesh_data['uvs'] is not None:
       uvs = mesh_data['uvs']  # Use Anny's native UVs
   else:
       uvs = compute_uvs(vertices, body_part_ids)  # Fallback
   ```

2. Update `texture_projector.py` to handle the Anny UV layout (it currently assumes the 5-region atlas from `uv_unwrap.py`). The projection math is UV-agnostic, but the gap inpainting and seam blending assume rectangular regions. Needs rework.

3. Test with existing textures to verify no regression.

**Risk:** This changes the UV space for ALL generated models, so any cached textures or pre-authored masks would break. Should be done as a clean cut with cache invalidation.

---

### Task 3.2: Pre-Authored Anatomical Masks

**What:** With standardized UVs (Task 3.1), overlay pre-painted anatomical detail maps:
- Subtle redness zones (knuckles, knees, elbows, nose tip)
- Baked ambient occlusion (navel, armpits, ear canals)
- Roughness variation masks (T-zone, palms)

**How:** Author these as 2048×2048 PNG overlays in the SMPL UV layout. Blend on top of the projected photo texture with low opacity (10-20%) to add anatomical realism without overriding the individual's skin appearance.

---

### Task 3.3: Neural Delighting (Optional Upgrade)

**What:** Replace the homomorphic filter (Task 2.1) with a learned delighting model.

**Options:**
- **Lumos** (Google, 2022): Single-image relighting/delighting, runs on CPU
- **Total Relighting** (Google, 2021): Higher quality but heavier
- **SwitchLight** (2024): State-of-art, but requires GPU

**When:** Only if the homomorphic filter proves insufficient — it should handle 80% of cases well enough.

---

## Implementation Order

| Priority | Task | Phase | Impact | Effort | Dependencies |
|----------|------|-------|--------|--------|-------------|
| 1 | 1.1 HDRI Environment | Frontend | High | 30 min | Download 1 HDRI file |
| 2 | 1.3 Tune SSS Params | Frontend | Medium | 15 min | None |
| 3 | 1.2 Micro-Normal Map | Frontend | High | 2 hours | Source/generate pore texture |
| 4 | 2.1 Delighting Pass | Backend | High | 3 hours | None |
| 5 | 1.4 SSAO Pass | Frontend | Medium | 3 hours | EffectComposer refactor |
| 6 | 2.2 Regional Roughness | Backend | Medium | 2 hours | UV + body_part_ids |
| 7 | 2.3 Depth Normal Map | Backend | Medium | 3 hours | Depth Anything output |
| 8 | 3.1 SMPL UV Layout | Backend | High | 8 hours | Texture projector rework |
| 9 | 3.2 Anatomical Masks | Both | Medium | 6 hours | Task 3.1 |
| 10 | 3.3 Neural Delight | Backend | Low | 8+ hours | Task 2.1 evaluation |

---

## File Change Map

```
MODIFIED:
  web_app/static/viewer3d/body_viewer.js    — Tasks 1.1–1.4 (env, material, SSAO)
  web_app/static/viewer3d/index.html         — New imports, UI controls
  core/texture_enhance.py                    — Task 2.1 (delight_texture)
  core/skin_texture.py                       — Task 2.2 (regional roughness)
  core/mesh_reconstruction.py                — Task 2.3 (depth normals), embed roughness texture
  web_app/controllers.py                     — Wire delighting + roughness into pipeline

NEW:
  web_app/static/viewer3d/hdri/studio_small_09_1k.hdr   — Task 1.1
  web_app/static/viewer3d/textures/skin_pore_normal.png  — Task 1.2
```

---

## Testing Checklist

- [ ] Load GLB with NO texture (procedural skin) — verify HDRI reflections + pore detail
- [ ] Load GLB with projected photo texture — verify no double-lighting artifacts
- [ ] Switch all 3 lighting presets — verify SSAO integrates with each
- [ ] Zoom to face/hands/feet — verify micro-normal doesn't tile visibly
- [ ] Check performance: FPS should stay above 30 on integrated GPU with SSAO
- [ ] Compare before/after screenshots at identical camera angles
- [ ] Verify mirror reflection still works with EffectComposer
- [ ] Test on Samsung A24 browser (low-end GPU) — SSAO should auto-disable
- [ ] Regenerate a body model with delighting — compare texture to non-delighted version
- [ ] Verify Clinical preset stays flat/even (no SSAO, minimal env contribution) for measurement accuracy
