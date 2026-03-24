"""
Blender headless script: Import existing Anny body GLB, apply proper UV unwrap
+ FreePBR skin textures with SSS, re-export as GLB.

Usage:
  blender --background --python scripts/blender_skin_anny.py -- <input.glb>

Output: meshes/anny_skinned.glb
"""
import bpy
import math
import os
import sys

# Get input GLB from command line args (after --)
argv = sys.argv
if '--' in argv:
    argv = argv[argv.index('--') + 1:]
    input_glb = argv[0] if argv else None
else:
    input_glb = None

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if not input_glb:
    # Use latest body GLB
    mesh_dir = os.path.join(project_dir, 'meshes')
    glbs = sorted([f for f in os.listdir(mesh_dir) if f.startswith('body_1_') and f.endswith('.glb')],
                  key=lambda f: os.path.getmtime(os.path.join(mesh_dir, f)), reverse=True)
    if glbs:
        input_glb = os.path.join(mesh_dir, glbs[0])
    else:
        print("ERROR: No body GLB found")
        sys.exit(1)

print(f"Input: {input_glb}")

# ── Clear scene ──
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
for mesh in bpy.data.meshes:
    bpy.data.meshes.remove(mesh)
for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)

# ── Import GLB ──
bpy.ops.import_scene.gltf(filepath=input_glb)

# Find mesh objects
mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
print(f"Found {len(mesh_objects)} mesh objects")

if not mesh_objects:
    print("ERROR: No mesh objects found in GLB")
    sys.exit(1)

# ── Join all mesh objects into one ──
bpy.ops.object.select_all(action='DESELECT')
for obj in mesh_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = mesh_objects[0]
if len(mesh_objects) > 1:
    bpy.ops.object.join()

body_obj = bpy.context.active_object
print(f"Body mesh: {len(body_obj.data.vertices)} verts, {len(body_obj.data.polygons)} faces")

# ── Re-UV unwrap (Smart UV Project for body-aware mapping) ──
# Remove existing UV layers
while body_obj.data.uv_layers:
    body_obj.data.uv_layers.remove(body_obj.data.uv_layers[0])

bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')

# Smart UV project with tight angle for body topology
bpy.ops.uv.smart_project(
    angle_limit=math.radians(66),
    island_margin=0.01,
    area_weight=0.0,
    scale_to_bounds=True,
)
bpy.ops.object.mode_set(mode='OBJECT')
print(f"UV layers: {len(body_obj.data.uv_layers)}")

# ── Smooth shading ──
bpy.ops.object.shade_smooth()

# ── Create skin material with FreePBR textures ──
# Remove all existing materials
body_obj.data.materials.clear()

mat = bpy.data.materials.new('RealisticSkin')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links

# Clear default nodes
for node in nodes:
    nodes.remove(node)

# Principled BSDF
bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (0, 0)

output = nodes.new('ShaderNodeOutputMaterial')
output.location = (400, 0)
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

# Base skin color
bsdf.inputs['Base Color'].default_value = (0.82, 0.65, 0.55, 1.0)
bsdf.inputs['Roughness'].default_value = 0.55
bsdf.inputs['Metallic'].default_value = 0.0

# SSS - critical for skin realism
bsdf.inputs['Subsurface Weight'].default_value = 0.3
bsdf.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
bsdf.inputs['Subsurface Scale'].default_value = 0.01

# Specular
bsdf.inputs['Specular IOR Level'].default_value = 0.4

# Coat (skin oil)
bsdf.inputs['Coat Weight'].default_value = 0.04
bsdf.inputs['Coat Roughness'].default_value = 0.3

# ── Load FreePBR textures ──
skin_dir = os.path.join(project_dir, 'apps', 'uploads', 'skin', 'freepbr', 'human-skin1-bl')
albedo_path = os.path.join(skin_dir, 'human-skin1_albedo.png')
normal_path = os.path.join(skin_dir, 'human-skin1_normal-ogl.png')
roughness_path = os.path.join(skin_dir, 'human-skin1_roughness.png')

# UV Mapping node (for tiling control)
mapping = nodes.new('ShaderNodeMapping')
mapping.location = (-1000, 0)
mapping.inputs['Scale'].default_value = (3.0, 5.0, 1.0)  # tile across body

texcoord = nodes.new('ShaderNodeTexCoord')
texcoord.location = (-1200, 0)
links.new(texcoord.outputs['UV'], mapping.inputs['Vector'])

if os.path.exists(albedo_path):
    print(f"Loading FreePBR textures from {skin_dir}")

    # Albedo
    albedo_img = bpy.data.images.load(albedo_path)
    albedo_tex = nodes.new('ShaderNodeTexImage')
    albedo_tex.image = albedo_img
    albedo_tex.location = (-600, 200)
    links.new(mapping.outputs['Vector'], albedo_tex.inputs['Vector'])
    links.new(albedo_tex.outputs['Color'], bsdf.inputs['Base Color'])

    # Normal
    if os.path.exists(normal_path):
        normal_img = bpy.data.images.load(normal_path)
        normal_img.colorspace_settings.name = 'Non-Color'
        normal_tex = nodes.new('ShaderNodeTexImage')
        normal_tex.image = normal_img
        normal_tex.location = (-600, -200)
        links.new(mapping.outputs['Vector'], normal_tex.inputs['Vector'])

        normal_map = nodes.new('ShaderNodeNormalMap')
        normal_map.location = (-200, -200)
        normal_map.inputs['Strength'].default_value = 1.5
        links.new(normal_tex.outputs['Color'], normal_map.inputs['Color'])
        links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])

    # Roughness
    if os.path.exists(roughness_path):
        rough_img = bpy.data.images.load(roughness_path)
        rough_img.colorspace_settings.name = 'Non-Color'
        rough_tex = nodes.new('ShaderNodeTexImage')
        rough_tex.image = rough_img
        rough_tex.location = (-600, -500)
        links.new(mapping.outputs['Vector'], rough_tex.inputs['Vector'])
        links.new(rough_tex.outputs['Color'], bsdf.inputs['Roughness'])
else:
    print("WARNING: FreePBR textures not found, using solid color")

# Assign material
body_obj.data.materials.append(mat)

# ── Bake textures into the GLB ──
# For GLB export, textures are embedded automatically when using image nodes

# ── Export GLB ──
output_path = os.path.join(project_dir, 'meshes', 'anny_skinned.glb')

# Select only the body
bpy.ops.object.select_all(action='DESELECT')
body_obj.select_set(True)
bpy.context.view_layer.objects.active = body_obj

bpy.ops.export_scene.gltf(
    filepath=output_path,
    export_format='GLB',
    use_selection=True,
    export_apply=True,
    export_materials='EXPORT',
    export_image_format='AUTO',
    export_normals=True,
    export_tangents=True,
)

# Also copy to static folder for direct viewer access
import shutil
static_path = os.path.join(project_dir, 'web_app', 'static', 'viewer3d', 'anny_skinned.glb')
shutil.copy2(output_path, static_path)

print(f"\n✓ Exported: {output_path}")
print(f"  Also at: {static_path}")
print(f"  Vertices: {len(body_obj.data.vertices)}")
print(f"  Faces: {len(body_obj.data.polygons)}")
print(f"  UV layers: {len(body_obj.data.uv_layers)}")
print(f"  Material: {mat.name}")
print(f"\nView at: http://localhost:8001/web_app/static/viewer3d/index.html?model=/web_app/static/viewer3d/anny_skinned.glb")
