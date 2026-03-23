# G-R13: Bone-Axis-Aligned Deformation Research

### 1. Per-Group Deformation Axes
For best results, scaling should be *perpendicular* to the bone direction (radial deformation).

| Muscle Group | Bone Direction (PCA Best Fit) | Scale Plane |
|--------------------|----------------------------------|------------------|
| biceps_l/r | Upper Arm (Humerus) | Perpendicular to Arm |
| forearms_l/r | Forearm (Ulna/Radius) | Perpendicular to Arm |
| deltoids_l | Clavicle to Shoulder | Radial from Shoulder |
| pectorals | Spine 3 | Forward (Y) + Side (X) |
| abs / obliques | Spine 1 / 2 | Forward (Y) + Side (X) |
| quads_l/r | Thigh (Femur) | Perpendicular to Leg |
| calves_l/r | Shin (Tibia) | Perpendicular to Leg |
| glutes | Pelvis to Hip | Backward (-Y) + Side (X) |

### 2. PCA Axis Computation (NumPy)
To find the natural bone direction automatically for a vertex cloud:

```python
# 1. Center the vertices
center = np.mean(verts, axis=0)
c_verts = verts - center

# 2. Singular Value Decomposition (SVD) for PCA
u, s, vh = np.linalg.svd(c_verts)
bone_vector = vh[0]  # The first principal component
```

### 3. Boundary Softening & Blending
1. **Distance-Weighted Blend:** Use a signmoid falloff function based on vertex distance from the muscle centroid.
2. **Laplacian Relaxation:** After all scaling, run 5-10 iterations of `trimesh.smoothing.filter_laplacian` to remove discontinuities at bone boundaries.
3. **Harmonic Weights:** For pro-level blooming, use bi-harmonic smoothing to diffuse the scale factors across the mesh adjacency graph.

### 4. Verdict
PCA is robust for finding bone directions. Local scaling should be done in the plane ngative to this vector, followed by Laplacian smoothing to maintain atatomical plausibility.