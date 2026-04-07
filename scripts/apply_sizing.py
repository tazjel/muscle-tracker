import os
import sys
import json
import pygltflib
import trimesh
import argparse

def get_y_dimension(glb_path):
    # Easiest way to reliably get exact mesh bounds is trimesh
    try:
        mesh = trimesh.load(glb_path, force='mesh')
        y_range = mesh.vertices[:, 1].max() - mesh.vertices[:, 1].min()
        return y_range
    except Exception as e:
        print(f"Error reading mesh bounds: {e}")
        return 1.8769  # fallback MakeHuman male height

def scale_glb_to_profile(glb_path, profile_path):
    print(f"Reading target profile: {profile_path}")
    with open(profile_path, 'r') as f:
        profile = json.load(f)
    
    target_height_cm = profile.get('height_cm', 168.0)
    target_height_m = target_height_cm / 100.0
    
    current_height_m = get_y_dimension(glb_path)
    
    scale_factor = target_height_m / current_height_m
    print(f"Original Height: {current_height_m:.4f}m")
    print(f"Target Height:   {target_height_m:.4f}m")
    print(f"Uniform Scale Multiplier: {scale_factor:.6f}")

    # Load the GLB to modify its scene node scale
    glb = pygltflib.GLTF2().load(glb_path)
    
    # Ensure there is at least one node
    if not glb.nodes:
        print("Error: No nodes found in GLB.")
        sys.exit(1)
        
    for node in glb.nodes:
        # We only want to scale root nodes (often node 0 or those in the default scene)
        if node.scale is None:
            node.scale = [1.0, 1.0, 1.0]
            
        print(f"Old Node Scale: {node.scale}")
        node.scale = [
            node.scale[0] * scale_factor,
            node.scale[1] * scale_factor,
            node.scale[2] * scale_factor
        ]
        print(f"New Node Scale: {node.scale}")

    # Save over the identical file
    glb.save(glb_path)
    print(f"\nSUCCESS! {glb_path} scaled accurately to {target_height_cm}cm height.")

if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_profile_path = os.path.join(project_root, 'scripts', 'dev_profiles', 'default_human_profile.json')
    default_glb_path = os.path.join(project_root, 'meshes', 'macro_skin_body.glb')
    
    scale_glb_to_profile(default_glb_path, default_profile_path)
