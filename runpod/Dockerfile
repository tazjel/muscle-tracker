# RunPod GPU Worker — LHM++ 3D Human Reconstruction Pipeline
# Replaces: HMR2.0 + DensePose
# Base: pytorch/pytorch 2.3.0 + CUDA 12.1 + cuDNN 8 devel
#   - Python 3.10 ships with this image
#   - PyTorch 2.3.0 + torchvision 0.18.0 ship with this image
#   - CUDA *devel* variant required for compiling LHM++ pointops C++ extension
FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-devel

# ── 1. System dependencies ──────────────────────────────────────────────────
# git        : clone LHM++ repo
# build-essential / ninja-build : compile pointops + diff-gaussian-rasterization
# libgl1-mesa-glx / libglib2.0-0 : headless OpenCV / Open3D
# wget       : fetch pre-built wheel files
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    ninja-build \
    wget \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 2. Upgrade pip ──────────────────────────────────────────────────────────
RUN pip install --no-cache-dir --upgrade pip

# ── 3. xformers (cu121 build, must match PyTorch 2.3.0) ────────────────────
RUN pip install --no-cache-dir -U \
    xformers==0.0.26.post1 \
    --index-url https://download.pytorch.org/whl/cu121

# ── 4. spconv for sparse 3D convolutions ───────────────────────────────────
RUN pip install --no-cache-dir spconv-cu121

# ── 5. PyTorch3D (pre-built wheel for py310 + cu121 + pt2.3.0) ─────────────
RUN pip install --no-cache-dir \
    pytorch3d \
    -f https://dl.fbaipublicfiles.com/pytorch3d/packaging/wheels/py310_cu121_pyt230/download.html

# ── 6. Gaussian-Splatting dependencies ─────────────────────────────────────
# diff-gaussian-rasterization and simple-knn must be built from source
# (no compatible pre-built wheels for this exact CUDA/torch combo)
RUN TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0" \
    pip install --no-cache-dir --no-build-isolation \
    git+https://github.com/ashawkey/diff-gaussian-rasterization/ \
    git+https://github.com/camenduru/simple-knn/

# ── 7. Pre-built wheels: torch_scatter + gsplat ────────────────────────────
# LHM++ requires exact versions; fetch cp310 linux cu121 wheels from official
# torch_scatter release page and LHM++ CI artifacts.
RUN pip install --no-cache-dir \
    "https://data.pyg.org/whl/torch-2.3.0%2Bcu121/torch_scatter-2.1.2%2Bpt23cu121-cp310-cp310-linux_x86_64.whl"

# gsplat 1.4.0 pre-built wheel (used by LHM++ for Gaussian primitives)
RUN pip install --no-cache-dir \
    "gsplat==1.4.0" \
    --index-url https://download.pytorch.org/whl/cu121 \
    || pip install --no-cache-dir \
       git+https://github.com/nerfstudio-project/gsplat.git@v1.4.0

# ── 8. rembg (CPU variant — GPU ONNX conflict with cu121 stack avoided) ─────
RUN pip install --no-cache-dir "rembg[cpu]"

# ── 9. RunPod serverless SDK ────────────────────────────────────────────────
RUN pip install --no-cache-dir runpod

# ── 10. Clone LHM++ repository ─────────────────────────────────────────────
RUN git clone --depth 1 https://github.com/aigc3d/LHM-plusplus.git /app/lhm

# ── 11. Install LHM++ Python requirements ──────────────────────────────────
# trimesh, pygltflib, open3d are included in requirements.txt
RUN pip install --no-cache-dir -r /app/lhm/requirements.txt

# ── 12. Build pointops C++ CUDA extension ──────────────────────────────────
# Must run AFTER all Python deps are installed; requires CUDA devel headers.
RUN cd /app/lhm/lib/pointops && \
    TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0" \
    python setup.py install

# ── 13. Bake model weights into image ──────────────────────────────────────
# Avoids downloading at cold-start (critical for fast serverless spin-up).
# download_all.py fetches: LHM-1B base model + SMPL-X + motion prior weights.
RUN python /app/lhm/scripts/download_all.py

# ── 14. Copy handler ────────────────────────────────────────────────────────
COPY runpod/handler_v2.py /app/handler_v2.py

# ── Environment ─────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV CUDA_DEVICE_ORDER=PCI_BUS_ID
# Cover all RunPod GPU generations: A100, A10G, H100, RTX 4090
ENV TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0"
# Tell LHM++ where its weights live (default is relative to repo root)
ENV LHM_MODEL_PATH=/app/lhm/pretrained_models

CMD ["python", "-u", "/app/handler_v2.py"]
