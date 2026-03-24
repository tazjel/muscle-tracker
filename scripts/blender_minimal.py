"""Absolute minimal render test."""
import bpy

# Don't clear anything - use default scene (cube + light + camera)
scene = bpy.context.scene

# Just render with defaults
scene.render.resolution_x = 400
scene.render.resolution_y = 400
scene.render.filepath = r"C:\Users\MiEXCITE\Projects\gtd3d\meshes\debug_minimal.png"
scene.render.image_settings.file_format = 'PNG'

# List what's in scene
print("Objects in default scene:")
for obj in scene.objects:
    print(f"  {obj.name} type={obj.type} visible={not obj.hide_render}")

print(f"Camera: {scene.camera}")
print(f"Engine: {scene.render.engine}")

bpy.ops.render.render(write_still=True)
print("[DONE]")
