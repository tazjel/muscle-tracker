# Gemini Research Tasks — Phase 4: Muscle/Weight Macros, DensePose Regen, Slider UX (2026-03-23)

## RULES — READ BEFORE STARTING
1. Read `CLAUDE.md` FIRST
2. RESEARCH ONLY — do NOT write code, do NOT run Blender, do NOT run Python
3. Reports under 100 lines, save to `research/` with `g_r` prefix
4. Do NOT re-research: g_r7–g_r17 (all completed; g_r16 is being REPLACED by G-R19)
5. Do NOT read `controllers.py` (3571 lines), `body_viewer.js` (4000+), or `main.dart` (2500+)
6. Reference existing research where applicable
7. All 3 tasks can run IN PARALLEL — no dependencies between them

## Existing Research (DO NOT REDO)
- g_r7: vertex groups | g_r8: shape keys | g_r9: UV layout | g_r10: deformation
- g_r11: region map | g_r12: deltas | g_r13: bone-axis PCA | g_r14: unassigned verts
- g_r15: extraction order | g_r16: CORRUPTED (replaced by G-R19) | g_r17: slider architecture

---

## Task G-R18: MPFB2 Muscle/Weight Macro System (HIGHEST PRIORITY)

**Why:** The Blender template export extracted 8 shape key deltas — ALL are gender keys (`$ma`, `$fe`). The filter includes `$mu`/`$wg`/`muscle`/`weight` patterns but found ZERO keys with delta > 1e-5. muscle_factor and weight_factor have NO effect on the mesh. We need to understand how MPFB2 actually produces muscular/heavy bodies.

**What to research:**
1. Does MPFB2 use `.target` files (sparse vertex deltas) for muscle/weight instead of standard Blender shape keys? If so, where are they stored in the MPFB2 add-on directory?
2. What is the MPFB2 Python API for setting muscle/weight? (e.g., `HumanService.setMuscle(human, value)` or `BodyService` calls)
3. After calling the MPFB2 API to set muscle=1.0 and weight=0.3, do the resulting changes appear as shape keys? Or are vertex positions modified through a different mechanism (bone transforms, modifiers, direct mesh manipulation)?
4. What is the correct Blender script sequence to: (a) create human, (b) set muscle=1.0, (c) read the resulting vertex positions, (d) compute delta from muscle=0.5 baseline?
5. Are muscle/weight targets additive to gender targets, or are they separate independent macros?
6. Reference `research/g_r8_shape_keys.md` and `research/g_r12_shape_key_deltas.md` for context on what keys exist

**Key detail:** The current Blender script Step 2 (lines 51-66) sets `$ma` keys to +0.3 and `$mu`/muscle keys to +0.2, but these `$mu` keys may not exist as standard shape keys. The MPFB2 add-on ZIP is at `scripts/add-on-mpfb-v2.0.14.zip` — check its Python source for the macro API.

**If MPFB2 does NOT use shape keys for muscle/weight:** Describe the alternative mechanism and how Sonnet can extract per-vertex deltas by creating two meshes (one at muscle=0, one at muscle=1) and computing the difference.

**Output:** `research/g_r18_mpfb2_muscle_weight_macros.md`

---

## Task G-R19: Regenerate G-R16 — DensePose IUV-to-MPFB2 UV Transfer

**Why:** The original G-R16 file (`research/g_r16_densepose_mpfb2_transfer.md`) has encoding corruption — binary garbage from line 5 onward. This research is REQUIRED for Sonnet task S-T19 (DensePose→MPFB2 end-to-end test).

**What to research:**
1. DensePose IUV structure: I = body part index (1-24), U/V = continuous surface coordinates (0-1) within each part. Explain exactly what U and V represent geometrically.
2. Transfer algorithm for MPFB2:
   - For each DensePose IUV pixel: (I, U, V) → 3D surface point on SMPL reference mesh
   - Find nearest vertex on MPFB2 mesh (KDTree nearest-neighbor in 3D space)
   - Use that MPFB2 vertex's UV coordinate to place the pixel color in the texture atlas
3. How does `texture_factory.get_part_ids(13380)` output map to DensePose's 24 part indices? (Reference `research/g_r11_mpfb2_smpl_region_map.md` for the mapping table)
4. Edge cases: vertices with no DensePose coverage (hands, feet, top of head), seam handling at part boundaries, fallback for unmapped regions
5. Pre-conditions for end-to-end test: RunPod DensePose endpoint status, photo requirements (front/back minimum), expected output format

**Context:** `scripts/run_densepose_texture.py` already auto-detects MPFB2 by vertex count (13380) and loads `template_uvs.npy`. The `bake_from_photos_nn()` in `core/texture_bake.py` does KDTree NN matching. The question is whether the SMPL→MPFB2 UV transfer works correctly or needs modifications.

**Output:** `research/g_r19_densepose_mpfb2_transfer_v2.md`

---

## Task G-R20: Phenotype Slider UX Patterns

**Why:** The viewer needs gender/muscle/weight sliders but no UI design exists. Sonnet needs guidance on labels, ranges, and layout.

**What to research:**
1. What slider labels and ranges do body-composition / fitness apps use? Examples:
   - "Muscle Definition" 0-100 vs "Lean Mass %" vs "Muscularity"
   - "Body Fat" 5-50% vs "Weight" 0-100 vs "Body Composition"
   - Gender: binary toggle vs continuous slider 0-100 (F↔M)
2. Should phenotype controls be global (sidebar, always visible) or contextual (per-region)?
3. For server round-trip with 500ms debounce (~1s re-deform), what UX patterns work? Loading indicators, progressive preview?
4. The viewer has tabs: Adjust, Analyze, Studio, Scene. Width/Depth/Length sliders are in Adjust tab inside `#adjust-panel`. Where should phenotype sliders go? (Suggest: above per-region adjustments, always visible in Adjust tab)

**Output:** `research/g_r20_phenotype_slider_ux.md` (<80 lines)

---

## DEPENDENCY GRAPH
```
G-R18 (muscle/weight macros)  ──→ blocks Sonnet S-T16 (Blender delta export)
G-R19 (DensePose regen)       ──→ blocks Sonnet S-T19 (DensePose e2e test)
G-R20 (slider UX)             ──→ blocks Sonnet S-T18 (viewer sliders)
```

All 3 Gemini tasks are independent — run them in parallel.
