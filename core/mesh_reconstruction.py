import numpy as np
import cv2
import math
import struct

def reconstruct_mesh_from_silhouettes(contour_front, contour_side, pixels_per_mm_front, pixels_per_mm_side, num_slices=40):
    if contour_front is None or contour_side is None: return {}
    
    xf, yf, wf, hf = cv2.boundingRect(contour_front)
    xs, ys, ws, hs = cv2.boundingRect(contour_side)
    
    y_min = min(yf, ys)
    y_max = max(yf + hf, ys + hs)
    total_h = y_max - y_min
    
    mask_f = np.zeros((y_max + 1, xf + wf + 1), dtype=np.uint8)
    cv2.fillPoly(mask_f, [contour_front], 255)
    mask_s = np.zeros((y_max + 1, xs + ws + 1), dtype=np.uint8)
    cv2.fillPoly(mask_s, [contour_side], 255)
    
    vertices = []
    faces = []

    slice_h = total_h / num_slices
    segments = 16 

    for i in range(num_slices + 1):
        curr_y = int(y_min + i * slice_h)
        if curr_y >= mask_f.shape[0] or curr_y >= mask_s.shape[0]:
            width_mm, depth_mm = 0, 0
        else:
            row_f = mask_f[curr_y, :]
            cols_f = np.where(row_f > 0)[0]
            width_mm = (cols_f[-1] - cols_f[0]) / pixels_per_mm_front if len(cols_f) >= 2 else 0

            row_s = mask_s[curr_y, :]
            cols_s = np.where(row_s > 0)[0]
            depth_mm = (cols_s[-1] - cols_s[0]) / pixels_per_mm_side if len(cols_s) >= 2 else 0

        a = width_mm / 2
        b = depth_mm / 2
        z = (curr_y - y_min) / ((pixels_per_mm_front + pixels_per_mm_side)/2)

        for s in range(segments):
            angle = 2 * math.pi * s / segments
            vx = a * math.cos(angle)
            vy = b * math.sin(angle)
            vertices.append([vx, vy, z])

        if i > 0:
            off = (i - 1) * segments
            curr = i * segments
            for s in range(segments):
                s_next = (s + 1) % segments
                faces.append([off + s, curr + s, off + s_next])
                faces.append([off + s_next, curr + s, curr + s_next])

    verts_np = np.array(vertices)
    faces_np = np.array(faces)

    vol_mm3 = 0
    for i in range(num_slices):
        curr_y = int(y_min + i * slice_h)
        if curr_y >= mask_f.shape[0] or curr_y >= mask_s.shape[0]: continue
        row_f = mask_f[curr_y, :]
        cols_f = np.where(row_f > 0)[0]
        w = (cols_f[-1] - cols_f[0]) / pixels_per_mm_front if len(cols_f) >= 2 else 0
        row_s = mask_s[curr_y, :]
        cols_s = np.where(row_s > 0)[0]
        d = (cols_s[-1] - cols_s[0]) / pixels_per_mm_side if len(cols_s) >= 2 else 0
        area = math.pi * (w/2) * (d/2)
        vol_mm3 += area * (slice_h / ((pixels_per_mm_front + pixels_per_mm_side)/2))

    return {
        'vertices': verts_np,
        'faces': faces_np,
        'volume_cm3': round(vol_mm3 / 1000.0, 2),
        'num_vertices': len(vertices),
        'num_faces': len(faces)
    }

def export_obj(vertices, faces, output_path):
    with open(output_path, 'w') as f:
        for v in vertices:
            f.write('v {} {} {}\n'.format(v[0], v[1], v[2]))
        for face in faces:
            f.write('f {} {} {}\n'.format(face[0]+1, face[1]+1, face[2]+1))

def export_stl(vertices, faces, output_path):
    # Binary STL format
    with open(output_path, 'wb') as f:
        f.write(b'\0' * 80) # Header
        f.write(struct.pack('<I', len(faces))) # Number of triangles
        for face in faces:
            # Normal (0,0,0) - not strictly required by many viewers
            f.write(struct.pack('<fff', 0, 0, 0))
            for v_idx in face:
                v = vertices[v_idx]
                f.write(struct.pack('<fff', v[0], v[1], v[2]))
            f.write(struct.pack('<H', 0)) # Attribute byte count

def generate_mesh_preview_image(vertices, faces, output_path):
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_trisurf(vertices[:, 0], vertices[:, 1], vertices[:, 2], triangles=faces, cmap='viridis')
    plt.savefig(output_path)
    plt.close()
    return output_path
