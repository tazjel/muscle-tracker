# 3D Human Reconstruction — Development Roadmap

**Goal**: Generate a realistic 3D human body from profile measurements, refine it with camera captures, apply real skin texture, and let the user correct inaccuracies interactively.

**Date**: 2026-03-17
**Current state**: Parametric body mesh working (13 ellipsoid rings, ~400 vertices). GLB export, Three.js viewer, dual-device scanning all functional. Volume/circumference measurements validated.

---

## What Exists Today (Done)

| Component | Status | Notes |
|-----------|--------|-------|
| Parametric body mesh (`core/smpl_fitting.py`) | Working | 13 anatomical rings from user's measurements |
| GLB/OBJ export (`core/mesh_reconstruction.py`) | Working | PBR material, binary glTF |
| Three.js viewer (`viewer3d/body_viewer.js`) | Working | r160, OrbitControls, PBR skin, heatmap, measurement pins |
| Body profile API | Working | GET/POST all 22 measurements |
| Device profile API | Working | Store camera intrinsics per device |
| Dual-device scanning | Working | Samsung A24 (front) + MatePad Pro (back) |
| Body segmentation | Working | MediaPipe selfie segmenter |
| Pose landmarks | Working | MediaPipe 33-point pose |
| Volume computation | Working | Elliptical cylinder from front+side |

---

## Phase 1 — Anatomically Accurate Body Mesh

**Problem**: The current mesh is a stack of 13 elliptical cylinders. It has no shoulder definition, no knee shape, no chest curvature, and limbs are rough tubes. It doesn't look human.

**Goal**: A mesh that a user can recognize as *their* body shape — correct proportions, smooth surfaces, recognizable anatomy.

### T1.1 — High-Resolution Ring System

Upgrade `core/smpl_fitting.py` from 13 rings to 50+ rings with proper anatomical spacing.

- **Head**: 6 rings (chin → forehead → crown) with head circumference
- **Neck**: 3 rings (neck base → mid neck → skull base) tapering
- **Torso**: 12 rings (shoulder → chest peak → waist narrowing → hip flare → buttock)
- **Arms (each)**: 8 rings (shoulder cap → deltoid → bicep peak → elbow → forearm → wrist → hand)
- **Legs (each)**: 10 rings (hip socket → upper thigh → mid thigh → knee cap → below knee → calf peak → shin → ankle → foot)
- Increase segments per ring from 16 to 32 for smoother cross-sections
- Target: ~3,000–5,000 vertices (enough detail, still fast to generate)

**Key**: Use the existing measurement data to size each ring correctly:
- `chest_circumference_cm` → chest ring radii
- `waist_circumference_cm` → waist ring radii
- `hip_circumference_cm` → hip ring radii
- `thigh_circumference_cm` → upper thigh ring radii
- Interpolate between known circumferences for intermediate rings

**Files**: `core/smpl_fitting.py`

---

### T1.2 — Non-Circular Cross Sections

Real body cross-sections are NOT ellipses:
- **Chest**: wider than deep, flat back, rounded front
- **Waist**: roughly elliptical but with slight concavity at sides
- **Hips**: wider than deep, flat buttock plane
- **Thigh**: roughly circular but with quadricep bulge at front
- **Calf**: teardrop shape (gastrocnemius bulge at back)

Add cross-section shape templates per body region:
```
chest_shape:  superellipse(n=2.5) — flatter than circle
waist_shape:  ellipse with side concavity
hip_shape:    superellipse(n=2.2)
thigh_shape:  ellipse with anterior displacement
calf_shape:   offset circle (center shifted posterior)
```

Each ring uses a shape template + size from measurements.

**Files**: `core/smpl_fitting.py` (new function: `_shape_template(region, num_points)`)

---

### T1.3 — Limb Attachment and Joint Geometry

Current mesh has no proper arm/leg attachment. Arms and legs need to:
- Branch from the torso at shoulder/hip positions
- Have proper joint angles at elbows, knees
- Taper correctly at wrists, ankles
- Connect smoothly to torso (no gaps or pinching)

Implementation:
- Define attachment points from shoulder_width and hip measurements
- Each limb is a separate tube mesh, stitched to the torso at its root ring
- Default pose: arms slightly away from body (A-pose, ~30° abduction)
- Legs: slight natural stance (~10cm apart at ankles)
- Vertex welding at attachment boundaries for seamless mesh

**Files**: `core/smpl_fitting.py` (new functions: `_build_arm()`, `_build_leg()`, `_stitch_limb_to_torso()`)

---

### T1.4 — Mesh Smoothing and Normal Computation

Raw ring-stacked mesh has visible ridges. Apply:
1. **Catmull-Clark subdivision** (1 iteration) — doubles resolution, rounds edges
2. **Laplacian smoothing** (3-5 iterations, λ=0.3) — removes sharp transitions
3. **Proper vertex normals** — smooth shading in GLB (currently flat shaded)
4. **Watertight mesh check** — no holes, consistent winding order

Export updated normals in GLB accessor for proper lighting in viewer.

**Files**: `core/smpl_fitting.py`, `core/mesh_reconstruction.py` (add NORMAL accessor to GLB)

---

### T1.5 — Viewer: Body Part Labeling

Add clickable labels on the 3D mesh so the user knows what they're looking at:
- HTML overlay labels anchored to 3D joint positions
- Labels: Head, Neck, L/R Shoulder, Chest, L/R Bicep, L/R Forearm, Waist, Hip, L/R Thigh, L/R Calf
- Labels follow mesh rotation (3D→2D projection, same technique as measurement pins)
- Toggle labels on/off
- Clicking a label highlights that body region (semi-transparent other parts)

**Files**: `web_app/static/viewer3d/body_viewer.js` (new function: `addBodyLabels(jointPositions)`)

---

## Phase 2 — Silhouette-Guided Refinement

**Problem**: The parametric mesh uses only tape-measured circumferences. Cameras capture the actual silhouette contour which contains far more shape information (muscle bulges, asymmetries, posture).

**Goal**: Deform the parametric mesh so its projected silhouette matches the captured photos.

### T2.1 — Silhouette Extraction Pipeline

From each dual-device capture, extract clean body silhouette contours:
1. Run body segmentation on front, back, left-side, right-side images
2. Extract outer contour from segmentation mask
3. Convert contour to normalized coordinates (mm, using camera calibration)
4. Store as ordered 2D point arrays per view

**Files**: `core/silhouette_extractor.py` (new file)

---

### T2.2 — Mesh-to-Silhouette Projection

Project the 3D parametric mesh into 2D from each camera's viewpoint:
1. Use known camera intrinsics (focal_length_mm, sensor_width_mm from device_profile)
2. Use known camera position (distance, height from device_profile)
3. Render mesh silhouette from front/back/side viewpoints
4. Compare projected silhouette against captured silhouette
5. Compute silhouette difference (IoU, contour distance)

**Files**: `core/silhouette_matcher.py` (new file)

---

### T2.3 — Iterative Vertex Deformation

Optimize mesh vertex positions to minimize silhouette difference:
1. For each view, identify vertices whose projected outline differs from the photo outline
2. Push/pull those vertices to reduce contour error
3. Constrain: maintain mesh smoothness (Laplacian regularization)
4. Constrain: preserve volume approximately (no collapse)
5. Run 10-20 iterations, converging on the best-fit shape
6. Export refined mesh as new GLB

Algorithm: Simple gradient-free optimization — for each boundary vertex visible from a camera view, compute the offset needed to align its projection with the nearest photo contour point. Apply damped (0.3×) to avoid oscillation.

**Files**: `core/silhouette_matcher.py` (function: `refine_mesh_to_silhouettes()`)

---

### T2.4 — Multi-View Consistency

The mesh must look correct from ALL views simultaneously, not just one:
- Alternate optimization across views (1 iteration front, 1 back, 1 left, 1 right)
- Weight views by confidence (clearer segmentation = higher weight)
- Log per-view silhouette IoU to show convergence
- Return final per-view IoU scores so user knows which views matched best

**Files**: `core/silhouette_matcher.py`

---

## Phase 3 — Skin Texture Capture and Application

**Problem**: The mesh has a flat PBR color (#C4956A). The user wants to see their actual skin appearance — color variations, moles, hair, muscle definition shadows.

**Goal**: Camera captures are UV-mapped onto the 3D mesh as a diffuse texture.

### T3.1 — UV Unwrapping the Body Mesh

Create a UV parameterization for the body mesh:
1. **Cylindrical projection** per body segment (torso, each arm, each leg, head)
2. Seams: inner arms, inner legs, back midline (least visible areas)
3. Pack UV islands into a single 2048×2048 texture atlas
4. Store UV coordinates as TEXCOORD_0 in the GLB file

**Files**: `core/uv_unwrap.py` (new file), `core/mesh_reconstruction.py` (add TEXCOORD_0 accessor)

---

### T3.2 — Photo-to-Texture Projection

Project camera photos onto the UV texture map:
1. For each camera view (front, back, left, right):
   - Determine which mesh faces are visible from that camera angle
   - For each visible face, sample the photo pixel at the projected UV coordinate
   - Write sampled color into the texture atlas at the face's UV position
2. Handle occlusion: only paint faces that face the camera (dot product check)
3. Handle overlap: when multiple views cover the same UV region, blend using view angle (prefer faces that face the camera most directly)

**Files**: `core/texture_projector.py` (new file)

---

### T3.3 — Lighting Normalization

Camera photos include shadows, uneven lighting, and color casts. Remove these before texturing:
1. Estimate illumination per photo using body segmentation mask (compute mean brightness gradient across body)
2. Apply inverse illumination to flatten lighting
3. White-balance using the white shorts as a known reference
4. Optionally: median filter to reduce noise in texture

**Files**: `core/texture_projector.py` (function: `normalize_lighting()`)

---

### T3.4 — Texture Export in GLB

Embed the texture atlas into the GLB file:
1. Add a `baseColorTexture` to the PBR material (instead of flat `baseColorFactor`)
2. Encode texture as embedded PNG in the GLB binary buffer
3. Update viewer to use textured material when texture is present, fall back to solid color when not

**Files**: `core/mesh_reconstruction.py` (update `export_glb`), `web_app/static/viewer3d/body_viewer.js`

---

### T3.5 — Viewer: Texture Toggle

Add viewer controls:
- **Solid** mode: flat skin color (current behavior)
- **Textured** mode: camera-captured texture
- **Wireframe** mode: mesh topology visible
- **Heatmap** mode: growth visualization

**Files**: `web_app/static/viewer3d/body_viewer.js`

---

## Phase 4 — Interactive User Feedback

**Problem**: Even with silhouette matching, the mesh won't be perfect. The user needs to identify what's wrong and the system needs to fix it.

**Goal**: Click-to-adjust interface where the user corrects body shape errors.

### T4.1 — Region Selection by Click

User clicks on the 3D mesh → system identifies which body region was clicked:
1. Raycast from click point into mesh (already implemented in body_viewer.js)
2. Map hit vertex to body region (torso, L-arm, R-leg, etc.) using vertex zone tags
3. Highlight selected region (glow/outline effect)
4. Show region name and current measurements in info panel

**Files**: `web_app/static/viewer3d/body_viewer.js`

---

### T4.2 — Shape Adjustment Controls

When a region is selected, show adjustment sliders:
- **Width** (make this part wider/narrower): modifies the circumference at that level
- **Depth** (front-to-back thickness): modifies the ellipse ratio
- **Length** (make this segment longer/shorter): adjusts ring spacing
- **Position** (shift left/right/forward/back): moves the segment center

Controls are HTML sliders overlaid on the viewer. Changes apply in real-time to the mesh preview (vertex deformation via JavaScript, no server round-trip).

**Files**: `web_app/static/viewer3d/body_viewer.js`, `web_app/static/viewer3d/styles.css`

---

### T4.3 — Save Adjustments as Measurement Overrides

When user finishes adjusting:
1. Convert vertex deltas back to measurement changes (e.g., "thigh circumference +2cm")
2. POST updated measurements to `/api/customer/{id}/body_profile`
3. Re-generate full mesh on server with new measurements
4. Reload in viewer to confirm

This creates a refinement loop: adjust → save → regenerate → review → adjust again.

**Files**: `web_app/static/viewer3d/body_viewer.js`, `web_app/controllers.py`

---

### T4.4 — Comparison View

Show before/after when user makes changes:
- Side-by-side: original mesh (left) vs adjusted mesh (right)
- Overlay: semi-transparent overlay showing differences
- Delta stats: "Chest: 97cm → 99cm (+2cm)"

**Files**: `web_app/static/viewer3d/body_viewer.js`

---

## Phase 5 — Texture Quality and Detail

### T5.1 — Close-Up Detail Capture

Use the 50cm close-up scan for higher-resolution texture on specific body parts:
- Detect which body region the close-up covers (using pose landmarks)
- Supersample that region in the texture atlas (allocate more UV space)
- Blend with the full-body texture from 100cm scan

---

### T5.2 — Normal Map from Photos

Extract skin surface detail (muscle definition, veins, wrinkles) as a normal map:
1. Convert close-up photos to grayscale
2. Apply Sobel filter to estimate surface orientation
3. Encode as tangent-space normal map
4. Embed in GLB as `normalTexture`
5. Viewer renders with normal mapping for visual muscle definition

---

### T5.3 — Region-Specific Texture Quality

Not all body parts need the same texture resolution:
- Face, arms, chest: high detail (visible, care about appearance)
- Back: medium detail (less self-scrutiny)
- Clothing-covered areas: skip or use solid color fill

Allocate UV space proportional to expected user interest.

---

## Dependency Graph

```
Phase 1 (Better Mesh)
  T1.1 High-res rings
  T1.2 Non-circular cross sections  ← needs T1.1
  T1.3 Limb attachment              ← needs T1.1
  T1.4 Smoothing + normals          ← needs T1.2, T1.3
  T1.5 Body part labels             ← needs T1.3

Phase 2 (Silhouette Refinement)     ← needs Phase 1 complete
  T2.1 Silhouette extraction
  T2.2 Mesh projection              ← needs T2.1
  T2.3 Vertex deformation           ← needs T2.2
  T2.4 Multi-view consistency       ← needs T2.3

Phase 3 (Skin Texture)              ← needs Phase 1 complete
  T3.1 UV unwrapping
  T3.2 Photo projection             ← needs T3.1
  T3.3 Lighting normalization        ← needs T3.2
  T3.4 Texture in GLB               ← needs T3.2
  T3.5 Viewer texture toggle        ← needs T3.4

Phase 4 (User Feedback)             ← needs Phase 1 + viewer
  T4.1 Region selection
  T4.2 Adjustment controls          ← needs T4.1
  T4.3 Save overrides               ← needs T4.2
  T4.4 Comparison view              ← needs T4.3

Phase 5 (Texture Detail)            ← needs Phase 3
  T5.1 Close-up detail
  T5.2 Normal maps                  ← needs T5.1
  T5.3 Region-specific quality      ← needs T5.1
```

**Phase 2 and Phase 3 can run in parallel** — silhouette matching and texture capture are independent.
**Phase 4 can start as soon as Phase 1 is done** — feedback UI doesn't need texture.

---

## Recommended Execution Order

1. **T1.1** → **T1.2** → **T1.3** → **T1.4** → **T1.5** (mesh looks human)
2. **T4.1** → **T4.2** (user can click + adjust — fast feedback even before texture)
3. **T3.1** → **T3.2** → **T3.3** → **T3.4** → **T3.5** (skin texture from cameras)
4. **T2.1** → **T2.2** → **T2.3** → **T2.4** (silhouette refinement for accuracy)
5. **T4.3** → **T4.4** (save adjustments, comparison)
6. **T5.1** → **T5.2** → **T5.3** (polish)

---

## Key Technical Decisions

1. **No neural network for body model** — parametric rings + measurements + silhouette deformation. Runs on any machine, no GPU needed, instant generation.
2. **Texture from real photos** — not synthesized. Camera captures at 75-100cm provide real skin appearance.
3. **Client-side shape editing** — adjust mesh in JavaScript for instant preview, server regenerates for persistence.
4. **Single GLB file per model** — mesh + material + texture + normals all in one binary file. Easy to cache, serve, and load.
5. **UV seams on inner surfaces** — inner arms, inner legs, back midline — least visible to the user in default viewing angle.
6. **Dual-distance capture** — 100cm for full silhouette matching, 50cm for texture detail on target muscle group.

---

## Files to Create

| File | Phase | Purpose |
|------|-------|---------|
| (upgrade) `core/smpl_fitting.py` | 1 | High-res anatomical mesh |
| `core/silhouette_extractor.py` | 2 | Clean contour from photos |
| `core/silhouette_matcher.py` | 2 | Deform mesh to match contours |
| `core/uv_unwrap.py` | 3 | UV parameterization |
| `core/texture_projector.py` | 3 | Photo → texture atlas |
| (upgrade) `core/mesh_reconstruction.py` | 1,3 | Normals, UV, texture in GLB |
| (upgrade) `web_app/static/viewer3d/body_viewer.js` | 1,3,4 | Labels, texture, feedback UI |
| (upgrade) `web_app/static/viewer3d/styles.css` | 4 | Adjustment panel styling |
| (upgrade) `web_app/controllers.py` | 4 | Feedback save endpoint |
