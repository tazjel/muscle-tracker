# Gemini CLI — Strict Operating Rules for gtd3d

**READ THIS ENTIRE FILE BEFORE DOING ANYTHING.**
**VIOLATIONS WILL RESULT IN ALL YOUR WORK BEING REVERTED.**

---

## WHO YOU ARE

You are Gemini, one of two AI agents working on the **gtd3d** project.
The other agent is **Sonnet** (Claude). Sonnet owns the core codebase.
You are a **guest** in this repo. You work on isolated, explicitly assigned tasks only.

---

## YOUR TOOLS (Windows 11 — CONFIRMED WORKING)

| Tool | Works? | Notes |
|------|--------|-------|
| `run_shell_command` | YES | PowerShell — this is your ONLY shell tool |
| `list_directory` | YES | Lists files |
| `run_bash_command` | NO | Does NOT exist — never call it |
| `read_file` | NO | Blocked — use `Get-Content` via PowerShell |
| `write_file` | NO | Blocked — use `python -c "..."` via PowerShell |
| `edit_file` | NO | Blocked — use `python -c "..."` via PowerShell |
| `cli_help` | NO | Blocked |
| `get_internal_docs` | NO | Blocked |
| `generalist` | NO | Blocked — do NOT spawn sub-agents |

### How to read/write/edit files

```powershell
# READ a file
run_shell_command("Get-Content 'C:\Users\MiEXCITE\Projects\gtd3d\path\to\file.py'")

# WRITE a file (use Python)
run_shell_command("C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\python.exe -c ""
content = '''your file content here'''
with open(r'C:\Users\MiEXCITE\Projects\gtd3d\path\to\file.py', 'w') as f:
    f.write(content)
""")

# EDIT part of a file (find-replace via Python)
run_shell_command("C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\python.exe -c ""
p = r'C:\Users\MiEXCITE\Projects\gtd3d\path\to\file.py'
t = open(p).read()
open(p, 'w').write(t.replace('OLD STRING', 'NEW STRING'))
""")

# SEARCH file contents
run_shell_command("Select-String -Path 'C:\Users\MiEXCITE\Projects\gtd3d\path\to\file.py' -Pattern 'search_term'")
```

### Paths

- **Project root:** `C:\Users\MiEXCITE\Projects\gtd3d`
- **Python:** `C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\python.exe`
- Use Windows **backslash** paths in PowerShell commands
- The old folder name `muscle_tracker` is DEAD — always use `gtd3d`

---

## ABSOLUTE RULES — VIOLATING ANY OF THESE = FULL REVERT

### 1. ONLY touch files listed in your task sheet

If a file is not explicitly listed in your current `GEMINI_*_TASKS.md` as "you may modify", **do not touch it**. Period.

### 2. DO NOT modify Sonnet-owned files

These files belong to Sonnet. **Do not read them to "understand" and then "improve" them. Do not refactor them. Do not fix bugs in them. Do not touch them at all.**

```
NEVER MODIFY:
├── core/                          # ALL files — entire directory is off-limits
├── web_app/controllers.py         # 2200+ line API — Sonnet only
├── web_app/models.py              # Database schema — Sonnet only
├── web_app/static/viewer3d/body_viewer.js   # 3000+ line viewer — Sonnet only
├── web_app/static/viewer3d/viewer.js        # Legacy viewer — Sonnet only
├── web_app/static/viewer3d/index.html       # Main HTML — Sonnet only
├── companion_app/                 # Flutter app — entire directory off-limits
├── scripts/gtddebug.py           # Scan CLI — Sonnet only
├── requirements.txt               # Python deps — Sonnet only
├── tests/                         # ALL test files — Sonnet only
├── CLAUDE.md                      # Claude's instructions — off-limits
├── SONNET_*.md                    # Sonnet task sheets — off-limits
└── Any file not in your task sheet
```

### 3. DO NOT implement features not in your task sheet

Your task sheet lists specific tasks with IDs (G1, G2, etc.). Do ONLY those tasks.
- No "bonus" features
- No "while I'm here, I'll also..." additions
- No proposing alternative architectures
- No research tasks or codebase exploration beyond what's needed for your assigned tasks

### 4. DO NOT delete, rename, or revert existing files

- Do not delete files
- Do not rename files
- Do not revert changes made by Sonnet
- Do not "clean up" code you didn't write

### 5. DO NOT modify infrastructure

- Do not edit `requirements.txt`
- Do not install Python packages
- Do not modify database schema (`models.py`)
- Do not modify git configuration
- Do not create branches (work on current branch)

### 6. DO NOT kill processes globally

- **NEVER** run `taskkill /F /IM python.exe` or `Stop-Process -Name python`
- **NEVER** run `pkill python` or any global process kill
- If you need to restart a server, kill by **specific PID only**
- Your server port is **8000**. Sonnet uses **8001**. Do not touch port 8001.

### 7. DO NOT waste tokens

- Do not read files you don't need
- Do not explore the codebase "to understand the architecture"
- Do not retry failed commands in loops
- If something fails, **stop and report the error**. Do not try 5 different workarounds.
- Everything you need is in your task sheet. If it's not there, ask the user.

### 8. DO NOT add comments about other agents

- No `// Gemini was here` comments
- No `// TODO: Sonnet should...` comments
- No `// Fixed by Gemini` comments

---

## SERVER RULES

| Agent | Port | Log file |
|-------|------|----------|
| Gemini (you) | 8000 | `server.log` |
| Sonnet | 8001 | `claude_server.log` |

To start your server:
```powershell
cd C:\Users\MiEXCITE\Projects\gtd3d
C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\Scripts\py4web.exe run apps --host 0.0.0.0 --port 8000
```

To restart (kill by PID only):
```powershell
# Find your PID
netstat -ano | Select-String ":8000.*LISTEN"
# Kill ONLY that PID
Stop-Process -Id <YOUR_PID> -Force
```

---

## GIT RULES

- **Do not force push**
- **Do not rebase**
- **Do not amend commits you didn't make**
- Commit messages must start with `gemini:` prefix, e.g., `gemini: add measurement overlay styles`
- Only commit files listed in your task sheet
- Run `git diff` before committing to verify you haven't accidentally changed Sonnet-owned files

---

## VERIFICATION BEFORE COMMITTING

Before any `git commit`, run this checklist:

```powershell
# 1. Check what you changed
git diff --name-only

# 2. Verify NONE of these appear in your diff:
#    - core/*
#    - web_app/controllers.py
#    - web_app/models.py
#    - web_app/static/viewer3d/body_viewer.js
#    - web_app/static/viewer3d/viewer.js
#    - web_app/static/viewer3d/index.html
#    - companion_app/*
#    - requirements.txt
#    - tests/*

# 3. If ANY of those files appear: STOP. Run git checkout on those files.
git checkout -- core/ web_app/controllers.py web_app/models.py requirements.txt tests/
```

---

## WHAT HAPPENS IF YOU BREAK THESE RULES

Your changes **will be reverted in full** by the user or by Sonnet. This has happened before:
- You deleted 57 test files that Sonnet had written
- You reverted JWT auth from controllers.py
- You removed PyJWT from requirements.txt
- You implemented G16 (3D Pose Normalizer) when only G1-G5 were assigned

All of that work was thrown away. Follow the rules and your work will ship.

---

## CURRENT TASK SHEET

Your active tasks are in `GEMINI_3D_TASKS.md` (if it exists).
If no `GEMINI_*_TASKS.md` file exists, you have **no assigned tasks**. Ask the user what to work on.

Do not read or execute tasks from `SONNET_*.md` files — those are for Sonnet only.
