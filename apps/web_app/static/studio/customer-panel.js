/* GTD3D Studio — Customer Panel
 * Left sidebar: customer list, search, profile view, create new.
 */
const CustomerPanel = {
    customers: [],
    filteredCustomers: [],

    async init() {
        await this.loadCustomers();
        this._bindSearch();
        this._bindCreateForm();
    },

    async loadCustomers() {
        const { ok, data } = await Studio.apiGet('/api/customers');
        if (!ok) {
            this._renderError('Failed to load customers');
            return;
        }
        this.customers = data.customers || data || [];
        this.filteredCustomers = this.customers;
        this._renderList();
    },

    _bindSearch() {
        const input = document.getElementById('customer-search');
        if (!input) return;
        input.addEventListener('input', () => {
            const q = input.value.toLowerCase().trim();
            this.filteredCustomers = q
                ? this.customers.filter(c =>
                    (c.name || '').toLowerCase().includes(q) ||
                    (c.email || '').toLowerCase().includes(q) ||
                    String(c.id).includes(q))
                : this.customers;
            this._renderList();
        });
    },

    _bindCreateForm() {
        const form = document.getElementById('create-customer-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = form.querySelector('[name="email"]').value.trim();
            if (!email) return;
            const btn = form.querySelector('button[type="submit"]');
            btn.disabled = true; btn.textContent = 'Creating...';
            const { ok, data } = await Studio.apiPost('/api/customers', { email });
            if (ok) {
                form.reset();
                await this.loadCustomers();
                Studio.log(`Created customer: ${email}`);
            } else {
                Studio.log(`Failed to create customer: ${data.error || 'Unknown'}`, 'error');
            }
            btn.disabled = false; btn.textContent = 'Create';
        });
    },

    _renderList() {
        const el = document.getElementById('customer-list');
        if (!el) return;
        if (this.filteredCustomers.length === 0) {
            el.innerHTML = '<div class="empty-state">No customers found</div>';
            return;
        }
        el.innerHTML = this.filteredCustomers.map(c => {
            const active = Studio.customerId === c.id ? 'active' : '';
            const scans = c.scan_count || 0;
            return `<div class="list-item ${active}" onclick="CustomerPanel.select(${c.id})">
                <div>
                    <div>${c.name || c.email || 'Customer #' + c.id}</div>
                    <div class="meta">${c.email}${scans ? ' · ' + scans + ' scan' + (scans !== 1 ? 's' : '') : ''}</div>
                </div>
            </div>`;
        }).join('');
    },

    async select(id) {
        const customer = this.customers.find(c => c.id === id);
        if (!customer) return;
        // Fetch full profile
        const { ok, data } = await Studio.apiGet(`/api/customer/${id}/body_profile`);
        if (ok) {
            customer.profile = data;
        }
        Studio.selectCustomer(customer);
        this._renderList();
        this._renderProfile(customer);
    },

    _renderProfile(customer) {
        const el = document.getElementById('customer-profile');
        if (!el) return;
        const p = customer.profile || {};
        const fields = [
            { label: 'Height', key: 'height_cm', unit: 'cm' },
            { label: 'Weight', key: 'weight_kg', unit: 'kg' },
            { label: 'Chest', key: 'chest_circumference_cm', unit: 'cm' },
            { label: 'Waist', key: 'waist_circumference_cm', unit: 'cm' },
            { label: 'Hips', key: 'hip_circumference_cm', unit: 'cm' },
            { label: 'Bicep', key: 'bicep_circumference_cm', unit: 'cm' },
            { label: 'Quad', key: 'quadricep_circumference_cm', unit: 'cm' },
            { label: 'Thigh', key: 'thigh_circumference_cm', unit: 'cm' },
            { label: 'Calf', key: 'calf_circumference_cm', unit: 'cm' },
            { label: 'Neck', key: 'neck_circumference_cm', unit: 'cm' },
            { label: 'Shoulders', key: 'shoulder_width_cm', unit: 'cm' },
            { label: 'Forearm', key: 'forearm_circumference_cm', unit: 'cm' },
        ];
        el.innerHTML = `
            <div style="padding:0.5rem 0;">
                <strong>${customer.email || 'Customer #' + customer.id}</strong>
            </div>
            ${fields.map(f => {
                const val = p[f.key];
                return val ? `<div class="form-group" style="display:flex;justify-content:space-between;">
                    <span class="form-label" style="display:inline;">${f.label}</span>
                    <span>${val} ${f.unit}</span>
                </div>` : '';
            }).join('')}
            <div class="btn-row">
                <button class="btn btn-sm" onclick="CustomerPanel.editProfile(${customer.id})">Edit Profile</button>
                <button class="btn btn-sm btn-accent" onclick="CustomerPanel.quickStats(${customer.id})">Quick Stats</button>
            </div>
        `;
    },

    async editProfile(id) {
        const { ok, data } = await Studio.apiGet(`/api/customer/${id}/body_profile`);
        if (!ok) return;
        const el = document.getElementById('customer-profile');
        if (!el) return;
        const fields = ['height_cm', 'weight_kg', 'chest_circumference_cm', 'waist_circumference_cm', 'hip_circumference_cm', 'bicep_circumference_cm', 'quadricep_circumference_cm', 'thigh_circumference_cm', 'calf_circumference_cm', 'neck_circumference_cm', 'shoulder_width_cm', 'forearm_circumference_cm'];
        el.innerHTML = `
            <form id="edit-profile-form">
                ${fields.map(f => `<div class="form-group">
                    <label class="form-label">${f.replace(/_/g, ' ').replace(' cm', ' (cm)').replace(' kg', ' (kg)')}</label>
                    <input class="form-input" name="${f}" type="number" step="0.1" value="${data[f] || ''}">
                </div>`).join('')}
                <div class="btn-row">
                    <button class="btn btn-accent btn-sm" type="submit">Save</button>
                    <button class="btn btn-sm" type="button" onclick="CustomerPanel.select(${id})">Cancel</button>
                </div>
            </form>
        `;
        document.getElementById('edit-profile-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = {};
            fields.forEach(f => {
                const val = e.target.querySelector(`[name="${f}"]`).value;
                if (val) formData[f] = parseFloat(val);
            });
            const { ok: saved } = await Studio.apiPost(`/api/customer/${id}/body_profile`, formData);
            if (saved) {
                Studio.log('Profile updated');
                this.select(id);
            }
        });
    },

    async quickStats(id) {
        const { ok, data } = await Studio.apiGet(`/api/customer/${id}/quick_stats`);
        if (!ok) return;
        const el = document.getElementById('customer-profile');
        if (!el) return;
        el.innerHTML = `
            <div style="padding:0.5rem 0;"><strong>Quick Stats</strong></div>
            ${Object.entries(data).map(([k, v]) =>
                `<div style="display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.8125rem;">
                    <span class="form-label" style="display:inline;">${k.replace(/_/g, ' ')}</span>
                    <span>${typeof v === 'number' ? v.toFixed(1) : v}</span>
                </div>`
            ).join('')}
            <div class="btn-row">
                <button class="btn btn-sm" onclick="CustomerPanel.select(${id})">Back</button>
            </div>
        `;
    },

    _renderError(msg) {
        const el = document.getElementById('customer-list');
        if (el) el.innerHTML = `<div class="empty-state" style="color:var(--error);">${msg}</div>`;
    },
};
