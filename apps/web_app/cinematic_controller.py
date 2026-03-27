from py4web import action, request, response, URL
from .models import db
from .controllers import _auth_check
import os
import logging
import base64
from core.cloud_gpu import cloud_train_splat, cloud_anchor_splat

logger = logging.getLogger(__name__)

# --- CINEMATIC SCAN PIPELINE ---

@action('api/cinematic_status', method=['GET'])
def cinematic_status():
    """Verify that the Cinematic Controller is loaded and healthy."""
    return dict(status='success', module='cinematic_controller', version='6.0-beta')


@action('api/customer/<customer_id:int>/cinematic_scan', method=['POST'])
@action.uses(db)
def cinematic_scan(customer_id):
    """
    Trigger a 3D Gaussian Splat (3DGS) training job from a video session.
    Delegates to RunPod Serverless (Action: train_splat).
    """
    payload, err = _auth_check(customer_id)
    if err: return err

    session_id = request.json.get('session_id')
    session = db.video_scan_session(session_id)
    if not session or session.customer_id != customer_id:
        return dict(status='error', message='Video session not found')

    if not os.path.exists(session.video_path):
        return dict(status='error', message='Video file missing on server')

    try:
        # 1. Read video bytes
        with open(session.video_path, 'rb') as f:
            video_bytes = f.read()

        # 2. Delegate to RunPod
        logger.info(f"Triggering RunPod 3DGS training for session {session_id}...")
        splat_url = cloud_train_splat(video_bytes)

        if splat_url:
            # 3. Update session status
            session.update_record(status='SPLAT_READY', splat_url=splat_url)
            db.commit()
            return dict(status='success', splat_url=splat_url)
        else:
            return dict(status='error', message='RunPod training failed')

    except Exception as e:
        logger.exception("Cinematic scan failed")
        return dict(status='error', message=str(e))


@action('api/customer/<customer_id:int>/anchor_splat', method=['POST'])
@action.uses(db)
def anchor_splat(customer_id):
    """
    Bind a trained Gaussian Splat to the latest MPFB2 mesh vertices.
    Delegates to RunPod (Action: anchor_splat).
    """
    payload, err = _auth_check(customer_id)
    if err: return err

    session_id = request.json.get('session_id')
    mesh_id = request.json.get('mesh_id')

    session = db.video_scan_session(session_id)
    mesh = db.mesh_model(mesh_id)

    if not session or not mesh:
        return dict(status='error', message='Session or Mesh not found')

    try:
        # 1. Load mesh vertices from real GLB
        from core.mesh_reconstruction import load_glb_vertices
        if not mesh.glb_path or not os.path.exists(mesh.glb_path):
            return dict(status='error', message='GLB file missing')

        verts = load_glb_vertices(mesh.glb_path)
        if verts is None:
            return dict(status='error', message='Failed to load vertices')

        # 2. Delegate to RunPod for alignment
        logger.info(f"Anchoring Splat {session.splat_url} to Mesh {mesh_id} ({len(verts)} verts)...")
        result = cloud_anchor_splat(session.splat_url, verts)

        if result:
            return dict(status='success', anchors=result.get('anchors_count'))
        else:
            return dict(status='error', message='Anchoring failed')

    except Exception as e:
        logger.exception("Splat anchoring failed")
        return dict(status='error', message=str(e))


@action('api/customer/<customer_id:int>/bake_cinematic', method=['POST'])
@action.uses(db)
def bake_cinematic(customer_id):
    """
    Bake photorealistic details from anchored Splat into PBR textures.
    Delegates to RunPod (Action: bake_cinematic).
    """
    payload, err = _auth_check(customer_id)
    if err: return err

    session_id = request.json.get('session_id')
    mesh_id = request.json.get('mesh_id')

    session = db.video_scan_session(session_id)
    mesh = db.mesh_model(mesh_id)

    if not session or not mesh:
        return dict(status='error', message='Session or Mesh not found')

    try:
        from core.mesh_reconstruction import load_glb_vertices
        from core.cloud_gpu import cloud_bake_cinematic
        import numpy as np

        # 1. Prepare geometry data
        verts = load_glb_vertices(mesh.glb_path)
        faces = np.load('meshes/template_faces.npy') # MPFB2 constant
        uvs = np.load('meshes/template_uvs.npy')     # MPFB2 constant

        # 2. Delegate to RunPod for baking
        logger.info(f"Baking Cinematic textures for Mesh {mesh_id}...")
        textures = cloud_bake_cinematic(verts, faces, uvs, session.splat_url)

        if textures:
            # 3. Save baked textures and update GLB
            # (Logic to update GLB with new maps would go here)
            return dict(status='success', textures=list(textures.keys()))
        else:
            return dict(status='error', message='Baking failed')

    except Exception as e:
        logger.exception("Cinematic bake failed")
        return dict(status='error', message=str(e))

