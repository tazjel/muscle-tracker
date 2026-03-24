"""Quick debug render to find the body."""
import bpy, math, mathutils

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Import GLB
glb = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\anny_skinned.glb"
bpy.ops.import_scene.gltf(filepath=glb)

# Find mesh
body = None
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        body = obj
        break

print(f"Body: {body.name}")
print(f"Location: {body.location}")
print(f"Dimensions: {body.dimensions}")
print(f"Scale: {body.scale}")

# Check all vertices to find actual bounds
import numpy as np
verts = body.data.vertices
coords = [(body.matrix_world @ v.co) for v in verts]
xs = [c.x for c in coords]
ys = [c.y for c in coords]
zs = [c.z for c in coords]
print(f"X range: {min(xs):.2f} to {max(xs):.2f}")
print(f"Y range: {min(ys):.2f} to {max(ys):.2f}")
print(f"Z range: {min(zs):.2f} to {max(zs):.2f}")

# Scale to meters
max_dim = max(body.dimensions)
if max_dim > 10:
    sf = 1.7 / max_dim
    body.scale = (sf, sf, sf)
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.transform_apply(scale=True)

# Re-check after scale
coords = [(body.matrix_world @ v.co) for v in body.data.vertices]
xs = [c.x for c in coords]
ys = [c.y for c in coords]
zs = [c.z for c in coords]
cx, cy, cz = (max(xs)+min(xs))/2, (max(ys)+min(ys))/2, (max(zs)+min(zs))/2
print(f"\nAfter scale:")
print(f"X: {min(xs):.3f} to {max(xs):.3f} (center {cx:.3f})")
print(f"Y: {min(ys):.3f} to {max(ys):.3f} (center {cy:.3f})")
print(f"Z: {min(zs):.3f} to {max(zs):.3f} (center {cz:.3f})")

# Simple bright material
mat = bpy.data.materials.new("Debug")
mat.use_nodes = True
bsdf = mat.node_tree.nodes['Principled BSDF']
bsdf.inputs['Base Color'].default_value = (0.9, 0.7, 0.6, 1.0)
body.data.materials.clear()
body.data.materials.append(mat)

# Bright world
world = bpy.data.worlds['World']
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (0.8, 0.8, 0.9, 1.0)
world.node_tree.nodes['Background'].inputs[1].default_value = 2.0

# Add sun light
sun = bpy.data.lights.new('Sun', 'SUN')
sun.energy = 3.0
sun_obj = bpy.data.objects.new('Sun', sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (math.radians(-45), 0, math.radians(30))

# Camera — try 4 angles, render each
scene = bpy.context.scene
# Try EEVEE variants for different Blender versions
for eng in ['BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE']:
    try:
        scene.render.engine = eng
        break
    except TypeError:
        continue
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.image_settings.file_format = 'PNG'

center = mathutils.Vector((cx, cy, cz))
cam_data = bpy.data.cameras.new('Cam')
cam_data.lens = 50
cam_obj = bpy.data.objects.new('Cam', cam_data)
bpy.context.collection.objects.link(cam_obj)
scene.camera = cam_obj

views = {
    'front_Y': (cx, cy + 4, cz),
    'front_Z': (cx, cy, cz + 4),
    'side_X':  (cx + 4, cy, cz),
    'angle':   (cx + 3, cy + 2, cz + 2),
}

for name, pos in views.items():
    cam_obj.location = pos
    direction = mathutils.Vector(pos) - center
    rot = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot.to_euler()

    out = rf"C:\Users\MiEXCITE\Projects\gtd3d\meshes\debug_{name}.png"
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print(f"[DEBUG] Rendered {name}: {out}")
