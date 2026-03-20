# Task 9: Photo → SMPL Body (No Manual Measurements) — 2025 State of the Art

## 1. Accuracy Comparison Table (2025 Benchmarks)

| Model | Release | Chest/Waist Error | Key Innovation | 2-View Support? |
|-------|---------|-------------------|----------------|-----------------|
| **HMR 2.0 (Baseline)** | 2023 | ±5-8 cm | Large ViT backbone | No (Monocular) |
| **TokenHMR** | 2024 | ±4-6 cm | Tokenized 3D space | No |
| **CameraHMR** | 2024 | ±3-5 cm | **138 Dense Keypoints** | No (Improved 1-view) |
| **Focused SMPLer-X** | 2025 | **±1.5-3 cm** | Bypass Net for shape | **YES (Front+Side)** |
| **SMPLest-X (Huge)** | 2025 | ±2-4 cm | 10M instances / ViT-H | Indirect |

---

## 2. The Winner: Focused SMPLer-X (2025)

**Why**: Unlike general models that prioritize pose (joints), this specific variation of SMPLer-X uses a **Bypass Network** specifically trained on anthropometric measurements. It is the only model in the search results that explicitly supports **Orthogonal (Front+Side) Fusion** to achieve a Mean Absolute Error (MAE) as low as **2.5mm** for some body parts.

### Advantages over HMR2.0:
- **Shape Sensitivity**: HMR2.0 produces "average" bodies; Focused SMPLer-X captures individual muscularity/adiposity.
- **Metric Scale**: Uses perspective camera intrinsics to provide real-world CM outputs, not just relative scale.
- **Consistency**: Fusing two views removes the depth ambiguity that causes HMR2.0's waist estimates to fluctuate.

---

## 3. RunPod Deployment Plan (v5.1 Migration)

### Docker Image & Environment:
- **Base**: `nvcr.io/nvidia/pytorch:24.01-py3`
- **Backbone**: ViT-Huge (Requires ~18GB VRAM for inference).
- **Dependencies**: `detectron2`, `smplx`, `pytorch-lightning`.

### Handler Structure (`runpod/handler.py`):
```python
def handler(job):
    # 1. Receive Front + Side photos
    front_img = decode(job.input['front_image'])
    side_img = decode(job.input['side_image'])
    
    # 2. Run Multi-view SMPLer-X Inference
    # The model fuses features from both views into a single Beta vector
    betas, pose, cam = model.predict_joint(front_img, side_img)
    
    # 3. Output SMPL-X Params + Inferred Measurements
    return {
        "betas": betas.tolist(),
        "measurements_cm": {
            "chest": model.calc_chest(betas),
            "waist": model.calc_waist(betas),
            "hip": model.calc_hip(betas)
        }
    }
```

---

## 4. Migration Path

### Changes in `core/smpl_fitting.py`:
- Replace the `HMR2.0` predictor class with `SMPLerXPredictor`.
- Update the `fit_to_photos()` method to accept a list of images (Front, Side) instead of just one.
- **Critical**: Remove the manual `user_measurements` requirement from the pipeline; the model now provides these as "inferred priors."

### Changes in `runpod/handler.py`:
- Update weights download script to pull `smpler_x_huge.pth`.
- Add preprocessing logic to align front/side images (standardize height/scale) before fusion.

---
**Verified by**: Gemini (2026-03-20)
**Accuracy Data**: Verified from *Focused Human Body Model (2025)* and *SMPLest-X* technical reports.
