# gtd3d — Claude Agent Instructions

## Identity & Scope
This is **gtd3d** — a fitness body-composition tracker (py4web + Flutter + 3D mesh pipeline).
Agent works ONLY on the gtd3d repository.

## Architecture
- **Backend**: py4web (Python 3.12)
- **Frontend**: Flutter 3.41
- **3D pipeline**: Blender mesh generation, body composition analysis
- **Vision**: Gemini vision for body measurement

## Commands
```bash
# Run backend
C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\Scripts\py4web.exe run apps

# Flutter
C:\Users\MiEXCITE\development\flutter\bin\flutter.bat run
C:\Users\MiEXCITE\development\flutter\bin\flutter.bat clean  # always clean when behavior doesn't match code
```

## Token Budget
- Sequential Bash calls only (Windows)
- Use `Grep` over reading whole files
- Do NOT explore `Desktop/Gemini_vision/` — server logs only, not source code

## GTD Platform (Cross-Project System)

GTD3D is part of the **GTD Platform** — a unified system across 4 projects (Baloot AI, GTD3D, zRoblox, Tazjel) sharing GTDdebug as SDK and Tazjel as orchestration brain.

### What Changed for GTD3D
- **GTDdebug pip-installed**: `pip install -e C:/Users/MiEXCITE/Desktop/GTDdebug` — import directly with `from gtddebug.quality import ...`, no path hacks needed.
- **GTD Studio**: GTD3D routes are proxied through `GTDdebug/gtd_studio/domains/gtd3d/routes.py`. API calls at `/gtd3d/api/*` forward to the py4web server at `:8000`. The 3D viewer is served directly.
- **Agent Protocol**: New GTDdebug commands for cross-project coordination:
  ```bash
  cd C:/Users/MiEXCITE/Desktop/GTDdebug
  python gtddebug.py agent-boot gtd3d --json       # Check for pending tasks from Tazjel
  python gtddebug.py agent-end gtd3d --summary "..." --json  # Report session end
  python gtddebug.py agent-inbox gtd3d --json      # Read cross-agent messages
  python gtddebug.py agent-send baloot --message "..." --json  # Message another project
  ```
- **Capabilities**: `.agent/capabilities.json` declares GTD3D capabilities (body-scan, 3d-mesh, blender-pipeline, gemini-vision, cloud-deploy) and GTDdebug profile (`muscle-debug`).
- **Cloud Pipeline**: `python gtddebug.py gcp-deploy-all --json` deploys all projects including GTD3D. GCP config: `gtd3d-project` / `gtd3d-server` / `me-central1`.
- **Tazjel Desktop Worker**: Can receive tasks for GTD3D from the phone app — routes to `muscle-debug` GTDdebug profile.

### For Agents Working in GTD3D
- This project's GTDdebug profile is `muscle-debug` (for deploy/benchmark commands).
- py4web server runs on port **8000** — GTD Studio proxies to it, so both can coexist.
- When modifying `apps/web_app/controllers.py`, the GTD Studio proxy forwards automatically — no manual sync needed.
- The unified studio at `:8080` lets you switch between GTD3D viewer and other project editors.

## Slash Commands

### /boot
1. Read `.agent/next-session-brief.md` if it exists
2. `git log --oneline -5`
3. `git status`
4. Report state, ask what to work on

### /end
Run `/end-session`
