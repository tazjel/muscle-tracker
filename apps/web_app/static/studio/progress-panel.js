/* GTD3D Studio — Progress Panel
 * Charts, trends, body composition, mesh comparison.
 */
const ProgressPanel = {
    chartCanvas: null,
    chartCtx: null,

    init() {
        document.addEventListener('customer-selected', (e) => {
            this.loadProgress(e.detail.id);
        });
    },

    async loadProgress(customerId) {
        const el = document.getElementById('progress-charts');
        if (!el) return;
        el.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading progress...</div>';

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/progress`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load progress</div>';
            return;
        }
        this._render(el, customerId, data);
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
            ${this._renderScanTimeline(scans)}

            <div class="btn-row" style="flex-wrap:wrap;">
                <button class="btn btn-sm" onclick="ProgressPanel.compare3D(${customerId})">3D Compare</button>
                <button class="btn btn-sm" onclick="ProgressPanel.exportData(${customerId})">Export CSV</button>
                <button class="btn btn-sm btn-accent" onclick="ProgressPanel.bodyComposition(${customerId})">Body Comp</button>
            </div>
        `;
    },

    _renderTrends(trends) {
        if (!trends || Object.keys(trends).length === 0) return '';
        const rows = Object.entries(trends).map(([key, val]) => {
            const label = key.replace(/_/g, ' ');
            const direction = val.slope > 0 ? '+' : '';
            const color = val.slope > 0 ? 'var(--success)' : val.slope < 0 ? 'var(--error)' : 'var(--text-secondary)';
            return `<div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                <span>${label}</span>
                <span style="color:${color}">${direction}${val.slope.toFixed(2)}/scan</span>
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
                <span>${typeof val === 'number' ? val.toFixed(1) : val} ${f.unit}</span>
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

    _renderScanTimeline(scans) {
        if (!scans || scans.length === 0) return '';
        const items = scans.slice(0, 10).map(s => {
            const date = s.created_on || s.scan_date || 'Unknown';
            return `<div class="list-item" style="padding:0.25rem 0;">
                <div>
                    <div style="font-size:0.8125rem;">Scan #${s.id}</div>
                    <div class="meta">${date}</div>
                </div>
            </div>`;
        }).join('');
        return `<div style="margin-bottom:0.75rem;">
            <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.25rem;">Recent Scans</div>
            ${items}
        </div>`;
    },

    async compare3D(customerId) {
        const el = document.getElementById('progress-charts');
        if (!el) return;
        // Need at least 2 scans with meshes
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
            mesh_id_1: mesh1, mesh_id_2: mesh2
        });
        if (cmpOk) {
            Studio.log('3D comparison complete');
            if (cmpData.heatmap_url) {
                Studio.showInViewport('heatmap', cmpData.heatmap_url);
            }
        } else {
            Studio.log('3D comparison failed', 'error');
        }
    },

    async exportData(customerId) {
        try {
            const resp = await fetch(`${Studio.API_BASE}/api/customer/${customerId}/export`);
            if (!resp.ok) { Studio.log('Export failed', 'error'); return; }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = `customer_${customerId}_export.json`;
            a.click();
            URL.revokeObjectURL(url);
            Studio.log('Data exported');
        } catch (e) {
            Studio.log(`Export error: ${e.message}`, 'error');
        }
    },

    async bodyComposition(customerId) {
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
