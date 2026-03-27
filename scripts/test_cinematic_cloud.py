import sys, os
sys.path.append('.')
import logging
import numpy as np
import cv2
from core.cloud_gpu import cloud_inference, is_configured

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_cloud_handshake():
    """Verify that we can reach RunPod and it responds to the new API."""
    print("\n=== RUNPOD CINEMATIC HANDSHAKE ===")
    
    if not is_configured():
        print("ERROR: RunPod not configured in .env")
        return

    # 1. Create a dummy view
    img = np.full((512, 512, 3), [128, 128, 128], dtype=np.uint8)
    cv2.putText(img, "GTD3D TEST", (50, 256), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    
    views = {'front': img}
    
    # 2. Test basic inference (RemBG + HMR)
    print("Testing basic 3D inference (HMR2.0)...")
    try:
        result = cloud_inference(views, tasks=['hmr', 'rembg'])
        if result:
            print("SUCCESS: Cloud backend is ALIVE")
            if 'hmr' in result:
                print(f"HMR Result: {len(result['hmr'].get('betas', []))} shape params")
            if 'rembg' in result:
                print(f"RemBG Result: Mask generated for {len(result['rembg'])} views")
        else:
            print("FAILED: No result from RunPod")
    except Exception as e:
        print(f"ERROR: Handshake failed: {e}")

if __name__ == "__main__":
    test_cloud_handshake()
