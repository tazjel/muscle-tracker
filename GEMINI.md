# Gemini Lead Agent — 3D Upgrade Branch (3dgemini)

This branch is designated for Gemini to lead the high-fidelity 3D upgrade of gtd3d.
Gemini is the primary authority in this branch.

---

## MISSION: gtd3d v5.5 "Cinematic Scan"

**Objective**: Complete the transition to the MPFB2 (MakeHuman) architecture with photorealistic PBR rendering, advanced muscle mapping, and real-time phenotype control.

---

## OPERATING RULES (3dgemini Branch)

1. **Full Codebase Access**: Gemini is authorized to modify any file necessary to achieve the mission objectives, including core logic, viewer JS, and integration controllers.
2. **Lead Architect**: Gemini owns the architectural direction of the MPFB2 transition.
3. **Validation First**: Every major change must be verified via the internal test suite and browser audits.
4. **Environment**: Windows 11 / PowerShell. Use absolute paths and UTF-8 encoding.

---

## BRANCH TOOLS

- **Primary Server**: Port 8000 (Gemini Instance)
- **Primary Task Sheet**: `GEMINI_3D_TASKS.md`
- **Audit Tool**: `scripts/agent_browser.py`

---

## AUTHORIZED MODIFICATION SCOPE

- `core/` (All vision, mesh, and deformation logic)
- `web_app/` (API controllers and 3D viewer)
- `meshes/` (Templates and shape deltas)
- `research/` (Technical reports and mapping data)

---

## MANDATORY BROWSER WORKFLOW (The "Always" Rule)

For every task involving the 3D viewer or web interface, you MUST follow this sequence:

1.  **Surgical Implementation**: Apply changes idiomatically and follow project style.
2.  **Browser Verification**: Use `scripts/agent_browser.py` (e.g., `console`, `describe`, or `cinematic-check`) to verify the work.
3.  **Console Audit**: You MUST read and resolve all browser console errors (404s, JS exceptions, etc.). Do not show work that has errors.
4.  **Set Optimal Defaults**: Programmatically set the view to the most visually impressive or requested state (active tabs, HDRI, visual modes) so the user sees the final work immediately without manual clicks.
5.  **Direct Launch**: Always execute a shell command to open the browser (e.g., `start chrome <link>`) with the final URL.

---

## PROJECT STATUS: v5.5 UPGRADE IN PROGRESS
- MPFB2 Standardized (13,380 verts)
- Vectorized Skin Quilting (50x speedup)
- Frequency-Separated PBR Normal mapping
- 3D Muscle Definition Projection
- Edge Warmth Ratio (EWR) Skin Audit

---

## WINDOWS & PY4WEB DISCOVERIES (v5.5)

1.  **Py4web `URL()` Syntax**: In templates, positional arguments are for path parameters (e.g., `[[=URL('action', 1)]]`), while query parameters must use `vars=dict()`. Keyword arguments for path params cause `TypeError`.
2.  **`Auth` Import Path**: In Py4web v1.2023+ (Windows), `Auth` should be imported from `py4web.utils.auth`, not directly from `py4web`.
3.  **Path Resolution**: Use absolute paths (`PROJECT_ROOT`) for all `static_file` serving and database URIs to avoid parent-depth bugs in the `apps/` directory structure.
4.  **CORS & IP Webcam**: Browser blocks direct `/sensors` fetch from Phone IPs. Must use server-side proxying for reliable sensor data integration in the Studio UI.
