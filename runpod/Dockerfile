# RunPod Serverless Worker — HMR2.0 + rembg + DSINE
# GPU-accelerated body mesh inference
FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04

WORKDIR /app

# Install system deps for OpenCV + EGL (headless OpenGL for pyrender)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx libglib2.0-0 \
    libegl1-mesa libegl1 libgles2-mesa \
    && rm -rf /var/lib/apt/lists/*

# Headless rendering for pyrender (no display needed)
ENV PYOPENGL_PLATFORM=egl

# Install Python dependencies (torch/torchvision already in base image)
RUN pip install --no-cache-dir \
    runpod \
    opencv-python-headless \
    rembg[gpu] \
    Pillow \
    scipy

# Install 4D-Humans (HMR2.0) dependencies (do NOT reinstall torch)
RUN pip install --no-cache-dir \
    smplx \
    einops \
    timm \
    yacs \
    omegaconf \
    pytorch-lightning \
    chumpy

# Clone and install 4D-Humans
RUN pip install --no-cache-dir git+https://github.com/shubham-goel/4D-Humans.git

# DSINE dependencies
RUN pip install --no-cache-dir geffnet

# Real-ESRGAN for GPU texture upscaling
RUN pip install --no-cache-dir \
    realesrgan \
    basicsr

# Force numpy 1.x LAST — some deps pull in numpy 2.x which breaks torch.from_numpy()
RUN pip install --no-cache-dir --force-reinstall "numpy==1.26.4"

# Verify torch + numpy work together
RUN python -c "import torch; import numpy as np; t = torch.from_numpy(np.zeros(3)); print('torch+numpy OK:', np.__version__)"

# Verify Real-ESRGAN loads
RUN python -c "from realesrgan import RealESRGANer; from basicsr.archs.rrdbnet_arch import RRDBNet; print('Real-ESRGAN OK')"

# Pre-download DSINE model weights (model loads at runtime)
RUN python -c "import torch; torch.hub.load('hugoycj/DSINE-hub', 'DSINE', trust_repo=True)" || true

# Pre-download Real-ESRGAN model weights
RUN python -c "from basicsr.utils.download_util import load_file_from_url; \
    load_file_from_url('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth', \
    model_dir='/root/.cache/realesrgan')" || true

# Copy SMPL model weights (required by HMR2.0)
RUN mkdir -p /root/.cache/4DHumans/data/smpl
COPY SMPL_NEUTRAL.pkl /root/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl

# Also place in the path 4D-Humans expects
RUN mkdir -p /app/data && ln -s /root/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl /app/data/basicModel_neutral_lbs_10_207_0_v1.0.0.pkl

# Copy handler
COPY handler.py /app/handler.py

# RunPod serverless entrypoint
CMD ["python", "-u", "/app/handler.py"]
