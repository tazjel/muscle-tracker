"""LHM++ avatar generation API routes.

POST  api/lhm/submit  — upload photos, enqueue RunPod job, return job_id
GET   api/lhm/status/<job_id>  — poll job progress; on completion serve GLB URL
"""
from py4web import action, request, response
from .models import db
from .controllers import cors, _auth_check, _abs_path, PROJECT_ROOT
import os
import sys
import uuid
import base64
import logging
import json
import threading
import time

logger = logging.getLogger(__name__)

# ── In-memory job store (reset on server restart) ────────────────────────────
# Structure: {job_id: {status, runpod_job_id, result_url, error, started_at, customer_id}}
_lhm_jobs = {}

# Upload sub-directory inside the project uploads/ folder
_UPLOAD_DIR = _abs_path('uploads', 'lhm_jobs')
os.makedirs(_UPLOAD_DIR, exist_ok=True)


def _make_runpod_headers():
    """Build RunPod auth headers using env vars loaded by cloud_gpu."""
    from core.cloud_gpu import RUNPOD_API_KEY
    return {
        'Authorization': f'Bearer {RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }


def _submit_to_runpod(job_id, frames_data, profile):
    """Background thread: submit frames to RunPod and update _lhm_jobs on completion."""
    try:
        import urllib.request as _ureq
        from core.cloud_gpu import (
            RUNPOD_BASE_URL, RUNPOD_ENDPOINT, RUNPOD_API_KEY,
            _poll_result_raw, is_configured,
        )

        if not is_configured():
            _lhm_jobs[job_id].update({
                'status': 'failed',
                'error': 'RunPod not configured (missing RUNPOD_API_KEY / RUNPOD_ENDPOINT)',
            })
            return

        payload = {
            'input': {
                'action': 'live_scan_bake',
                'frames': frames_data,
                'profile': profile,
            }
        }
        headers = _make_runpod_headers()
        data = json.dumps(payload).encode('utf-8')
        url = f"{RUNPOD_BASE_URL}/{RUNPOD_ENDPOINT}/run"

        logger.info('LHM submit: posting %d frames to RunPod async', len(frames_data))
        req = _ureq.Request(url, data=data, headers=headers, method='POST')
        with _ureq.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        runpod_job_id = result.get('id')
        if not runpod_job_id:
            _lhm_jobs[job_id].update({'status': 'failed', 'error': f'No job ID: {result}'})
            return

        _lhm_jobs[job_id]['runpod_job_id'] = runpod_job_id
        _lhm_jobs[job_id]['status'] = 'processing'
        logger.info('LHM job %s → RunPod ID %s', job_id, runpod_job_id)

        # Poll RunPod until done (uses existing helper from cloud_gpu)
        output = _poll_result_raw(runpod_job_id, headers)
        if output is None:
            _lhm_jobs[job_id].update({'status': 'failed', 'error': 'RunPod job timed out or failed'})
            return

        if output.get('status') != 'success':
            _lhm_jobs[job_id].update({
                'status': 'failed',
                'error': output.get('message', 'Unknown RunPod error'),
            })
            return

        # Save the GLB returned as base64 to uploads/lhm_jobs/<job_id>.glb
        glb_b64 = output.get('glb_b64', '')
        if not glb_b64:
            _lhm_jobs[job_id].update({'status': 'failed', 'error': 'No GLB in RunPod output'})
            return

        glb_path = os.path.join(_UPLOAD_DIR, f'{job_id}.glb')
        with open(glb_path, 'wb') as f:
            f.write(base64.b64decode(glb_b64))
        logger.info('LHM job %s: GLB saved (%d KB)', job_id, os.path.getsize(glb_path) // 1024)

        _lhm_jobs[job_id].update({
            'status': 'completed',
            'glb_filename': f'{job_id}.glb',
            'vertex_count': output.get('vertex_count', 0),
            'face_count': output.get('face_count', 0),
            'lhm_used': output.get('lhm_used', False),
            'profile_metadata': output.get('profile_metadata', {}),
        })

    except Exception as exc:
        logger.exception('LHM background submit failed for job %s', job_id)
        _lhm_jobs[job_id].update({'status': 'failed', 'error': str(exc)})


# ── Routes ────────────────────────────────────────────────────────────────────

@action('api/lhm/submit', method=['POST'])
@action.uses(db, cors)
def lhm_submit():
    """Accept photos + profile, submit async LHM++ job to RunPod.

    Form fields:
        customer_id   (int, optional)
        height_cm     (float, optional)
        weight_kg     (float, optional)
        gender        (string, optional: male/female)
        photo_front   (file, optional)
        photo_side    (file, optional)
        photo_back    (file, optional)
        photo         (file, optional — single-photo mode)

    Returns:
        {status: 'submitted', job_id: '...'}
    """
    payload, err = _auth_check()
    if err:
        return err

    job_id = str(uuid.uuid4())[:16]

    # Collect profile params from form
    profile = {}
    for field in ('height_cm', 'weight_kg', 'gender'):
        val = request.forms.get(field)
        if val:
            try:
                profile[field] = float(val) if field != 'gender' else val
            except ValueError:
                pass

    customer_id = request.forms.get('customer_id')
    if customer_id:
        try:
            customer_id = int(customer_id)
        except ValueError:
            customer_id = None

    # Encode uploaded images as base64 frames for RunPod
    frames_data = []
    for slot in ('photo_front', 'photo_side', 'photo_back', 'photo'):
        img_file = request.files.get(slot)
        if img_file:
            img_bytes = img_file.file.read()
            img_b64 = base64.b64encode(img_bytes).decode('ascii')
            region = slot.replace('photo_', '').replace('photo', 'front')
            frames_data.append({
                'image_b64': img_b64,
                'region': region,
                'sharpness': 1.0,
            })

    if not frames_data:
        response.status = 400
        return dict(status='error', message='At least one photo is required (photo_front, photo_side, photo_back, or photo)')

    # Register job in memory
    _lhm_jobs[job_id] = {
        'status': 'pending',
        'runpod_job_id': None,
        'glb_filename': None,
        'error': None,
        'started_at': time.time(),
        'customer_id': customer_id,
        'frame_count': len(frames_data),
    }

    # Fire background thread — don't block the HTTP response
    t = threading.Thread(
        target=_submit_to_runpod,
        args=(job_id, frames_data, profile),
        daemon=True,
    )
    t.start()

    logger.info('LHM job %s queued (%d frames)', job_id, len(frames_data))
    return dict(status='submitted', job_id=job_id, frame_count=len(frames_data))


@action('api/lhm/status/<job_id>', method=['GET'])
@action.uses(cors)
def lhm_status(job_id):
    """Poll LHM++ job status.

    Returns:
        {status: 'pending'|'processing'|'completed'|'failed',
         result_url: '/web_app/uploads/lhm_jobs/<job_id>.glb',  # when completed
         error: '...',  # when failed
         elapsed: seconds,
         vertex_count: int,
         ...}
    """
    payload, err = _auth_check()
    if err:
        return err

    job = _lhm_jobs.get(job_id)
    if not job:
        response.status = 404
        return dict(status='error', message=f'Job {job_id} not found')

    elapsed = round(time.time() - job['started_at'], 1)
    out = {
        'status': job['status'],
        'elapsed': elapsed,
        'frame_count': job.get('frame_count', 0),
        'runpod_job_id': job.get('runpod_job_id'),
    }

    if job['status'] == 'completed':
        glb_fn = job['glb_filename']
        # Serve via the existing uploads/ static route in controllers.py
        out['result_url'] = f'/web_app/uploads/lhm_jobs/{glb_fn}'
        out['vertex_count'] = job.get('vertex_count', 0)
        out['face_count'] = job.get('face_count', 0)
        out['lhm_used'] = job.get('lhm_used', False)
        out['profile_metadata'] = job.get('profile_metadata', {})

    elif job['status'] == 'failed':
        out['error'] = job.get('error', 'Unknown error')

    return out
