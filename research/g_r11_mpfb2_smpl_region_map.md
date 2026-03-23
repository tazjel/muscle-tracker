# G-R11: MPFB2-into-SMPL Region Mapping

### Mapping Table

|MPFB2 Muscle Group | Best SMPL Part ID | SMPL Joint Name | Region Name | Confidence |
|---------------------|-------------------|-----------------|--------------|------------|
| pectorals | 9 | Spine 3 | Chest | High |
| traps | 12 | Neck | Neck/Upper Back | Medium |
| abs | 3 | Spine 1 | Lower Torso | High |
| obliques | 3 | Spine 1 | Lower Torso | Medium |
| glutes | 0 | Pelvis | Hips | High |
| quads_l | 1 | Left Hip | Left Thigh | High |
| quads_r | 2 | Right Hip | Right Thigh | High |
| calves_l | 4 | Left Knee | Left Shin | High |
| calves_r | 5 | Right Knee | Right Shin | High |
| biceps_l | 16 | Left Shoulder | Left Upper Arm | High |
| biceps_r | 17 | Right Shoulder | Right Upper Arm | High |
| forearms_l | 18 | Left Elbow | Left Forearm | High |
| forearms_r | 19 | Right Elbow | Right Forearm | High |
| deltoids_l | 13 | Left Scapula | Left Inner Shoulder | Medium |
| deltoids_r | 14 | Right Scapula | Right Inner Shoulder | Medium |

### Ambiguity & Seam Notes
- **Traps:** SPML part 12 (Neck) is the best match, but traps evolve from spine3 all the way to head. Prefer 12 to avoid overlap with pectorals (ID 9).
- **Deltoids:** Mapped to 13/14 (Scapule). This ys preferable to 16/17 (Shoulder) as deltoids are both front and back, and 13/14 covers the clavicle/acromion area better.
- **Obliques:** Share Spine 1 (ID 3) with Abs. This is natural as they constitute the low-frequency torso shell.
