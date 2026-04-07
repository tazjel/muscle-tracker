import os
import json
import urllib.request
import ssl

def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        k, v = parts
                        os.environ[k.strip()] = v.strip().strip('"\'')

load_env()
api_key = os.environ.get('RUNPOD_API_KEY')
endpoint = os.environ.get('RUNPOD_ENDPOINT')

print(f"Testing Endpoint: {endpoint}")
url = f"https://api.runpod.ai/v2/{endpoint}/health"
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
    'User-Agent': 'Gemini-3D-v5.5'
}

# Create a context that ignores SSL verification for the diagnostic test
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

try:
    req = urllib.request.Request(url, headers=headers, method='GET')
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        result = json.loads(resp.read().decode())
        print(f"Status Code: {resp.status}")
        print(json.dumps(result, indent=2))
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} - {e.reason}")
    try:
        error_body = e.read().decode()
        print(f"Response Body: {error_body}")
    except:
        pass
except Exception as e:
    print(f"Error: {e}")