import numpy as np
from scipy.spatial import KDTree

def compare_meshes(mesh_before, mesh_after):
    vb = mesh_before.get('vertices')
    va = mesh_after.get('vertices')
    if vb is None or va is None: return {}
    tree = KDTree(vb)
    distances, indices = tree.query(va)
    cb = np.mean(vb, axis=0)
    sd = []
    for i, v in enumerate(va):
        d = distances[i]
        v_a = v - cb
        v_b = vb[indices[i]] - cb
        if np.linalg.norm(v_a) >= np.linalg.norm(v_b):
            sd.append(d)
        else:
            sd.append(-d)
    disp_map = np.array(sd)
    return {
        'displacement_map': disp_map,
        'mean_growth_mm': float(np.mean(disp_map)),
        'max_growth_mm': float(np.max(disp_map)),
        'volume_change_cm3': mesh_after.get('volume_cm3', 0) - mesh_before.get('volume_cm3', 0)
    }

def export_colored_obj(vertices, faces, displacement_map, output_path):
    max_d = np.max(np.abs(displacement_map)) if len(displacement_map) > 0 else 1
    with open(output_path, 'w') as f:
        for i, v in enumerate(vertices):
            d = displacement_map[i] if i < len(displacement_map) else 0
            if d > 0:
                r, g, b = 0, d/max_d, 0
            else:
                r, g, b = abs(d)/max_d, 0, 0
            f.write('v {} {} {} {} {} {}\n'.format(v[0], v[1], v[2], r, g, b))
        for face in faces:
            f.write('f {} {} {}\n'.format(face[0]+1, face[1]+1, face[2]+1))
