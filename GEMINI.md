# Gemini CLI — Environment & Tool Guide

## CRITICAL: Your Actual Available Tools

**Your shell tool is `run_shell_command` — it runs PowerShell.**
Do NOT use `run_bash_command` — it does not exist in your tool list.

Other file tools (`write_file`, `read_file`, `edit_file`, `cli_help`, `get_internal_docs`) are all blocked or missing.

**Your working tools:**
- `run_shell_command` — runs PowerShell commands (use this for everything)
- `list_directory` — lists files in a directory

---

## Environment

- **OS**: Windows 11, PowerShell via `run_shell_command`
- **Python**: `C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\python.exe`
- **Project root**: `C:\Users\MiEXCITE\Projects\muscle_tracker`
- **Git Bash available** at: `C:\Program Files\Git\bin\bash.exe`

---

## How to Do Everything with `run_shell_command`

### Read a file
```powershell
Get-Content C:\Users\MiEXCITE\Projects\muscle_tracker\path\to\file.py
```

### Write/overwrite a file (use Python to handle quoting safely)
```powershell
python -c "open(r'C:\Users\MiEXCITE\Projects\muscle_tracker\path\to\file.py', 'w').write('''YOUR CONTENT HERE''')"
```

For large files, write Python content using a multi-line approach:
```powershell
python C:\Users\MiEXCITE\Projects\muscle_tracker\path\to\write_script.py
```

### Edit part of a file (find and replace)
```powershell
python -c "p=r'C:\Users\MiEXCITE\Projects\muscle_tracker\path\to\file.py'; t=open(p).read(); open(p,'w').write(t.replace('OLD STRING','NEW STRING'))"
```

### Search file contents
```powershell
Select-String -Path C:\Users\MiEXCITE\Projects\muscle_tracker\path\to\file.py -Pattern "search_term"
```

### List files
```powershell
Get-ChildItem C:\Users\MiEXCITE\Projects\muscle_tracker\
Get-ChildItem -Recurse -Filter "*.py" C:\Users\MiEXCITE\Projects\muscle_tracker\
```

### Run tests
```powershell
python -m pytest C:\Users\MiEXCITE\Projects\muscle_tracker\tests\ -v
```

### Git commit
```powershell
cd C:\Users\MiEXCITE\Projects\muscle_tracker; git add <files>; git commit -m "your message"
```

### Review gate (run via bash)
```powershell
bash C:\Users\MiEXCITE\Projects\muscle_tracker\claude_review.sh
```

---

## Common Mistakes to Avoid

1. **Do NOT call `run_bash_command`** — it does not exist. Use `run_shell_command`.
2. **Do NOT call `write_file`, `read_file`, `edit_file`, `cli_help`, `get_internal_docs`** — all blocked.
3. **Do NOT use Unix forward-slash paths in PowerShell** — use `C:\Users\...` backslash paths.
4. **Do NOT loop retrying a failed tool** — switch approach immediately.
5. **Do NOT spawn sub-agents** (`generalist`, `codebase_investigator`) — not available.
