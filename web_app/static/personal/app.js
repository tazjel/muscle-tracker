/* ── Config ── */
const API = '';   // same-origin; set full URL for dev: 'http://localhost:8000'
let customerId = null;
let token = null;
let allScans = [];
let charts = {};

/* ── Muscle groups + body map geometry (front-view SVG coordinates) ── */
const MUSCLE_MAP = {
  bicep:    { emoji:'💪', label:'Biceps',     polys:['65,140 80,130 85,160 70,165','115,130 130,140 130,165 115,160'] },
  tricep:   { emoji:'🦾', label:'Triceps',    polys:['55,130 65,140 70,165 55,155','130,140 140,130 145,155 130,165'] },
  deltoid:  { emoji:'⬛', label:'Deltoids',   polys:['55,100 75,95 75,130 55,130','125,95 145,100 145,130 125,130'] },
  chest:    { emoji:'🏋️', label:'Chest',      polys:['75,95 125,95 125,145 75,145'] },
  lat:      { emoji:'🔷', label:'Lats',       polys:['55,130 75,145 75,170 55,165','125,145 145,130 145,165 125,170'] },
  quadricep:{ emoji:'🦵', label:'Quads',      polys:['75,200 95,200 95,280 75,275','105,200 125,200 125,275 105,280'] },
  hamstring:{ emoji:'🦿', label:'Hamstrings', polys:['75,275 95,280 95,330 78,325','105,280 125,275 122,325 105,330'] },
  calf:     { emoji:'🦶', label:'Calves',     polys:['78,325 94,330 90,370 76,368','106,330 122,325 124,368 110,370'] },
  glute:    { emoji:'🔵', label:'Glutes',     polys:['75,170 125,170 120,200 80,200'] },
};

const SCORE_COLOR = s => s >= 75 ? '#00c866' : s >= 50 ? '#ff8c00' : s > 0 ? '#e03030' : '#444';

/* ── Bootstrap ── */
document.addEventListener('DOMContentLoaded', () => {
  token = localStorage.getItem('mt_token');
  customerId = localStorage.getItem('mt_customer_id');
  const name = localStorage.getItem('mt_customer_name') || 'Athlete';
  document.getElementById('user-name').textContent = name;

  if (!token || !customerId) {
    renderDemo();
    return;
  }

  // Hide login button when already authenticated
  document.getElementById('btn-login').style.display = 'none';
  loadAll();
});

/* ── Login ── */
async function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';
  if (!email) { errEl.textContent = 'Email required'; errEl.style.display = 'block'; return; }

  try {
    const r = await fetch(`${API}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const data = await r.json();
    if (data.status !== 'success') {
      errEl.textContent = data.message || 'Login failed';
      errEl.style.display = 'block';
      return;
    }
    token      = data.token;
    customerId = data.customer_id;
    localStorage.setItem('mt_token',         token);
    localStorage.setItem('mt_customer_id',   String(customerId));
    localStorage.setItem('mt_customer_name', data.name || 'Athlete');
    document.getElementById('user-name').textContent = data.name || 'Athlete';
    document.getElementById('btn-login').style.display = 'none';
    closeModal('login-modal');
    loadAll();
  } catch (e) {
    errEl.textContent = 'Network error — try again';
    errEl.style.display = 'block';
  }
}

async function loadAll() {
  await Promise.all([loadScans(), loadProgress()]);
}

/* ── Data Loading ── */
async function loadScans() {
  try {
    const r = await apiFetch(`/api/customer/${customerId}/scans`);
    if (r.status === 'success') {
      allScans = r.scans || [];
      renderScans(allScans);
      renderStats(allScans);
      renderBodyMap(allScans);
      populateMuscleSelect(allScans);
      updateLastScan(allScans);
    }
  } catch (e) { console.warn('loadScans:', e); }
}

async function loadProgress() {
  try {
    const r = await apiFetch(`/api/customer/${customerId}/progress`);
    if (r.status === 'success') {
      renderCharts(allScans);
    }
  } catch (e) { renderCharts(allScans); }
}

/* ── Stats ── */
function renderStats(scans) {
  document.getElementById('stat-scans').textContent = scans.length;
  const groups = new Set(scans.map(s => s.muscle_group)).size;
  document.getElementById('stat-muscles').textContent = groups;

  const growths = scans.map(s => s.growth_pct).filter(v => v != null);
  const best = growths.length ? Math.max(...growths) : null;
  document.getElementById('stat-growth').textContent = best != null ? `+${best.toFixed(1)}%` : '–';

  const days = scans.length > 1
    ? Math.round((new Date(scans[0].scan_date) - new Date(scans[scans.length - 1].scan_date)) / 86400000)
    : 0;
  document.getElementById('stat-days').textContent = days;
  document.getElementById('stat-streak').textContent = calcStreak(scans);
}

function calcStreak(scans) {
  if (!scans.length) return 0;
  const dates = [...new Set(scans.map(s => s.scan_date?.slice(0, 10)))].sort().reverse();
  let streak = 1, prev = new Date(dates[0]);
  for (let i = 1; i < dates.length; i++) {
    const d = new Date(dates[i]);
    if ((prev - d) / 86400000 <= 7) { streak++; prev = d; } else break;
  }
  return streak;
}

function updateLastScan(scans) {
  const lbl = scans.length
    ? `Last scan: ${new Date(scans[0].scan_date).toLocaleDateString()}`
    : 'No scans yet';
  document.getElementById('last-scan-label').textContent = lbl;
}

/* ── Body Map ── */
function renderBodyMap(scans) {
  const svg = document.getElementById('body-svg');
  svg.innerHTML = '';

  // Body outline
  const outline = `
    <ellipse cx="100" cy="22" rx="18" ry="20" fill="#2a2d3e" stroke="#3a3d50" stroke-width="1"/>
    <rect x="72" y="88" width="56" height="85" rx="6" fill="#2a2d3e" stroke="#3a3d50" stroke-width="1"/>
    <rect x="50" y="88" width="22" height="75" rx="6" fill="#232637" stroke="#3a3d50" stroke-width="1"/>
    <rect x="128" y="88" width="22" height="75" rx="6" fill="#232637" stroke="#3a3d50" stroke-width="1"/>
    <rect x="72" y="173" width="24" height="110" rx="6" fill="#2a2d3e" stroke="#3a3d50" stroke-width="1"/>
    <rect x="104" y="173" width="24" height="110" rx="6" fill="#2a2d3e" stroke="#3a3d50" stroke-width="1"/>
    <rect x="74" y="283" width="20" height="80" rx="5" fill="#232637" stroke="#3a3d50" stroke-width="1"/>
    <rect x="106" y="283" width="20" height="80" rx="5" fill="#232637" stroke="#3a3d50" stroke-width="1"/>
  `;
  svg.innerHTML = outline;

  // Latest score per muscle group
  const latest = {};
  [...scans].reverse().forEach(s => { latest[s.muscle_group] = s; });

  Object.entries(MUSCLE_MAP).forEach(([key, def]) => {
    const scan = latest[key];
    const score = scan?.shape_score ?? 0;
    const color = scan ? SCORE_COLOR(score) : '#333';

    def.polys.forEach(pts => {
      const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      poly.setAttribute('points', pts);
      poly.setAttribute('fill', color);
      poly.setAttribute('fill-opacity', '0.75');
      poly.setAttribute('stroke', '#1a1d27');
      poly.setAttribute('stroke-width', '1');
      poly.setAttribute('class', 'muscle-region');
      poly.setAttribute('title', def.label);
      poly.addEventListener('click', () => showMuscleDetail(key, scan));
      svg.appendChild(poly);
    });
  });
}

function showMuscleDetail(key, scan) {
  const def = MUSCLE_MAP[key];
  const panel = document.getElementById('muscle-detail');
  panel.classList.remove('hidden');
  document.getElementById('detail-name').textContent = `${def.emoji} ${def.label}`;
  document.getElementById('detail-volume').textContent  = scan ? `Volume: ${scan.volume_cm3?.toFixed(1) ?? '–'} cm³` : 'Not scanned';
  document.getElementById('detail-score').textContent   = scan ? `Shape: ${scan.shape_score?.toFixed(0) ?? '–'}/100 (${scan.shape_grade ?? '–'})` : '';
  document.getElementById('detail-growth').textContent  = scan?.growth_pct != null ? `Growth: ${scan.growth_pct > 0 ? '+' : ''}${scan.growth_pct.toFixed(1)}%` : '';
  document.getElementById('detail-circ').textContent    = scan?.circumference_cm ? `Circ: ${scan.circumference_cm.toFixed(1)} cm` : '';
}

/* ── Scan Cards ── */
function renderScans(scans) {
  const container = document.getElementById('scan-cards');
  container.innerHTML = '';
  const recent = scans.slice(0, 12);
  if (!recent.length) { container.innerHTML = '<p style="color:var(--text-dim);padding:16px">No scans yet.</p>'; return; }

  recent.forEach(scan => {
    const card = document.createElement('div');
    card.className = 'scan-card';
    card.onclick = () => showScanDetail(scan);
    const graw = scan.growth_pct;
    const gcls = graw > 0 ? 'scan-growth-pos' : graw < 0 ? 'scan-growth-neg' : '';
    const gstr = graw != null ? `${graw > 0 ? '+' : ''}${graw.toFixed(1)}%` : '';
    card.innerHTML = `
      <div class="scan-thumb">${MUSCLE_MAP[scan.muscle_group]?.emoji ?? '📷'}</div>
      <div class="scan-info">
        <div class="scan-muscle">${scan.muscle_group}</div>
        <div class="scan-date">${new Date(scan.scan_date).toLocaleDateString()}</div>
        <div class="scan-metric">${scan.volume_cm3?.toFixed(1) ?? ''} cm³ <span class="${gcls}">${gstr}</span></div>
      </div>`;
    container.appendChild(card);
  });
}

/* ── Charts ── */
const CHART_DEFAULTS = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { display: false }, tooltip: { backgroundColor: '#1a1d27', titleColor: '#00b4cc', bodyColor: '#e2e4f0' } },
  scales: {
    x: { ticks: { color: '#7a7f9a', font: { size: 10 } }, grid: { color: '#2e3245' } },
    y: { ticks: { color: '#7a7f9a', font: { size: 10 } }, grid: { color: '#2e3245' } },
  },
};

function renderCharts(scans) {
  const muscleFilter = document.getElementById('chart-muscle')?.value;
  const filtered = muscleFilter ? scans.filter(s => s.muscle_group === muscleFilter) : scans;
  const sorted = [...filtered].sort((a, b) => new Date(a.scan_date) - new Date(b.scan_date));
  const labels = sorted.map(s => new Date(s.scan_date).toLocaleDateString());

  const mkDataset = (data, color) => ({
    data, borderColor: color, backgroundColor: color + '22',
    fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: color,
  });

  ['volume', 'circumference', 'shape', 'definition'].forEach(key => destroyChart(key));

  buildChart('chart-volume',        labels, mkDataset(sorted.map(s => s.volume_cm3       ?? null), '#00b4cc'));
  buildChart('chart-circumference', labels, mkDataset(sorted.map(s => s.circumference_cm ?? null), '#00c866'));
  buildChart('chart-shape',         labels, mkDataset(sorted.map(s => s.shape_score      ?? null), '#ffcc00'));
  buildChart('chart-definition',    labels, mkDataset(sorted.map(s => s.definition_score ?? null), '#ff8c00'));
}

function buildChart(id, labels, dataset) {
  const ctx = document.getElementById(id)?.getContext('2d');
  if (!ctx) return;
  charts[id] = new Chart(ctx, { type: 'line', data: { labels, datasets: [dataset] }, options: CHART_DEFAULTS });
}

function destroyChart(key) {
  const id = `chart-${key}`;
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function showTab(name) {
  ['volume', 'circumference', 'shape', 'definition'].forEach(k => {
    document.getElementById(`chart-${k}`).classList.toggle('hidden', k !== name);
  });
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['volume', 'circumference', 'shape', 'definition'][i] === name);
  });
}

function refreshCharts() { renderCharts(allScans); }

/* ── Muscle Select ── */
function populateMuscleSelect(scans) {
  const sel = document.getElementById('chart-muscle');
  const groups = [...new Set(scans.map(s => s.muscle_group))];
  groups.forEach(g => {
    const opt = document.createElement('option');
    opt.value = g; opt.textContent = g.charAt(0).toUpperCase() + g.slice(1);
    sel.appendChild(opt);
  });
}

/* ── Scan Detail Modal ── */
function showScanDetail(scan) {
  document.getElementById('modal-title').textContent = `${scan.muscle_group?.toUpperCase()} — ${new Date(scan.scan_date).toLocaleDateString()}`;
  const items = [
    ['Volume', scan.volume_cm3 != null ? `${scan.volume_cm3.toFixed(2)} cm³` : '–'],
    ['Circumference', scan.circumference_cm != null ? `${scan.circumference_cm.toFixed(1)} cm` : '–'],
    ['Growth', scan.growth_pct != null ? `${scan.growth_pct > 0 ? '+' : ''}${scan.growth_pct.toFixed(1)}%` : '–'],
    ['Shape Score', scan.shape_score != null ? `${scan.shape_score.toFixed(0)}/100 (${scan.shape_grade})` : '–'],
    ['Definition Grade', scan.definition_grade ?? '–'],
    ['Definition Score', scan.definition_score != null ? `${scan.definition_score.toFixed(0)}/100` : '–'],
    ['Calibrated', scan.calibrated ? 'Yes' : 'No'],
  ];
  const downloadBtn = token && customerId
    ? `<button class="btn btn-primary" style="margin-top:14px;width:100%"
         onclick="downloadReport(${scan.id})">Download PDF Report</button>`
    : '';

  document.getElementById('modal-body').innerHTML = `
    <div class="detail-grid">
      ${items.map(([l, v]) => `<div class="detail-item"><div class="lbl">${l}</div><div class="val">${v}</div></div>`).join('')}
    </div>
    ${downloadBtn}`;
  openModal('scan-modal');
}

/* ── Download Report ── */
async function downloadReport(scanId) {
  if (!token || !customerId) return;
  try {
    const r = await fetch(`${API}/api/customer/${customerId}/session_report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ scan_id: scanId }),
    });
    if (!r.ok) { alert('Report generation failed'); return; }
    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `session_report_${scanId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(`Download failed: ${e.message}`);
  }
}

/* ── Upload Modal ── */
function showUploadModal() {
  alert('Upload via the Clinic View or Flutter app. Personal upload coming soon!');
}

/* ── Modal Helpers ── */
function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

/* ── API Helper ── */
async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetch(API + path, { headers, ...opts });
  return r.json();
}

/* ── Demo Mode (no login) ── */
function renderDemo() {
  const demo = [
    { muscle_group:'bicep', scan_date: new Date(Date.now()-2*86400000).toISOString(), volume_cm3:124.5, shape_score:72, shape_grade:'B', growth_pct:3.2, circumference_cm:38.1, calibrated:true },
    { muscle_group:'tricep', scan_date: new Date(Date.now()-5*86400000).toISOString(), volume_cm3:98.3, shape_score:65, shape_grade:'B', growth_pct:1.8, circumference_cm:32.4, calibrated:true },
    { muscle_group:'quadricep', scan_date: new Date(Date.now()-8*86400000).toISOString(), volume_cm3:680.2, shape_score:81, shape_grade:'A', growth_pct:4.5, circumference_cm:54.8, calibrated:true },
    { muscle_group:'bicep', scan_date: new Date(Date.now()-14*86400000).toISOString(), volume_cm3:120.6, shape_score:68, shape_grade:'B', growth_pct:null, circumference_cm:37.4, calibrated:true },
  ];
  document.getElementById('user-name').textContent = 'Demo Athlete';
  allScans = demo;
  renderScans(demo);
  renderStats(demo);
  renderBodyMap(demo);
  renderCharts(demo);
  populateMuscleSelect(demo);
  updateLastScan(demo);
}
