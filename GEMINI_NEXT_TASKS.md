# Gemini Research Tasks — Phase 3: Phenotype, DensePose, Sliders (2026-03-23)

## Context
Phases 1-2 complete: MPFB2 template (13,380 verts), bone-axis deformation, texture dispatcher, e2e test passing. Phase 3 adds runtime shape key morphing, DensePose texture on MPFB2, and live deformation via viewer sliders. These 3 research tasks unblock Sonnet's implementation.

## RULES — READ BEFORE STARTING
1. **Read `CLAUDE.md` FIRST** — paths, gotchas, conventions
2. **RESEARCH ONLY** — do NOT write code, do NOT run Blender, do NOT run Python
3. **Reports under 100 lines** — concise findings, save to `research/` with `g_r` prefix
4. **Do NOT re-research:** g_r7-g_r14 (all completed and committed)
5. **Do NOT read:** `controllers.py` (3600+), `body_viewer.js` (4000+), `main.dart` (2500+)
6. Reference existing research where applicable

## Existing Research (DO NOT REDO)
- g_r7: MPFB2 vertex groups — g_r8: shape keys ($ma/$mu patterns) — g_r9: UV layout (single atlas)
- g_r10: deformation (NumPy) — g_r11: MPFB2→SMPL region map — g_r12: shape key deltas
- g_r13: bone-axis PCA — g_r14: unassigned verts (KDTree strategy)

---

## Task G-R15: Shape Key Delta Extraction Order (HIGH PRIORITY — DO FIRST)

**Why:** The Blender script removes 5,778 helper vertices (eyes, hair, etc.) BEFORE baking shape keys. Shape keys reference ALL 19,158 vertices. If we extract deltas before vertex removal, indices won't match the 13,380-body mesh. Need the correct order.

**What to research:**
1. In Blender Python, when vertices are deleted from a mesh (`bmesh.ops.delete`), do shape key vertex arrays auto-shrink to match?
2. Or do shape key `data[i].co` indices become stale after vertex deletion?
3. What is the correct order:
   - (a) Remove helpers → extract deltas (shape keys auto-reindexed to 13,380 verts)
   - (b) Extract deltas for all 19,158 → remove helpers → re-index deltas manually
4. Does `bpy.ops.object.shape_key_remove(all=True, apply_mix=True)` preserve the mesh if called AFTER extraction?
5. Reference `research/g_r12_shape_key_deltas.md` for extraction snippet

**Output:** `research/g_r15_shape_key_extraction_order.md`
- Which order is correct (a or b)
- Blender Python snippet for safe extraction (DO NOT RUN)
- Any edge cases (shape keys with drivers, relative vs absolute)

---

## Task G-R16: DensePose IUV-to-MPFB2 UV Transfer (HIGH PRIORITY)

**Why:** DensePose outputs IUV maps in SMPL's UV parameterization (24 body parts, each with own UV space). Need to know if/how this maps to MPFB2's single-atlas UV layout.

**What to research:**
1. DensePose IUV format: I = body part index (1-24), U/V = surface coordinates within that part. Are U/V normalized [0,1]?
2. Is DensePose UV space tied to SMPL mesh topology, or is it a continuous body surface parameterization?
3. Transfer approach: DensePose (I, U, V) → SMPL 3D surface point → KDTree nearest MPFB2 vertex → MPFB2 UV
4. Does this require a precomputed SMPL→MPFB2 correspondence map? Or can KDTree on 3D positions work?
5. Any open-source tools for cross-topology texture transfer via DensePose? (e.g., DensePose Transfer, Tex2Shape)

**Output:** `research/g_r16_densepose_mpfb2_transfer.md`
- Transfer algorithm (step by step)
- Whether a precomputed correspondence table is needed
- Estimated quality (lossy? seams?)

---

## Task G-R17: Viewer Slider Architecture

**Why:** Sonnet needs to wire viewer sliders to a new server endpoint. Need the current event model without reading 4000 lines of JS.

**What to research:**
1. Grep `body_viewer.js` for lines 1785-1813 ONLY — what HTML elements are the sliders? (`input[type=range]`?)
2. What events do they fire? (`input`, `change`, custom?)
3. Do they currently POST to any API, or only modify Three.js BufferGeometry locally?
4. What measurement keys do sliders use? (e.g., `chest_width` maps to which profile field?)
5. Is there a debounce/throttle utility already in the viewer JS?
6. How does the viewer know which customer_id to use? (URL param? global var?)

**Output:** `research/g_r17_viewer_slider_architecture.md` — under 60 lines
- Slider element type + event model
- Key→measurement mapping table
- Customer ID source
- Whether any API calls exist

---

## DEPENDENCY INFO
- **G-R15 blocks S-T7** (shape key delta export)
- **G-R16 blocks S-T9** (DensePose MPFB2 integration)
- **G-R17 blocks S-T11** (viewer slider wiring)
- All 3 can run in parallel — no interdependencies
