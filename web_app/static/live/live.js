/* ── Config ── */
const API          = '';        // same-origin; set full URL for dev
const ANALYZE_FPS  = 2;         // frames per second to send for analysis
const MIN_INTERVAL = 1000 / ANALYZE_FPS;

/* ── State ── */
let stream       = null;
let facingMode   = 'environment';  // rear camera first
let analyzing    = false;
let paused       = false;
let intervalId   = null;
let lastResult   = null;

const video          = document.getElementById('video');
const overlay        = document.getElementById('overlay-canvas');
const captureCanvas  = document.getElementById('capture-canvas');
const lockedCanvas   = document.getElementById('locked-canvas');
const ctx            = overlay.getContext('2d');
const captureCtx     = captureCanvas.getContext('2d');

/* ── Camera ── */
async function startCamera() {
  document.getElementById('btn-start').classList.add('hidden');
  setStatus('Requesting camera…');

  try {
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode, width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();

    resizeOverlay();
    window.addEventListener('resize', resizeOverlay);

    document.getElementById('btn-pause').classList.remove('hidden');
    document.getElementById('btn-lock').classList.remove('hidden');
    setStatus('Live — analyzing…');
    startAnalysis();
  } catch (err) {
    setStatus(`Camera error: ${err.message}`);
    document.getElementById('btn-start').classList.remove('hidden');
  }
}

function flipCamera() {
  facingMode = facingMode === 'environment' ? 'user' : 'environment';
  if (stream) startCamera();
}

function resizeOverlay() {
  const rect = video.getBoundingClientRect();
  overlay.width  = rect.width;
  overlay.height = rect.height;
}

/* ── Analysis loop ── */
function startAnalysis() {
  if (intervalId) clearInterval(intervalId);
  intervalId = setInterval(analyzeFrame, MIN_INTERVAL);
}

async function analyzeFrame() {
  if (paused || analyzing || video.readyState < 2) return;
  if (video.videoWidth === 0) return;

  analyzing = true;
  showScanning(true);

  // Capture current frame
  captureCanvas.width  = video.videoWidth;
  captureCanvas.height = video.videoHeight;
  captureCtx.drawImage(video, 0, 0);

  const muscleGroup = document.getElementById('muscle-select').value;

  try {
    // Convert to base64 JPEG (low quality for speed)
    const b64 = captureCanvas.toDataURL('image/jpeg', 0.6).split(',')[1];

    const resp = await fetch(`${API}/api/live_analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frame_base64: b64, muscle_group: muscleGroup }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.status === 'success') {
      lastResult = data;
      updateMetrics(data);
      drawContour(data.contour_points);
      setStatus(`Live — ${muscleGroup} detected`);
    } else {
      clearContour();
      setStatus('No muscle detected — adjust angle');
    }
  } catch (err) {
    // Network/API error — don't spam
    setStatus(`Analysis paused: ${err.message}`);
  } finally {
    analyzing = false;
    showScanning(false);
  }
}

/* ── UI Updates ── */
function updateMetrics(data) {
  const cirBadge = document.getElementById('badge-circ');
  const wBadge   = document.getElementById('badge-width');
  const aBadge   = document.getElementById('badge-area');

  if (data.circumference_cm != null) {
    document.getElementById('val-circ').textContent = `${data.circumference_cm} cm`;
    cirBadge.classList.add('live');
  }
  if (data.width != null) {
    const unit = data.calibrated ? 'mm' : 'px';
    document.getElementById('val-width').textContent = `${data.width?.toFixed(1)} ${unit}`;
    wBadge.classList.add('live');
  }
  if (data.area != null) {
    const unit = data.calibrated ? 'mm²' : 'px²';
    document.getElementById('val-area').textContent = `${data.area?.toFixed(0)} ${unit}`;
    aBadge.classList.add('live');
  }
}

function drawContour(points) {
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  if (!points || points.length < 3) return;

  const scaleX = overlay.width  / video.videoWidth;
  const scaleY = overlay.height / video.videoHeight;

  ctx.beginPath();
  ctx.moveTo(points[0][0] * scaleX, points[0][1] * scaleY);
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i][0] * scaleX, points[i][1] * scaleY);
  }
  ctx.closePath();
  ctx.strokeStyle = '#00b4cc';
  ctx.lineWidth   = 2;
  ctx.stroke();
  ctx.fillStyle   = 'rgba(0,180,204,0.08)';
  ctx.fill();
}

function clearContour() {
  ctx.clearRect(0, 0, overlay.width, overlay.height);
}

function setStatus(msg) {
  document.getElementById('status-label').textContent = msg;
}

function showScanning(on) {
  document.getElementById('scan-indicator').classList.toggle('hidden', !on);
}

/* ── Controls ── */
function togglePause() {
  paused = !paused;
  document.getElementById('btn-pause').textContent = paused ? 'Resume' : 'Pause';
  if (paused) {
    clearContour();
    setStatus('Paused');
  } else {
    setStatus('Live — analyzing…');
  }
}

function lockAndSave() {
  if (!lastResult) {
    alert('No analysis result yet — wait for a muscle to be detected.');
    return;
  }

  // Copy current frame to locked canvas
  lockedCanvas.width  = captureCanvas.width;
  lockedCanvas.height = captureCanvas.height;
  lockedCanvas.getContext('2d').drawImage(captureCanvas, 0, 0);

  // Redraw contour on locked canvas
  const lCtx   = lockedCanvas.getContext('2d');
  const points = lastResult.contour_points || [];
  if (points.length >= 3) {
    lCtx.beginPath();
    lCtx.moveTo(points[0][0], points[0][1]);
    for (let i = 1; i < points.length; i++) lCtx.lineTo(points[i][0], points[i][1]);
    lCtx.closePath();
    lCtx.strokeStyle = '#00b4cc';
    lCtx.lineWidth   = 3;
    lCtx.stroke();
  }

  // Populate metrics
  const r    = lastResult;
  const unit = r.calibrated ? 'mm' : 'px';
  const rows = [
    ['Circumference', r.circumference_cm != null ? `${r.circumference_cm} cm` : '–'],
    ['Width',         r.width   != null ? `${r.width?.toFixed(1)} ${unit}`   : '–'],
    ['Height',        r.height  != null ? `${r.height?.toFixed(1)} ${unit}`  : '–'],
    ['Area',          r.area    != null ? `${r.area?.toFixed(0)} ${unit}²`   : '–'],
    ['Calibrated',    r.calibrated ? 'Yes' : 'No'],
  ];
  document.getElementById('locked-metrics').innerHTML = rows.map(([l, v]) => `
    <div class="locked-metric">
      <div class="lbl">${l}</div>
      <div class="val">${v}</div>
    </div>`).join('');

  document.getElementById('locked-panel').classList.remove('hidden');
  paused = true;
  document.getElementById('btn-pause').textContent = 'Resume';
  setStatus('Frame locked');
}

function downloadLocked() {
  const link  = document.createElement('a');
  link.href   = lockedCanvas.toDataURL('image/png');
  link.download = `muscle_scan_${Date.now()}.png`;
  link.click();
}

function dismissLocked() {
  document.getElementById('locked-panel').classList.add('hidden');
  paused = false;
  document.getElementById('btn-pause').textContent = 'Pause';
  setStatus('Live — analyzing…');
}

/* ── Init ── */
// Auto-start if browser supports getUserMedia
if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
  document.getElementById('btn-start').textContent = 'Start Camera';
} else {
  setStatus('Camera not supported in this browser');
  document.getElementById('btn-start').disabled = true;
}
