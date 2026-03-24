# SHOPPING LIST: Pro-Grade 3D Human Scanning Rig

This list outlines the recommended hardware for moving from basic Arduino setups to a professional-grade 3D scanning booth compatible with the `gtd3d` vision engine.

## 1. The "Brain" (Processing & Integration)
- **Raspberry Pi 5 (8GB RAM)** 
  - **Reason:** Necessary to run `Open3D` and `MediaPipe` for real-time volumetric integration.
  - **Est. Cost:** $80
  - **Source:** [Adafruit](https://www.adafruit.com/product/5812) | [CanaKit](https://www.canakit.com/raspberry-pi-5-8gb.html)

## 2. The "Eyes" (Distributed Capture Nodes)
- **Seeed Studio XIAO ESP32S3 Sense**
  - **Reason:** Smallest WiFi-vision node with AI vector acceleration. Best for multi-camera arrays.
  - **Est. Cost:** $15/node
  - **Source:** [Seeed Studio](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5631.html)
- **OV5640 (5MP) Camera Module** (Replacement for standard 2MP)
  - **Reason:** Increases feature detection density for photogrammetry.
  - **Est. Cost:** $10

## 3. The "Depth" (Physical Volumetrics)
- **RPLIDAR A1M8 (360 Degree Laser Scanner)**
  - **Reason:** Provides millimeter-accurate cross-sections (Visual Hull) for body fat % calculation.
  - **Est. Cost:** $90
  - **Source:** [DFRobot](https://www.dfrobot.com/product-1125.html) | [Amazon](https://www.amazon.com/Slamtec-RPLIDAR-A1-Scanning-Triangulation/dp/B07T6958L3)

## 4. Main Capture Sensors
- **Raspberry Pi Camera Module 3 (Wide-Angle)**
  - **Reason:** Integrated PDAF (Phase Detection Autofocus) + 120° FOV. Perfect for full-body tracking.
  - **Est. Cost:** $25
- **Raspberry Pi High Quality Camera (Sony IMX477 - 12.3MP)**
  - **Reason:** Supports C/CS-mount lenses. Essential for capturing high-res muscle detail.
  - **Est. Cost:** $50
- **6mm Wide Angle Lens (for HQ Camera)**
  - **Est. Cost:** $25

## 5. Specialized Filters (For Task 4 Calibration)
- **37mm Circular Polarizing (CPL) Filter**
  - **Reason:** Screw onto the HQ Camera lens to eliminate skin glare (specular highlights).
  - **Est. Cost:** $15

## 6. DIY Rig Hardware (Arduino-Based)
- **NEMA 17 Stepper Motor + A4988 Driver** (To rotate the person/turntable)
- **Logic Level Converter (3.3V to 5V)** (To bridge ESP32/Pi to 5V Arduino components)