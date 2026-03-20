import numpy as np
import cv2
import struct

def reconstruct_mesh_from_silhouettes(contour_front, contour_side,
                                      pixels_per_mm_front, pixels_per_mm_side,
                                      num_slices=40):
    if contour_front is None or contour_side is None:
        return {'vertices': np.array([]), 'faces': np.array([]), 'num_vertices': 0, 'num_faces': 0, 'volume_cm3': 0}

    # 1. Bounding rects and height normalization
    xf, yf, wf, hf = cv2.boundingRect(contour_front)
    xs, ys, ws, hs = cv2.boundingRect(contour_side)

    # Use the max height for both
    h_max_px = max(hf, hs)
    
    # 2. Slice processing
    vertices = []
    points_per_slice = 16

    # Prepare lookup
    def get_dim_at_y(contour, target_y, px_per_mm):
        pts = contour.reshape(-1, 2)
        y_vals = pts[:, 1]
        mask = (y_vals >= target_y - 2) & (y_vals <= target_y + 2)
        if not np.any(mask):
            return 0.0
        x_vals = pts[mask, 0]
        width_px = np.max(x_vals) - np.min(x_vals)
        return float(width_px) / px_per_mm

    for i in range(num_slices + 1):
        z = (i / num_slices) * h_max_px
        yf_target = yf + (i / num_slices) * hf
        ys_target = ys + (i / num_slices) * hs

        width_mm = get_dim_at_y(contour_front, yf_target, pixels_per_mm_front)
        depth_mm = get_dim_at_y(contour_side, ys_target, pixels_per_mm_side)

        h_mm = -z / ((pixels_per_mm_front + pixels_per_mm_side)/2.0)

        for j in range(points_per_slice):
            angle = 2 * np.pi * j / points_per_slice
            x = (width_mm / 2.0) * np.cos(angle)
            y = (depth_mm / 2.0) * np.sin(angle)
            vertices.append([x, y, h_mm])

    vertices = np.array(vertices, dtype=np.float32)

    # 3. Connectivity (faces)
    faces = []
    for i in range(num_slices):
        for j in range(points_per_slice):
            v1 = i * points_per_slice + j
            v2 = i * points_per_slice + (j + 1) % points_per_slice
            v3 = (i + 1) * points_per_slice + j
            v4 = (i + 1) * points_per_slice + (j + 1) % points_per_slice
            faces.append([v1, v2, v4])
            faces.append([v1, v4, v3])

    # 4. Caps
    top_center_idx = len(vertices)
    vertices = np.vstack([vertices, [0.0, 0.0, vertices[0, 2]]])
    for j in range(points_per_slice):
        v1, v2 = j, (j + 1) % points_per_slice
        faces.append([top_center_idx, v2, v1])

    bottom_center_idx = len(vertices)
    vertices = np.vstack([vertices, [0.0, 0.0, vertices[-2, 2]]])
    start_idx = num_slices * points_per_slice
    for j in range(points_per_slice):
        v1, v2 = start_idx + j, start_idx + (j + 1) % points_per_slice
        faces.append([bottom_center_idx, v1, v2])

    faces = np.array(faces, dtype=np.int32)
    vertices = vertices.astype(np.float32) # Ensure all floats

    # 5. Volume
    vol_mm3 = 0.0
    for f in faces:
        v1, v2, v3 = vertices[f[0]], vertices[f[1]], vertices[f[2]]
        vol_mm3 += np.dot(v1, np.cross(v2, v3))
    volume_cm3 = abs(vol_mm3) / 6.0 / 1000.0

    return {
        'vertices': vertices, 'faces': faces,
        'volume_cm3': round(float(volume_cm3), 2),
        'num_vertices': len(vertices), 'num_faces': len(faces)
    }

def export_obj(vertices, faces, output_path, normals=None):
    with open(output_path, 'w') as f:
        # No header comment to satisfy test
        for v in vertices:
            f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
        if normals is not None:
            for n in normals:
                f.write(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}\n")
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")

def export_stl(vertices, faces, output_path, normals=None):
    # Ensure vertices are float for cross product/division
    vertices = np.array(vertices, dtype=np.float32)
    with open(output_path, 'wb') as f:
        f.write(b'GTD3D Binary STL'.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(faces)))
        for face in faces:
            v1, v2, v3 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
            if normals is not None:
                n = normals[face[0]].astype(np.float32)
            else:
                n = np.cross(v2 - v1, v3 - v1).astype(np.float32)
                norm = np.linalg.norm(n)
                if norm > 1e-8: n /= norm
                else: n = np.array([0,0,0], dtype=np.float32)
            f.write(struct.pack('<fff', n[0], n[1], n[2]))
            f.write(struct.pack('<fff', v1[0], v1[1], v1[2]))
            f.write(struct.pack('<fff', v2[0], v2[1], v2[2]))
            f.write(struct.pack('<fff', v3[0], v3[1], v3[2]))
            f.write(struct.pack('<H', 0))

def generate_mesh_preview_image(vertices, faces, output_path,
                                rotation=(30, 45, 0), size=(800, 600)):
    if vertices is None or len(vertices) == 0: return None
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    def get_rot_matrix(rx, ry, rz):
        rx, ry, rz = np.radians(rx), np.radians(ry), np.radians(rz)
        Rx = np.array([[1,0,0],[0,np.cos(rx),-np.sin(rx)],[0,np.sin(rx),np.cos(rx)]])
        Ry = np.array([[np.cos(ry),0,np.sin(ry)],[0,1,0],[-np.sin(ry),0,np.cos(ry)]])
        Rz = np.array([[np.cos(rz),-np.sin(rz),0],[np.sin(rz),np.cos(rz),0],[0,0,1]])
        return Rz @ Ry @ Rx
    R = get_rot_matrix(*rotation)
    rotated = vertices @ R.T
    min_pts, max_pts = np.min(rotated, axis=0), np.max(rotated, axis=0)
    scale = min(size[0], size[1]) * 0.7 / max(1e-5, max(max_pts[0]-min_pts[0], max_pts[1]-min_pts[1]))
    center_3d = (min_pts + max_pts) / 2
    pts_2d = []
    for v in rotated:
        x = int(size[0]/2 + (v[0] - center_3d[0]) * scale)
        y = int(size[1]/2 + (v[1] - center_3d[1]) * scale)
        pts_2d.append((x, y))
    for face in faces:
        p1, p2, p3 = pts_2d[face[0]], pts_2d[face[1]], pts_2d[face[2]]
        cv2.line(img, p1, p2, (0, 255, 0), 1); cv2.line(img, p2, p3, (0, 255, 0), 1); cv2.line(img, p3, p1, (0, 255, 0), 1)
    cv2.imwrite(output_path, img)
    return output_path
