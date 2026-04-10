# GTD3D — Sonnet Task Updates

> Sonnet updates this file after each completed task.
> Opus reads this to track progress and plan next waves.

<!-- Updates will appear below, newest first -->

## [2026-04-10] Wave 3C Update

### Task 3C.1 — Add MOCK_MODE toggle UI
- Status: done
- Files changed: `apps/web_app/templates/studio_v2.html`, `apps/web_app/static/studio/studio.js`
- Notes: Added toggle button in topbar (top-right area). `toggleMockMode()` flips `Studio.MOCK_MODE`, updates button appearance (text Mock/Live, accent color on Live), logs mode change, re-inits CustomerPanel and RenderPanel. `MOCK_MODE: true` remains default.

### Task 3C.2 — Harden panels for MOCK_MODE=false
- Status: done
- Files changed: `customer-panel.js`, `body-scan-panel.js`, `report-panel.js`, `3dgs-panel.js`, `lhm-panel.js`, `multi-capture-panel.js`, `studio_v2.html`
- Notes:
  - `customer-panel.js`: added mock fallback with 2 demo customers; `select()` skips profile fetch in mock mode; error message improved.
  - `body-scan-panel.js`: `loadSessions` shows mock empty state; `startNewSession` logs error and bails in mock mode; `!ok` message improved.
  - `report-panel.js`: improved error message on `!ok`.
  - Mock-only panels (`3dgs-panel.js`, `lhm-panel.js`, `multi-capture-panel.js`): added `_renderModeBanner()` with red "Requires backend — enable Live mode and start py4web" banner; banner div IDs added to HTML.

### Task 3C.3 — Wire viewport
- Status: done (already implemented)
- Files changed: none
- Notes: `render-panel.js` `viewMesh()` already calls `Studio.showInViewport('glb', url)`. `studio.js` already has `showInViewport()` dispatching `CustomEvent('viewport-load')`. `viewport.js` already listens for `viewport-load` and calls `handleLoad()` which dispatches to `loadGLB()`. Full pipeline was already wired.
