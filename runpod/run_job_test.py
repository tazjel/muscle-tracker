import urllib.request, json
import os
import ssl
import base64

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
ENDPOINT_ID = "1lbdnj99ui3fe4"
url = f"https://api.runpod.ai/v2/{ENDPOINT_ID}/run"

image_path = "captures/cinematic_result_v2.png"
if not os.path.exists(image_path):
    # Fallback to another image if not exists
    image_path = "captures/mpfb_v3_render_fixed.png"

with open(image_path, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

payload = {
    "input": {
        "action": "hmr",
        "images": [img_b64],
        "directions": ["front"]
    }
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    url, 
    data=json.dumps(payload).encode(), 
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0"
    }, 
    method="POST"
)

print(f"Submitting job to Endpoint: {ENDPOINT_ID}...")
try:
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        result = json.loads(resp.read().decode())
        print(f"Status Code: {resp.status}")
        print(json.dumps(result, indent=2))
        
        job_id = result.get("id")
        if job_id:
            print(f"Job ID: {job_id}")
            # Poll for status
            # Actually, I'll just print it and wait for the user or a second run
except Exception as e:
    print(f"ERROR: {e}")
