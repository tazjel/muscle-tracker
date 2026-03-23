# Phase 6: Custom Body Mesh Research — Gemini Tasks

**Branch**: `gemini/research-phase6`
**Priority**: CRITICAL — blocks all viewer, texture, and muscle highlight work
**Rules**: All rules from `research/GEMINI_RULES.md` apply. READ THEM FIRST.

---

## Context: Why We Need This

Our current meshes are broken for our use case:
- **SMPL 6890-vert mesh**: cylindrical UVs cause visible seams at armpits/crotch/sides. Non-commercial license.
- **Decimated 2154-vert mesh**: no UVs, too low-poly for skin texture.
- **Subdivided 21334-vert mesh**: vertex indices don't match Meshcapade segmentation, so muscle highlighting fails.

We need ONE mesh that has:
1. **Proper UV unwrapping** — artist-quality single atlas, no visible seams when projecting skin photos
2. **Enough detail** — 10k-25k vertices for smooth surface + web performance
3. **Known vertex groups** — labeled body part segmentation for muscle highlighting
4. **Parametric control** — body shape sliders (height, weight, muscularity, fat) for fitness app
5. **Commercial-safe license** — Apache 2.0, CC0, or MIT
6. **GLB export** — must work in Three.js r160 viewer

---

## Task 26: MakeHuman/MPFB2 Mesh Deep Dive

**Goal**: Full technical spec of the MakeHuman mesh topology, UV layout, and vertex groups. Can we use it as our base mesh?

### What to research:
1. **Mesh topology**: Exact vertex count, face count, edge loops around joints. Is it quad-based? How does it subdivide?
2. **UV layout**: Download or screenshot the actual UV atlas layout. How many UV islands? Where are the seams? Is it a single-atlas or multi-tile?
3. **Vertex groups**: List ALL named vertex groups available. Are there body-part groups (torso, left_arm, right_leg, etc.)? How many vertices per group?
4. **Parametric sliders**: What body shape controls exist? Can we set: height, weight, muscularity, body fat%, waist, chest, hip circumference?
5. **GLB export quality**: Export a default male body as GLB from Blender+MPFB2. Report: vertex count, file size, UV presence, material setup.
6. **Skin texture workflow**: Can we paint/project a texture onto the UV atlas? What resolution is optimal (1024, 2048, 4096)?

### Sources to check:
- https://github.com/makehumancommunity/makehuman (main repo)
- https://github.com/makehumancommunity/mpfb2 (Blender addon)
- https://static.makehumancommunity.org/makehuman/docs/professional_mesh_topology.html
- https://static.makehumancommunity.org/mpfb/docs/ (full MPFB2 docs)
- http://www.makehumancommunity.org/wiki/Main_Page
- Blender Artists forum threads about MakeHuman UV quality

### Deliverable: `research/task26_makehuman_mesh_spec.md`
Include: vertex count, UV atlas screenshot/description, full vertex group list, parametric controls list, GLB export test results, license confirmation (CC0 for exported models).

---

## Task 27: Anny Body Model Technical Evaluation

**Goal**: Can Anny (Naver Labs) replace SMPL as our parametric body model? Full technical comparison.

### What to research:
1. **Mesh topology**: Vertex count (reported 13,380). Face type (quads vs tris). Edge flow quality around joints.
2. **UV layout**: Anny uses MakeHuman's UV map — confirm this. Get the actual UV coordinates or atlas image.
3. **Body segmentation**: Does Anny provide vertex group labels? The 564 blendshapes — list the ones relevant to fitness (muscle, fat, body proportions).
4. **SMPL compatibility**: Can we convert SMPL betas → Anny parameters? Is there a mapping?
5. **Python API**: Exact code to generate a body with custom measurements. Show: `import`, class init, set height/weight/muscle, export OBJ.
6. **GLB export**: Generate an Anny body, convert to GLB with UVs. What tools needed? trimesh? Blender?
7. **Performance**: Inference time on CPU. Model file size. Dependencies.

### Sources to check:
- https://github.com/naver/anny (READ THE ACTUAL SOURCE CODE — Rule 13)
- https://arxiv.org/abs/2511.03589 (Anny paper)
- https://europe.naverlabs.com/blog/anny-a-free-to-use-3d-human-parametric-model-for-all-ages/
- Read `anny/model.py`, `anny/body_model.py`, or whatever the main module is — get EXACT class names and function signatures

### Deliverable: `research/task27_anny_evaluation.md`
Include: exact Python code to generate a body (VERIFIED against source), blendshape list, UV confirmation, comparison table vs SMPL, license (Apache 2.0 confirmed?).

---

## Task 28: UV Unwrapping Best Practices for Skin Texture Projection

**Goal**: What is the correct way to UV-unwrap a human body mesh for photorealistic skin texture projection from camera photos?

### What to research:
1. **UV seam placement**: Where should seams go on a human body to minimize visibility? Standard industry practice (back of body, inner limbs, scalp).
2. **UV packing**: Single atlas vs UDIM tiles. What do game studios use? What resolution per body part?
3. **Texture projection math**: Given a camera photo of a person's arm, how to project those pixels onto the mesh UV space? The camera intrinsics/extrinsics → UV coordinate mapping.
4. **DensePose → UV**: DensePose gives IUV maps (body part + UV per pixel). How to convert DensePose UV to mesh UV? Are they compatible?
5. **Seam blending**: Techniques to hide seam lines — Laplacian blending, Poisson blending, feathered edges.
6. **Multi-view fusion**: When we have front + back photos, how to merge textures without visible boundary?

### Sources to check:
- https://github.com/facebookresearch/DensePose (DensePose UV documentation)
- https://github.com/AliaksandrSiaworski/DensePose_UV (UV coordinate tools)
- Search ResearchGate for: "human body UV texture projection" and "DensePose texture transfer"
- https://research.facebook.com/publications/densepose-dense-human-pose-estimation-in-the-wild/ (original DensePose paper)
- Game dev resources on character UV unwrapping (polycount.com wiki, cgcookie tutorials)
- Search GitHub for: "densepose texture transfer mesh" and "body texture projection uv"

### Deliverable: `research/task28_uv_unwrap_best_practices.md`
Include: seam placement diagram (ASCII art is fine), DensePose UV → mesh UV mapping explanation, code snippets for texture projection, recommended atlas resolution.

---

## Task 29: Vertex Group Segmentation for Fitness Muscle Highlighting

**Goal**: How to create accurate muscle group vertex labels on our chosen mesh for the Three.js viewer highlighter.

### What to research:
1. **Meshcapade segmentation**: We already have `smpl_vert_segmentation.json` (24 parts). Can this be remapped to a non-SMPL mesh?
2. **Skinning weight transfer**: If mesh A has bone weights and mesh B doesn't, can we transfer via nearest-vertex or barycentric interpolation?
3. **Anatomical muscle groups for fitness**: Map the 24 SMPL parts to fitness-relevant groups: biceps, triceps, pectorals, deltoids, lats, abs, obliques, glutes, quads, hamstrings, calves, forearms, traps. Which SMPL parts combine for each?
4. **MakeHuman vertex groups**: Does MakeHuman export named vertex groups for body parts? Can they map to muscles?
5. **Blender scripting**: Python script to assign vertex groups by bone proximity or weight painting — so we can create segmentation for ANY mesh.
6. **Runtime transfer**: If our mesh changes (parametric), do vertex group assignments survive? Or do we need to re-segment?

### Sources to check:
- https://github.com/Meshcapade/wiki/tree/main/assets/SMPL_body_segmentation (we have this)
- https://meshcapade.wiki/SMPL (Meshcapade wiki)
- Blender Python API docs for vertex groups: https://docs.blender.org/api/current/bpy.types.VertexGroup.html
- Search GitHub for: "smpl vertex groups transfer" and "mesh segmentation body parts"
- Our file: `core/smpl_vert_segmentation.json` (downloaded Meshcapade data)

### Deliverable: `research/task29_vertex_group_segmentation.md`
Include: mapping table (fitness muscle → SMPL parts → vertex indices), Blender script to create vertex groups, method to transfer groups between mesh topologies.

---

## Task 30: GLB Export Pipeline — Mesh + UVs + Texture + Vertex Groups → Three.js

**Goal**: End-to-end pipeline from parametric body model → production GLB file that works in our Three.js viewer.

### What to research:
1. **GLB format spec**: What data can a GLB carry? Mesh, UVs, normals, textures, vertex colors, morph targets, skeleton. What does Three.js r160 support?
2. **Python GLB export**: Compare libraries — `trimesh`, `pygltflib`, `gltflib`. Which one preserves UVs + textures + vertex colors correctly?
3. **Texture embedding**: Should we embed the skin texture in the GLB (larger file, single request) or reference external PNG (smaller GLB, extra request)?
4. **PBR material setup**: For realistic skin in Three.js — what maps do we need? baseColor, normal, roughness, subsurface scattering. How to set these in the GLB?
5. **Morph targets**: Can we embed body shape morphs (slim → muscular) in the GLB and animate them client-side in Three.js?
6. **Compression**: Draco compression for geometry. KTX2/Basis for textures. What's the file size impact?

### Sources to check:
- https://github.com/KhronosGroup/glTF/tree/main/specification/2.0 (glTF 2.0 spec)
- https://threejs.org/docs/#examples/en/loaders/GLTFLoader (Three.js GLTFLoader)
- https://github.com/mikedh/trimesh (trimesh — we already use this)
- https://github.com/KhronosGroup/glTF-Sample-Models (reference GLB files)
- https://github.com/mrdoob/three.js/tree/dev/examples (Three.js morph target examples)
- Search GitHub for: "python glb export texture uv" and "threejs morph targets body"

### Deliverable: `research/task30_glb_export_pipeline.md`
Include: recommended Python library with exact code to export GLB with UVs + texture + vertex colors, PBR material recipe for skin, morph target example, compression recommendations.

---

## Task 31: Complete Mesh Pipeline Design — From Photos to Viewer

**Goal**: Design the full pipeline that connects everything. This is the capstone task — synthesize Tasks 26-30 into a concrete implementation plan.

### What to deliver:
1. **Mesh choice recommendation**: MakeHuman, Anny, or hybrid? One clear recommendation with justification.
2. **Pipeline flowchart**:
   ```
   User photos (front + back)
     → DensePose body segmentation
     → Parametric body fitting (measurements → mesh shape)
     → Skin texture extraction + projection onto UV atlas
     → Muscle group vertex labeling
     → GLB export (mesh + UVs + texture + vertex groups)
     → Three.js viewer (muscle highlights + skin texture)
   ```
3. **Integration points**: For each step, name the EXACT file in our codebase that handles it (or needs to be created).
4. **What we keep vs replace**:
   - KEEP: `core/smpl_fitting.py` shape parameters → mesh deformation
   - KEEP: `core/densepose_texture.py` photo → IUV maps
   - REPLACE: `core/uv_unwrap.py` cylindrical UVs → proper atlas UVs
   - REPLACE: `core/mesh_reconstruction.py` export_glb → new pipeline
   - KEEP: `web_app/static/viewer3d/muscle_highlighter.js` (update vertex data)
5. **Estimated effort**: For each pipeline step, is it a 1-day task, 1-week task, or needs GPU/cloud?
6. **Open questions**: What we still don't know after all research.

### Sources: All findings from Tasks 26-30 + our existing codebase.

### Deliverable: `research/task31_mesh_pipeline_design.md`
This is the MOST IMPORTANT deliverable. It should be actionable enough that Claude can implement from it.

---

## Execution Order

| Order | Task | Depends On | Priority |
|-------|------|-----------|----------|
| 1 | Task 26 (MakeHuman spec) | — | Do first |
| 1 | Task 27 (Anny evaluation) | — | Do in parallel with 26 |
| 2 | Task 28 (UV best practices) | 26, 27 | After mesh choice |
| 2 | Task 29 (Vertex groups) | 26, 27 | After mesh choice |
| 3 | Task 30 (GLB pipeline) | 28, 29 | After UV + groups |
| 4 | Task 31 (Full design) | ALL | Final synthesis |

Tasks 26 and 27 can run in parallel. Tasks 28 and 29 can run in parallel after 26+27. Task 30 after 28+29. Task 31 last.

---

## Token Budget Rules

- Do NOT read large source files line-by-line. Use `grep` to find relevant functions.
- Do NOT re-research things already covered in Phase 1-5 tasks. Reference them.
- Each task deliverable should be 150-300 lines MAX. Dense, not padded.
- Include EXACT code snippets, not "use library X". Show imports, function calls, outputs.
- Every GitHub URL must be REAL and VERIFIED (Rule 3).
- Every paper must have REAL arXiv ID or DOI (Rule 3).
- Do NOT modify any `.py`, `.js`, `.html` files (Rule 1).

---

## Branch Workflow

```bash
git checkout master
git checkout -b gemini/research-phase6
# Do all research tasks, commit each deliverable
git add research/task26_*.md && git commit -m "gemini: task 26 — MakeHuman mesh spec"
git add research/task27_*.md && git commit -m "gemini: task 27 — Anny evaluation"
# ... etc
# Update SUMMARY.md on the branch
```
