/* GTD3D Studio — Progress Panel
 * Charts, trends, body composition, mesh comparison, RunPod job tracker, health log.
 */
const ProgressPanel = {
    _customerId: null,
    _pollTimer: null,
    job: null,

    // Mock data for MOCK_MODE
    _MOCK_PROGRESS: {
        scans: [
            { id: 1, date: '2025-11-01', weight_kg: 85.2, chest_cm: 102, waist_cm: 88, hip_cm: 98, created_at: '2025-11-01', status: 'done' },
            { id: 2, date: '2025-12-15', weight_kg: 83.0, chest_cm: 100, waist_cm: 85, hip_cm: 97, created_at: '2025-12-15', status: 'done' },
            { id: 3, date: '2026-01-30', weight_kg: 80.5, chest_cm: 99, waist_cm: 82, hip_cm: 96, created_at: '2026-01-30', status: 'done' },
        ],
        trends: { weight_kg: { slope: -1.1 }, waist_cm: { slope: -1.8 } },
        health_logs: [
            { id: 1, date: '2026-01-28', weight_kg: 81.0, notes: 'Felt great today' },
            { id: 2, date: '2026-01-29', weight_kg: 80.8, notes: 'Light workout' },
        ],
    },

    init() {
        document.addEventListener('customer-selected', (e) => {
            this._customerId = e.detail.id;
            this._stopPoll();
            this.job = null;
            this.loadProgress(e.detail.id);
        });
        document.addEventListener('hd-requested', () => {
            if (Studio.MOCK_MODE) {
                this._startMockJob();
            } else {
                this._startRealJob(this._customerId);
            }
        });
    },

    // ─── Progress data loading ────────────────────────────────────────────────

    async loadProgress(customerId) {
        const el = document.getElementById('progress-charts');
        if (!el) return;
        el.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading progress...</div>';

        if (Studio.MOCK_MODE) {
            this._render(el, customerId, {
                scans: this._MOCK_PROGRESS.scans,
                trends: this._MOCK_PROGRESS.trends,
                body_composition_trend: [],
                correlation: null,
            });
            this._loadHealthLog(customerId, this._MOCK_PROGRESS.health_logs);
            return;
        }

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/progress`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load progress</div>';
            return;
        }
        this._render(el, customerId, data);

        // Health log loaded separately
        const { ok: hOk, data: hData } = await Studio.apiGet(`/api/customer/${customerId}/health_logs`);
        if (hOk) {
            this._loadHealthLog(customerId, hData.logs || hData || []);
        }
    },

    _render(el, customerId, data) {
        const scans = data.scans || [];
        const trends = data.trends || {};
        const bodyComp = data.body_composition_trend || [];
        const correlation = data.correlation || null;

        el.innerHTML = `
            <div class="progress-summary">
                <div style="font-weight:600;margin-bottom:0.5rem;">Progress Overview</div>
                <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.75rem;">
                    ${scans.length} scan${scans.length !== 1 ? 's' : ''} recorded
                </div>
            </div>

            ${this._renderTrends(trends)}
            ${this._renderBodyComp(bodyComp)}
            ${this._renderCorrelation(correlation)}
            ${this._renderScanTimeline(scans, customerId)}

            <div class="btn-row" style="flex-wrap:wrap;">
                <button class="btn btn-sm" onclick="ProgressPanel.compare3D(${customerId})">3D Compare</button>
                <button class="btn btn-sm" onclick="ProgressPanel.exportData(${customerId})">Export JSON</button>
                <button class="btn btn-sm btn-accent" onclick="ProgressPanel.bodyComposition(${customerId})">Body Comp</button>
            </div>
        `;
    },

    _renderTrends(trends) {
        if (!trends || Object.keys(trends).length === 0) return '';
        const rows = Object.entries(trends).map(([key, val]) => {
            const label = key.replace(/_/g, ' ');
            const slope = val.slope != null ? val.slope : 0;
            const direction = slope > 0 ? '+' : '';
            const color = slope > 0 ? 'var(--success, #22c55e)' : slope < 0 ? 'var(--error, #ef4444)' : 'var(--text-secondary)';
            return `<div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                <span>${label}</span>
                <span style="color:${color}">${direction}${slope.toFixed(2)}/scan</span>
            </div>`;
        }).join('');
        return `<div style="margin-bottom:0.75rem;">
            <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.25rem;">Trends</div>
            ${rows}
        </div>`;
    },

    _renderBodyComp(bodyComp) {
        if (!bodyComp || bodyComp.length === 0) return '';
        const latest = bodyComp[bodyComp.length - 1];
        const fields = [
            { key: 'body_fat_pct', label: 'Body Fat', unit: '%' },
            { key: 'lean_mass_kg', label: 'Lean Mass', unit: 'kg' },
            { key: 'bmi', label: 'BMI', unit: '' },
        ];
        const rows = fields.map(f => {
            const val = latest[f.key];
            if (val == null) return '';
            return `<div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                <span>${f.label}</span>
                <span>${typeof val === 'number' ? val.toFixed(1) : val}${f.unit ? ' ' + f.unit : ''}</span>
            </div>`;
        }).join('');
        return `<div style="margin-bottom:0.75rem;">
            <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.25rem;">Body Composition</div>
            ${rows}
        </div>`;
    },

    _renderCorrelation(correlation) {
        if (!correlation) return '';
        const rows = Object.entries(correlation).map(([key, val]) => {
            const label = key.replace(/_/g, ' ');
            const strength = Math.abs(val) > 0.7 ? 'tag-ok' : Math.abs(val) > 0.4 ? 'tag-warn' : 'tag-info';
            return `<div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                <span>${label}</span>
                <span class="tag ${strength}">${val.toFixed(2)}</span>
            </div>`;
        }).join('');
        return `<div style="margin-bottom:0.75rem;">
            <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.25rem;">Health Correlations</div>
            ${rows}
        </div>`;
    },

    _renderScanTimeline(scans, customerId) {
        if (!scans || scans.length === 0) return '';
        const sorted = [...scans].sort((a, b) =>
            new Date(b.created_at || b.date || 0) - new Date(a.created_at || a.date || 0)
        );
        const items = sorted.slice(0, 10).map(s => {
            const sid = s.id || s.session_id;
            const date = s.created_at
                ? new Date(s.created_at).toLocaleDateString()
                : (s.date || 'Unknown');
            const status = s.status || 'done';
            const tagClass = status === 'done' || status === 'finalized' ? 'tag-ok'
                : status === 'error' ? 'tag-err' : 'tag-warn';
            return `<div class="list-item" style="padding:0.25rem 0;display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-size:0.8125rem;">Scan #${sid}</div>
                    <div class="meta">${date}</div>
                </div>
                <div style="display:flex;gap:0.25rem;align-items:center;">
                    <span class="tag ${tagClass}" style="font-size:9px;">${status}</span>
                    <a href="${Studio.API_BASE}/api/customer/${customerId}/report/${sid}"
                       target="_blank"
                       style="color:var(--accent,#4caf50);text-decoration:none;font-size:10px;">Report</a>
                </div>
            </div>`;
        }).join('');
        return `<div style="margin-bottom:0.75rem;">
            <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.25rem;">Recent Scans</div>
            ${items}
        </div>`;
    },

    // ─── Health log ──────────────────────────────────────────────────────────

    _loadHealthLog(customerId, logs) {
        const el = document.getElementById('health-log-container');
        if (!el) return;

        const recent = (logs || []).slice(-5).reverse();
        const logHtml = recent.length === 0
            ? '<div class="empty-state" style="font-size:0.8125rem;">No entries yet.</div>'
            : recent.map(e => {
                const date = e.date || e.created_at || '?';
                const weight = e.weight_kg ? `${e.weight_kg}kg` : '';
                const notes = e.notes || '';
                return `<div class="list-item" style="padding:0.25rem 0;">
                    <div>
                        <div style="font-size:0.8125rem;">${date}${weight ? ' · ' + weight : ''}</div>
                        ${notes ? `<div class="meta">${notes}</div>` : ''}
                    </div>
                </div>`;
            }).join('');

        el.innerHTML = `
            ${logHtml}
            <form id="health-log-form" style="margin-top:0.5rem;" onsubmit="ProgressPanel.addHealthLog(event, ${customerId})">
                <div class="form-group">
                    <label class="form-label">Date</label>
                    <input class="form-input" name="date" type="date" value="${new Date().toISOString().slice(0,10)}">
                </div>
                <div class="form-group">
                    <label class="form-label">Weight (kg)</label>
                    <input class="form-input" name="weight_kg" type="number" step="0.1" placeholder="e.g. 80.5">
                </div>
                <div class="form-group">
                    <label class="form-label">Notes</label>
                    <input class="form-input" name="notes" type="text" placeholder="Optional notes">
                </div>
                <button class="btn btn-accent btn-sm" type="submit" style="width:100%;">Add Entry</button>
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
            Studio.log(`Health log added (mock): ${date}${weight ? ' ' + weight + 'kg' : ''}`);
            this._MOCK_PROGRESS.health_logs.push({ ...entry, id: Date.now() });
            this._loadHealthLog(customerId, this._MOCK_PROGRESS.health_logs);
            return;
        }

        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true; btn.textContent = 'Saving…';
        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/health_log`, entry);
        if (ok) {
            Studio.log(`Health log entry added: ${date}`);
            await this.loadProgress(customerId);
        } else {
            Studio.log(`Health log failed: ${(data && data.error) || 'Unknown'}`, 'error');
            btn.disabled = false; btn.textContent = 'Add Entry';
        }
    },

    // ─── RunPod job (mock) ────────────────────────────────────────────────────

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
        this._renderJob();

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'processing';
            this.job.cost = 0.04;
            this.job.elapsed = 8;
            this._renderJob();
        }, 2000);

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'complete';
            this.job.cost = 0.12;
            this.job.elapsed = 45;
            this._renderJob();
            Studio.log('HD render complete — $0.12, 45s');
        }, 7000);
    },

    // ─── RunPod job (real) ────────────────────────────────────────────────────

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
        this._renderJob();

        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/reconstruct_3d`, {});
        if (!ok) {
            this.job.status = 'error';
            this.job.errors = 1;
            this._renderJob();
            Studio.log(`Reconstruction failed: ${(data && data.error) || 'Unknown'}`, 'error');
            return;
        }

        this.job.id = data.job_id || data.id || ('job-' + Date.now());
        this.job.gpuType = data.gpu_type || 'A40';
        this.job.status = 'processing';
        Studio.log(`Reconstruction job ${this.job.id} started`);
        this._renderJob();
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
        const { ok, data } = await Studio.apiGet('/api/gpu_status');
        if (ok) {
            if (this.job._startTs) {
                this.job.elapsed = Math.round((Date.now() - this.job._startTs) / 1000);
            }
            if (data.job_status) this.job.status = data.job_status;
            if (data.cost != null) this.job.cost = data.cost;
            if (data.gpu_type) this.job.gpuType = data.gpu_type;
            this._renderJob();

            if (this.job.status === 'complete' || this.job.status === 'error') {
                this._stopPoll();
                Studio.log(`Job ${this.job.id} ${this.job.status}`);
                if (this.job.status === 'complete' && data.glb_url) {
                    Studio.showInViewport('glb', data.glb_url);
                }
            }
        }
    },

    _renderJob() {
        // Job status shown in progress-charts area (top section)
        const el = document.getElementById('progress-charts');
        if (!el || !this.job) return;

        const statusColors = { queued: '#eab308', processing: '#3b82f6', complete: '#22c55e', error: '#ef4444' };
        const color = statusColors[this.job.status] || '#6b7280';
        const label = this.job.status.charAt(0).toUpperCase() + this.job.status.slice(1);

        const row = (k, v) =>
            `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
                <span style="color:var(--text-secondary);">${k}</span><span>${v}</span></div>`;

        // Inject job card at top without replacing full progress view
        let jobCard = document.getElementById('pp-job-card');
        if (!jobCard) {
            jobCard = document.createElement('div');
            jobCard.id = 'pp-job-card';
            jobCard.style.cssText = 'margin-bottom:0.75rem;padding:0.5rem;background:rgba(255,255,255,0.04);border-radius:4px;border:1px solid rgba(255,255,255,0.08);';
            el.insertBefore(jobCard, el.firstChild);
        }

        jobCard.innerHTML = `
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-secondary);margin-bottom:4px;">HD Render Job</div>
            ${row('Status', `<span style="color:${color};font-weight:600;">${label}</span>`)}
            ${row('Job ID', (this.job.id || 'pending').toString().substring(0, 16))}
            ${row('GPU', this.job.gpuType)}
            ${row('Time', this.job.elapsed + 's')}
            ${row('Cost', '$' + this.job.cost.toFixed(2))}
            ${this.job.status === 'processing'
                ? '<div style="margin-top:6px;height:3px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;"><div style="height:100%;width:40%;background:#3b82f6;border-radius:2px;"></div></div>'
                : ''}
            ${this.job.status === 'complete'
                ? '<div style="margin-top:6px;font-size:11px;color:#22c55e;">Render complete. View in viewport.</div>'
                : ''}
        `;
    },

    // ─── Advanced actions ─────────────────────────────────────────────────────

    async compare3D(customerId) {
        if (Studio.MOCK_MODE) { Studio.log('3D compare (mock): need 2 meshes'); return; }
        const el = document.getElementById('progress-charts');
        if (!el) return;
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/meshes`);
        if (!ok || !data.meshes || data.meshes.length < 2) {
            Studio.log('Need at least 2 meshes for comparison', 'error');
            return;
        }
        const meshes = data.meshes;
        const mesh1 = meshes[meshes.length - 2].id;
        const mesh2 = meshes[meshes.length - 1].id;

        Studio.log(`Comparing meshes #${mesh1} vs #${mesh2}...`);
        const { ok: cmpOk, data: cmpData } = await Studio.apiPost(`/api/customer/${customerId}/compare_meshes`, {
            mesh_id_1: mesh1, mesh_id_2: mesh2,
        });
        if (cmpOk) {
            Studio.log('3D comparison complete');
            if (cmpData.heatmap_url) Studio.showInViewport('heatmap', cmpData.heatmap_url);
        } else {
            Studio.log('3D comparison failed', 'error');
        }
    },

    async exportData(customerId) {
        Studio.log('Exporting progress data…');
        let exportObj;

        if (Studio.MOCK_MODE) {
            exportObj = {
                customer_id: customerId,
                exported_at: new Date().toISOString(),
                scans: this._MOCK_PROGRESS.scans,
                health_logs: this._MOCK_PROGRESS.health_logs,
            };
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

    async bodyComposition(customerId) {
        if (Studio.MOCK_MODE) { Studio.log('Body composition (mock): no backend'); return; }
        const el = document.getElementById('progress-charts');
        if (!el) return;
        el.innerHTML = '<div class="empty-state"><span class="spinner"></span> Calculating...</div>';

        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/body_composition`, {});
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Calculation failed</div>';
            return;
        }

        const fields = [
            { key: 'body_fat_pct', label: 'Body Fat %' },
            { key: 'lean_mass_kg', label: 'Lean Mass (kg)' },
            { key: 'bmi', label: 'BMI' },
            { key: 'bmr_kcal', label: 'BMR (kcal)' },
            { key: 'tdee_kcal', label: 'TDEE (kcal)' },
        ];
        el.innerHTML = `
            <div style="font-weight:600;margin-bottom:0.5rem;">Body Composition</div>
            ${fields.map(f => {
                const val = data[f.key];
                if (val == null) return '';
                return `<div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                    <span>${f.label}</span>
                    <span>${typeof val === 'number' ? val.toFixed(1) : val}</span>
                </div>`;
            }).join('')}
            ${data.visual_url ? `<img src="${Studio.API_BASE}${data.visual_url}" style="width:100%;border-radius:var(--radius-sm);margin-top:0.5rem;">` : ''}
            <div class="btn-row">
                <button class="btn btn-sm" onclick="ProgressPanel.loadProgress(${customerId})">Back</button>
            </div>
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => ProgressPanel.init());
