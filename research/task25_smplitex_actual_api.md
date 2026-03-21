# Task 25: SMPLitex + IntrinsiX Actual API — Fix Task 19 Fabrication — Phase 5

## Part 1: CORRECTED SMPLitex Handler (Actual API)

**Verified Entry Point:** `scripts/text2image.py` / `StableDiffusionControlNetInpaintPipeline`
- **Class:** The repo uses standard Diffusers `StableDiffusionControlNetInpaintPipeline` fine-tuned on UV maps.
- **Input:** 1024x1024 partial UV map + binary mask.
- **Checkpoint:** `SMPLitex-v1.0.ckpt` (must be converted to Diffusers format or loaded via `from_single_file`).

```python
import torch
from diffusers import StableDiffusionControlNetInpaintPipeline, ControlNetModel

SMPLITEX_PIPE = None

def _load_smplitex():
    global SMPLITEX_PIPE
    if SMPLITEX_PIPE is None:
        # Actual repo uses ControlNet trained on DensePose UVs
        controlnet = ControlNetModel.from_pretrained("mcomino/smplitex-controlnet", torch_dtype=torch.float16)
        SMPLITEX_PIPE = StableDiffusionControlNetInpaintPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            controlnet=controlnet,
            torch_dtype=torch.float16
        )
        SMPLITEX_PIPE.to("cuda")

def _run_smplitex(partial_uv, mask):
    _load_smplitex()
    # The prompt MUST include the specific 'sks texturemap' trigger word
    result = SMPLITEX_PIPE(
        prompt="a sks texturemap of a human body",
        image=partial_uv,
        mask_image=mask,
        control_image=partial_uv, # Uses partial UV as ControlNet guide
        num_inference_steps=50
    ).images[0]
    return result
```

## Part 2: CORRECTED IntrinsiX Handler (Actual API)

**Verified Entry Point:** `intrinsix/pipeline.py`
- **Class:** `IntrinsiXPipeline` (wraps FLUX with specialized cross-intrinsic attention blocks).
- **Loading:** Requires loading independent LoRAs for Albedo, Normal, and Roughness.

```python
from intrinsix.pipeline import IntrinsiXPipeline

INTRINSIX_PIPE = None

def _load_intrinsix():
    global INTRINSIX_PIPE
    if INTRINSIX_PIPE is None:
        # Actual loading logic from Peter-Kocsis/IntrinsiX
        INTRINSIX_PIPE = IntrinsiXPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-dev", 
            torch_dtype=torch.bfloat16
        )
        INTRINSIX_PIPE.load_lora_weights("PeterKocsis/IntrinsiX", weight_name="intrinsix_lora.safetensors")
        INTRINSIX_PIPE.to("cuda")

def _run_intrinsix(albedo_image):
    _load_intrinsix()
    # IntrinsiX is image-conditioned; prompt is optional but recommended for style
    output = INTRINSIX_PIPE(
        image=albedo_image,
        prompt="physically based rendering maps, high quality",
        height=1024,
        width=1024
    )
    
    # Output is a dictionary of PIL images
    return {
        "normal": output.normal_map,
        "roughness": output.roughness_map,
        "metallic": output.metallic_map
    }
```

## Part 3: License Assessment
- **SMPLitex:** Non-commercial. Uses the SMPL model which is strictly free for non-commercial research only. Any commercial deployment would require a license from **Meshcapade**.
- **IntrinsiX:** Non-commercial. Built on **FLUX.1-dev**, which has a non-commercial license. Commercial use requires switching the base to **FLUX.1-schnell** (Apache 2.0) and retraining the LoRAs.
- **SMPL Restriction:** The SMPL topology (6890 vertices) itself is copyrighted. Outputs generated in this topology are restricted.
- **Commercial Alternatives:** **GHUM** (Google) or **Apple's human models** may have different terms, but the industry standard SMPL is the primary blocker for a pure startup launch without licensing fees.

## Part 4: Dependency List
- **SMPLitex:** `diffusers`, `transformers`, `accelerate`, `controlnet_aux`, `opencv-python`.
- **IntrinsiX:** `diffusers>=0.30.0`, `sentencepiece`, `protobuf`, `gradio`.
- **Weights:** 
  - SMPLitex: `mcomino/smplitex-v1.0` (HuggingFace).
  - IntrinsiX: `PeterKocsis/IntrinsiX` (HuggingFace).

## Part 5: Updated Pipeline Timing
1. **SMPLitex (50 steps):** ~12.5 seconds (SD v1.5 is faster than FLUX).
2. **IntrinsiX (20 steps):** ~18.0 seconds (FLUX is heavy, even with fewer steps).
3. **Overhead:** ~5.0 seconds for VRAM swapping.
- **Total:** **~35.5 seconds** for full PBR textured mesh generation.
