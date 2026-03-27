import os
import subprocess
import json

actions = [
    {"click": "#btn-splat"},
    {"wait": 5},
    {"screenshot": "splat_applied.png"}
]
actions_json = json.dumps(actions)
cmd = ["uv", "run", "scripts/agent_browser.py", "interact", "http://127.0.0.1:8000/web_app/static/viewer3d/index.html", "--actions", actions_json]

print(f"Running command: {' '.join(cmd)}")
result = subprocess.run(cmd, capture_output=True, text=True)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
