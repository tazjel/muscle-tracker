# G-R2: Photo -> SMPL Model Weights Verification

| Model | Repo | Weights | Dual-View? | Accuracy (V2V) |
|---|---|---|---|---|
| **CameraHMR** | [pixelite1201/CameraHMR](https://github.com/pixelite1201/CameraHMR) | HuggingFace (pixelite1201/CameraHMR) | No (Monocular) | 30.2mm (SOTA) |
| **SMPLer-X** | [caizhongang/SMPLer-X](https://github.com/caizhongang/SMPLer-X) | HuggingFace (caizhongang/SMPLer-X) | No | 38.5mm |
| **PHD** | [ICCV 2025 Paper](https://arxiv.org/abs/2412.14742) | Coming soon / Unverified | **YES** | Verified on multi-frame |

## Recommendation
Upgrade to **CameraHMR** for single-frame shape accuracy. It uses 138 dense keypoints which capture muscle volume significantly better than HMR2.0's 17 sparse joints.
