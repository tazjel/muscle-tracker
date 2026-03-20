#!/bin/bash
# Deploy RunPod GPU worker image
# Usage: bash runpod/deploy.sh [--test]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE="ghcr.io/tazjel/gtd3d-gpu-worker:latest"

echo "=== Building Docker image ==="
docker build --no-cache -t "$IMAGE" "$SCRIPT_DIR"

echo ""
echo "=== Pushing to GHCR ==="
docker push "$IMAGE"

echo ""
echo "=== Image pushed successfully ==="
echo "Image: $IMAGE"
echo "Size: $(docker image inspect "$IMAGE" --format='{{.Size}}' | awk '{printf "%.0fMB", $1/1024/1024}')"

if [ "$1" = "--test" ]; then
    echo ""
    echo "=== Running health check ==="
    # Load secrets
    if [ -f ~/.secrets.env ]; then
        source ~/.secrets.env
    fi

    if [ -z "$RUNPOD_API_KEY" ] || [ -z "$RUNPOD_ENDPOINT" ]; then
        echo "ERROR: RUNPOD_API_KEY and RUNPOD_ENDPOINT must be set"
        exit 1
    fi

    # Check endpoint health
    HEALTH=$(curl -s "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT/health" \
        -H "Authorization: Bearer $RUNPOD_API_KEY")
    echo "Health: $HEALTH"

    # Send a minimal test job (just rembg on a tiny image)
    echo ""
    echo "=== Sending test job ==="
    TEST_IMG=$(python3 -c "
import base64, cv2, numpy as np
img = np.full((64, 64, 3), 200, dtype=np.uint8)
_, buf = cv2.imencode('.jpg', img)
print(base64.b64encode(buf.tobytes()).decode())
")

    RESULT=$(curl -s "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT/runsync" \
        -H "Authorization: Bearer $RUNPOD_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"input\":{\"images\":{\"test\":\"$TEST_IMG\"},\"tasks\":[\"rembg\"]}}" \
        --max-time 120)

    STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','UNKNOWN'))")
    echo "Test result: $STATUS"

    if [ "$STATUS" = "COMPLETED" ]; then
        echo "=== ALL TESTS PASSED ==="
    else
        echo "=== TEST FAILED ==="
        echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"
        exit 1
    fi
fi
