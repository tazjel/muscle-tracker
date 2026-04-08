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

    async init() {
        this._setupTabs();
        this._setupPanelToggles();
        this._setupKeyboardShortcuts();
        this._pollDevices();
        this._pollGPU();
        // Load panel modules
        if (window.CustomerPanel) CustomerPanel.init();
        if (window.ScanPanel) ScanPanel.init();
        if (window.ViewportPanel) ViewportPanel.init();
        if (window.BodyScanPanel) BodyScanPanel.init();
        if (window.TexturePanel) TexturePanel.init();
        if (window.RenderPanel) RenderPanel.init();
        if (window.ProgressPanel) ProgressPanel.init();
        if (window.ReportPanel) ReportPanel.init();
        this.log('Studio initialized');
    },

    // --- API helpers ---
    async api(path, options = {}) {
        const url = `${this.API_BASE}${path}`;
        const defaults = { headers: { 'Content-Type': 'application/json' } };
        if (options.body && typeof options.body === 'object') {
            options.body = JSON.stringify(options.body);
        }
        try {
            const resp = await fetch(url, { ...defaults, ...options });
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
                case '2': this._activateNav('body-scan'); break;
                case '3': this._activateNav('texture'); break;
                case '4': this._activateNav('render'); break;
                case '5': this._activateNav('progress'); break;
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
        this.log(`Switched to ${section}`);
    },

    async _exportQuick() {
        if (!this.customerId) { this.log('No customer selected', 'error'); return; }
        if (window.ProgressPanel) ProgressPanel.exportData(this.customerId);
    },
};

// Boot on DOM ready
document.addEventListener('DOMContentLoaded', () => Studio.init());
