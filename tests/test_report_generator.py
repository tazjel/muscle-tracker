import os
import pytest
from core.report_generator import generate_clinical_report


def test_generate_clinical_report_creates_pdf():
    scan_result = {
        "status": "Success",
        "verdict": "Slight Increase",
        "metrics": {"area_delta_mm2": 150.0, "growth_pct": 2.5},
        "confidence": {"detection": 95}
    }
    output = "test_report.pdf"
    if os.path.exists(output):
        os.remove(output)
        
    res_path = generate_clinical_report(scan_result, output_path=output)
    
    assert os.path.exists(res_path)
    assert res_path.endswith(".pdf")
    # Basic PDF header check
    with open(res_path, 'rb') as f:
        header = f.read(4)
        assert header == b'%PDF'
    
    os.remove(res_path)


def test_generate_clinical_report_handles_png_ext():
    """Verify it converts .png extension to .pdf automatically."""
    scan_result = {"status": "Success", "metrics": {}}
    output = "test_report.png"
    res_path = generate_clinical_report(scan_result, output_path=output)
    
    assert res_path.endswith(".pdf")
    assert os.path.exists(res_path)
    os.remove(res_path)


def test_generate_clinical_report_all_sections():
    scan_result = {"status": "Success", "verdict": "Stable", "metrics": {}}
    volume_result = {"volume_cm3": 450.5, "model": "elliptical_cylinder"}
    shape_result = {"score": 88.0, "grade": "A"}
    symmetry_result = {"status": "Success", "risk_level": "low", "symmetry_indices": {"composite_pct": 2.1}}
    
    output = "full_test_report.pdf"
    res_path = generate_clinical_report(
        scan_result, volume_result, symmetry_result, shape_result,
        output_path=output, patient_name="Test Patient"
    )
    
    assert os.path.exists(res_path)
    os.remove(res_path)
