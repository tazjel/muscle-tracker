# Gemini Research Tasks — gtd3d Knowledge Gaps

Generated: 2026-03-22 | Purpose: Fill research gaps that BLOCK Sonnet implementation tasks.

---

## Rules for Gemini

- **You are a RESEARCHER, not a coder.** Your output is markdown files with findings — NOT code commits.
- **NEVER fabricate**: If you can't find a paper, weight URL, or repo — say "NOT FOUND" instead of making one up. Fabricated citations, arXiv IDs, HuggingFace model IDs, and vertex indices have wasted multiple sessions already.
- **Verify every URL**: Before citing a repo or model, confirm it exists. Open the URL. If you can't confirm, mark it as UNVERIFIED.
- **Use the extraction tables**: Each task has a table format. Fill it exactly. Don't write prose summaries — fill the table.
- **One file per task**: Save results to `research/gXX_<name>.md` (e.g., `research/g_r1_body_comp_ml.md`)
- **Time limit**: Do NOT spend more than ~15 minutes per task. If you haven't found quality results by then, write what you found and note the gaps.
- **Filter aggressively**: Skip papers with no code, no weights, no accuracy metrics, or requiring hardware we don't have (CT/MRI/DXA/LiDAR/depth cameras).

---

## G-R1: Body Composition ML from SMPL Shape (UNBLOCKS Sonnet S-U8)

**Priority**: HIGH | **Why**: `core/body_composition.py` only has Navy formula. We need ML-based body fat prediction from SMPL betas or mesh.

**Background**: Gemini Phase 1 Task 1 and Phase 4 Task 17 both attempted this. Task 1 was just the prompt (no results). Task 17 was marked "Done" in SUMMARY.md but has NO output file — findings were lost or never saved.

**What we have**: SMPL mesh with 10 betas per user. Circumference measurements extracted from mesh. No DXA/BIA/CT scanner.

**What we need**:

### Extraction Table (fill for each paper found)

| Field | What to capture |
|---|---|
| Title + DOI | Full citation, verified link |
| Input format | SMPL betas? Mesh vertices? Silhouette? Circumference measurements? |
| Output | Body fat %, lean mass kg, regional fat, visceral fat? |
| Model architecture | GPR, CNN, MLP, transformer, linear regression? |
| Training data | How many subjects? What ground truth (DXA, BIA, water displacement)? |
| Accuracy | R², MAE, correlation with DXA — MUST have numbers |
| Code/weights available? | YES with URL, or NO |
| License | Commercial OK? Research only? |
| Can we replicate? | Do we have the required inputs? |
| VRAM / compute | Runs on CPU? Needs GPU? How much? |

### Search strategy
1. Google Scholar: `"body composition" "SMPL" OR "body shape parameters" prediction 2023 2024 2025`
2. Google Scholar: `"body fat" "3D body scan" OR "3D mesh" estimation regression 2024 2025`
3. arXiv: `body composition shape parameters smartphone`
4. GitHub: search repos with keywords `body-composition smpl` or `body-fat 3d-scan`
5. Check if `DavidBoja/SMPL-Anthropometry` repo has any body composition prediction built in

### Filter OUT
- Papers requiring CT/MRI/DXA as **input** (we only have photos + mesh)
- Papers using proprietary scanning hardware
- Papers with no accuracy metrics
- Papers older than 2022
- Papers with no available code or weights

### Deliverable
A ranked table of **top 3 papers** by replicability. For the #1 pick:
1. Download URL for code/weights
2. Input format (what do we feed it from our pipeline?)
3. Expected accuracy (MAE for body fat %)
4. Integration sketch: how does this connect to `core/body_composition.py`?

### If nothing found
If no paper meets all criteria, research these fallback approaches:
- **Waist-to-height ratio regression** trained on NHANES public data
- **SMPL beta → BMI → body fat** regression chain (simpler, less accurate)
- **Mesh volume ratio** (trunk volume / total volume) as body fat proxy

Save to: `research/g_r1_body_comp_ml.md`

---

## G-R2: Photo → SMPL Model Weights Verification (UNBLOCKS Sonnet S-U9)

**Priority**: HIGH | **Why**: Task 9 recommended "Focused SMPLer-X" but never confirmed weights exist or dual-view actually works.

**Background**: Current pipeline uses HMR2.0 (monocular, ±5-8cm error). We capture front + side photos. Task 9 claimed Focused SMPLer-X achieves ±1.5-3cm with dual-view fusion, but:
- No weight download URL was provided
- "Focused SMPLer-X" may be a fabricated variant name
- Dual-view fusion capability was claimed but not verified

**What we need**:

### For each candidate model, verify and fill:

| Field | What to capture |
|---|---|
| Model name (exact) | As listed on GitHub/paper |
| Paper | DOI or arXiv ID — OPEN THE LINK and confirm it's real |
| GitHub repo | URL — OPEN IT and confirm it exists and has code |
| Weights URL | Direct download link — confirm file exists (check releases/HuggingFace) |
| Weight file size | In GB |
| Dual-view support? | YES (cite the specific code/function) or NO |
| Input requirements | Image resolution, background, pose constraints? |
| Output format | SMPL betas + pose? SMPL-X? Mesh only? |
| Accuracy on 3DPW/Human3.6M | MPJPE, PA-MPJPE, V2V in mm |
| Measurement accuracy | Chest/waist MAE in cm (if reported) |
| VRAM | Minimum GPU memory |
| Inference time | Per-image on A40/A100 |
| Framework | PyTorch version, CUDA version |

### Models to investigate (in priority order)
1. **SMPLer-X** — `caizhongang/SMPLer-X` on GitHub. Check if it actually has dual-view fusion or if Task 9 made that up.
2. **TokenHMR** — Check for multi-view variant
3. **CameraHMR** — Check for the "138 dense keypoints" claim from Task 9
4. **HMR 2.0b** / **4DHumans** — latest version, any improvements over what we have?
5. **BEDLAM** / **CLIFF** — robust alternatives
6. **PyMAF-X** — multi-view capable?

### Critical question to answer
**Can ANY of these models accept 2 photos (front + side) and produce better shape estimation than HMR2.0 with 1 photo?** If yes → which one, with proof. If no → what's the best single-image model we should upgrade to?

### Deliverable
- Verified comparison table of 3-5 models with all fields filled
- Clear recommendation: "Use [model X] because [reason], download from [URL]"
- If no model supports dual-view: say so, and recommend the best single-image upgrade

Save to: `research/g_r2_photo_to_smpl_verified.md`

---

## G-R3: Verify SMPLitex + IntrinsiX Model IDs (SUPPORTS Sonnet S-U5, S-U7)

**Priority**: HIGH | **Effort**: Small (< 10 min) | **Why**: Task 25 provided handler code but model IDs may be fabricated.

**Verify these exact claims**:

| Claim | How to verify | Result |
|---|---|---|
| `mcomino/smplitex-controlnet` exists on HuggingFace | Open `https://huggingface.co/mcomino/smplitex-controlnet` | EXISTS / 404 |
| `PeterKocsis/IntrinsiX` exists on HuggingFace | Open `https://huggingface.co/PeterKocsis/IntrinsiX` | EXISTS / 404 |
| SMPLitex repo is at `ggxxii/texdreamer` | Open `https://github.com/ggxxii/texdreamer` | EXISTS / 404 |
| IntrinsiX repo is at `Peter-Kocsis/IntrinsiX` | Open `https://github.com/Peter-Kocsis/IntrinsiX` | EXISTS / 404 |
| SMPLitex uses trigger word "sks texturemap" | Check repo README or training config | CONFIRMED / NOT FOUND |
| IntrinsiX outputs normal + roughness + metallic maps | Check repo code/README | CONFIRMED / NOT FOUND |
| FLUX.1-dev is required base for IntrinsiX | Check repo requirements | CONFIRMED / DIFFERENT BASE |

**If any ID is wrong**: Find the CORRECT model ID/repo and document it.
**If the entire model doesn't exist**: Find the best alternative for UV texture infill and PBR map generation. Candidates: TexDreamer, Paint3D, SiTH.

Save to: `research/g_r3_model_id_verification.md`

---

## G-R4: SMPL Vertex Index Ground Truth (SUPPORTS Sonnet S-U2)

**Priority**: MEDIUM | **Effort**: Small (< 10 min) | **Why**: Task 22 provided vertex indices but Gemini has fabricated data before.

**Verify**:
1. Open `https://github.com/DavidBoja/SMPL-Anthropometry`
2. Find the actual landmark/vertex definition files in `data/` or `measurement_definitions/`
3. Extract the REAL vertex indices for these measurement points:
   - Head top, Heel, Neck, Nipples (L/R), Belly button, Hip
   - Shoulders (L/R), Elbows (L/R), Wrists (L/R)
   - Thigh, Calf, Ankle, Bicep, Forearm, Crotch

4. Compare against Task 22's claimed indices:
   ```
   HEAD_TOP=412, L_HEEL=3458, NECK=3050, L_NIPPLE=3042, R_NIPPLE=6489,
   BELLY_BUTTON=3501, LOW_LEFT_HIP=3134, L_SHOULDER=3011, R_SHOULDER=6470,
   L_THIGH=947, L_CALF=1103, R_BICEP=4855, R_FOREARM=5197,
   L_WRIST=2241, R_WRIST=5559, L_ANKLE=3325, L_ELBOW=1643, CROTCH=1210
   ```

5. Report: which indices are CORRECT, which are WRONG, and what the correct values are.

Also check: Does the repo use single vertex indices, or does it use vertex GROUPS (multiple vertices per landmark) for cutting plane definition?

Save to: `research/g_r4_vertex_index_verification.md`

---

## G-R5: SMPL Body Segmentation Vertex Groups (SUPPORTS Sonnet S-U3)

**Priority**: MEDIUM | **Effort**: Small (< 10 min)

**What to do**:
1. Open `https://github.com/Meshcapade/wiki/tree/main/assets/SMPL_body_segmentation`
2. Download the segmentation JSON/file
3. Extract the complete vertex index lists for these SMPL segments:
   - L_UpperArm, R_UpperArm (biceps)
   - Spine2 (chest/pectorals)
   - Spine1 (abs)
   - Pelvis (glutes)
   - L_Thigh, R_Thigh (quads/hamstrings)
   - L_Calf, R_Calf
   - L_Shoulder, R_Shoulder (deltoids)

4. Format as a JSON-ready dict: `{"biceps_l": [1643, 1644, ...], "biceps_r": [...], ...}`
5. Report total vertex count per group (sanity check: should sum to ~6890)

If the Meshcapade wiki doesn't have it, check:
- `https://github.com/gulvarol/surreal` (SMPL segmentation used in SURREAL)
- SMPL official site body segmentation data

Save to: `research/g_r5_smpl_segmentation_data.md`

---

## G-R6: Commercial Licensing Path for SMPL + Texture Models

**Priority**: LOW | **Effort**: Medium | **Why**: Task 25 flagged that SMPL, SMPLitex, and FLUX.1-dev are all non-commercial. Need to understand what a commercial launch requires.

**Research**:
1. **SMPL licensing**: What does Meshcapade charge for commercial SMPL use? Is there a startup tier? What exactly is restricted — the model weights, the topology (6890 verts), or both?
2. **Alternatives to SMPL**: GHUM (Google), Apple body models, STAR (free topology?) — which have commercial-friendly licenses?
3. **FLUX.1-schnell**: Apache 2.0 licensed. Can IntrinsiX LoRAs be retrained on schnell? Performance difference?
4. **Stable Diffusion alternatives**: SD 1.5 is CreativeML OpenRAIL-M (commercial OK with restrictions). Does SMPLitex work with SD2.1 or SDXL?

**Deliverable**: Table of licensing options + estimated costs for a commercial fitness app.

Save to: `research/g_r6_licensing_paths.md`

---

## Task Priority and Dependencies

```
HIGH (blocks Sonnet work):
  G-R1  Body comp ML papers      → unblocks S-U8
  G-R2  Photo→SMPL weight verify → unblocks S-U9
  G-R3  Model ID verification    → unblocks S-U5, S-U7

MEDIUM (improves Sonnet quality):
  G-R4  Vertex index verification → improves S-U2
  G-R5  Segmentation vertex data  → provides data for S-U3

LOW (strategic planning):
  G-R6  Commercial licensing      → informs business decisions
```

**Recommended order**: G-R3 → G-R4 → G-R5 (quick verifications) → G-R1 → G-R2 (deep research) → G-R6 (strategic)
