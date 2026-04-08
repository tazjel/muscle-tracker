# RunPod GPU Worker v7 — Live Scan Bake (HMR2.0 + Texture + GLB)
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

# 1. System deps
RUN apt-get update && apt-get install -y \
    ffmpeg colmap libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Core Python packages (split to isolate failures)
RUN pip install --no-cache-dir \
    runpod \
    opencv-python-headless \
    smplx \
    einops \
    timm \
    yacs \
    omegaconf \
    pytorch-lightning \
    geffnet \
    pygltflib \
    scipy \
    mediapipe

# 3. rembg (ignore blinker conflict from base image)
RUN pip install --no-cache-dir --ignore-installed blinker && \
    pip install --no-cache-dir rembg[gpu]

# 4. chumpy first (4D-Humans needs it), then HMR2.0
RUN pip install --no-cache-dir --no-build-isolation chumpy && \
    pip install --no-cache-dir git+https://github.com/shubham-goel/4D-Humans.git

# 5. Force numpy 1.x (torch compat)
RUN pip install --no-cache-dir --force-reinstall "numpy==1.26.4"

# 6. Copy code
COPY core/ /app/core/
COPY runpod/ /app/

# 7. SMPL weights
RUN mkdir -p /root/.cache/4DHumans/data/smpl && \
    cp /app/SMPL_NEUTRAL.pkl /root/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl

ENV PYTHONUNBUFFERED=1
ENV CUDA_DEVICE_ORDER=PCI_BUS_ID
ENV TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0 12.0"

CMD ["python", "-u", "handler_v2.py"]
