#!/bin/bash
# GTD3D Repo Rename: muscle-tracker → gtd3d
# Run this script once from the repo root.
# Prerequisites: gh CLI installed and authenticated.

set -e

echo "=== GTD3D Repo Rename ==="

# 1. Rename on GitHub
echo "Renaming GitHub repo..."
gh repo rename gtd3d --yes

# 2. Update git remote
echo "Updating git remote..."
git remote set-url origin https://github.com/tazjel/gtd3d.git

# 3. Verify
echo "Verifying..."
git remote -v
gh repo view --json name -q '.name'

echo "=== Done! Repo is now 'gtd3d' ==="
