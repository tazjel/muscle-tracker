import sys
import os
import cv2
import json
import argparse
import base64
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.skin_texture import process_skin_photo

def add_detail_maps_to_glb(base_glb_path, out_glb_path, normal_img_path, roughness_img_path, uv_scale):
    """
    Directly hacks the GLTF JSON to inject KHR_texture_transform for Normal/Roughness maps
    WITHOUT touching the base Albedo texture layout!
    """
    import pygltflib
    
    # Needs the extension enabled
    glb = pygltflib.GLTF2().load(base_glb_path)
    if glb.extensionsUsed is None:
        glb.extensionsUsed = []
    if "KHR_texture_transform" not in glb.extensionsUsed:
        glb.extensionsUsed.append("KHR_texture_transform")

    if glb.extensionsRequired is None:
        glb.extensionsRequired = []
    if "KHR_texture_transform" not in glb.extensionsRequired:
        glb.extensionsRequired.append("KHR_texture_transform")

    # Read our generated images
    with open(normal_img_path, "rb") as f:
        normal_b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode('utf-8')
    with open(roughness_img_path, "rb") as f:
        rough_b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode('utf-8')

    # Create images using URI (bypasses complex buffer binary injection)
    norm_image_idx = len(glb.images)
    glb.images.append(pygltflib.Image(mimeType="image/png", uri=normal_b64))
    
    rough_image_idx = len(glb.images)
    glb.images.append(pygltflib.Image(mimeType="image/png", uri=rough_b64))

    # Create textures
    norm_texture_idx = len(glb.textures)
    glb.textures.append(pygltflib.Texture(source=norm_image_idx))
    
    rough_texture_idx = len(glb.textures)
    glb.textures.append(pygltflib.Texture(source=rough_image_idx))

    # Apply to materials mapping
    for material in glb.materials:
        material.normalTexture = pygltflib.NormalMaterialTexture(
            index=norm_texture_idx,
            scale=1.5,
            extensions={
                "KHR_texture_transform": {
                    "scale": [uv_scale, uv_scale]
                }
            }
        )
        if not material.pbrMetallicRoughness:
            material.pbrMetallicRoughness = pygltflib.PbrMetallicRoughness()
            
        material.pbrMetallicRoughness.metallicRoughnessTexture = pygltflib.TextureInfo(
            index=rough_texture_idx,
            extensions={
                "KHR_texture_transform": {
                    "scale": [uv_scale, uv_scale]
                }
            }
        )
        material.pbrMetallicRoughness.roughnessFactor = 0.8
        material.pbrMetallicRoughness.metallicFactor = 0.05

    glb.save(out_glb_path)
    return True


def main():
    parser = argparse.ArgumentParser(description='Apply scalable micro detail normal maps.')
    parser.add_argument('--macro', type=str, required=True, help='Path to macro skin image')
    parser.add_argument('--uv-scale', type=float, default=60.0, help='Scale factor for the DETAIL map only.')
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(project_root, 'meshes', 'debug_textures')
    
    print("\n=== Processing Detail Normal Maps ===")
    try:
        pbr_paths = process_skin_photo(args.macro, out_dir, size=512)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("\n=== Injecting KHR_texture_transform into GLB ===")
    base_glb = os.path.join(project_root, 'meshes', 'mpfb_male_body.glb')
    out_glb = os.path.join(project_root, 'meshes', 'macro_skin_body.glb')
    
    add_detail_maps_to_glb(
        base_glb, 
        out_glb, 
        pbr_paths['normal'], 
        pbr_paths['roughness'], 
        args.uv_scale
    )
    
    print(f"\nSUCCESS! Micro-Detail maps baked to {out_glb}")

if __name__ == '__main__':
    main()
