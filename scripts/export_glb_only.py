import bpy, os, sys, math
BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
OUT_GLB = os.path.join(BASE, "meshes", "mpfb_v4_body.glb")
bpy.ops.mpfb.create_human()
body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH' and len(obj.data.vertices) > 1000:
        body = obj
        break
if not body: sys.exit(1)
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.export_scene.gltf(filepath=OUT_GLB, use_selection=True, export_format='GLB', export_apply=True)
print(f"EXPORTED: {OUT_GLB} ({len(body.data.vertices)} verts)")
