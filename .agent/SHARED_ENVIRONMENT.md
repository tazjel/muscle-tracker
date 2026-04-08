# Shared Development Environment — Best Practices for LLM Agents

This machine runs multiple projects that share system resources (ports, ADB devices, Python processes).
Follow these rules to avoid conflicts, zombie processes, and wasted debugging time.

---

## Port Map (MEMORIZE THIS)

| Project | Server | Port | Process signature |
|---------|--------|------|-------------------|
| **gtd3d** | py4web | **8000** | `py4web run apps` |
| **baloot-ai Studio** | Bottle | **8080** | `python run.py` (in `baloot-ai/studio/`) |
| **baloot-ai game** | FastAPI/uvicorn | **3005** | `uvicorn server.main:app` |

**Rule:** gtd3d owns port 8000. NEVER start py4web on 8080 — that's baloot-ai Studio's port.

---

## ADB Device Map

| Project | Device | Connection | Serial |
|---------|--------|------------|--------|
| **gtd3d** | MatePad MRX-AL09 | **USB** | `U4G6R20509000263` |
| **gtd3d** | MatePad MRX-AL09 | **WiFi** | `192.168.100.2:5556` |
| **baloot-ai** | Samsung A24 | **WiFi** | `192.168.100.6:5555` |

**Rules:**
- When multiple devices are connected, ALWAYS specify `-s <serial>` in ADB commands
- Run `adb devices` first to confirm which devices are attached
- gtd3d targets the MatePad (USB serial `U4G6R20509000263` or WiFi `192.168.100.2:5556`)
- MatePad uses **port 5556** for WiFi ADB (to avoid collision with baloot's 5555)
- If you see `192.168.100.6:5555` — that's baloot-ai's phone, leave it alone

---

## Before Starting Your Server

ALWAYS check if the port is already in use before starting py4web:

```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000 | findstr LISTENING
```

- **If empty** — safe to start
- **If a PID shows up** — another process is on your port. Check what it is:

```bash
# Identify the process hogging the port
tasklist /FI "PID eq <pid>"
```

Then decide:
- If it's YOUR py4web from a previous session → kill it: `taskkill /F /PID <pid>`
- If it's something else → investigate before killing

---

## Killing Zombie Processes

Servers can hang after crashes, Ctrl+C failures, or agent session timeouts.

### Quick kill by port
```bash
# Kill whatever is on port 8000 (gtd3d)
for /f "tokens=5" %a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %a
```

### Kill all py4web processes
```bash
taskkill /F /IM python.exe /FI "WINDOWTITLE eq py4web*"
```

### Nuclear option (kills ALL python — use only if desperate)
```bash
taskkill /F /IM python.exe
```
**WARNING:** This kills baloot-ai servers too. Only use when nothing else works.

---

## Common Symptoms & Fixes

### "Address already in use" when starting py4web
```
OSError: [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)
```
**Fix:** Kill the zombie process on port 8000 (see above).

### ADB targets wrong device
```
error: more than one device/emulator
```
**Fix:** 
1. `adb devices` — list all connected
2. Use the USB serial (NOT the WiFi IP): `adb -s <usb-serial> <command>`

### MatePad install fails
**Fix:** Uninstall first (MatePad doesn't support `-r` reinstall):
```bash
adb -s <serial> uninstall <package.name>
adb -s <serial> install path/to/app.apk
```
Also disable package verifier before install (Settings > Security).

### Server appears running but doesn't respond
The process may be a zombie (listening but not processing).
**Fix:** Kill by PID and restart fresh.

---

## Startup Checklist (copy-paste into your session)

```bash
# 1. Check for zombies on my port
netstat -ano | findstr :8000 | findstr LISTENING

# 2. Check ADB devices
adb devices

# 3. Start py4web (only if port is clear)
C:\Users\MiEXCITE\AppData\Local\Programs\Python\Python312\Scripts\py4web.exe run apps
```

---

## Shutdown Checklist (before ending session)

```bash
# 1. Stop your server gracefully (Ctrl+C in its terminal)
# 2. Verify port is released
netstat -ano | findstr :8000 | findstr LISTENING
# 3. If still occupied, force kill
for /f "tokens=5" %a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %a
```

---

## Key Principle

**Your project owns port 8000 and USB ADB. Don't touch port 8080 (baloot-ai Studio) or WiFi ADB (192.168.100.6:5555). Check before you start, clean up when you leave.**
