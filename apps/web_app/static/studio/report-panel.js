/* GTD3D Studio — Report Panel
 * PDF reports, health logs, data export.
 */
const ReportPanel = {
    init() {
        document.addEventListener('customer-selected', (e) => {
            this._customerId = e.detail.id;
            this.loadHealthLogs(e.detail.id);
        });
    },

    _customerId: null,

    async loadHealthLogs(customerId) {
        const el = document.getElementById('health-log-container');
        if (!el) return;
        el.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/health_logs`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Backend unavailable — start py4web or enable Mock mode</div>';
            return;
        }
        this._renderHealthLogs(el, customerId, data.logs || data || []);
    },

    _renderHealthLogs(el, customerId, logs) {
        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <span style="font-weight:600;font-size:0.8125rem;">Health Logs</span>
                <button class="btn btn-sm btn-accent" onclick="ReportPanel.showAddLog(${customerId})">+ Log</button>
            </div>
            ${logs.length === 0 ? '<div class="empty-state">No health logs yet</div>' :
                logs.slice(0, 15).map(log => `
                    <div class="list-item" style="flex-direction:column;align-items:flex-start;gap:0.25rem;padding:0.375rem 0;">
                        <div style="display:flex;justify-content:space-between;width:100%;">
                            <span style="font-size:0.8125rem;">${log.log_date || 'No date'}</span>
                            <span class="tag tag-info">${log.activity_type || 'general'}</span>
                        </div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">
                            ${log.weight_kg ? `Weight: ${log.weight_kg}kg` : ''}
                            ${log.calories ? ` | Cal: ${log.calories}` : ''}
                            ${log.sleep_hours ? ` | Sleep: ${log.sleep_hours}h` : ''}
                        </div>
                        ${log.notes ? `<div style="font-size:0.6875rem;color:var(--text-secondary);font-style:italic;">${log.notes}</div>` : ''}
                    </div>
                `).join('')
            }
            <div class="btn-row" style="margin-top:0.75rem;">
                <button class="btn btn-sm" onclick="ReportPanel.generateReport(${customerId})">Generate Report</button>
                <button class="btn btn-sm" onclick="ProgressPanel.exportData(${customerId})">Export Data</button>
            </div>
        `;
    },

    showAddLog(customerId) {
        const el = document.getElementById('health-log-container');
        if (!el) return;
        const today = new Date().toISOString().split('T')[0];
        el.innerHTML = `
            <div style="font-weight:600;margin-bottom:0.5rem;">New Health Log</div>
            <form id="health-log-form">
                <div class="form-group">
                    <label class="form-label">Date</label>
                    <input class="form-input" name="log_date" type="date" value="${today}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Weight (kg)</label>
                    <input class="form-input" name="weight_kg" type="number" step="0.1" placeholder="75.0">
                </div>
                <div class="form-group">
                    <label class="form-label">Calories</label>
                    <input class="form-input" name="calories" type="number" placeholder="2000">
                </div>
                <div class="form-group">
                    <label class="form-label">Sleep (hours)</label>
                    <input class="form-input" name="sleep_hours" type="number" step="0.5" placeholder="7.5">
                </div>
                <div class="form-group">
                    <label class="form-label">Activity</label>
                    <select class="form-select" name="activity_type">
                        <option value="rest">Rest</option>
                        <option value="light">Light</option>
                        <option value="moderate" selected>Moderate</option>
                        <option value="intense">Intense</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Notes</label>
                    <input class="form-input" name="notes" type="text" placeholder="Optional notes...">
                </div>
                <div class="btn-row">
                    <button class="btn btn-accent btn-sm" type="submit">Save</button>
                    <button class="btn btn-sm" type="button" onclick="ReportPanel.loadHealthLogs(${customerId})">Cancel</button>
                </div>
            </form>
        `;
        document.getElementById('health-log-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const payload = {};
            ['log_date', 'weight_kg', 'calories', 'sleep_hours', 'activity_type', 'notes'].forEach(f => {
                const val = form.querySelector(`[name="${f}"]`).value;
                if (val) {
                    payload[f] = ['weight_kg', 'calories', 'sleep_hours'].includes(f) ? parseFloat(val) : val;
                }
            });
            const { ok } = await Studio.apiPost(`/api/customer/${customerId}/health_log`, payload);
            if (ok) {
                Studio.log('Health log saved');
                this.loadHealthLogs(customerId);
            } else {
                Studio.log('Failed to save health log', 'error');
            }
        });
    },

    async generateReport(customerId) {
        // Need a scan ID — get latest
        const { ok: scanOk, data: scanData } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
        if (!scanOk || !scanData.scans || scanData.scans.length === 0) {
            Studio.log('No scans available for report', 'error');
            return;
        }
        const latestScan = scanData.scans[scanData.scans.length - 1];
        Studio.log(`Generating report for scan #${latestScan.id}...`);

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/report/${latestScan.id}`);
        if (ok && data.pdf_url) {
            // Download PDF
            const a = document.createElement('a');
            a.href = `${Studio.API_BASE}${data.pdf_url}`;
            a.download = `report_${customerId}_${latestScan.id}.pdf`;
            a.click();
            Studio.log('Report generated');
        } else if (ok && data.report) {
            Studio.log('Report generated (inline)');
        } else {
            Studio.log('Report generation failed', 'error');
        }
    },
};
