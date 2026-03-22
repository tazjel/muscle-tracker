# Sonnet Implementation Tasks — gtd3d Research-Informed Upgrades (v2)

Generated: 2026-03-22 | Source: Gemini Research Phases 1-5 + Codebase Audit
Previous Sonnet tasks: `SONNET_TASKS.md` (T1-T10: 2D silhouette pipeline) — still valid, these are ADDITIONAL.

---

## Rules for Sonnet

- **Python**: `/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe`
- **Server restart required** after any `core/*.py` or `web_app/*.py` changes
- **Always grep before reading** — `controllers.py` is 2200+ lines, `main.dart` is 1900+ lines
- **Run `photo_preflight.py` before pipeline, `agent_verify.py` after** — always
- **Do NOT use MCP tools** — use project scripts or create new ones in `scripts/`
- **Do NOT run `flutter analyze`**
- **Commit after each task completes** — descriptive message, no batching
- **Read `.agent/TOOLS_GUIDE.md`** for all verification tool usage
- **`onBeforeCompile` is BANNED** in viewer JS (breaks MeshPhysicalMaterial)

---

## S-U1: LAB Color Harmonization for Multi-View Texture

**Priority**: URGENT | **Effort**: Small (< 30 min) | **Depends on**: Nothing

**Problem**: Color shifts between front/back/side photos create visible seams on the UV atlas.

**What to build**: Pre-process all camera views to match the front photo's color before UV baking.

**File to edit**: `core/densepose_texture.py`
- Grep for `def.*bake` and `def.*inpaint` to find where multi-view photos are combined
- Add `harmonize_view()` function BEFORE views enter UV baking

**Exact algorithm** (from `research/task7_texture_seam_fix.md` — "Approach #1"):
```python
import cv2, numpy as np

def harmonize_view(source_bgr, anchor_bgr):
    """Match source photo colors to anchor (front) photo using LAB space."""
    src_lab = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2LAB).astype("float32")
    tar_lab = cv2.cvtColor(anchor_bgr, cv2.COLOR_BGR2LAB).astype("float32")
    for i in range(3):
        src_mu, src_sigma = src_lab[:,:,i].mean(), src_lab[:,:,i].std()
        tar_mu, tar_sigma = tar_lab[:,:,i].mean(), tar_lab[:,:,i].std()
        if src_sigma > 0:
            src_lab[:,:,i] = (src_lab[:,:,i] - src_mu) * (tar_sigma / src_sigma) + tar_mu
    return cv2.cvtColor(np.clip(src_lab, 0, 255).astype("uint8"), cv2.COLOR_LAB2BGR)
```

**Integration**: Call `harmonize_view(back_img, front_img)` on every non-front view before they enter the baking loop.

**Test**:
```bash
PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
$PY scripts/run_densepose_texture.py --verify
$PY scripts/agent_verify.py meshes/latest.glb
```

**Do NOT**: Touch UV mapping logic. Only pre-process input photos.

---

## S-U2: SMPL Vertex Index Integration for Measurements

**Priority**: HIGH | **Effort**: Medium | **Depends on**: Nothing

**Problem**: `core/smpl_optimizer.py` `extract_measurements()` (~line 356) uses approximate landmarks. Gemini Task 22 provides exact SMPL 6890 vertex indices.

**What to build**: Replace approximate landmark detection with verified vertex indices for circumference cutting planes.

**File to edit**: `core/smpl_optimizer.py` — grep for `extract_measurements`

**Vertex index mapping** (from `research/task22_smpl_anthropometry_mapping.md`):
```python
SMPL_LANDMARKS = {
    'HEAD_TOP': 412, 'L_HEEL': 3458,
    'NECK': 3050, 'L_NIPPLE': 3042, 'R_NIPPLE': 6489,
    'BELLY_BUTTON': 3501, 'LOW_LEFT_HIP': 3134,
    'L_SHOULDER': 3011, 'R_SHOULDER': 6470,
    'L_THIGH': 947, 'L_CALF': 1103,
    'R_BICEP': 4855, 'R_FOREARM': 5197,
    'L_WRIST': 2241, 'R_WRIST': 5559,
    'L_ANKLE': 3325, 'L_ELBOW': 1643, 'CROTCH': 1210,
}
```

**CRITICAL — verify indices first** (Gemini has fabricated data before):
```bash
$PY -c "
from core.smpl_direct import build_smpl_mesh
m = build_smpl_mesh()
v = m['vertices']
print(f'Head top (412): Y={v[412][1]:.1f}')   # should be highest Y
print(f'Waist (3501): Y={v[3501][1]:.1f}')     # should be mid-torso
print(f'Heel (3458): Y={v[3458][1]:.1f}')      # should be near 0
print(f'Neck (3050): Y={v[3050][1]:.1f}')       # should be below head
print(f'L_Shoulder (3011): Y={v[3011][1]:.1f}') # should be near neck
"
```
If Y-values don't make anatomical sense → clone `https://github.com/DavidBoja/SMPL-Anthropometry` and extract correct indices from its `data/` files. Do NOT blindly trust the indices.

**For circumferences**: Use vertex as plane center, bone direction (parent_joint → child_joint) as plane normal, intersect mesh surface with plane, measure perimeter.

**Acceptance**: Default-betas mesh measurements vs SMPL-Anthropometry library → MAE < 2cm on circumferences.

---

## S-U3: Three.js Muscle Group Highlighter

**Priority**: MEDIUM | **Effort**: Medium | **Depends on**: Nothing

**Problem**: No per-muscle visualization in viewer. Users can't see which groups are tracked.

**Files**:
- Read `web_app/static/viewer3d/viewer.js` — mesh loading
- Read `web_app/static/viewer3d/measurement_overlay.js` — click/hover patterns
- Create `web_app/static/viewer3d/muscle_highlighter.js`

**Data source**: SMPL 24-part segmentation JSON from `https://github.com/Meshcapade/wiki/tree/main/assets/SMPL_body_segmentation` — download the JSON, embed vertex indices for 14 muscle groups:

| Display Name | SMPL Segments to use |
|---|---|
| Biceps L/R | L_UpperArm / R_UpperArm |
| Pectorals | Spine2 (chest) |
| Abs | Spine1 (stomach) |
| Glutes | Pelvis (buttocks) |
| Quads L/R | L_Thigh / R_Thigh |
| Calves L/R | L_Calf / R_Calf |
| Deltoids L/R | L_Shoulder / R_Shoulder |

**Three.js code** (from `research/task24_muscle_segmentation.md` Part 5):
```javascript
const count = geometry.attributes.position.count;
geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
const colors = geometry.attributes.color;
// Highlight selected group, default white for others
material.vertexColors = true;
```

**UI**: Sidebar with muscle group buttons. Click → highlight vertices → show group name.

**Do NOT**: Write custom shaders. Vertex colors + MeshStandardMaterial are sufficient and mobile-safe.
**Do NOT**: Use `onBeforeCompile` (banned — breaks MeshPhysicalMaterial).

---

## S-U4: A2B Regressor (Measurements → SMPL Betas)

**Priority**: HIGH | **Effort**: Large | **Depends on**: S-U2

**Problem**: No inverse mapping from measurements → SMPL betas. Blocks "FutureMe" body morphing feature (user enters target weight/measurements → sees predicted body shape).

**Create**: `core/a2b_regressor.py`
**Read**: `core/smpl_optimizer.py` — `extract_measurements()` (~line 356) and `smpl_forward()` (~line 68)

**Step 1 — Generate synthetic data** (run once, save to `data/a2b_training.csv`):
```python
import numpy as np
for i in range(10000):
    betas = np.random.randn(10) * 1.5  # wider than N(0,1) for body diversity
    mesh = smpl_forward(betas)
    measurements = extract_measurements(mesh['vertices'], mesh['joints'], mesh['faces'])
    # CSV row: [all_measurement_values..., all_beta_values...]
```

**Step 2 — Train MLP** (from `research/task23_a2b_regressor_training.md`):
- Architecture: input_dim→128→64→10 (ReLU, MSE loss, Adam lr=0.001, 200 epochs)
- Split: 80/20 train/test

**Step 3 — Validate**:
- Round-trip: input_measurements → predict_betas → rebuild_mesh → extract_measurements → delta < 1cm per key
- V2V mesh error: < 5mm average

**Step 4 — Export**: `torch.onnx.export()` → int8 quantize → `models/a2b_regressor.onnx` (~20KB)

**Do NOT**: Use ANSUR/CAESAR (restricted licenses). Synthetic data is sufficient and license-clean.
**Do NOT**: Install heavy dependencies — torch is already available, just add onnxruntime for export.

---

## S-U5: SMPLitex Texture Handler on RunPod

**Priority**: HIGH | **Effort**: Medium | **Depends on**: RunPod access

**Problem**: `core/densepose_texture.py` `inpaint_atlas()` (~line 216) uses cv2.inpaint(Telea) for unseen body regions — looks flat/mannequin. SMPLitex generates realistic skin via diffusion.

**Files**:
- Edit `runpod/handler.py` — add SMPLitex action
- Edit `core/densepose_texture.py` — add `inpaint_atlas_gpu()` calling RunPod

**CRITICAL — verify model ID first** (Gemini has fabricated HuggingFace IDs):
```bash
curl -sI https://huggingface.co/mcomino/smplitex-controlnet | head -5
# If 404 → search HuggingFace for "smplitex" to find real ID
# Also check: https://github.com/ggxxii/texdreamer for the actual repo
```

**Handler code** (from `research/task25_smplitex_actual_api.md` Part 1):
- Pipeline: `StableDiffusionControlNetInpaintPipeline` (diffusers)
- ControlNet: `mcomino/smplitex-controlnet`
- Base: `runwayml/stable-diffusion-v1-5`, torch.float16
- Prompt MUST include: `"a sks texturemap of a human body"`
- Input: 1024x1024 partial UV + binary mask
- Output: complete UV atlas
- Time: ~12.5s on A40

**Feature flag**: `USE_GPU_INFILL = os.environ.get('GPU_INFILL', 'false') == 'true'`

**Do NOT**: Remove cv2.inpaint fallback. Keep as free-tier/offline path.

---

## S-U6: Longitudinal Body Change Heatmap in Viewer

**Priority**: MEDIUM | **Effort**: Medium | **Depends on**: S-U2

**Problem**: `comparison_viewer.js` shows side-by-side meshes but no per-vertex change heatmap. Users can't see WHERE they changed.

**Files**:
- Read `core/mesh_comparison.py` — `compare_meshes()` returns displacement map
- Read `core/progress.py` — trend analysis exists (~240 lines)
- Edit `web_app/static/viewer3d/comparison_viewer.js` — add heatmap mode

**Backend**:
- New endpoint: `GET /api/customer/<id>/body_diff?from=<date>&to=<date>`
- Zero pose params (theta=0) on both meshes before diff (pose-invariant — this is already how our meshes are stored in A-pose)
- Return: `{vertex_displacements: [float...], min_mm, max_mm}`

**Frontend**:
- Load displacements → normalize to [-1, +1]
- Map to colormap: blue (loss) → white (no change) → red (growth)
- Apply as vertex color BufferAttribute
- Toggle: "Show Changes" button in viewer toolbar

**Do NOT**: Build a timeline slider — just A-vs-B comparison for MVP.
**Do NOT**: Use `onBeforeCompile` (banned).

---

## S-U7: IntrinsiX PBR Maps on RunPod

**Priority**: MEDIUM | **Effort**: Medium | **Depends on**: S-U5

**Problem**: Pipeline produces albedo only. Photorealistic Three.js rendering needs normal/roughness/metallic maps.

**CRITICAL — verify first**:
```bash
curl -sI https://huggingface.co/PeterKocsis/IntrinsiX | head -5
```

**Handler code** (from `research/task25_smplitex_actual_api.md` Part 2):
- `IntrinsiXPipeline` wrapping FLUX.1-dev + LoRA `PeterKocsis/IntrinsiX`
- Input: albedo 1024x1024 → Output: normal_map, roughness_map, metallic_map
- Time: ~18s on A40

**Licensing**: FLUX.1-dev is non-commercial. SMPL topology is copyrighted. Flag for user decision before commercial use.

**Total with S-U5**: ~35.5s for partial_UV → complete albedo → PBR maps.

---

## S-U8: Body Composition ML — BLOCKED on Gemini G-R1

**Priority**: HIGH | **Cannot start until**: Gemini G-R1 delivers verified paper + weights

**When unblocked**: Add `estimate_body_composition_ml(betas)` to `core/body_composition.py` alongside existing Navy formula. Keep Navy as fallback.

---

## S-U9: Photo → SMPL Auto-Estimation — BLOCKED on Gemini G-R2

**Priority**: HIGH | **Cannot start until**: Gemini G-R2 confirms weight URLs + dual-view support

**When unblocked**: Add SMPLer-X to RunPod handler, add `fit_from_photos(front, side)` to `core/smpl_fitting.py`, make Flutter measurement entry optional.

---

## Execution Order

```
IMMEDIATE (no dependencies, can run in parallel):
  S-U1  LAB color fix           ← 30 min, biggest texture quality win
  S-U2  Vertex indices          ← foundation for S-U4, S-U6
  S-U3  Muscle highlighter      ← standalone viewer feature

AFTER S-U2:
  S-U4  A2B regressor           ← needs accurate measurement extraction
  S-U6  Heatmap viewer          ← needs vertex indices for region stats

AFTER RunPod model IDs verified:
  S-U5  SMPLitex texture        ← verify HuggingFace IDs before coding
  S-U7  IntrinsiX PBR           ← needs S-U5 working

BLOCKED (waiting on Gemini research):
  S-U8  Body comp ML            ← blocked on G-R1
  S-U9  Photo → SMPL auto       ← blocked on G-R2

Recommended serial order: S-U1 → S-U2 → S-U3 → S-U4 → S-U5 → S-U6 → S-U7
```
