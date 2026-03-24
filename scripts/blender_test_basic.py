"""Basic render test — cube + imported GLB side by side."""
import bpy, math, mathutils

# Clear
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Bright world
world = bpy.data.worlds['World']
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.9, 0.9, 1.0, 1.0)
bg.inputs[1].default_value = 3.0

# Add reference cube at origin
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
cube = bpy.context.active_object
cube.name = "RefCube"
mat_cube = bpy.data.materials.new("CubeMat")
mat_cube.use_nodes = True
mat_cube.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (1, 0, 0, 1)
cube.data.materials.append(mat_cube)

# Import GLB
glb = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\anny_skinned.glb"
bpy.ops.import_scene.gltf(filepath=glb)

# List ALL objects after import
print("=== All objects in scene ===")
for obj in bpy.data.objects:
    print(f"  {obj.name} | type={obj.type} | loc={obj.location} | dims={obj.dimensions} | parent={obj.parent}")

# Find all meshes
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.name != 'RefCube']
print(f"\nFound {len(meshes)} mesh objects from GLB")

# Scale all imported objects
for obj in meshes:
    max_d = max(obj.dimensions)
    if max_d > 10:
        sf = 1.7 / max_d
        obj.scale *= sf
        print(f"  Scaled {obj.name}: {max_d:.0f} -> {max(obj.dimensions):.2f}")

bpy.context.view_layer.update()

# Place GLB body next to cube (offset X)
for obj in meshes:
    obj.location.x += 2  # move right of cube

# Sun light
sun = bpy.data.lights.new('Sun', 'SUN')
sun.energy = 5.0
sun_obj = bpy.data.objects.new('Sun', sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (math.radians(-45), 0, math.radians(30))

# Camera
cam_data = bpy.data.cameras.new('Cam')
cam_data.lens = 35  # wide angle to capture both
cam_obj = bpy.data.objects.new('Cam', cam_data)
bpy.context.collection.objects.link(cam_obj)
# Camera 6m in front, 1m up, looking at midpoint (1, 0, 0.5)
cam_obj.location = (1, 6, 1.5)
target = mathutils.Vector((1, 0, 0.5))
direction = cam_obj.location - target
rot = direction.to_track_quat('-Z', 'Y')
cam_obj.rotation_euler = rot.to_euler()

scene = bpy.context.scene
scene.camera = cam_obj
scene.render.engine = 'CYCLES'
scene.cycles.samples = 32  # fast preview
scene.cycles.use_denoising = True
scene.render.resolution_x = 800
scene.render.resolution_y = 800
scene.render.filepath = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\debug_basic.png"
scene.render.image_settings.file_format = 'PNG'

bpy.ops.render.render(write_still=True)
print(f"\n[DONE] Rendered: meshes/debug_basic.png")
