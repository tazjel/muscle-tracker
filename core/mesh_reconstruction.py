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

def _compute_smooth_normals(vertices, faces):
    """Average face normals at each vertex for smooth shading."""
    normals = np.zeros_like(vertices, dtype=np.float32)
    for f in faces:
        v0, v1, v2 = vertices[f[0]], vertices[f[1]], vertices[f[2]]
        n = np.cross(v1 - v0, v2 - v0)
        length = np.linalg.norm(n)
        if length > 0:
            n /= length
        normals[f[0]] += n
        normals[f[1]] += n
        normals[f[2]] += n
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals /= lengths
    return normals.astype(np.float32)


def export_glb(vertices, faces, output_path, normals=True,
               uvs=None, texture_image=None):
    """
    Export mesh as a binary glTF (.glb) file using pygltflib.

    Args:
        vertices:      numpy array (N, 3) float32 — coordinates in mm.
        faces:         numpy array (M, 3) uint32  — triangle indices.
        output_path:   destination .glb file path.
        normals:       embed smooth normals (default True).
        uvs:           optional (N, 2) float32 — UV coordinates [0,1].
        texture_image: optional (H, W, 3) uint8 BGR — texture to embed as PNG.

    Returns:
        output_path on success, raises on failure.
    """
    try:
        import pygltflib
    except ImportError:
        raise ImportError("pygltflib is required: pip install pygltflib")

    verts = np.array(vertices, dtype=np.float32)
    tris  = np.array(faces,    dtype=np.uint32)

    tris_binary  = tris.tobytes()
    verts_binary = verts.tobytes()

    # ── Smooth normals ─────────────────────────────────────────────────────────
    norms_binary = b''
    if normals:
        norms = _compute_smooth_normals(verts, tris)
        norms_binary = norms.tobytes()

    # ── UV coordinates ─────────────────────────────────────────────────────────
    uvs_binary = b''
    if uvs is not None:
        uvs_arr = np.array(uvs, dtype=np.float32)
        uvs_binary = uvs_arr.tobytes()

    # ── Texture PNG ────────────────────────────────────────────────────────────
    png_binary = b''
    if texture_image is not None:
        success, enc = cv2.imencode('.png', texture_image)
        if success:
            png_binary = enc.tobytes()
            # Pad to 4-byte alignment
            pad = (4 - len(png_binary) % 4) % 4
            png_binary += b'\x00' * pad

    # ── Assemble buffer: tris → verts → norms → uvs → png ────────────────────
    blob  = tris_binary + verts_binary + norms_binary + uvs_binary + png_binary
    offset = 0

    buf_views = []
    accessors  = []

    # BV 0: indices
    buf_views.append(pygltflib.BufferView(
        buffer=0, byteOffset=offset, byteLength=len(tris_binary),
        target=pygltflib.ELEMENT_ARRAY_BUFFER,
    ))
    accessors.append(pygltflib.Accessor(
        bufferView=0, componentType=pygltflib.UNSIGNED_INT,
        count=int(tris.size), type=pygltflib.SCALAR,
        max=[int(tris.max())], min=[0],
    ))
    offset += len(tris_binary)

    # BV 1: positions
    buf_views.append(pygltflib.BufferView(
        buffer=0, byteOffset=offset, byteLength=len(verts_binary),
        target=pygltflib.ARRAY_BUFFER,
    ))
    accessors.append(pygltflib.Accessor(
        bufferView=1, componentType=pygltflib.FLOAT,
        count=int(len(verts)), type=pygltflib.VEC3,
        max=verts.max(axis=0).tolist(), min=verts.min(axis=0).tolist(),
    ))
    offset += len(verts_binary)

    attr_kwargs = {'POSITION': 1}

    # BV 2: normals (optional)
    if norms_binary:
        buf_views.append(pygltflib.BufferView(
            buffer=0, byteOffset=offset, byteLength=len(norms_binary),
            target=pygltflib.ARRAY_BUFFER,
        ))
        accessors.append(pygltflib.Accessor(
            bufferView=len(buf_views) - 1, componentType=pygltflib.FLOAT,
            count=int(len(verts)), type=pygltflib.VEC3,
        ))
        attr_kwargs['NORMAL'] = len(accessors) - 1
        offset += len(norms_binary)

    # BV for UVs (optional)
    if uvs_binary:
        buf_views.append(pygltflib.BufferView(
            buffer=0, byteOffset=offset, byteLength=len(uvs_binary),
            target=pygltflib.ARRAY_BUFFER,
        ))
        accessors.append(pygltflib.Accessor(
            bufferView=len(buf_views) - 1, componentType=pygltflib.FLOAT,
            count=int(len(verts)), type=pygltflib.VEC2,
        ))
        attr_kwargs['TEXCOORD_0'] = len(accessors) - 1
        offset += len(uvs_binary)

    # BV for PNG texture (optional — no target, it's image data)
    images, textures, samplers = [], [], []
    if png_binary:
        buf_views.append(pygltflib.BufferView(
            buffer=0, byteOffset=offset, byteLength=len(png_binary),
        ))
        images.append(pygltflib.Image(
            mimeType='image/png', bufferView=len(buf_views) - 1,
        ))
        samplers.append(pygltflib.Sampler(
            magFilter=pygltflib.LINEAR, minFilter=pygltflib.LINEAR_MIPMAP_LINEAR,
            wrapS=pygltflib.CLAMP_TO_EDGE, wrapT=pygltflib.CLAMP_TO_EDGE,
        ))
        textures.append(pygltflib.Texture(source=0, sampler=0))

    # ── Material ───────────────────────────────────────────────────────────────
    if png_binary and uvs_binary:
        pbr = pygltflib.PbrMetallicRoughness(
            baseColorTexture=pygltflib.TextureInfo(index=0),
            roughnessFactor=0.65, metallicFactor=0.0,
        )
    else:
        pbr = pygltflib.PbrMetallicRoughness(
            baseColorFactor=[0.769, 0.584, 0.416, 1.0],  # #C4956A skin tone
            roughnessFactor=0.65, metallicFactor=0.0,
        )

    attributes = pygltflib.Attributes(**attr_kwargs)

    gltf = pygltflib.GLTF2(
        scene=0,
        scenes=[pygltflib.Scene(nodes=[0])],
        nodes=[pygltflib.Node(mesh=0)],
        meshes=[pygltflib.Mesh(primitives=[
            pygltflib.Primitive(attributes=attributes, indices=0, material=0)
        ])],
        materials=[pygltflib.Material(
            pbrMetallicRoughness=pbr, doubleSided=True,
        )],
        accessors=accessors,
        bufferViews=buf_views,
        buffers=[pygltflib.Buffer(byteLength=len(blob))],
        images=images or None,
        textures=textures or None,
        samplers=samplers or None,
    )
    gltf.set_binary_blob(blob)
    gltf.save(output_path)
    return output_path


def load_glb_vertices(glb_path):
    """Load vertex positions from a GLB file. Returns (N, 3) float32 or None."""
    try:
        import pygltflib
        glb_path = glb_path.replace('\\', '/')  # normalise Windows paths
        gltf = pygltflib.GLTF2().load(glb_path)
        accessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
        bv = gltf.bufferViews[accessor.bufferView]
        blob = gltf.binary_blob()
        data = blob[bv.byteOffset: bv.byteOffset + bv.byteLength]
        count = accessor.count
        verts = np.array(struct.unpack(f'<{count * 3}f', data)).reshape(count, 3)
        return verts.astype(np.float32)
    except Exception:
        return None


def generate_mesh_preview_image(vertices, faces, output_path):
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_trisurf(vertices[:, 0], vertices[:, 1], vertices[:, 2], triangles=faces, cmap='viridis')
    plt.savefig(output_path)
    plt.close()
    return output_path
