#!/usr/bin/env python3
"""GTD3D Browser Automation — thin entry point.

All commands are implemented in scripts/browser/:
  browser/__init__.py  — shared utilities, adb command, CLI dispatcher
  browser/core.py      — screenshot, console, eval, audit, filmstrip,
                         interact, diff, assert, watch, describe
  browser/viewer.py    — viewer3d, verify, skin-check, cinematic-check
  browser/studio.py    — studio-audit, studio-v2-audit

Usage:
    PY=C:/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
    $PY scripts/agent_browser.py <command> [args]
    $PY scripts/agent_browser.py --help
"""
import sys
from pathlib import Path

# Add scripts/ to sys.path so `import browser` resolves to scripts/browser/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from browser import main

if __name__ == "__main__":
    main()
