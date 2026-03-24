"""Test camera aiming."""
import bpy, mathutils

scene = bpy.context.scene
cam = scene.camera

# Test 1: default camera, just render
scene.render.resolution_x = 400
scene.render.resolution_y = 400

scene.render.filepath = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\cam_test1_default.png"
bpy.ops.render.render(write_still=True)
print(f"[1] Default cam at {cam.location}, rot={cam.rotation_euler}")

# Test 2: move camera, no rotation change
cam.location = (5, -5, 3)
scene.render.filepath = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\cam_test2_moved.png"
bpy.ops.render.render(write_still=True)
print(f"[2] Moved cam at {cam.location}")

# Test 3: use track_to_quat
cam.location = (0, -6, 2)
target = mathutils.Vector((0, 0, 0))
direction = cam.location - target
rot = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot.to_euler()
scene.render.filepath = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\cam_test3_tracked.png"
bpy.ops.render.render(write_still=True)
print(f"[3] Tracked cam at {cam.location}, rot={cam.rotation_euler}")

# Test 4: manual rotation (look at origin from front)
import math
cam.location = (0, -6, 1)
cam.rotation_euler = (math.radians(80), 0, 0)
scene.render.filepath = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\cam_test4_manual.png"
bpy.ops.render.render(write_still=True)
print(f"[4] Manual cam at {cam.location}, rot={cam.rotation_euler}")
