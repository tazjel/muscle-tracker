#!/usr/bin/env python3
"""Seed demo customer with complete profile + 5 historical meshes for viewer demo."""
import sys, os, time, requests

SERVER = os.environ.get('GTD_SERVER', 'http://localhost:8001/web_app')

def main():
    # 1. Login
    r = requests.post(f'{SERVER}/api/login', json={
        'email': 'demo@muscle.com', 'password': 'demo123'
    })
    data = r.json()
    token = data.get('token')
    cid = data.get('customer_id', 1)
    if not token:
        print(f'Login failed: {data}')
        sys.exit(1)
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    print(f'Logged in as customer {cid}')

    # 2. Set complete profile
    profile = {
        'height_cm': 168, 'weight_kg': 63, 'gender': 'Male',
        'shoulder_width_cm': 37, 'neck_to_shoulder_cm': 15,
        'shoulder_to_head_cm': 25, 'arm_length_cm': 80,
        'upper_arm_length_cm': 35, 'forearm_length_cm': 45,
        'torso_length_cm': 50, 'floor_to_knee_cm': 52,
        'knee_to_belly_cm': 40, 'back_buttock_to_knee_cm': 61.6,
        'head_circumference_cm': 56, 'neck_circumference_cm': 35,
        'chest_circumference_cm': 97, 'bicep_circumference_cm': 32,
        'forearm_circumference_cm': 29, 'hand_circumference_cm': 21,
        'waist_circumference_cm': 90, 'hip_circumference_cm': 92,
        'thigh_circumference_cm': 53, 'quadricep_circumference_cm': 52,
        'calf_circumference_cm': 34, 'skin_tone_hex': 'C4956A',
    }
    r = requests.post(f'{SERVER}/api/customer/{cid}/body_profile',
                      json=profile, headers=headers)
    print(f'Profile set: {r.json().get("status")}')

    # 3. Generate 5 meshes with slightly varying profiles (simulating weeks of training)
    growth_steps = [
        {},  # week 0 — baseline
        {'chest_circumference_cm': 97.5, 'bicep_circumference_cm': 32.3},
        {'chest_circumference_cm': 98.0, 'bicep_circumference_cm': 32.7, 'thigh_circumference_cm': 53.3},
        {'chest_circumference_cm': 98.8, 'bicep_circumference_cm': 33.2, 'thigh_circumference_cm': 53.8, 'weight_kg': 63.5},
        {'chest_circumference_cm': 99.5, 'bicep_circumference_cm': 33.8, 'thigh_circumference_cm': 54.2, 'waist_circumference_cm': 89, 'weight_kg': 64},
    ]

    mesh_ids = []
    for i, overrides in enumerate(growth_steps):
        print(f'Generating mesh {i+1}/5 (week {i})...', end=' ', flush=True)
        r = requests.post(f'{SERVER}/api/customer/{cid}/body_model',
                          json=overrides, headers=headers, timeout=60)
        result = r.json()
        mid = result.get('mesh_id')
        cached = result.get('cached', False)
        if mid:
            mesh_ids.append(mid)
            vol = result.get('volume_cm3', 0)
            verts = result.get('num_vertices', 0)
            print(f'mesh #{mid}, {verts} verts, {vol:.0f} cm³' + (' (cached)' if cached else ''))
        else:
            print(f'FAILED: {result.get("message", "unknown error")}')
        if i < len(growth_steps) - 1:
            time.sleep(1)

    print(f'\nDone! {len(mesh_ids)} meshes created: {mesh_ids}')
    if mesh_ids:
        latest = mesh_ids[-1]
        host = SERVER.replace('/web_app', '')
        print(f'Viewer URL: {host}/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/{latest}.glb&customer={cid}')

if __name__ == '__main__':
    main()
