"""
setup_densepose.py — Install DensePose inference backend.

Tries multiple approaches in order of simplicity:
  1. DensePose-TorchScript (lightweight, just PyTorch + OpenCV)
  2. Detectron2 + DensePose (full, needs CUDA)
  3. Cloud GPU setup check

Usage:
  python scripts/setup_densepose.py
"""
import subprocess
import sys
import os

PY = sys.executable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIRD_PARTY = os.path.join(PROJECT_ROOT, 'third_party')


def run(cmd, check=False, timeout=300):
    """Run a shell command, return (success, output)."""
    print(f"  $ {cmd}")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 and check:
            print(f"    FAILED: {r.stderr[:200]}")
            return False, r.stderr
        return r.returncode == 0, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT after {timeout}s")
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def check_torch():
    """Check if PyTorch is installed and has CUDA."""
    ok, out = run(f'"{PY}" -c "import torch; print(torch.__version__, torch.cuda.is_available())"')
    if ok:
        parts = out.strip().split()
        version = parts[0] if parts else 'unknown'
        has_cuda = 'True' in out
        print(f"  PyTorch {version}, CUDA: {has_cuda}")
        return True, has_cuda
    print("  PyTorch not installed")
    return False, False


def install_torch():
    """Install PyTorch with CUDA support."""
    print("\n=== Installing PyTorch ===")
    # Try CUDA 12.4 first (latest), fall back to CPU
    ok, _ = run(f'"{PY}" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124', timeout=600)
    if ok:
        return True
    # CPU fallback
    ok, _ = run(f'"{PY}" -m pip install torch torchvision', timeout=600)
    return ok


def setup_torchscript():
    """Clone and set up DensePose-TorchScript."""
    print("\n=== Setting up DensePose-TorchScript ===")
    os.makedirs(THIRD_PARTY, exist_ok=True)
    ts_path = os.path.join(THIRD_PARTY, 'DensePose-TorchScript')

    if os.path.exists(ts_path):
        print(f"  Already cloned at {ts_path}")
    else:
        ok, _ = run(f'git clone https://github.com/dajes/DensePose-TorchScript "{ts_path}"')
        if not ok:
            print("  Failed to clone DensePose-TorchScript")
            return False

    # Check if model export script exists
    export_script = os.path.join(ts_path, 'export.py')
    if os.path.exists(export_script):
        print(f"  Export script found: {export_script}")
    else:
        print(f"  WARNING: export.py not found in {ts_path}")

    # Install requirements if they exist
    req_file = os.path.join(ts_path, 'requirements.txt')
    if os.path.exists(req_file):
        run(f'"{PY}" -m pip install -r "{req_file}"')

    print("  DensePose-TorchScript ready!")
    return True


def setup_detectron2():
    """Try to install Detectron2 + DensePose."""
    print("\n=== Setting up Detectron2 + DensePose ===")

    # Check if already installed
    ok, _ = run(f'"{PY}" -c "import detectron2; print(detectron2.__version__)"')
    if ok:
        print("  Detectron2 already installed")
        return True

    # Try pip install from GitHub
    print("  Installing detectron2 from GitHub...")
    ok, out = run(f'"{PY}" -m pip install "git+https://github.com/facebookresearch/detectron2.git"', timeout=600)
    if not ok:
        print("  Detectron2 installation failed (common on Windows)")
        print("  Consider using DensePose-TorchScript or Cloud GPU instead")
        return False

    # Install DensePose
    print("  Installing DensePose...")
    ok, _ = run(f'"{PY}" -m pip install "git+https://github.com/facebookresearch/detectron2@main#subdirectory=projects/DensePose"', timeout=300)

    return ok


def setup_uv_converter():
    """Clone UVTextureConverter."""
    print("\n=== Setting up UVTextureConverter ===")
    os.makedirs(THIRD_PARTY, exist_ok=True)
    uv_path = os.path.join(THIRD_PARTY, 'UVTextureConverter')

    if os.path.exists(uv_path):
        print(f"  Already cloned at {uv_path}")
        return True

    ok, _ = run(f'git clone https://github.com/kuboshizuma/UVTextureConverter "{uv_path}"')
    if ok:
        # Install deps
        run(f'"{PY}" -m pip install pillow numpy')
        print("  UVTextureConverter ready!")
    return ok


def check_cloud():
    """Check if RunPod cloud GPU is configured."""
    print("\n=== Checking Cloud GPU (RunPod) ===")
    api_key = os.environ.get('RUNPOD_API_KEY', '')
    endpoint = os.environ.get('RUNPOD_ENDPOINT', '')

    if api_key and endpoint:
        print(f"  RunPod configured: endpoint={endpoint[:8]}...")
        return True

    # Check if configured in cloud_gpu.py
    ok, _ = run(f'"{PY}" -c "from core.cloud_gpu import is_configured; print(is_configured())"')
    if ok and 'True' in _:
        print("  RunPod configured via cloud_gpu.py")
        return True

    print("  RunPod not configured (set RUNPOD_API_KEY + RUNPOD_ENDPOINT)")
    return False


def download_model_weights():
    """Download DensePose model weights."""
    print("\n=== Downloading model weights ===")
    models_dir = os.path.join(PROJECT_ROOT, 'models', 'densepose')
    os.makedirs(models_dir, exist_ok=True)

    weights_path = os.path.join(models_dir, 'model_final_162be9.pkl')
    if os.path.exists(weights_path):
        size_mb = os.path.getsize(weights_path) / 1024 / 1024
        print(f"  Already downloaded: {weights_path} ({size_mb:.0f} MB)")
        return True

    url = ("https://dl.fbaipublicfiles.com/densepose/"
           "densepose_rcnn_R_50_FPN_s1x/165712039/model_final_162be9.pkl")
    print(f"  Downloading from {url}...")
    wp = weights_path.replace('\\', '/')
    ok, _ = run(f'"{PY}" -c "import urllib.request; urllib.request.urlretrieve(\'{url}\', \'{wp}\')"', timeout=300)
    if ok:
        size_mb = os.path.getsize(weights_path) / 1024 / 1024
        print(f"  Downloaded: {size_mb:.0f} MB")
    return ok


def main():
    print("=" * 60)
    print("DensePose Setup for gtd3d")
    print("=" * 60)

    # Step 1: Check PyTorch
    print("\n=== Checking PyTorch ===")
    has_torch, has_cuda = check_torch()
    if not has_torch:
        if not install_torch():
            print("\nFATAL: Could not install PyTorch")
            sys.exit(1)
        has_torch, has_cuda = check_torch()

    # Step 2: Try DensePose-TorchScript (easiest)
    ts_ok = setup_torchscript()

    # Step 3: Try UVTextureConverter
    uv_ok = setup_uv_converter()

    # Step 4: Try Detectron2 (harder on Windows)
    d2_ok = False
    if has_cuda:
        d2_ok = setup_detectron2()

    # Step 5: Check cloud
    cloud_ok = check_cloud()

    # Summary
    print("\n" + "=" * 60)
    print("SETUP SUMMARY")
    print("=" * 60)
    print(f"  PyTorch:              {'OK' if has_torch else 'MISSING'} (CUDA: {has_cuda})")
    print(f"  DensePose-TorchScript: {'OK' if ts_ok else 'FAILED'}")
    print(f"  UVTextureConverter:    {'OK' if uv_ok else 'FAILED'}")
    print(f"  Detectron2:           {'OK' if d2_ok else 'SKIPPED'}")
    print(f"  Cloud GPU (RunPod):   {'OK' if cloud_ok else 'NOT SET'}")

    if ts_ok or d2_ok or cloud_ok:
        print("\n  Ready! Run:")
        print("    python scripts/skin_texture_densepose.py --dir captures/skin_scan/")
    else:
        print("\n  No backend available. Set up at least one option above.")

    print()


if __name__ == '__main__':
    main()
