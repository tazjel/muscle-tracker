import os
import sys
import struct
import math
import pygltflib
import trimesh

def reduce_glute_volume(glb_path, out_path, reduction_factor=0.82):
    """
    Applies a smooth spatial falloff deformation to physically reduce 
    the glute/butt volume natively in the GLB buffer without touching 
    the topology or texture mapping.
    """
    glb = pygltflib.GLTF2().load(glb_path)
    
    # 1. Locate the Position buffer
    mesh = glb.meshes[0]
    primitive = mesh.primitives[0]
    accessor = glb.accessors[primitive.attributes.POSITION]
    view = glb.bufferViews[accessor.bufferView]
    
    buffer_data = bytearray(glb.binary_blob())
    
    offset = view.byteOffset + (accessor.byteOffset or 0)
    count = accessor.count

    # Glute spatial bounds on a ~1.87m model (before scaling multipliers are recursively applied)
    # The actual vertex buffer contains the original 1.87m vertices 
    # (the node.scale we applied is just a render transform!).
    
    y_center = 0.96          # Peak glute height
    y_radius = 0.18          # Falloff distance vertically (thigh to lower back)
    z_start = 0.05           # Z threshold where the back begins
    
    print(f"Modifying {count} vertices for Glute flattening...")
    
    modified = 0
    for i in range(count):
        idx = offset + i * 12
        x, y, z = struct.unpack_from('<fff', buffer_data, idx)
        
        # Only affect the back of the body
        if z > z_start:
            # Calculate distance from the vertical center of the glute
            y_dist = abs(y - y_center)
            
            if y_dist < y_radius:
                # Smooth cosine falloff based on vertical distance: 1.0 at center, 0.0 at edge
                vertical_falloff = (math.cos((y_dist / y_radius) * math.pi) + 1.0) / 2.0
                
                # Smooth linear falloff based on depth: it shouldn't compress the core spine
                depth_falloff = min(1.0, (z - z_start) / 0.10)
                
                # Combine falloffs
                total_falloff = vertical_falloff * depth_falloff
                
                # Apply reduction
                # reduction_factor=0.8 means 20% smaller
                current_multiplier = 1.0 - ((1.0 - reduction_factor) * total_falloff)
                
                new_z = z * current_multiplier
                
                struct.pack_into('<fff', buffer_data, idx, x, y, new_z)
                modified += 1
                
                # Update accessor bounds 
                if new_z < accessor.min[2]: accessor.min[2] = new_z
                if new_z > accessor.max[2]: accessor.max[2] = new_z

    print(f"Successfully sculpted {modified} vertices with organic falloff.")
    
    glb.set_binary_blob(bytes(buffer_data))
    
    # Recalculate max Z properly
    max_z = -9999.0
    for i in range(count):
        _, _, z = struct.unpack_from('<fff', buffer_data, offset + i * 12)
        if z > max_z: max_z = z
    accessor.max[2] = max_z

    glb.save(out_path)
    return True

if __name__ == '__main__':
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_glb = os.path.join(project_root, 'meshes', 'macro_skin_body.glb')
    
    print("=== Spatial Deformation: Glute Reduction ===")
    reduce_glute_volume(target_glb, target_glb, reduction_factor=0.75) # 25% reduction at peak
    print("=== Complete! ===")
