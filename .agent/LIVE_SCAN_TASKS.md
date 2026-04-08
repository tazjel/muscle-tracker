# LHM++ Live Scan Pipeline — Task List

> **READ THIS FIRST.** Each task has exact file paths and line numbers.
> Do NOT explore the codebase — go straight to the listed locations.
> Do NOT run `flutter analyze`. Do NOT read files not listed here.
> Sequential Bash calls only (Windows).

---

## Status Legend
- [ ] Not started
- [x] Done

---

## TASK 1: Fix Docker Build — CUDA arch flags (BLOCKING)
**Status**: [x] Done (commit `8970cd0`)
**What**: `TORCH_CUDA_ARCH_LIST` was set at Dockerfile line 95 but needed at line 45 during `diff-gaussian-rasterization` compile. GitHub Actions has no GPU so torch can't auto-detect.
**Fix applied**: Set `TORCH_CUDA_ARCH_LIST` inline in the RUN command at line 45.
**Verify**: `gh run list --workflow=257905070 --repo tazjel/muscle-tracker --limit 1`

---

## TASK 2: Fix `ref_view` off-by-one in handler
**Status**: [ ]
**File**: `runpod/handler_v2.py` line 483
**Bug**: `ref_view = min(len(selected), 16)` — LHM++ expects `ref_view` as a 0-based index. If 16 frames are selected, this passes `ref_view=16` which is out of bounds (valid range: 0–15).
**Fix**: Change to:
```python
ref_view = min(len(selected), 16) - 1
```

---

## TASK 3: Remove dead code actions from handler
**Status**: [ ]
**File**: `runpod/handler_v2.py`
**What**: Three actions import modules that don't exist in the Docker image and will always crash:
1. `_bake_cinematic()` (lines 769–818) — imports `core.densepose_infer` and `core.texture_bake` which are NOT in the Docker image
2. `_train_splat()` (lines 674–721) — imports `from gsplat import Trainer, SplatModel` which don't exist in gsplat 1.4.0
3. `_anchor_splat()` (lines 724–766) — same gsplat API issue

**Fix**: Delete these three functions (lines 674–818). Remove their entries from the `handler()` dispatch table (around lines 843–882, look for `train_splat`, `anchor_splat`, `bake_cinematic`). Clean up the module docstring (lines 1–15) to remove references to these dead actions.

**Do NOT delete**: `_extract_frames()` and `_run_colmap()` (lines 637–671) — standalone utilities, keep them.

---

## TASK 4: Fix `body_scan_result` endpoint — hardcoded zeros
**Status**: [ ]
**File**: `apps/web_app/controllers.py` lines 3806–3808
**Bug**: `vertex_count` and `face_count` are hardcoded to 0, never read from session. The `body_scan_session` table (models.py lines 214–232) has no `vertex_count`/`face_count` columns either.

**Three-part fix**:

### 4a. Add columns to model (`apps/web_app/models.py`)
After line 230 (`coverage_pct` field), add:
```python
Field('vertex_count', 'integer', default=0),
Field('face_count', 'integer', default=0),
```

### 4b. Save values in finalize (`apps/web_app/controllers.py` ~line 4543)
Change the `db.update()` call to include the new fields:
```python
db(db.body_scan_session.id == session.id).update(
    status='COMPLETE',
    glb_path=glb_path,
    texture_path=texture_path,
    mesh_path=glb_path,
    vertex_count=result.get('vertex_count', 0),
    face_count=result.get('face_count', 0),
)
```

### 4c. Read values in result endpoint (`apps/web_app/controllers.py` ~lines 3806–3808)
Replace the hardcoded zeros:
```python
vertex_count = session.vertex_count or 0
face_count = session.face_count or 0
```

### 4d. Migrate SQLite (required because `fake_migrate_all=True`)
```bash
sqlite3 apps/web_app/databases/storage.db "ALTER TABLE body_scan_session ADD COLUMN vertex_count INTEGER DEFAULT 0;"
sqlite3 apps/web_app/databases/storage.db "ALTER TABLE body_scan_session ADD COLUMN face_count INTEGER DEFAULT 0;"
```

---

## TASK 5: Create RunPod Endpoint (USER MANUAL STEP)
**Status**: [ ]
**Prerequisite**: Docker build succeeds (Task 1)
**Image**: `ghcr.io/tazjel/gtd3d-gpu-worker:latest`
**The user must do this** — requires RunPod web console.
**Settings**: GPU = RTX 4090 or A10G (8GB+ VRAM), Min workers = 0, Max workers = 1, Idle timeout = 5s
**After creation**, set env vars:
```bash
export RUNPOD_API_KEY=<key>
export RUNPOD_ENDPOINT=<new endpoint ID>
```

---

## TASK 6: End-to-End Test with curl
**Status**: [ ]
**Prerequisite**: Tasks 2–5 all done
**Test images**: `test_frames/vid5_man/` — front1.jpg, back1.jpg, right_hand.jpg, left_hand.jpg

**Step 1** — Start py4web:
```bash
C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\Scripts\py4web.exe run apps --host 0.0.0.0
```

**Step 2** — Create test customer (if needed):
```bash
curl -X POST http://localhost:8000/web_app/api/customer \
  -H "Content-Type: application/json" \
  -d '{"name": "Test User", "height_cm": 175, "weight_kg": 70}'
```

**Step 3** — Upload body scan frames:
```bash
curl -X POST http://localhost:8000/web_app/api/customer/1/body_scan \
  -F "frame_0=@test_frames/vid5_man/front1.jpg" \
  -F "frame_1=@test_frames/vid5_man/back1.jpg" \
  -F "frame_2=@test_frames/vid5_man/right_hand.jpg" \
  -F "frame_3=@test_frames/vid5_man/left_hand.jpg" \
  -F 'pass_config={"passes": 1}'
```
Note the `session_id` from response.

**Step 4** — Finalize (triggers RunPod, takes 30–120s):
```bash
curl -X POST http://localhost:8000/web_app/api/customer/1/body_scan/<SESSION_ID>/finalize \
  -H "Content-Type: application/json" \
  -d '{"height_cm": 175, "weight_kg": 70, "gender": "male"}'
```

**Step 5** — Check result:
```bash
curl http://localhost:8000/web_app/api/body_scan_result?session=<SESSION_ID>
```
Expected: `status=COMPLETE`, `glb_url` pointing to `.glb`, `vertex_count > 0`.

**Step 6** — View in browser:
Open `http://localhost:8000/web_app/body_viewer?session=<SESSION_ID>`

---

## TASK 7: Verify GLB renders in body_viewer.html
**Status**: [ ]
**File**: `apps/web_app/templates/body_viewer.html`
**What**: Viewer uses `THREE.GLTFLoader`. The Gaussian→GLB uses degenerate triangles `[i,i,i]` per point — may render as invisible zero-area faces.

**If model appears invisible**:
- Option A: In `handler_v2.py` `_gaussians_to_glb()` (lines 188–295), switch to `GL_POINTS` primitive mode
- Option B: In `body_viewer.html`, add `THREE.Points` fallback for point-cloud GLBs
- **Do NOT attempt gsplat.js without user approval** — major scope change

---

## Architecture Reference (read-only context)

### API Flow
```
MatePad → POST /api/customer/{id}/body_scan (frames)
       → POST /api/customer/{id}/body_scan/{session}/finalize
       → controllers.py._finalize_via_runpod()
       → RunPod handler_v2.py._live_scan_bake()
       → returns {glb_b64, vertex_count, face_count, texture_coverage}
       → controllers.py saves GLB, updates body_scan_session
       → body_viewer.html fetches /api/body_scan_result?session=X
       → THREE.GLTFLoader renders GLB
```

### Key Files
| File | Purpose |
|------|---------|
| `runpod/handler_v2.py` | GPU worker — LHM++ inference + Gaussian→GLB |
| `runpod/Dockerfile` | Docker image for RunPod serverless |
| `apps/web_app/controllers.py` | py4web API endpoints |
| `apps/web_app/models.py` | Database table definitions |
| `apps/web_app/templates/body_viewer.html` | Three.js 3D viewer |
| `apps/web_app/common.py` | DB connection (`fake_migrate_all=True`) |
| `.github/workflows/cinematic_build.yml` | GitHub Actions Docker build |

### Environment
- py4web: `C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\Scripts\py4web.exe run apps --host 0.0.0.0`
- Python: `C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\python.exe`
- RunPod balance: $13.86
- Docker image: `ghcr.io/tazjel/gtd3d-gpu-worker:latest`
- Test images: `test_frames/vid5_man/` (front1.jpg, back1.jpg, right_hand.jpg, left_hand.jpg)

### Execution Order
```
Task 1 (Docker fix ✅) → Task 2 (ref_view fix) → Task 3 (dead code cleanup)
→ Task 4 (DB columns) → Task 5 (RunPod endpoint — user manual)
→ Task 6 (curl test) → Task 7 (viewer check)
```
