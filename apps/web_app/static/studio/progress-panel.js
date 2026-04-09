/* GTD3D Studio — Progress Panel
 * Right sidebar: RunPod job tracker with cost/time/status stats.
 */
const ProgressPanel = {
    job: null,

    init() {
        document.addEventListener('hd-requested', () => this.startMockJob());
        this.render();
    },

    startMockJob() {
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
        this.render();

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'processing';
            this.job.cost = 0.04;
            this.job.elapsed = 8;
            this.render();
        }, 2000);

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'complete';
            this.job.cost = 0.12;
            this.job.elapsed = 45;
            this.render();
            if (typeof Studio !== 'undefined') Studio.log('HD render complete — $0.12, 45s');
        }, 7000);
    },

    render() {
        const el = document.getElementById('runpod-stats');
        if (!el) return;

        if (!this.job) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">No HD render requested yet.</div>';
            return;
        }

        const statusColors = { queued: '#eab308', processing: '#3b82f6', complete: '#22c55e', error: '#ef4444' };
        const color = statusColors[this.job.status] || '#6b7280';
        const label = this.job.status.charAt(0).toUpperCase() + this.job.status.slice(1);

        const row = (k, v) => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
            <span style="color:var(--text-dim);">${k}</span><span>${v}</span></div>`;

        el.innerHTML = `
            ${row('Status', `<span style="color:${color};font-weight:600;">${label}</span>`)}
            ${row('Job ID', this.job.id.substring(0, 16))}
            ${row('GPU', this.job.gpuType)}
            ${row('Resolution', this.job.resolution)}
            ${row('Time', this.job.elapsed + 's')}
            ${row('Cost', '$' + this.job.cost.toFixed(2))}
            ${row('Errors', this.job.errors)}
            ${row('Started', this.job.startedAt)}
            ${this.job.status === 'processing' ? '<div style="margin-top:8px;"><div style="height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;"><div style="height:100%;width:40%;background:#3b82f6;border-radius:2px;"></div></div></div>' : ''}
            ${this.job.status === 'complete' ? '<div style="margin-top:8px;padding:6px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:4px;font-size:11px;color:#22c55e;">Render complete. View in viewport.</div>' : ''}
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => ProgressPanel.init());
