import numpy as np
import pytest
import os
import tempfile
from core.session_report import generate_session_report


class TestGenerateSessionReport:
    def test_generates_pdf_with_minimal_data(self):
        scan_results = {
            'patient_name': 'Test User',
            'scan_date': '2026-03-15',
            'muscle_group': 'bicep',
            'image_bgr': np.zeros((300, 300, 3), dtype=np.uint8),
            'metrics': {'area_mm2': 5000, 'width_mm': 100, 'height_mm': 150},
        }
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            path = f.name
        try:
            result = generate_session_report(scan_results, output_path=path)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 100  # not empty
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_generates_pdf_with_full_data(self):
        scan_results = {
            'patient_name': 'Test User',
            'scan_date': '2026-03-15',
            'muscle_group': 'bicep',
            'image_bgr': np.zeros((300, 300, 3), dtype=np.uint8),
            'metrics': {'area_mm2': 5000, 'width_mm': 100, 'height_mm': 150},
            'contour': np.array([[50,50],[250,50],[250,250],[50,250]], dtype=np.int32).reshape(-1,1,2),
            'growth_analysis': {'growth_pct': 5.2, 'area_change_mm2': 250},
            'volume_cm3': 120.5,
            'circumference_cm': 38.2,
            'shape_score': 72,
            'shape_grade': 'B',
            'definition': {'overall_definition': 65, 'grade': 'Defined'},
            'body_composition': {'bmi': 24.7, 'estimated_body_fat_pct': 18.0, 'classification': 'Fit'},
            'symmetry': {'composite_imbalance_pct': 3.2, 'verdict': 'Balanced'},
        }
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            path = f.name
        try:
            result = generate_session_report(scan_results, output_path=path)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 500  # substantial PDF
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_missing_optional_sections_still_works(self):
        """Should not crash when optional data is missing."""
        scan_results = {
            'patient_name': 'Test User',
            'scan_date': '2026-03-15',
            'muscle_group': 'bicep',
        }
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            path = f.name
        try:
            result = generate_session_report(scan_results, output_path=path)
            assert os.path.exists(result)
        finally:
            if os.path.exists(path):
                os.unlink(path)
