# CLAUDE REVIEW: Muscle Tracker Clinical Ecosystem (v1.7)

## 1. Project Overview
**Goal**: A professional-grade muscle growth analysis suite for clinics and athletes, outperforming rivals like ZOZOFIT and in3D via direct metrology and sensor-guided data collection.
**Project Path**: `C:\Users\MiEXCITE\Projects\muscle_tracker`

## 2. Technical Architecture
```text
muscle_tracker/
├── muscle_tracker.py           — Professional CLI entry point (v1.1 - v1.6)
├── core/                       — Computer Vision & Metrology Engine
│   ├── calibration.py          — [v1.1] Green marker detection & Px-to-MM ratio
│   ├── vision_medical.py       — [v1.1] High-precision area & width detection
│   ├── visualization.py        — [v1.2] High-contrast growth heatmaps
│   ├── alignment.py            — [v1.3] ORB/Homography pose-invariant registration
│   ├── symmetry.py             — [v1.4] Left vs Right imbalance analysis
│   ├── segmentation.py         — [v1.5] Hu Moments shape-matching against Pro templates
│   └── volumetrics.py          — [v1.6] 3D mass estimation (cm3) from dual views
├── companion_app/              — [v1.4] Flutter APK (Sensor-guided capture)
│   └── lib/main.dart           — Pitch/Roll Accelerometer Leveling HUD
└── web_app/                    — [v1.7] py4web Clinical Backend
    ├── models.py               — DAL Schema (Customers, Scans, Diet/Activity Logs)
    └── controllers.py          — API for APK uploads & automated vision processing
```

## 3. "Super Power" Feature Deep Dive

### v1.1 Clinical Metrology (Calibration)
- **Engine**: `core/calibration.py`
- **Logic**: Auto-detects a 20mm green clinical marker.
- **Output**: Converts raw pixel deltas into real-world **millimeters (mm)**.

### v1.3 Alignment Guard (Image Registration)
- **Engine**: `core/alignment.py`
- **Logic**: Uses ORB feature matching and Homography to warp the "After" image to perfectly match the "Before" pose, eliminating camera angle errors.

### v1.6 Volumetric Mass Analysis
- **Engine**: `core/volumetrics.py`
- **Logic**: Implements an Elliptical Cylinder Model to estimate 3D muscle volume (**cm³**) from Front and Side 2D scans.

### v1.7 Clinical Cloud (py4web)
- **Engine**: `web_app/models.py`
- **Logic**: Correlates muscle gains with diet (protein/calories) and activity. Uses DAL for future-proof integration with Google Cloud SQL.

## 4. Competitive Benchmarking
| Feature | Rival (Abody.ai / Shapez) | Muscle Tracker Advantage |
| :--- | :--- | :--- |
| **Accuracy** | AI "Guess" based on height | **Physical Metrology** via calibration marker |
| **Pose** | Manual user alignment | **Sensor-Locked APK** + CV Auto-Alignment |
| **Symmetry** | Rare / Not specialized | **Native Symmetry Audit** (L vs R comparison) |

## 5. Review Instructions for Claude
1. **Engine Validation**: Review `core/volumetrics.py` for mathematical stability in the elliptical model.
2. **Security Audit**: Check `web_app/controllers.py` for secure file storage handling in the `api/upload_scan` endpoint.
3. **Template Expansion**: Suggest 3 additional "Pro Physique" templates for `core/segmentation.py` beyond the current `bicep_peak`.

---
*Status: MVP Complete | Session: 2026-03-15 | Author: Gemini CLI (YOLO Mode)*
