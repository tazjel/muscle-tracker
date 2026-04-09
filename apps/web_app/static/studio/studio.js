/* GTD3D Studio — Main controller
 * Manages panel navigation, API communication, and global state.
 */
const Studio = {
    // Auto-detect base path: /gtd3d when served via GTD Studio proxy, /web_app when direct py4web
    API_BASE: window.location.pathname.startsWith('/gtd3d') ? '/gtd3d' : '/web_app',
    customer: null,      // Currently selected customer object
    customerId: null,     // Currently selected customer ID
    panels: {},          // Registered panel modules
    logs: [],            // Activity log entries
    _token: null,        // JWT token acquired on init
    MOCK_MODE: true,     // Dev mode — no backend needed

    async _acquireToken() {
        try {
            const resp = await fetch(`${this.API_BASE}/api/auth/admin_token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_secret: 'dev-admin-secret' }),
            });
            const data = await resp.json();
            if (resp.ok && data.token) {
                this._token = data.token;
                this.log('Auth token acquired');
            } else {
                this.log(`Token acquire failed: ${JSON.stringify(data)}`, 'error');
            }
        } catch (e) {
            this.log(`Token acquire error: ${e.message}`, 'error');
        }
    },

    async init() {
        // await this._acquireToken(); // disabled in dev mode
        this._setupTabs();
        this._setupPanelToggles();
        this._setupNavLinks();
        this._setupKeyboardShortcuts();
        // this._pollDevices(); // disabled in dev mode
        // this._pollGPU();     // disabled in dev mode
        // Load panel modules (const globals aren't on window — check typeof)
        if (typeof CustomerPanel !== 'undefined') {
            try { await CustomerPanel.init(); } catch(e) { this.log('CustomerPanel init error: ' + e.message, 'error'); }
        }
        if (typeof ScanPanel !== 'undefined') ScanPanel.init();
        if (typeof ViewportPanel !== 'undefined') ViewportPanel.init();
        if (typeof BodyScanPanel !== 'undefined') BodyScanPanel.init();
        if (typeof TexturePanel !== 'undefined') TexturePanel.init();
        if (typeof RenderPanel !== 'undefined') RenderPanel.init();
        if (typeof ProgressPanel !== 'undefined') ProgressPanel.init();
        if (typeof ReportPanel !== 'undefined') ReportPanel.init();
        if (typeof GaussianPanel !== 'undefined') GaussianPanel.init();
        if (typeof LHMPanel !== 'undefined') LHMPanel.init();
        if (typeof MultiCapturePanel !== 'undefined') MultiCapturePanel.init();
        this.log('Studio initialized');
    },

    // --- API helpers ---
    async api(path, options = {}, _isRetry = false) {
        if (this.MOCK_MODE) return { ok: false, status: 0, data: { error: 'Mock mode — no backend' } };
        const url = `${this.API_BASE}${path}`;
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
                ...(this._token ? { 'Authorization': `Bearer ${this._token}` } : {}),
            },
        };
        if (options.body && typeof options.body === 'object') {
            options.body = JSON.stringify(options.body);
        }
        try {
            const resp = await fetch(url, { ...defaults, ...options });
            if (resp.status === 401 && !_isRetry) {
                this.log('Token expired, re-acquiring…');
                await this._acquireToken();
                return this.api(path, options, true);
            }
            const data = await resp.json();
            this.log(`${options.method || 'GET'} ${path} → ${resp.status}`);
            return { ok: resp.ok, status: resp.status, data };
        } catch (e) {
            this.log(`ERROR ${path}: ${e.message}`, 'error');
            return { ok: false, status: 0, data: { error: e.message } };
        }
    },

    async apiGet(path) { return this.api(path); },
    async apiPost(path, body) { return this.api(path, { method: 'POST', body }); },

    // --- Customer selection ---
    selectCustomer(customer) {
        this.customer = customer;
        this.customerId = customer.id;
        this.log(`Selected customer: ${customer.email || customer.id}`);
        // Notify all panels
        document.dispatchEvent(new CustomEvent('customer-selected', { detail: customer }));
        // Update topbar
        const el = document.getElementById('current-customer');
        if (el) el.textContent = customer.email || `Customer #${customer.id}`;
    },

    // --- Tab switching ---
    _setupTabs() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const group = btn.closest('.tab-bar').dataset.group;
                const target = btn.dataset.tab;
                // Deactivate all in group
                document.querySelectorAll(`.tab-bar[data-group="${group}"] .tab-btn`).forEach(b => b.classList.remove('active'));
                document.querySelectorAll(`.tab-content[data-group="${group}"]`).forEach(c => c.classList.remove('active'));
                // Activate target
                btn.classList.add('active');
                const content = document.getElementById(`tab-${target}`);
                if (content) content.classList.add('active');
            });
        });
    },

    // --- Panel collapse/expand ---
    _setupPanelToggles() {
        document.querySelectorAll('.panel-header').forEach(header => {
            header.addEventListener('click', () => {
                const body = header.nextElementSibling;
                if (body && body.classList.contains('panel-body')) {
                    body.classList.toggle('hidden');
                    header.classList.toggle('collapsed');
                }
            });
        });
    },

    // --- Nav panel switching ---
    // Maps each nav tab to the panel IDs it should show in left and right sidebars.
    // Customer panels (first 2 .panel elements in left sidebar) are always visible.
    _NAV_PANELS: {
        'scan':     { left: ['panel-camera', 'panel-scan-upload', 'panel-scan-history', 'panel-device-status'], right: [] },
        'mesh':     { left: ['panel-mesh-info'], right: [] },
        'texture':  { left: [],                  right: ['panel-texture-checklist'] },
        'render':   { left: [],                  right: ['panel-render-controls', 'panel-render-meshes'] },
        'progress': { left: [],                  right: ['panel-progress-report'] },
        '3dgs':     { left: ['panel-3dgs-upload'],   right: ['panel-3dgs-status'] },
        'lhm':      { left: ['panel-lhm-upload'],    right: ['panel-lhm-status'] },
        'multi-capture': { left: ['panel-multi-capture-devices'], right: ['panel-multi-capture-controls'] },
    },

    _setupNavLinks() {
        document.querySelectorAll('.nav-links a').forEach(a => {
            a.addEventListener('click', (e) => {
                e.preventDefault();
                const section = a.dataset.nav;
                if (section) this._activateNav(section);
            });
        });
        // Apply initial state for the default active tab (scan)
        this._switchNavPanels('scan');
    },

    _switchNavPanels(section) {
        const map = this._NAV_PANELS[section];
        if (!map) return;

        // Left sidebar: all switchable panels (those with an id), skip the first 2 customer panels
        const leftPanels = document.querySelectorAll('#sidebar-left .panel[id]');
        leftPanels.forEach(panel => {
            panel.style.display = map.left.includes(panel.id) ? '' : 'none';
        });

        // Right sidebar: all panels with an id
        const rightPanels = document.querySelectorAll('#sidebar-right .panel[id]');
        rightPanels.forEach(panel => {
            panel.style.display = map.right.includes(panel.id) ? '' : 'none';
        });
    },

    // --- Device polling ---
    async _pollDevices() {
        const update = async () => {
            try {
                const resp = await fetch('/api/devices').catch(() => null);
                if (!resp) return;
                const data = await resp.json();
                const el = document.getElementById('device-status');
                if (el) {
                    const count = data.count || 0;
                    el.innerHTML = `<span class="dot ${count > 0 ? 'dot-ok' : 'dot-off'}"></span>${count} device${count !== 1 ? 's' : ''}`;
                }
            } catch (e) { /* silent */ }
        };
        await update();
        setInterval(update, 15000);
    },

    // --- GPU status polling ---
    async _pollGPU() {
        const update = async () => {
            const { ok, data } = await this.apiGet('/api/gpu_status');
            const el = document.getElementById('gpu-status');
            if (el && ok) {
                const status = data.available ? 'ok' : 'off';
                el.innerHTML = `<span class="dot dot-${status}"></span>GPU ${data.available ? 'Ready' : 'Offline'}`;
            }
        };
        await update();
        setInterval(update, 30000);
    },

    // --- Activity log ---
    log(msg, level = 'info') {
        const ts = new Date().toLocaleTimeString();
        this.logs.push({ ts, msg, level });
        if (this.logs.length > 200) this.logs.shift();
        const el = document.getElementById('activity-log');
        if (el) el.textContent = `${ts} ${msg}`;
    },

    // --- Viewport helpers ---
    showInViewport(type, url) {
        document.dispatchEvent(new CustomEvent('viewport-load', { detail: { type, url } }));
    },

    // --- Keyboard shortcuts ---
    _setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't capture when typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

            const key = e.key.toLowerCase();
            if (e.ctrlKey || e.metaKey) {
                switch (key) {
                    case 's': e.preventDefault(); this.log('Ctrl+S: nothing to save'); break;
                    case 'e': e.preventDefault(); this._exportQuick(); break;
                }
                return;
            }
            switch (key) {
                case '1': this._activateNav('scan'); break;
                case '2': this._activateNav('mesh'); break;
                case '3': this._activateNav('texture'); break;
                case '4': this._activateNav('render'); break;
                case '5': this._activateNav('progress'); break;
                case '6': this._activateNav('3dgs'); break;
                case '7': this._activateNav('lhm'); break;
                case '8': this._activateNav('multi-capture'); break;
                case 'r': if (window.ViewportPanel) ViewportPanel.resetView(); break;
                case 'w': if (window.ViewportPanel) ViewportPanel.toggleWireframe(); break;
                case '/': document.getElementById('customer-search')?.focus(); e.preventDefault(); break;
            }
        });
    },

    _activateNav(section) {
        document.querySelectorAll('.nav-links a').forEach(a => {
            a.classList.toggle('active', a.dataset.nav === section);
        });
        this._switchNavPanels(section);
        this.log(`Switched to ${section}`);
    },

    async _exportQuick() {
        if (!this.customerId) { this.log('No customer selected', 'error'); return; }
        if (window.ProgressPanel) ProgressPanel.exportData(this.customerId);
    },
};

// Boot on DOM ready
document.addEventListener('DOMContentLoaded', () => Studio.init());
