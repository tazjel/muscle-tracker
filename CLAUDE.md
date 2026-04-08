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

## Slash Commands

### /boot
1. Read `.agent/next-session-brief.md` if it exists
2. `git log --oneline -5`
3. `git status`
4. Report state, ask what to work on

### /end
Run `/end-session`
