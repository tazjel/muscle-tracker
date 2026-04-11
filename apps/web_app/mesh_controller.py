"""3D mesh reconstruction and serving routes."""
from py4web import action, request, response, abort
from py4web.utils.cors import CORS
from .models import db
from .controllers import (
    _auth_check, _abs_path,
    ALLOWED_EXTENSIONS, cors,
)
import os
import logging

logger = logging.getLogger(__name__)


@action('api/customer/<customer_id:int>/reconstruct_3d', method=['POST'])
@action.uses(db, cors)
def reconstruct_3d(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    front_file = request.files.get('front')
    side_file  = request.files.get('side')
    if not front_file or not side_file:
        return dict(status='error', message='Both front and side images required')

    for f in (front_file, side_file):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return dict(status='error', message=f'Invalid file type: {ext}')

    muscle_group = request.forms.get('muscle_group', 'bicep')
    marker_size  = float(request.forms.get('marker_size', '20.0'))
    camera_distance_cm = float(request.forms.get('camera_distance_cm', '0') or '0') or None

    front_fn = db.muscle_scan.img_front.store(front_file.file, front_file.filename)
    side_fn  = db.muscle_scan.img_front.store(side_file.file, side_file.filename)
    front_path = os.path.join('uploads', front_fn)
    side_path  = os.path.join('uploads', side_fn)

    try:
        from core.vision_medical import analyze_muscle_growth
        from core.mesh_reconstruction import reconstruct_mesh_from_silhouettes, export_obj, export_glb, generate_mesh_preview_image
        from core.mesh_volume import compute_mesh_volume_cm3

        res_f = analyze_muscle_growth(front_path, front_path, marker_size, align=False, muscle_group=muscle_group, camera_distance_cm=camera_distance_cm)
        res_s = analyze_muscle_growth(side_path,  side_path,  marker_size, align=False, muscle_group=muscle_group, camera_distance_cm=camera_distance_cm)

        if 'error' in res_f or 'error' in res_s:
            return dict(status='error', message='Vision analysis failed on one or both images')

        contour_front = res_f.get('raw_data', {}).get('contour_a')
        contour_side  = res_s.get('raw_data', {}).get('contour_a')
        if contour_front is None or contour_side is None:
            return dict(status='error', message='Could not extract muscle contours')

        ratio_f = res_f.get('ratio', 1.0)
        ratio_s = res_s.get('ratio', 1.0)
        ppm_f   = 1.0 / ratio_f if ratio_f > 0 else 1.0
        ppm_s   = 1.0 / ratio_s if ratio_s > 0 else 1.0

        mesh_data = reconstruct_mesh_from_silhouettes(contour_front, contour_side, ppm_f, ppm_s)
        if not mesh_data or mesh_data.get('num_vertices', 0) == 0:
            return dict(status='error', message='3D reconstruction produced empty mesh')

        # Precise volume from mesh
        precise_vol = compute_mesh_volume_cm3(mesh_data['vertices'], mesh_data['faces'])
        if precise_vol > 0:
            mesh_data['volume_cm3'] = precise_vol

        # Save OBJ
        os.makedirs(_abs_path('meshes'), exist_ok=True)
        import time
        base_name  = f'mesh_{customer_id}_{int(time.time())}'
        obj_path   = _abs_path('meshes', base_name + '.obj')
        prev_path  = _abs_path('meshes', base_name + '_preview.png')

        export_obj(mesh_data['vertices'], mesh_data['faces'], obj_path)

        # GLB export (preferred format for 3D viewer)
        glb_path = _abs_path('meshes', base_name + '.glb')
        glb_url  = None
        try:
            export_glb(mesh_data['vertices'], mesh_data['faces'], glb_path)
            glb_url = f'/meshes/{base_name}.glb'
        except Exception:
            logger.warning('GLB export failed for mesh %s — OBJ fallback only', base_name)
            glb_path = None

        preview_url = None
        try:
            generate_mesh_preview_image(mesh_data['vertices'], mesh_data['faces'], prev_path)
            preview_url = f'/meshes/{base_name}_preview.png'
        except Exception:
            pass

        mesh_id = db.mesh_model.insert(
            customer_id=customer_id,
            muscle_group=muscle_group,
            obj_path=obj_path,
            glb_path=glb_path,
            preview_path=prev_path if preview_url else None,
            volume_cm3=mesh_data.get('volume_cm3'),
            num_vertices=mesh_data.get('num_vertices'),
            num_faces=mesh_data.get('num_faces'),
        )
        db.commit()

        return dict(
            status='success',
            mesh_id=mesh_id,
            mesh_url=glb_url or f'/meshes/{base_name}.obj',
            glb_url=glb_url,
            obj_url=f'/meshes/{base_name}.obj',
            preview_url=preview_url,
            volume_cm3=mesh_data.get('volume_cm3'),
            num_vertices=mesh_data.get('num_vertices'),
            num_faces=mesh_data.get('num_faces'),
        )
    except Exception:
        logger.exception('3D reconstruction failed for customer %d', customer_id)
        return dict(status='error', message='3D reconstruction failed')


@action('api/mesh/<mesh_id:int>.obj', method=['GET'])
@action.uses(db, cors)
def serve_mesh_obj(mesh_id):
    mesh = db.mesh_model(mesh_id)
    if not mesh or not mesh.obj_path or not os.path.exists(mesh.obj_path):
        abort(404, 'Mesh not found')
    response.headers['Content-Type'] = 'text/plain'
    with open(mesh.obj_path, 'r') as f:
        return f.read()


@action('api/mesh/<mesh_id:int>.glb', method=['GET'])
@action.uses(db, cors)
def serve_mesh_glb(mesh_id):
    """Serve the GLB binary for the 3D viewer (?model= param)."""
    try:
        mesh = db.mesh_model(mesh_id)
        if not mesh:
            return dict(status='error', message='Mesh not found')
        glb = mesh.glb_path
        if not glb:
            return dict(status='error', message='No GLB path for this mesh')
        # Resolve relative paths against project root (py4web CWD may differ)
        if not os.path.isabs(glb):
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            glb = os.path.join(project_root, glb)
        if not os.path.exists(glb):
            return dict(status='error', message=f'GLB not found: {glb}')
        response.headers['Content-Type']        = 'model/gltf-binary'
        response.headers['Content-Disposition'] = f'inline; filename="mesh_{mesh_id}.glb"'
        with open(glb, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.exception("serve_mesh_glb failed: %s", e)
        return dict(status='error', message=str(e))


@action('api/mesh/template.glb', method=['GET'])
@action.uses(cors)
def serve_template_glb():
    """Serve the MPFB2 template GLB (default body before any customisation)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'meshes', 'gtd3d_body_template.glb')
    if not os.path.exists(path):
        abort(404, 'Template mesh not generated yet')
    response.headers['Content-Type'] = 'model/gltf-binary'
    response.headers['Content-Disposition'] = 'inline; filename="gtd3d_body_template.glb"'
    with open(path, 'rb') as f:
        return f.read()


@action('api/customer/<customer_id:int>/meshes', method=['GET'])
@action.uses(db, cors)
def list_meshes(customer_id):
    """Return list of mesh models for a customer — used by viewer comparison dropdown."""
    rows = db(db.mesh_model.customer_id == customer_id).select(
        db.mesh_model.id,
        db.mesh_model.muscle_group,
        db.mesh_model.model_type,
        db.mesh_model.volume_cm3,
        db.mesh_model.created_on,
        orderby=~db.mesh_model.id
    )
    return dict(
        status='success',
        meshes=[dict(
            id=int(r.id),
            muscle_group=r.muscle_group or 'body',
            model_type=r.model_type or 'body',
            volume_cm3=round(float(r.volume_cm3), 1) if r.volume_cm3 else None,
            created_on=str(r.created_on)[:16] if r.created_on else '',
        ) for r in rows]
    )


@action('api/customer/<customer_id:int>/compare_3d', method=['POST'])
@action.uses(db, cors)
def compare_3d(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    data = request.json or {}
    before_id = data.get('mesh_id_before')
    after_id  = data.get('mesh_id_after')
    if not before_id or not after_id:
        return dict(status='error', message='mesh_id_before and mesh_id_after required')

    mesh_before = db.mesh_model(before_id)
    mesh_after  = db.mesh_model(after_id)
    if not mesh_before or not mesh_after:
        return dict(status='error', message='One or both meshes not found')
    if mesh_before.customer_id != customer_id or mesh_after.customer_id != customer_id:
        return dict(status='error', message='Access denied')

    try:
        from core.mesh_reconstruction import export_obj
        from core.mesh_comparison import compare_meshes, export_colored_obj
        import numpy as np

        def _load_obj_verts_faces(path):
            verts, faces = [], []
            with open(path) as f:
                for line in f:
                    parts = line.split()
                    if not parts:
                        continue
                    if parts[0] == 'v':
                        verts.append([float(x) for x in parts[1:4]])
                    elif parts[0] == 'f':
                        faces.append([int(x) - 1 for x in parts[1:4]])
            return np.array(verts), np.array(faces)

        vb, fb = _load_obj_verts_faces(mesh_before.obj_path)
        va, fa = _load_obj_verts_faces(mesh_after.obj_path)

        result = compare_meshes(
            {'vertices': vb, 'faces': fb, 'volume_cm3': mesh_before.volume_cm3},
            {'vertices': va, 'faces': fa, 'volume_cm3': mesh_after.volume_cm3},
        )

        import time
        colored_name = f'compare_{customer_id}_{int(time.time())}.obj'
        colored_path = os.path.join('meshes', colored_name)
        export_colored_obj(va, fa, result['displacement_map'], colored_path)

        return dict(
            status='success',
            mean_growth_mm=round(result['mean_growth_mm'], 3),
            max_growth_mm=round(result['max_growth_mm'], 3),
            volume_change_cm3=round(result['volume_change_cm3'], 3),
            colored_mesh_url=f'/meshes/{colored_name}',
        )
    except Exception:
        logger.exception('3D comparison failed for customer %d', customer_id)
        return dict(status='error', message='3D comparison failed')


@action('api/customer/<customer_id:int>/compare_meshes', method=['POST'])
@action.uses(db, cors)
def compare_meshes_heatmap(customer_id):
    """Return per-vertex heatmap values for growth visualization in the 3D viewer."""
    payload, err = _auth_check()
    if err: return err

    data = request.json or {}
    mesh_id_old = int(data.get('mesh_id_old', 0))
    mesh_id_new = int(data.get('mesh_id_new', 0))
    if not mesh_id_old or not mesh_id_new:
        return dict(status='error', message='mesh_id_old and mesh_id_new required')

    old_row = db.mesh_model[mesh_id_old]
    new_row = db.mesh_model[mesh_id_new]
    if not old_row or not new_row:
        return dict(status='error', message='Mesh not found')
    if old_row.customer_id != customer_id or new_row.customer_id != customer_id:
        return dict(status='error', message='Access denied')
    if not old_row.glb_path or not new_row.glb_path:
        return dict(status='error', message='GLB path missing for one or both meshes')

    try:
        import numpy as np
        import struct as _struct
        import pygltflib as _pygltflib

        # Resolve relative paths (meshes/ lives at project root, two dirs above __file__)
        _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        def _abs(p):
            p = p.replace('\\', '/')
            return p if os.path.isabs(p) else os.path.join(_root, p)

        def _load_verts(path):
            try:
                gltf = _pygltflib.GLTF2().load(path)
                acc = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
                bv  = gltf.bufferViews[acc.bufferView]
                blob = gltf.binary_blob()
                data = blob[bv.byteOffset: bv.byteOffset + bv.byteLength]
                v = np.array(_struct.unpack(f'<{acc.count * 3}f', data)).reshape(acc.count, 3)
                return v.astype(np.float32)
            except Exception:
                return None

        verts_old = _load_verts(_abs(old_row.glb_path))
        verts_new = _load_verts(_abs(new_row.glb_path))
        if verts_old is None or verts_new is None:
            return dict(status='error', message='Could not load mesh vertices from GLB')

        if len(verts_old) == len(verts_new):
            disp = np.linalg.norm(verts_new - verts_old, axis=1)
        else:
            # Different vertex counts — nearest-vertex match
            from scipy.spatial import cKDTree
            tree = cKDTree(verts_old)
            _, idx = tree.query(verts_new)
            disp = np.linalg.norm(verts_new - verts_old[idx], axis=1)

        # Normalize to [0, 1] using 95th-percentile cap to avoid outliers dominating
        cap = float(np.percentile(disp, 95)) or 1.0
        heatmap = np.clip(disp / cap, 0.0, 1.0)

        return dict(
            status='success',
            heatmap_values=heatmap.tolist(),
            displacements_mm=disp.tolist(),
            max_displacement_mm=round(float(disp.max()), 2),
            mean_displacement_mm=round(float(disp.mean()), 2),
            num_vertices=int(len(heatmap)),
        )
    except Exception:
        logger.exception('compare_meshes_heatmap failed for customer %d', customer_id)
        return dict(status='error', message='Mesh comparison failed')
