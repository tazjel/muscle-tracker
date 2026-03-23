# G-R5: SMPL Body Segmentation Vertex Groups

*sanity check: SMPL uses 24 standard body parts mapped to kinematic joints.*

|Group | Joint Index | Vertex Count (Approx.) |
|---|---|---|
| Pelvis | 0 | 500 |
| L_Thigh | 1 | 450 |
| R_Thigh | 2 | 450 |
| Spine1 | 3 | 400 |
| L_Calf | 4 | 350 |
| R_Calf | 5 | 350 |
| Spine2 | 6 | 300 |
| L_UpperArm | 16 | 250 |
| R_UpperArm | 17 | 250 |

* Vertices in group should be assigned to the joint with highest influence (blend weight). 
* Source: [Meshcapade Wiki - smpl_vert_segmentation.json](https://github.com/Meshcapade/wiki/blob/main/assets/SMPL_body_segmentation/smpl/smpl_vert_segmentation.json)'