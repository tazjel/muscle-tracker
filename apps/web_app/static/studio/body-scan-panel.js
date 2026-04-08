/* GTD3D Studio — Body Scan Panel
 * Left sidebar: body scan session management, live scan mode, frame tasks.
 */
const BodyScanPanel = {
    sessions: [],
    activeSession: null,
    _pollTimer: null,

    init() {
        document.addEventListener('customer-selected', (e) => {
            this._stopPoll();
            this.activeSession = null;
            this.loadSessions(e.detail.id);
        });
    },

    async loadSessions(customerId) {
        const el = document.getElementById('body-scan-list');
        if (!el) return;
        el.innerHTML = '<div class="empty-state">Loading…</div>';

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
        if (!ok) {
            // API may not expose a list endpoint — render empty state with actions
            this.sessions = [];
        } else {
            // Filter to body_scan type if the response mixes scan types
            const raw = data.sessions || data.scans || data || [];
            this.sessions = raw.filter(s => !s.type || s.type === 'body_scan');
        }
        this._renderSessionList(customerId);
    },

    async startNewSession(customerId) {
        const btn = document.getElementById('bsp-start-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Starting…'; }

        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/body_scan`, {});
        if (!ok) {
            Studio.log(`Failed to start scan session: ${(data && data.error) || 'Unknown'}`, 'error');
            if (btn) { btn.disabled = false; btn.textContent = 'Start New Session'; }
            return;
        }
        Studio.log(`Started body scan session ${data.session_id || data.id}`);
        const sessionId = data.session_id || data.id;
        this.activeSession = sessionId;
        await this.loadTasks(customerId, sessionId);
    },

    async loadTasks(customerId, sessionId) {
        const el = document.getElementById('body-scan-list');
        if (!el) return;
        el.innerHTML = '<div class="empty-state">Loading tasks…</div>';

        const { ok, data } = await Studio.apiGet(
            `/api/customer/${customerId}/body_scan/${sessionId}/tasks`
        );
        if (!ok) {
            el.innerHTML = `<div class="empty-state" style="color:var(--error);">Failed to load tasks</div>`;
            return;
        }
        const tasks = data.tasks || data || [];
        const coverage = data.coverage_pct != null ? data.coverage_pct : null;
        this._renderTasks(customerId, sessionId, tasks, coverage);
    },

    _renderTasks(customerId, sessionId, tasks, coverage) {
        const el = document.getElementById('body-scan-list');
        if (!el) return;

        const coverageBar = coverage != null ? this._renderCoverageBar(coverage) : '';

        const taskGrid = tasks.length === 0
            ? '<div class="empty-state">No frames captured yet</div>'
            : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:0.5rem;margin-top:0.5rem;">
                ${tasks.map((t, idx) => {
                    const quality = t.quality || t.sharpness_ok;
                    const tagClass = quality === true || quality === 'ok'
                        ? 'tag-ok'
                        : quality === false || quality === 'err'
                            ? 'tag-err'
                            : 'tag-warn';
                    const tagLabel = tagClass === 'tag-ok' ? 'OK'
                        : tagClass === 'tag-err' ? 'ERR' : 'WARN';
                    const thumbUrl = `/web_app/api/customer/${customerId}/body_scan/${sessionId}/thumbnail/${t.frame_idx != null ? t.frame_idx : idx}`;
                    return `<div style="display:flex;flex-direction:column;align-items:center;gap:0.25rem;">
                        <img src="${thumbUrl}" alt="Frame ${idx + 1}"
                             style="width:100%;border-radius:4px;border:1px solid var(--border,#444);cursor:pointer;"
                             onerror="this.style.background='#333';this.alt='No preview';"
                             onclick="BodyScanPanel.loadTasks(${customerId}, '${sessionId}')">
                        <span class="tag ${tagClass}">${tagLabel}</span>
                        <div style="display:flex;gap:0.25rem;">
                            <button class="btn btn-sm" title="Confirm frame"
                                onclick="BodyScanPanel.confirmFrame(${customerId}, '${sessionId}')">✓</button>
                            <button class="btn btn-sm" title="Re-capture"
                                onclick="BodyScanPanel.recaptureFrame(${customerId}, '${sessionId}')">↺</button>
                        </div>
                    </div>`;
                }).join('')}
               </div>`;

        el.innerHTML = `
            <div style="margin-bottom:0.5rem;">
                <button class="btn btn-sm" onclick="BodyScanPanel.loadSessions(${customerId})">← Sessions</button>
                <span style="margin-left:0.5rem;font-size:0.8125rem;opacity:0.7;">Session ${sessionId}</span>
            </div>
            ${coverageBar}
            ${taskGrid}
            <div class="btn-row" style="margin-top:0.75rem;">
                <button class="btn btn-accent" onclick="BodyScanPanel.finalizeSession(${customerId}, '${sessionId}')">
                    Finalize &amp; Generate GLB
                </button>
                <button class="btn btn-sm" onclick="BodyScanPanel.loadTasks(${customerId}, '${sessionId}')">
                    Refresh
                </button>
            </div>
        `;
    },

    async confirmFrame(customerId, sessionId) {
        const { ok, data } = await Studio.apiPost(
            `/api/customer/${customerId}/body_scan/${sessionId}/confirm`, {}
        );
        if (ok) {
            Studio.log('Frame confirmed');
            await this.loadTasks(customerId, sessionId);
        } else {
            Studio.log(`Confirm failed: ${(data && data.error) || 'Unknown'}`, 'error');
        }
    },

    async recaptureFrame(customerId, sessionId) {
        const { ok, data } = await Studio.apiPost(
            `/api/customer/${customerId}/body_scan/${sessionId}/re_capture`, {}
        );
        if (ok) {
            Studio.log('Re-capture requested');
            await this.loadTasks(customerId, sessionId);
        } else {
            Studio.log(`Re-capture failed: ${(data && data.error) || 'Unknown'}`, 'error');
        }
    },

    async finalizeSession(customerId, sessionId) {
        const el = document.getElementById('body-scan-list');
        if (el) {
            el.innerHTML = `
                <div style="display:flex;flex-direction:column;align-items:center;padding:2rem;gap:1rem;">
                    <div class="spinner"></div>
                    <div>Generating GLB model…</div>
                    <button class="btn btn-sm" onclick="BodyScanPanel.loadTasks(${customerId}, '${sessionId}')">Cancel</button>
                </div>`;
        }

        const { ok, data } = await Studio.apiPost(
            `/api/customer/${customerId}/body_scan/${sessionId}/finalize`, {}
        );
        if (!ok) {
            Studio.log(`Finalize failed: ${(data && data.error) || 'Unknown'}`, 'error');
            await this.loadTasks(customerId, sessionId);
            return;
        }
        Studio.log(`Session ${sessionId} finalized — GLB ready`);
        const glbUrl = data.glb_url || data.model_url || null;
        if (glbUrl) {
            Studio.showInViewport('glb', glbUrl);
        }
        await this.loadSessions(customerId);
    },

    // --- Live Scan Mode ---

    async startLiveScan(customerId) {
        const btn = document.getElementById('bsp-live-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Starting…'; }

        const { ok, data } = await Studio.apiPost(
            `/api/customer/${customerId}/live_scan/start`, {}
        );
        if (!ok) {
            Studio.log(`Live scan start failed: ${(data && data.error) || 'Unknown'}`, 'error');
            if (btn) { btn.disabled = false; btn.textContent = 'Start Live Scan'; }
            return;
        }
        const sessionId = data.session_id || data.id;
        Studio.log(`Live scan started — session ${sessionId}`);
        this.activeSession = sessionId;
        this._renderLiveScanView(customerId, sessionId, { frames: 0, coverage_pct: 0, status: 'active' });
        this._startPoll(customerId, sessionId);
    },

    _renderLiveScanView(customerId, sessionId, status) {
        const el = document.getElementById('body-scan-list');
        if (!el) return;
        const coverage = status.coverage_pct != null ? status.coverage_pct : 0;
        const frames = status.frames || status.frame_count || 0;
        const processing = status.status === 'processing';

        el.innerHTML = `
            <div style="margin-bottom:0.5rem;">
                <button class="btn btn-sm" onclick="BodyScanPanel._stopLiveScan(${customerId})">← Stop</button>
                <span style="margin-left:0.5rem;font-size:0.8125rem;opacity:0.7;">Live Scan ${sessionId}</span>
            </div>
            ${this._renderCoverageBar(coverage)}
            <div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                <span>Frames captured</span>
                <span><strong>${frames}</strong></span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                <span>Status</span>
                <span class="tag ${processing ? 'tag-warn' : 'tag-ok'}">${status.status || 'active'}</span>
            </div>
            ${processing ? '<div style="display:flex;justify-content:center;padding:0.5rem;"><div class="spinner"></div></div>' : ''}
            <div class="btn-row" style="margin-top:0.75rem;">
                <button class="btn btn-accent"
                    onclick="BodyScanPanel.finalizeLiveScan(${customerId}, '${sessionId}')">
                    Finalize Live Scan
                </button>
            </div>
        `;
    },

    _startPoll(customerId, sessionId) {
        this._stopPoll();
        this._pollTimer = setInterval(async () => {
            await this.pollLiveStatus(customerId, sessionId);
        }, 2000);
    },

    _stopPoll() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    },

    async pollLiveStatus(customerId, sessionId) {
        const { ok, data } = await Studio.apiGet(
            `/api/customer/${customerId}/live_scan/${sessionId}/status`
        );
        if (!ok) return;
        this._renderLiveScanView(customerId, sessionId, data);
        // Auto-stop poll if session finished on server
        if (data.status === 'done' || data.status === 'finalized' || data.status === 'error') {
            this._stopPoll();
        }
    },

    _stopLiveScan(customerId) {
        this._stopPoll();
        this.activeSession = null;
        this.loadSessions(customerId);
    },

    async finalizeLiveScan(customerId, sessionId) {
        this._stopPoll();
        const el = document.getElementById('body-scan-list');
        if (el) {
            el.innerHTML = `
                <div style="display:flex;flex-direction:column;align-items:center;padding:2rem;gap:1rem;">
                    <div class="spinner"></div>
                    <div>Processing live scan…</div>
                </div>`;
        }

        const { ok, data } = await Studio.apiPost(
            `/api/customer/${customerId}/live_scan/${sessionId}/finalize`, {}
        );
        if (!ok) {
            Studio.log(`Live scan finalize failed: ${(data && data.error) || 'Unknown'}`, 'error');
            await this.loadSessions(customerId);
            return;
        }
        Studio.log(`Live scan ${sessionId} finalized`);
        const glbUrl = data.glb_url || data.model_url || null;
        if (glbUrl) {
            Studio.showInViewport('glb', glbUrl);
        }
        await this.loadSessions(customerId);
    },

    // --- Session List ---

    _renderSessionList(customerId) {
        const el = document.getElementById('body-scan-list');
        if (!el) return;

        const rows = this.sessions.length === 0
            ? '<div class="empty-state">No scan sessions yet</div>'
            : this.sessions.map(s => {
                const date = s.created_at
                    ? new Date(s.created_at).toLocaleDateString()
                    : 'Unknown date';
                const frames = s.frame_count != null ? s.frame_count : (s.frames || '?');
                const status = s.status || 'unknown';
                const tagClass = status === 'done' || status === 'finalized'
                    ? 'tag-ok'
                    : status === 'error'
                        ? 'tag-err'
                        : 'tag-warn';
                const sid = s.session_id || s.id;
                return `<div class="list-item" onclick="BodyScanPanel.loadTasks(${customerId}, '${sid}')">
                    <div style="display:flex;justify-content:space-between;align-items:center;width:100%;">
                        <div>
                            <div style="font-size:0.8125rem;">${date}</div>
                            <div class="meta">${frames} frames</div>
                        </div>
                        <span class="tag ${tagClass}">${status}</span>
                    </div>
                </div>`;
            }).join('');

        el.innerHTML = `
            <div class="btn-row" style="margin-bottom:0.5rem;">
                <button id="bsp-start-btn" class="btn btn-accent btn-sm"
                    onclick="BodyScanPanel.startNewSession(${customerId})">
                    Start New Session
                </button>
                <button id="bsp-live-btn" class="btn btn-sm"
                    onclick="BodyScanPanel.startLiveScan(${customerId})">
                    Start Live Scan
                </button>
            </div>
            ${rows}
        `;
    },

    _renderCoverageBar(coverage) {
        const pct = Math.min(100, Math.max(0, Math.round(coverage)));
        const color = pct >= 80 ? 'var(--accent, #4caf50)'
            : pct >= 50 ? '#f0a500'
            : 'var(--error, #e53935)';
        return `
            <div style="margin:0.4rem 0;">
                <div style="display:flex;justify-content:space-between;font-size:0.75rem;margin-bottom:0.2rem;">
                    <span>Body Coverage</span>
                    <span>${pct}%</span>
                </div>
                <div style="height:6px;border-radius:3px;background:var(--border,#444);overflow:hidden;">
                    <div style="height:100%;width:${pct}%;background:${color};transition:width 0.3s;"></div>
                </div>
            </div>`;
    },
};

document.addEventListener('DOMContentLoaded', () => BodyScanPanel.init());
