"""Create RunPod serverless endpoint for body mesh GPU inference."""
import runpod
import os
import sys

API_KEY = os.environ.get('RUNPOD_API_KEY', '')
if not API_KEY:
    # Try loading from secrets file
    secrets_path = os.path.expanduser('~/.secrets.env')
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            for line in f:
                if line.startswith('export RUNPOD_API_KEY='):
                    API_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")

if not API_KEY:
    print("ERROR: RUNPOD_API_KEY not set")
    sys.exit(1)

runpod.api_key = API_KEY

# Create serverless endpoint
endpoint = runpod.create_endpoint(
    name="gtd3d-cinematic-v6",
    image_name="ghcr.io/tazjel/gtd3d-gpu-worker:latest",
    gpu_ids="ADA_24",      # 24GB ADA GPUs (RTX 4090, L40) for fast 3DGS
    workers_min=0,         # Scale to zero when idle ($0/hr)
    workers_max=1,         # Max 1 worker (enough for testing)
    idle_timeout=10,       # 10s idle before scale down
)

endpoint_id = endpoint.get('id', 'unknown')
print(f"\nEndpoint created successfully!")
print(f"  Endpoint ID: {endpoint_id}")
print(f"  Image: ghcr.io/tazjel/gtd3d-gpu-worker:latest")
print(f"  GPU: 24GB (Ampere)")
print(f"  Min workers: 0 (scales to zero)")
print(f"  Max workers: 1")
print(f"\nAdd this to ~/.secrets.env:")
print(f'  export RUNPOD_ENDPOINT="{endpoint_id}"')
