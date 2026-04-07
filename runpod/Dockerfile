# RunPod Cinematic 3DGS Engine (v6.0)
# Base: CUDA 12.4 + PyTorch 2.4 (Optimized for Blackwell/Ada)
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

# 1. Install System Dependencies (Cinematic Scan Pipeline)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    colmap \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Install 2026-Standard Python Packages
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    runpod \
    opencv-python-headless \
    rembg[gpu] \
    mediapipe \
    gsplat>=1.5.0 \
    nerfstudio>=1.1.5 \
    diffusers \
    transformers \
    accelerate \
    controlnet_aux \
    smplx \
    einops \
    timm \
    yacs \
    omegaconf \
    pytorch-lightning \
    geffnet \
    realesrgan \
    basicsr && \
    pip install --no-cache-dir --no-build-isolation chumpy

# 3. Clone and install 4D-Humans (HMR2.0)
RUN pip install --no-cache-dir git+https://github.com/shubham-goel/4D-Humans.git

# 4. Force numpy 1.x LAST — some deps pull in numpy 2.x which breaks torch.from_numpy()
RUN pip install --no-cache-dir --force-reinstall "numpy==1.26.4"

# 5. Pre-compile CUDA Kernels (Saves 2-5 minutes of cold-start cost)
RUN python -c "import gsplat; print('gsplat CUDA kernels pre-compiled successfully')"

# 6. Copy Code & Assets
COPY . .
# Ensure SMPL weights are in the cache path
RUN mkdir -p /root/.cache/4DHumans/data/smpl && \
    cp SMPL_NEUTRAL.pkl /root/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl

# Environment Variables for Performance
ENV PYTHONUNBUFFERED=1
ENV CUDA_DEVICE_ORDER=PCI_BUS_ID
ENV TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0 12.0" 

# Start RunPod Handler (v2 for Cinematic support)
CMD ["python", "-u", "handler_v2.py"]
