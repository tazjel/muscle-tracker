import urllib.request, json
import os
import ssl
import sys

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
ENDPOINT_ID = "1lbdnj99ui3fe4"
JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "2e634ae8-4ef1-47c4-9840-331dbd68f010-e2"

url = f"https://api.runpod.ai/v2/{ENDPOINT_ID}/status/{JOB_ID}"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    url, 
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0"
    }, 
    method="GET"
)

print(f"Checking Job Status: {JOB_ID}...")
try:
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        result = json.loads(resp.read().decode())
        print(json.dumps(result, indent=2))
except Exception as e:
    print(f"ERROR: {e}")
