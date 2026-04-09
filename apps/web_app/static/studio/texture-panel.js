/* GTD3D Studio — Texture Panel
 * Right sidebar: body-part texture checklist with approve/re-capture actions.
 */
const TexturePanel = {
    regions: [
        { id: 'head', name: 'Head', status: 'captured' },
        { id: 'neck', name: 'Neck', status: 'captured' },
        { id: 'chest', name: 'Chest', status: 'captured' },
        { id: 'back', name: 'Back', status: 'missing' },
        { id: 'abdomen', name: 'Abdomen', status: 'blurry' },
        { id: 'upper-arm-l', name: 'Upper Arm L', status: 'captured' },
        { id: 'upper-arm-r', name: 'Upper Arm R', status: 'captured' },
        { id: 'forearm-l', name: 'Forearm L', status: 'missing' },
        { id: 'forearm-r', name: 'Forearm R', status: 'captured' },
        { id: 'hand-l', name: 'Hand L', status: 'captured' },
        { id: 'hand-r', name: 'Hand R', status: 'captured' },
        { id: 'hip', name: 'Hip', status: 'blurry' },
        { id: 'thigh-l', name: 'Thigh L', status: 'captured' },
        { id: 'thigh-r', name: 'Thigh R', status: 'captured' },
        { id: 'calf-l', name: 'Calf L', status: 'missing' },
        { id: 'calf-r', name: 'Calf R', status: 'captured' },
    ],

    _statusColors: {
        captured: '#22c55e',
        missing: '#ef4444',
        blurry: '#eab308',
        approved: '#6366f1',
        pending: '#6b7280',
    },

    init() {
        this.render();
    },

    render() {
        const el = document.getElementById('texture-parts');
        if (!el) return;

        const total = this.regions.length;
        const good = this.regions.filter(r => r.status === 'captured' || r.status === 'approved').length;

        let html = `<div style="margin-bottom:8px;font-size:12px;color:var(--text-dim);">${good}/${total} regions ready</div>`;
        html += this.regions.map(r => {
            const color = this._statusColors[r.status] || '#6b7280';
            const label = r.status.charAt(0).toUpperCase() + r.status.slice(1);
            const isGood = r.status === 'captured' || r.status === 'approved';
            return `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
                <span style="flex:1;">${r.name}</span>
                <span style="color:${color};width:60px;text-align:center;font-size:11px;">${label}</span>
                <span style="width:100px;text-align:right;">
                    ${isGood && r.status !== 'approved'
                        ? `<button onclick="TexturePanel.approve('${r.id}')" style="background:none;border:1px solid #6366f1;color:#6366f1;border-radius:3px;padding:2px 6px;font-size:10px;cursor:pointer;">Approve</button>`
                        : r.status === 'approved'
                            ? '<span style="color:#6366f1;font-size:10px;">Approved</span>'
                            : `<button onclick="TexturePanel.requestRecapture('${r.id}')" style="background:none;border:1px solid #ef4444;color:#ef4444;border-radius:3px;padding:2px 6px;font-size:10px;cursor:pointer;">Re-capture</button>`
                    }
                </span>
            </div>`;
        }).join('');

        el.innerHTML = html;
    },

    approve(id) {
        const region = this.regions.find(r => r.id === id);
        if (region) {
            region.status = 'approved';
            if (typeof Studio !== 'undefined') Studio.log(`Approved texture: ${region.name}`);
            this.render();
        }
    },

    requestRecapture(id) {
        const region = this.regions.find(r => r.id === id);
        if (region) {
            region.status = 'pending';
            if (typeof Studio !== 'undefined') Studio.log(`Re-capture requested: ${region.name}`);
            this.render();
        }
    },
};

document.addEventListener('DOMContentLoaded', () => TexturePanel.init());
