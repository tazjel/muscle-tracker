# RunPod Configuration Upgrade Log (v6.0 Cinematic Scan)

## **Mission Overview**
Upgrade the RunPod Serverless environment to support 3D Gaussian Splatting (3DGS) training, mesh-guided alignment, and cinematic PBR baking.

---

## **Safety & Cost Guardrails**
1. **Backups:** Original files stored in `runpod/backups/`.
2. **Flashboot Integration:** Use multi-stage builds and local caching to minimize "cold start" duration (and associated costs).
3. **Lazy Loading:** All CUDA-heavy models (gsplat, Nerfstudio, HMR2) are lazy-loaded only when their specific action is called, saving VRAM and initialization time.
4. **Volume Mounting:** Large model weights (SMPL, checkpoints) are moved to a persistent Network Volume to avoid redundant `pip install` or `wget` calls during container startup.

---

## **Change Log**

### **[2026-03-26] Phase 1: Infrastructure Initialization**
- **Action:** Created `RUNPOD_UPGRADE_LOG.md`.
- **Action:** Performed full backup of `runpod/` directory.
- **Decision:** Selected `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04` as the 2026 base image for `gsplat` v1.5.0+ and Blackwell compatibility.
- **Strategy:** Moving weights (SMPL, HMR2) to `/workspace` (Network Volume) to avoid container bloat and cold-start costs.

### **[2026-03-26] Phase 3: Application Integration (Web App)**
- **Note:** Docker Desktop unavailable on host; shifting to local application integration for zero-cost validation.
- **Action:** Created `apps/web_app/cinematic_controller.py` to handle `api/cinematic_scan` and `api/anchor_splat`.
- **Action:** Updated `apps/web_app/models.py` with `splat_url` field for the `video_scan_session` table.
- **Action:** Updated `core/cloud_gpu.py` with `cloud_train_splat` and `cloud_anchor_splat` client logic.
- **Status:** Application logic is ready. Ready to verify endpoint registration.

---
**Status:** All configurations (Dockerfile.new, handler_v2.py) are finalized and backed up. Application integration complete. Ready for verification.


---
**Status:** Backups Complete. Initializing Dockerfile Research.
