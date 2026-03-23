# Gemini Research Tasks — MPFB2 Texture Compatibility (2026-03-23)

## Context
MPFB2 template pipeline is working (13,380 verts, 15 muscle groups, runtime deformation). But the **texture subsystem** (`texture_factory.py`, `skin_patch.py`) is hardcoded to SMPL's 6890-vert / 24-joint topology. We need research to inform the adapter layer that maps MPFB2 groups to SMPL-compatible part IDs.

## RULES — READ BEFORE STARTING
1. **Read `CLAUDE.md` FIRST** — paths, gotchas, conventions
2. **RESEARCH ONLY** — do NOT write code, do NOT run Blender, do NOT run Python
3. **Never read files over 200 lines** — grep for specific sections
4. **Reports under 100 lines** — concise findings, not essays
5. **Save reports to `research/`** with `g_r` prefix
6. **Do NOT read:** `controllers.py` (3600+ lines), `body_viewer.js` (3900+ lines), `template_vert_segmentation.json` (one giant line)
7. **Do NOT re-research topics already covered** — check existing reports first

## Existing Research (DO NOT REDO)
- `research/g_r5_smpl_segmentation_data.md` — SMPL 24-joint part IDs and vertex assignments
- `research/g_r7_mpfb2_vertex_groups.md` — MPFB2 bone names, front/back splitting (FIXED)
- `research/g_r8_makehuman_shape_keys.md` — Shape key naming patterns ($ma, $mu)
- `research/g_r9_mpfb2_uv_layout.md` — Single-atlas UV layout confirmed
- `research/g_r10_runtime_deformation.md` — NumPy deformation approach

## Current Template Stats (DO NOT re-derive)
- 13,380 body vertices, 26,756 triangulated faces
- 4,623 vertices assigned to 15 muscle groups (34.6%)
- 8,757 unassigned (head, hands, feet, inner surfaces)
- Groups: biceps_l/r, forearms_l/r, deltoids_l/r, pectorals, traps, abs, obliques, glutes, quads_l/r, calves_l/r

---

## Task G-R11: MPFB2-to-SMPL Region Mapping (HIGH PRIORITY — DO FIRST)

**Why:** Sonnet needs to build a dispatcher that converts MPFB2 muscle groups into SMPL-compatible integer part IDs (0-23). Wrong mapping = wrong roughness zones and broken skin compositing.

**What to research:**
1. For each of the 15 MPFB2 muscle groups, which SMPL joint part ID(s) correspond anatomically?
2. Reference `research/g_r5_smpl_segmentation_data.md` for the SMPL joint index table
3. Some MPFB2 groups span multiple SMPL joints (e.g., traps might map to spine2 + neck) — pick the single best match
4. Verify the proposed mapping in the plan is correct:
   - pectorals→9, traps→12, abs→3, obliques→3, glutes→0
   - quads_l→1, quads_r→2, calves_l→4, calves_r→5
   - biceps_l→16, biceps_r→17, forearms_l→18, forearms_r→19
   - deltoids_l→13, deltoids_r→14

**Output:** `research/g_r11_mpfb2_smpl_region_map.md`
- Table: MPFB2 Group | Best SMPL Part ID | SMPL Joint Name | Region Name | Confidence
- Flag any mappings that are ambiguous or could cause texture seams

---

## Task G-R14: Unassigned Vertex Coverage Analysis (HIGH PRIORITY)

**Why:** 8,757 of 13,380 vertices have no muscle group assignment. The adapter needs a strategy to assign them part IDs (for roughness maps, skin compositing, anatomical overlay).

**What to research:**
1. What body regions do the unassigned 8,757 vertices belong to? (head, hands, feet, inner thighs, lower back, armpits?)
2. Check MPFB2 source for additional vertex groups beyond what we mapped (e.g., head, hands, feet groups)
3. Would KDTree nearest-neighbor from the 4,623 assigned vertices produce reasonable results? Or would it create artifacts (e.g., hand vertices assigned to forearm)?
4. Alternative: height-band heuristic (Z-ranges for head, torso, arms, legs)
5. Should the Blender script export additional groups (head, hands, feet, back)?

**Output:** `research/g_r14_unassigned_vertex_analysis.md`
- Height-band breakdown: Z ranges for each body region
- Recommended assignment strategy (KDTree vs height-band vs extra groups)
- List of additional MPFB2 vertex groups available but not yet exported

---

## Task G-R12: Shape Key Delta Export for Runtime Phenotype

**Why:** Currently the Blender script bakes shape keys into the mesh. To support runtime body type adjustment (muscle, fat, proportions) without re-running Blender, we need shape key deltas as numpy arrays.

**What to research:**
1. Mathematical structure of MPFB2 shape key deltas (per-vertex displacement vectors?)
2. Can deltas be extracted via Blender Python as `(N, 3)` arrays per shape key?
3. Are shape key combinations linear (additive) or do they interact non-linearly?
4. How many shape keys are relevant for fitness tracking? (muscle definition, body fat, limb proportions)
5. Storage size estimate: how many numpy files, how many MB?

**Reference:** `research/g_r8_makehuman_shape_keys.md` for shape key naming patterns

**Output:** `research/g_r12_shape_key_deltas.md`
- Blender Python snippet to extract deltas (DO NOT RUN IT)
- List of fitness-relevant shape keys with names
- Storage/linearity analysis

---

## Task G-R13: Bone-Axis-Aligned Deformation Research

**Why:** Current deformation uses simple radial XY scaling from body center. Limbs not aligned with XY axes (e.g., arms at an angle) get distorted. Need per-group bone-axis scaling.

**What to research:**
1. For each of the 15 muscle groups, what is the natural scaling axis? (perpendicular to bone direction)
2. How to compute per-group principal axis from vertex positions (PCA on vertex cloud)
3. Best boundary smoothing: Laplacian vs heat diffusion vs distance-weighted blend
4. Any open-source implementations for reference?

**Reference:** `research/g_r10_runtime_deformation.md` for prior deformation findings

**Output:** `research/g_r13_bone_axis_deform.md`
- Per-group axis table: Group | Bone Direction | Scale Plane
- Pseudocode for PCA axis computation
- Recommended smoothing method with rationale

---

## DEPENDENCY INFO FOR GEMINI
- **G-R11 and G-R14 are HIGH PRIORITY** — Sonnet is blocked until these are done
- **G-R12 and G-R13 can run after** — they inform Phase 2/3, not blocking Phase 1
- Do G-R11 and G-R14 first, then G-R12 and G-R13
