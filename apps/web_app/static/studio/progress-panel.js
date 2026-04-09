/* GTD3D Studio — Progress Panel
 * Right sidebar: RunPod job tracker, customer progress chart, scan timeline, health log.
 */
const ProgressPanel = {
    job: null,
    _pollTimer: null,
    _customerId: null,

    // Mock data for MOCK_MODE
    _MOCK_PROGRESS: {
        scans: [
            { id: 1, date: '2025-11-01', weight_kg: 85.2, chest_cm: 102, waist_cm: 88, hip_cm: 98, notes: 'Initial scan' },
            { id: 2, date: '2025-12-15', weight_kg: 83.0, chest_cm: 100, waist_cm: 85, hip_cm: 97, notes: 'Month 2' },
            { id: 3, date: '2026-01-30', weight_kg: 80.5, chest_cm: 99, waist_cm: 82, hip_cm: 96, notes: 'Month 3' },
        ],
        health_logs: [
            { id: 1, date: '2026-01-28', weight_kg: 81.0, notes: 'Felt great today' },
            { id: 2, date: '2026-01-29', weight_kg: 80.8, notes: 'Light workout' },
        ],
    },

    init() {
        document.addEventListener('hd-requested', () => {
            if (Studio.MOCK_MODE) {
                this._startMockJob();
            } else {
                this._startRealJob(this._customerId);
            }
        });
        document.addEventListener('customer-selected', (e) => {
            this._customerId = e.detail.id;
            this._stopPoll();
            this.job = null;
            this._loadCustomerData(e.detail.id);
        });
        this._renderEmpty();
    },

    // ─── RunPod Job (mock) ───────────────────────────────────────────────────

    _startMockJob() {
        this.job = {
            id: 'rpjob-' + Date.now(),
            status: 'queued',
            startedAt: new Date().toLocaleTimeString(),
            elapsed: 0,
            cost: 0.00,
            errors: 0,
            gpuType: 'A40',
            resolution: '4K',
        };
        this._renderJobStats();

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'processing';
            this.job.cost = 0.04;
            this.job.elapsed = 8;
            this._renderJobStats();
        }, 2000);

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'complete';
            this.job.cost = 0.12;
            this.job.elapsed = 45;
            this._renderJobStats();
            Studio.log('HD render complete — $0.12, 45s');
        }, 7000);
    },

    // ─── RunPod Job (real) ───────────────────────────────────────────────────

    async _startRealJob(customerId) {
        if (!customerId) { Studio.log('No customer selected for reconstruction', 'error'); return; }

        this.job = {
            id: null,
            status: 'queued',
            startedAt: new Date().toLocaleTimeString(),
            elapsed: 0,
            cost: 0.00,
            errors: 0,
            gpuType: '—',
            resolution: '4K',
            _startTs: Date.now(),
        };
        this._renderJobStats();

        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/reconstruct_3d`, {});
        if (!ok) {
            this.job.status = 'error';
            this.job.errors = 1;
            this._renderJobStats();
            Studio.log(`Reconstruction failed: ${(data && data.error) || 'Unknown'}`, 'error');
            return;
        }

        this.job.id = data.job_id || data.id || ('job-' + Date.now());
        this.job.gpuType = data.gpu_type || 'A40';
        this.job.status = 'processing';
        Studio.log(`Reconstruction job ${this.job.id} started`);
        this._renderJobStats();
        this._startJobPoll(customerId);
    },

    _startJobPoll(customerId) {
        this._stopPoll();
        this._pollTimer = setInterval(async () => {
            await this._pollJobStatus(customerId);
        }, 5000);
    },

    _stopPoll() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    },

    async _pollJobStatus(customerId) {
        if (!this.job || !this.job.id) return;
        const { ok, data } = await Studio.apiGet(`/api/gpu_status`);
        if (ok) {
            // Update elapsed time from local clock
            if (this.job._startTs) {
                this.job.elapsed = Math.round((Date.now() - this.job._startTs) / 1000);
            }
            if (data.job_status) this.job.status = data.job_status;
            if (data.cost) this.job.cost = data.cost;
            if (data.gpu_type) this.job.gpuType = data.gpu_type;
            this._renderJobStats();

            if (this.job.status === 'complete' || this.job.status === 'error') {
                this._stopPoll();
                Studio.log(`Job ${this.job.id} ${this.job.status}`);
                if (this.job.status === 'complete' && data.glb_url) {
                    Studio.showInViewport('glb', data.glb_url);
                }
            }
        }
    },

    // ─── Customer data loading ────────────────────────────────────────────────

    async _loadCustomerData(customerId) {
        const el = document.getElementById('progress-customer-data');
        if (el) el.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">Loading…</div>';

        if (Studio.MOCK_MODE) {
            this._renderProgress(this._MOCK_PROGRESS.scans);
            this._renderHealthLog(this._MOCK_PROGRESS.health_logs, customerId);
            return;
        }

        // Fetch progress + scans + health logs in sequence (Windows sequential calls)
        const { ok: pOk, data: pData } = await Studio.apiGet(`/api/customer/${customerId}/progress`);
        const scans = pOk ? (pData.scans || pData || []) : [];

        const { ok: sOk, data: sData } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
        const scanList = sOk ? (sData.scans || sData || []) : [];

        const { ok: hOk, data: hData } = await Studio.apiGet(`/api/customer/${customerId}/health_logs`);
        const healthLogs = hOk ? (hData.logs || hData || []) : [];

        // Use progress data if available, fall back to scan list
        const progressScans = scans.length > 0 ? scans : scanList;
        this._renderProgress(progressScans);
        this._renderScanTimeline(scanList, customerId);
        this._renderHealthLog(healthLogs, customerId);
    },

    // ─── Progress summary ────────────────────────────────────────────────────

    _renderProgress(scans) {
        const el = document.getElementById('progress-customer-data');
        if (!el) return;
        if (!scans || scans.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">No progress data yet.</div>';
            return;
        }

        const first = scans[0];
        const last = scans[scans.length - 1];
        const delta = (key) => {
            const a = parseFloat(first[key]);
            const b = parseFloat(last[key]);
            if (isNaN(a) || isNaN(b)) return null;
            return (b - a).toFixed(1);
        };

        const rowStyle = 'display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:11px;';
        const deltaColor = (v) => v === null ? '' : parseFloat(v) < 0 ? 'color:#22c55e;' : parseFloat(v) > 0 ? 'color:#ef4444;' : '';

        const metrics = [
            { label: 'Weight', key: 'weight_kg', unit: 'kg' },
            { label: 'Chest', key: 'chest_cm', unit: 'cm' },
            { label: 'Waist', key: 'waist_cm', unit: 'cm' },
            { label: 'Hips', key: 'hip_cm', unit: 'cm' },
        ];

        const rows = metrics.map(m => {
            const d = delta(m.key);
            const sign = d !== null && parseFloat(d) > 0 ? '+' : '';
            const dText = d !== null ? `<span style="${deltaColor(d)}">${sign}${d} ${m.unit}</span>` : '—';
            return `<div style="${rowStyle}"><span style="color:var(--text-dim);">${m.label}</span>${dText}</div>`;
        }).join('');

        el.innerHTML = `
            <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">
                ${scans.length} scan${scans.length !== 1 ? 's' : ''} · ${first.date || 'Unknown'} → ${last.date || 'Unknown'}
            </div>
            ${rows}
        `;
    },

    // ─── Scan timeline ────────────────────────────────────────────────────────

    _renderScanTimeline(scans, customerId) {
        const el = document.getElementById('progress-scan-timeline');
        if (!el) return;
        if (!scans || scans.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">No scans found.</div>';
            return;
        }

        const sorted = [...scans].sort((a, b) =>
            new Date(b.created_at || b.date || 0) - new Date(a.created_at || a.date || 0)
        );

        el.innerHTML = sorted.map(s => {
            const sid = s.id || s.session_id;
            const date = s.created_at
                ? new Date(s.created_at).toLocaleDateString()
                : (s.date || 'Unknown date');
            const status = s.status || 'done';
            const tagClass = status === 'done' || status === 'finalized' ? 'tag-ok'
                : status === 'error' ? 'tag-err' : 'tag-warn';
            return `<div style="display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:11px;">
                <span>${date}</span>
                <span class="tag ${tagClass}" style="font-size:9px;">${status}</span>
                <a href="${Studio.API_BASE}/api/customer/${customerId}/report/${sid}"
                   target="_blank"
                   style="color:var(--accent,#4caf50);text-decoration:none;font-size:10px;">Report</a>
            </div>`;
        }).join('');
    },

    // ─── Health log ──────────────────────────────────────────────────────────

    _renderHealthLog(logs, customerId) {
        const el = document.getElementById('progress-health-log');
        if (!el) return;

        const recent = (logs || []).slice(-5).reverse();
        const logHtml = recent.length === 0
            ? '<div style="color:var(--text-dim);font-size:11px;margin-bottom:6px;">No entries yet.</div>'
            : recent.map(e => {
                const date = e.date || e.created_at || '?';
                const weight = e.weight_kg ? `${e.weight_kg}kg` : '';
                const notes = e.notes || '';
                return `<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:11px;">
                    <span style="color:var(--text-dim);">${date}</span>
                    ${weight ? `<span style="margin-left:6px;">${weight}</span>` : ''}
                    ${notes ? `<div style="color:var(--text-dim);font-size:10px;margin-top:1px;">${notes}</div>` : ''}
                </div>`;
            }).join('');

        el.innerHTML = `
            ${logHtml}
            <form id="health-log-form" style="margin-top:6px;" onsubmit="ProgressPanel.addHealthLog(event, ${customerId})">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:4px;">
                    <input class="form-input" name="date" type="date" placeholder="Date"
                           value="${new Date().toISOString().slice(0,10)}"
                           style="font-size:10px;padding:3px 5px;">
                    <input class="form-input" name="weight_kg" type="number" step="0.1" placeholder="Weight (kg)"
                           style="font-size:10px;padding:3px 5px;">
                </div>
                <input class="form-input" name="notes" type="text" placeholder="Notes (optional)"
                       style="width:100%;font-size:10px;padding:3px 5px;margin-bottom:4px;box-sizing:border-box;">
                <button class="btn btn-sm btn-accent" type="submit" style="width:100%;font-size:10px;">Add Entry</button>
            </form>
        `;
    },

    async addHealthLog(e, customerId) {
        e.preventDefault();
        const form = e.target;
        const date = form.querySelector('[name="date"]').value;
        const weight = form.querySelector('[name="weight_kg"]').value;
        const notes = form.querySelector('[name="notes"]').value;

        const entry = { date };
        if (weight) entry.weight_kg = parseFloat(weight);
        if (notes) entry.notes = notes;

        if (Studio.MOCK_MODE) {
            Studio.log(`Health log added (mock): ${date} ${weight ? weight + 'kg' : ''}`);
            this._MOCK_PROGRESS.health_logs.push({ ...entry, id: Date.now() });
            this._renderHealthLog(this._MOCK_PROGRESS.health_logs, customerId);
            return;
        }

        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true; btn.textContent = 'Saving…';
        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/health_log`, entry);
        if (ok) {
            Studio.log(`Health log entry added: ${date}`);
            await this._loadCustomerData(customerId);
        } else {
            Studio.log(`Health log failed: ${(data && data.error) || 'Unknown'}`, 'error');
            btn.disabled = false; btn.textContent = 'Add Entry';
        }
    },

    // ─── Export ──────────────────────────────────────────────────────────────

    async exportData(customerId) {
        Studio.log('Exporting progress data…');
        let exportObj;

        if (Studio.MOCK_MODE) {
            exportObj = { customer_id: customerId, exported_at: new Date().toISOString(), ...this._MOCK_PROGRESS };
        } else {
            const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/progress`);
            if (!ok) { Studio.log('Export failed: could not fetch progress', 'error'); return; }
            exportObj = { customer_id: customerId, exported_at: new Date().toISOString(), ...data };
        }

        const blob = new Blob([JSON.stringify(exportObj, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `progress_${customerId}_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
        Studio.log('Progress data exported');
    },

    // ─── Render helpers ──────────────────────────────────────────────────────

    _renderEmpty() {
        const statsEl = document.getElementById('runpod-stats');
        if (statsEl) statsEl.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">No HD render requested yet.</div>';
    },

    _renderJobStats() {
        const el = document.getElementById('runpod-stats');
        if (!el || !this.job) return;

        const statusColors = { queued: '#eab308', processing: '#3b82f6', complete: '#22c55e', error: '#ef4444' };
        const color = statusColors[this.job.status] || '#6b7280';
        const label = this.job.status.charAt(0).toUpperCase() + this.job.status.slice(1);

        const row = (k, v) =>
            `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
                <span style="color:var(--text-dim);">${k}</span><span>${v}</span></div>`;

        el.innerHTML = `
            ${row('Status', `<span style="color:${color};font-weight:600;">${label}</span>`)}
            ${row('Job ID', (this.job.id || 'pending').toString().substring(0, 16))}
            ${row('GPU', this.job.gpuType)}
            ${row('Resolution', this.job.resolution)}
            ${row('Time', this.job.elapsed + 's')}
            ${row('Cost', '$' + this.job.cost.toFixed(2))}
            ${row('Errors', this.job.errors)}
            ${row('Started', this.job.startedAt)}
            ${this.job.status === 'processing'
                ? '<div style="margin-top:8px;"><div style="height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;"><div style="height:100%;width:40%;background:#3b82f6;border-radius:2px;animation:none;"></div></div></div>'
                : ''}
            ${this.job.status === 'complete'
                ? '<div style="margin-top:8px;padding:6px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:4px;font-size:11px;color:#22c55e;">Render complete. View in viewport.</div>'
                : ''}
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => ProgressPanel.init());
