"""Import GLB and render with ZERO modifications."""
import bpy, mathutils

scene = bpy.context.scene

# Keep default scene (cube at origin, camera, light)
# Just import GLB
glb = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\anny_skinned.glb"
bpy.ops.import_scene.gltf(filepath=glb)

# List everything
print("=== Scene objects ===")
for obj in bpy.data.objects:
    print(f"  {obj.name} | type={obj.type} | dims={tuple(round(d,1) for d in obj.dimensions)} | vis_vp={not obj.hide_viewport} vis_render={not obj.hide_render}")
    if obj.type == 'MESH' and obj.data:
        print(f"    -> {len(obj.data.vertices)} verts, {len(obj.data.polygons)} faces, {len(obj.data.materials)} materials")
        for i, m in enumerate(obj.data.materials):
            if m:
                print(f"    -> mat[{i}]: {m.name}")

# Scale imported body to fit
for obj in bpy.data.objects:
    if obj.type == 'MESH' and obj.name != 'Cube':
        md = max(obj.dimensions)
        if md > 10:
            sf = 2.0 / md
            obj.scale = (sf, sf, sf)
            print(f"  Scaled {obj.name} by {sf:.6f}")
        # Move it 3 units to the right of default cube
        obj.location.x += 3

bpy.context.view_layer.update()

# Move camera WAY back to see everything
cam = scene.camera
cam.location = (0, -10, 3)
target = mathutils.Vector((1.5, 0, 0))
direction = cam.location - target
rot = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot.to_euler()
cam.data.lens = 35

# Brighten the default light
for obj in bpy.data.objects:
    if obj.type == 'LIGHT':
        obj.data.energy = 5000

# Small fast render
scene.render.resolution_x = 600
scene.render.resolution_y = 400
scene.render.filepath = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\debug_glb_import.png"
bpy.ops.render.render(write_still=True)
print("[DONE]")
