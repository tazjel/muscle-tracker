"""
Test the live_scan_bake RunPod action with real captured frames.
Usage: python test_live_scan.py [session_dir]
  e.g. python test_live_scan.py uploads/live_scans/1_bf83ffcf
"""
import os, sys, json, base64, time, glob
import requests

API_KEY = os.environ.get('RUNPOD_API_KEY', '')
ENDPOINT = os.environ.get('RUNPOD_ENDPOINT', '')

def main():
    if not ENDPOINT:
        print("ERROR: Set RUNPOD_ENDPOINT env var")
        sys.exit(1)

    session_dir = sys.argv[1] if len(sys.argv) > 1 else 'uploads/live_scans/1_bf83ffcf'
    jpgs = sorted(glob.glob(os.path.join(session_dir, '*.jpg')))
    if not jpgs:
        print(f"No JPGs found in {session_dir}")
        sys.exit(1)

    # Pick up to 10 best frames (evenly spaced)
    step = max(1, len(jpgs) // 10)
    selected = jpgs[::step][:10]
    print(f"Selected {len(selected)} frames from {len(jpgs)} total")

    frames = []
    for i, path in enumerate(selected):
        with open(path, 'rb') as f:
            image_b64 = base64.b64encode(f.read()).decode()
        # Check for IUV .npy
        iuv_b64 = None
        npy_pattern = path.replace('.jpg', '_iuv.npy')
        if os.path.exists(npy_pattern):
            import numpy as np, cv2
            iuv = np.load(npy_pattern)
            _, buf = cv2.imencode('.png', iuv)
            iuv_b64 = base64.b64encode(buf.tobytes()).decode()
        frames.append({
            'image_b64': image_b64,
            'iuv_b64': iuv_b64,
            'region': f'view_{i}',
            'sharpness': 100.0,
        })

    payload = {
        'input': {
            'action': 'live_scan_bake',
            'frames': frames,
            'profile': {'height_cm': 175, 'weight_kg': 72, 'gender': 'male'},
        }
    }

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }

    print(f"Submitting job to RunPod endpoint {ENDPOINT}...")
    print(f"Payload size: {len(json.dumps(payload)) / 1024 / 1024:.1f} MB")

    resp = requests.post(
        f"https://api.runpod.io/v2/{ENDPOINT}/run",
        json=payload, headers=headers, timeout=30,
    )
    resp.raise_for_status()
    job = resp.json()
    job_id = job['id']
    print(f"Job submitted: {job_id}")

    # Poll
    status_url = f"https://api.runpod.io/v2/{ENDPOINT}/status/{job_id}"
    while True:
        time.sleep(5)
        sr = requests.get(status_url, headers=headers, timeout=15)
        sd = sr.json()
        status = sd.get('status', '')
        print(f"  Status: {status}")
        if status == 'COMPLETED':
            output = sd.get('output', {})
            print(f"\n=== RESULT ===")
            print(f"Status: {output.get('status')}")
            print(f"HMR used: {output.get('hmr_used')}")
            print(f"Vertices: {output.get('vertex_count')}")
            print(f"Faces: {output.get('face_count')}")
            print(f"Coverage: {output.get('texture_coverage', 0)*100:.1f}%")
            # Save GLB
            glb_b64 = output.get('glb_b64', '')
            if glb_b64:
                out_path = os.path.join(session_dir, 'runpod_result.glb')
                with open(out_path, 'wb') as f:
                    f.write(base64.b64decode(glb_b64))
                print(f"GLB saved: {out_path} ({os.path.getsize(out_path)/1024:.0f} KB)")
            break
        elif status == 'FAILED':
            print(f"FAILED: {sd.get('error', 'unknown')}")
            break

if __name__ == '__main__':
    main()
