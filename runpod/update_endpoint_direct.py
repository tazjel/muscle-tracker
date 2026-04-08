import urllib.request, json
import os

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
ENDPOINT_ID = "1lbdnj99ui3fe4"
url = f"https://api.runpod.io/graphql?api_key={API_KEY}"

# Update existing endpoint to trigger a fresh worker pull
mutation = """
mutation {
  saveEndpoint(
    input: {
      id: "1lbdnj99ui3fe4"
      name: "gtd3d-body-mesh"
      imageName: "ghcr.io/tazjel/gtd3d-gpu-worker:latest"
      gpuIds: "AMPERE_24"
      idleTimeout: 10
      minWorkers: 0
      maxWorkers: 1
    }
  ) {
    id
    name
  }
}
"""

req = urllib.request.Request(
    url, 
    data=json.dumps({"query": mutation}).encode(), 
    headers={"Content-Type": "application/json"}, 
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(json.dumps(result, indent=2))
except Exception as e:
    print(f"ERROR: {e}")
