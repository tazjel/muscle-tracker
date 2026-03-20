import numpy as np

def compare_meshes(mesh_before, mesh_after):
    if mesh_before is None or mesh_after is None:
        return {}

    v_before = mesh_before.get('vertices', np.array([]))
    v_after = mesh_after.get('vertices', np.array([]))
    
    if len(v_before) == 0 or len(v_after) == 0:
        return {'displacement_map': np.array([]), 'mean_growth_mm': 0, 'volume_change_cm3': 0}

    displacements = []
    center = np.mean(v_after, axis=0)
    
    for va in v_after:
        dists = np.linalg.norm(v_before - va, axis=1)
        nearest_idx = np.argmin(dists)
        nearest_v = v_before[nearest_idx]
        
        dist = dists[nearest_idx]
        
        vec_va = va - center
        vec_v_nearest = nearest_v - center
        
        if np.linalg.norm(vec_va) < np.linalg.norm(vec_v_nearest):
            dist = -dist
            
        displacements.append(dist)
        
    displacements = np.array(displacements)
    mean_growth = np.mean(displacements)
    max_growth = np.max(displacements)
    
    vol_before = mesh_before.get('volume_cm3', 0.0)
    vol_after = mesh_after.get('volume_cm3', 0.0)
    vol_change = vol_after - vol_before

    return {
        'displacement_map': displacements,
        'mean_growth_mm': round(float(mean_growth), 3),
        'max_growth_mm': round(float(max_growth), 3),
        'volume_change_cm3': round(float(vol_change), 2),
        'growth_zones': []
    }

def export_colored_obj(vertices, faces, displacement_map, output_path):
    if vertices is None or faces is None:
        return
    with open(output_path, 'w') as f:
        for i, v in enumerate(vertices):
            d = displacement_map[i] if i < len(displacement_map) else 0
            if d > 0: r, g, b = 0, min(255, int(d * 10)), 0
            else: r, g, b = min(255, int(abs(d) * 10)), 0, 0
            f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f} {r/255.0:.3f} {g/255.0:.3f} {b/255.0:.3f}\n")
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
