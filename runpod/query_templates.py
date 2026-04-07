import urllib.request, json
import os
import ssl

API_KEY = "***REMOVED***"
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"

query = """
query {
  myself {
    podTemplates {
      id
      name
      imageName
      containerDiskInGb
    }
  }
}
"""

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    url, 
    data=json.dumps({"query": query}).encode(), 
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }, 
    method="POST"
)

print("Querying RunPod Templates...")
try:
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
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
    print(f"ERROR: {e}")
