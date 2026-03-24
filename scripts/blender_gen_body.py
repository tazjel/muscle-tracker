"""
Blender headless script: Generate a human body mesh with proper UVs and
realistic skin material, export as GLB.

Usage:
  blender --background --python scripts/blender_gen_body.py

Output: meshes/realistic_body.glb
"""
import bpy
import bmesh
import math
import os
import numpy as np

# ── Clear scene ──
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
for mesh in bpy.data.meshes:
    bpy.data.meshes.remove(mesh)
for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)
for img in bpy.data.images:
    bpy.data.images.remove(img)

# ── Body parameters (athletic male, ~178cm) ──
body_height = 1.78
shoulder_width = 0.46
hip_width = 0.34
chest_depth = 0.24
waist_width = 0.32
neck_radius = 0.065
head_radius = 0.10

# ── Build body from profile curves (cross-sections at different heights) ──
# Each section: (height_ratio, width, depth, shape_factor)
# shape_factor: 1.0=circle, >1=wider ellipse
body_sections = [
    # (height_fraction, half_width, half_depth)
    (0.00, 0.045, 0.055),   # feet
    (0.03, 0.050, 0.065),   # ankles
    (0.15, 0.060, 0.070),   # calves (widest)
    (0.25, 0.050, 0.060),   # knees
    (0.35, 0.070, 0.080),   # lower thigh
    (0.45, 0.090, 0.095),   # upper thigh
    (0.50, 0.170, 0.120),   # crotch/hip join
    (0.53, 0.175, 0.125),   # hip
    (0.57, 0.165, 0.120),   # waist
    (0.60, 0.160, 0.115),   # natural waist
    (0.65, 0.180, 0.130),   # lower chest
    (0.70, 0.210, 0.135),   # chest
    (0.73, 0.230, 0.130),   # shoulders
    (0.75, 0.220, 0.120),   # upper shoulder
    (0.80, 0.070, 0.070),   # neck base
    (0.83, 0.065, 0.065),   # neck
    (0.86, 0.085, 0.095),   # jaw
    (0.90, 0.095, 0.100),   # face
    (0.94, 0.090, 0.095),   # forehead
    (0.97, 0.075, 0.080),   # top of head
    (1.00, 0.010, 0.010),   # crown
]

# ── Create body mesh using lathe/revolution ──
segments = 32  # circumference resolution
num_sections = len(body_sections)

verts = []
faces = []

for si, (h_ratio, hw, hd) in enumerate(body_sections):
    y = h_ratio * body_height
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        # Elliptical cross-section
        x = hw * math.cos(angle)
        z = hd * math.sin(angle)
        verts.append((x, z, y))  # Blender Z-up

# Build faces (quads connecting adjacent rings)
for si in range(num_sections - 1):
    for i in range(segments):
        i_next = (i + 1) % segments
        v0 = si * segments + i
        v1 = si * segments + i_next
        v2 = (si + 1) * segments + i_next
        v3 = (si + 1) * segments + i
        faces.append((v0, v1, v2, v3))

# Create mesh object
mesh = bpy.data.meshes.new('BodyMesh')
mesh.from_pydata(verts, [], faces)
mesh.update()

body_obj = bpy.data.objects.new('Body', mesh)
bpy.context.collection.objects.link(body_obj)
bpy.context.view_layer.objects.active = body_obj
body_obj.select_set(True)

# ── Smooth the mesh ──
# Add subdivision surface for smooth appearance
bpy.ops.object.modifier_add(type='SUBSURF')
body_obj.modifiers['Subdivision'].levels = 2
body_obj.modifiers['Subdivision'].render_levels = 2

# Smooth shading
bpy.ops.object.shade_smooth()

# ── UV Unwrap ──
# Smart UV project gives decent body-mapped UVs
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')

# ── Create realistic skin material ──
mat = bpy.data.materials.new('SkinMaterial')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links

# Clear default nodes
for node in nodes:
    nodes.remove(node)

# Create principled BSDF
bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (0, 0)

output = nodes.new('ShaderNodeOutputMaterial')
output.location = (300, 0)
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

# Skin base color (warm peach)
bsdf.inputs['Base Color'].default_value = (0.82, 0.65, 0.55, 1.0)
bsdf.inputs['Roughness'].default_value = 0.55
bsdf.inputs['Metallic'].default_value = 0.0

# Subsurface scattering — THE key to realistic skin
bsdf.inputs['Subsurface Weight'].default_value = 0.3
bsdf.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)  # R>G>B (blood)
bsdf.inputs['Subsurface Scale'].default_value = 0.01

# Specular (skin has subtle specular)
bsdf.inputs['Specular IOR Level'].default_value = 0.4

# Coat (skin oil)
bsdf.inputs['Coat Weight'].default_value = 0.04
bsdf.inputs['Coat Roughness'].default_value = 0.3

# ── Load FreePBR skin textures if available ──
skin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'apps', 'uploads', 'skin', 'freepbr', 'human-skin1-bl')

albedo_path = os.path.join(skin_dir, 'human-skin1_albedo.png')
normal_path = os.path.join(skin_dir, 'human-skin1_normal-ogl.png')
roughness_path = os.path.join(skin_dir, 'human-skin1_roughness.png')

if os.path.exists(albedo_path):
    print(f"Loading FreePBR skin textures from {skin_dir}")

    # Albedo texture
    albedo_img = bpy.data.images.load(albedo_path)
    albedo_tex = nodes.new('ShaderNodeTexImage')
    albedo_tex.image = albedo_img
    albedo_tex.location = (-600, 200)

    # UV mapping with tiling
    mapping = nodes.new('ShaderNodeMapping')
    mapping.location = (-1000, 0)
    mapping.inputs['Scale'].default_value = (4.0, 6.0, 1.0)  # tile 4x6

    texcoord = nodes.new('ShaderNodeTexCoord')
    texcoord.location = (-1200, 0)

    links.new(texcoord.outputs['UV'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], albedo_tex.inputs['Vector'])
    links.new(albedo_tex.outputs['Color'], bsdf.inputs['Base Color'])

    # Normal map
    if os.path.exists(normal_path):
        normal_img = bpy.data.images.load(normal_path)
        normal_img.colorspace_settings.name = 'Non-Color'
        normal_tex = nodes.new('ShaderNodeTexImage')
        normal_tex.image = normal_img
        normal_tex.location = (-600, -200)
        links.new(mapping.outputs['Vector'], normal_tex.inputs['Vector'])

        normal_map = nodes.new('ShaderNodeNormalMap')
        normal_map.location = (-200, -200)
        normal_map.inputs['Strength'].default_value = 1.2
        links.new(normal_tex.outputs['Color'], normal_map.inputs['Color'])
        links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])

    # Roughness map
    if os.path.exists(roughness_path):
        rough_img = bpy.data.images.load(roughness_path)
        rough_img.colorspace_settings.name = 'Non-Color'
        rough_tex = nodes.new('ShaderNodeTexImage')
        rough_tex.image = rough_img
        rough_tex.location = (-600, -500)
        links.new(mapping.outputs['Vector'], rough_tex.inputs['Vector'])
        links.new(rough_tex.outputs['Color'], bsdf.inputs['Roughness'])
else:
    print("No FreePBR textures found, using solid skin color")

# Assign material
body_obj.data.materials.append(mat)

# ── Apply subdivision before export ──
bpy.ops.object.modifier_apply(modifier='Subdivision')

# ── Export GLB ──
output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meshes')
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'realistic_body.glb')

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

print(f"\n✓ Exported: {output_path}")
print(f"  Vertices: {len(body_obj.data.vertices)}")
print(f"  Faces: {len(body_obj.data.polygons)}")
print(f"  Has UVs: {len(body_obj.data.uv_layers) > 0}")
print(f"  Material: {mat.name}")
