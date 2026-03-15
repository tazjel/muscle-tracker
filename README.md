# Muscle Tracker — Clinical Metrology Engine (v4.0)

A high-precision muscle growth analysis and clinical reporting engine.

## Key Features
- **ML Segmentation:** Automated body/muscle isolation using MediaPipe for high-accuracy ROIs.
- **Auto-detection:** Integrated pose-based muscle group classification (Biceps, Quads, etc.).
- **Advanced Volumetrics:** Slice-integration model for tapered limbs, exceeding simple cylinder models.
- **Clinical Dashboard:** Real-time patient monitoring, historical tracking, and analytics SPA.
- **PDF Reporting:** Professional-grade clinical reports using ReportLab for Consultation-ready output.
- **Security:** JWT-enforced clinical endpoints, patient-level ownership checks, and detailed audit logging.

## Quick Start (Docker)
The engine is containerized for rapid deployment.

```bash
docker-compose up -d
```
Access the clinical dashboard at `http://localhost:8000/web_app/static/dashboard/index.html`

## Development Setup
```bash
pip install -r requirements.txt
python muscle_tracker.py --dashboard
```

## Core Components
- `core/`: ML models, vision logic, and volumetric engines.
- `web_app/`: py4web clinical API and static dashboard.
- `companion_app/`: Flutter-based capture client (v3.0).
