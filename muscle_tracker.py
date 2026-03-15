#!/usr/bin/env python3
"""
Muscle Tracker v2.0 — Clinical Muscle Growth Analysis Suite

Commands:
  growth       Compare before/after images for muscle growth
  volumetrics  Estimate 3D muscle volume from front + side views
  symmetry     Compare left vs right limbs for imbalance
  shape-check  Score muscle shape against pro physique templates
  report       Generate a full clinical report image
"""
import sys
import argparse
import json
import os
import logging

from core.vision_medical import analyze_muscle_growth
from core.volumetrics import estimate_muscle_volume, compare_volumes
from core.symmetry import compare_symmetry
from core.segmentation import score_muscle_shape, AVAILABLE_TEMPLATES
from core.visualization import generate_growth_heatmap, generate_side_by_side
from core.report_generator import generate_clinical_report
from core.pose_analyzer import analyze_pose, POSE_RULES


def main():
    parser = argparse.ArgumentParser(
        description='Muscle Tracker v2.0 — Clinical Muscle Growth Analysis Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable detailed logging')
    parser.add_argument('--output-format', choices=['json', 'text'], default='json',
                        help='Output format (default: json)')

    subparsers = parser.add_subparsers(dest='command', help='Analysis command')

    # --- GROWTH ---
    growth_p = subparsers.add_parser('growth', help='Compare before/after images')
    growth_p.add_argument('--before', required=True, help='Before image path')
    growth_p.add_argument('--after', required=True, help='After image path')
    growth_p.add_argument('--marker-size', type=float, default=20.0,
                          help='Calibration marker size in mm (default: 20)')
    growth_p.add_argument('--no-align', action='store_true',
                          help='Skip auto-alignment')
    growth_p.add_argument('--heatmap', help='Output path for growth heatmap')
    growth_p.add_argument('--side-by-side', help='Output path for side-by-side comparison')

    # --- VOLUMETRICS ---
    vol_p = subparsers.add_parser('volumetrics', help='Estimate muscle volume (cm3)')
    vol_p.add_argument('--front', required=True, help='Front view image')
    vol_p.add_argument('--side', required=True, help='Side view image')
    vol_p.add_argument('--marker-size', type=float, default=20.0)
    vol_p.add_argument('--model', choices=['elliptical_cylinder', 'prismatoid'],
                        default='elliptical_cylinder', help='Volume estimation model')

    # --- SYMMETRY ---
    sym_p = subparsers.add_parser('symmetry', help='Compare left vs right limbs')
    sym_p.add_argument('--left', required=True, help='Left limb image')
    sym_p.add_argument('--right', required=True, help='Right limb image')
    sym_p.add_argument('--marker-size', type=float, default=20.0)
    sym_p.add_argument('--muscle-group', help='Muscle group name')

    # --- SHAPE CHECK ---
    shape_p = subparsers.add_parser('shape-check', help='Score muscle shape')
    shape_p.add_argument('--image', required=True, help='Muscle image to score')
    shape_p.add_argument('--template', required=True,
                         choices=AVAILABLE_TEMPLATES,
                         help='Pro template to compare against')
    shape_p.add_argument('--marker-size', type=float, default=20.0)

    # --- POSE CHECK ---
    pose_p = subparsers.add_parser('pose-check', help='Check pose and get correction instructions')
    pose_p.add_argument('--image', required=True, help='Image to analyze')
    pose_p.add_argument('--muscle-group', default='bicep',
                        choices=list(POSE_RULES.keys()),
                        help='Target muscle group (default: bicep)')

    # --- REPORT ---
    report_p = subparsers.add_parser('report', help='Generate clinical report')
    report_p.add_argument('--front', required=True, help='Front view image')
    report_p.add_argument('--side', required=True, help='Side view image')
    report_p.add_argument('--before', help='Previous scan (for growth comparison)')
    report_p.add_argument('--marker-size', type=float, default=20.0)
    report_p.add_argument('--model', default='elliptical_cylinder')
    report_p.add_argument('--template', choices=AVAILABLE_TEMPLATES,
                          help='Shape template for scoring')
    report_p.add_argument('--patient', default='Patient', help='Patient name')
    report_p.add_argument('--output', default='report.png', help='Output report path')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(name)s | %(levelname)s | %(message)s')
    else:
        logging.basicConfig(level=logging.WARNING)

    if not args.command:
        parser.print_help()
        return

    # Dispatch
    handlers = {
        'growth': _cmd_growth,
        'volumetrics': _cmd_volumetrics,
        'symmetry': _cmd_symmetry,
        'shape-check': _cmd_shape_check,
        'pose-check': _cmd_pose_check,
        'report': _cmd_report,
    }

    result = handlers[args.command](args)
    _output(result, args.output_format)


def _cmd_growth(args):
    """Handle the growth comparison command."""
    for path in (args.before, args.after):
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}

    result = analyze_muscle_growth(
        args.before, args.after,
        marker_size_mm=args.marker_size,
        align=not args.no_align
    )

    if "error" in result:
        return result

    # Remove non-serializable raw data for output
    output = {k: v for k, v in result.items() if k != 'raw_data'}

    # Generate visuals if requested
    if args.heatmap:
        generate_growth_heatmap(
            result['raw_data']['img_a'], result['raw_data']['img_b'],
            result['raw_data']['contour_a'], result['raw_data']['contour_b'],
            args.heatmap, result['metrics']
        )
        output['heatmap_path'] = args.heatmap

    if args.side_by_side:
        generate_side_by_side(
            result['raw_data']['img_a'], result['raw_data']['img_b'],
            result['raw_data']['contour_a'], result['raw_data']['contour_b'],
            args.side_by_side
        )
        output['side_by_side_path'] = args.side_by_side

    return output


def _cmd_volumetrics(args):
    """Handle the volumetrics command."""
    for path in (args.front, args.side):
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}

    res_f = analyze_muscle_growth(args.front, args.front,
                                  args.marker_size, align=False)
    res_s = analyze_muscle_growth(args.side, args.side,
                                  args.marker_size, align=False)

    if "error" in res_f:
        return {"error": f"Front view: {res_f['error']}"}
    if "error" in res_s:
        return {"error": f"Side view: {res_s['error']}"}

    unit = "mm" if res_f.get("calibrated") else "px"
    area_f = res_f['metrics'].get(f'area_a_{unit}2', 0.0)
    area_s = res_s['metrics'].get(f'area_a_{unit}2', 0.0)
    width_f = res_f['metrics'].get(f'width_a_{unit}', 0.0)
    width_s = res_s['metrics'].get(f'width_a_{unit}', 0.0)

    vol_result = estimate_muscle_volume(area_f, area_s, width_f, width_s, args.model)

    return {
        "status": "Success",
        "type": "Volumetric Mass Estimation",
        "calibrated": res_f.get("calibrated", False),
        **vol_result,
        "input_metrics": {
            f"front_area_{unit}2": area_f,
            f"side_area_{unit}2": area_s,
            f"front_width_{unit}": width_f,
            f"side_width_{unit}": width_s,
        }
    }


def _cmd_symmetry(args):
    """Handle the symmetry command."""
    for path in (args.left, args.right):
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}

    return compare_symmetry(args.left, args.right,
                            args.marker_size, args.muscle_group)


def _cmd_pose_check(args):
    """Handle the pose-check command."""
    if not os.path.exists(args.image):
        return {"error": f"File not found: {args.image}"}

    import cv2
    img = cv2.imread(args.image)
    if img is None:
        return {"error": f"Could not read image: {args.image}"}

    result = analyze_pose(img, args.muscle_group)

    if result.get("status") == "ok":
        result["message"] = "Pose is good for measurement."
    elif result.get("corrections"):
        instructions = [c["instruction"] for c in result["corrections"]]
        result["message"] = "Adjust your pose: " + "; ".join(instructions)

    return result


def _cmd_shape_check(args):
    """Handle the shape-check command."""
    if not os.path.exists(args.image):
        return {"error": f"File not found: {args.image}"}

    result = analyze_muscle_growth(args.image, args.image,
                                   args.marker_size, align=False)
    if "error" in result:
        return result

    contour = result['raw_data']['contour_a']
    shape_result = score_muscle_shape(contour, args.template)
    shape_result["calibrated"] = result.get("calibrated", False)
    return shape_result


def _cmd_report(args):
    """Handle the full report generation command."""
    for path in (args.front, args.side):
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}

    # Volumetrics
    res_f = analyze_muscle_growth(args.front, args.front,
                                  args.marker_size, align=False)
    res_s = analyze_muscle_growth(args.side, args.side,
                                  args.marker_size, align=False)

    if "error" in res_f or "error" in res_s:
        return {"error": "Vision analysis failed"}

    unit = "mm" if res_f.get("calibrated") else "px"
    vol_result = estimate_muscle_volume(
        res_f['metrics'].get(f'area_a_{unit}2', 0.0),
        res_s['metrics'].get(f'area_a_{unit}2', 0.0),
        res_f['metrics'].get(f'width_a_{unit}', 0.0),
        res_s['metrics'].get(f'width_a_{unit}', 0.0),
        args.model
    )

    # Growth comparison (if before image provided)
    scan_result = None
    if args.before and os.path.exists(args.before):
        scan_result = analyze_muscle_growth(
            args.before, args.front, args.marker_size)
        if "error" in scan_result:
            scan_result = None

    # Shape scoring (if template provided)
    shape_result = None
    if args.template:
        contour = res_f['raw_data']['contour_a']
        shape_result = score_muscle_shape(contour, args.template)

    # Build the scan result for report (use front view analysis)
    report_scan = {k: v for k, v in res_f.items() if k != 'raw_data'}
    if scan_result:
        report_scan = {k: v for k, v in scan_result.items() if k != 'raw_data'}

    report_path = generate_clinical_report(
        scan_result=report_scan,
        volume_result=vol_result,
        shape_result=shape_result,
        output_path=args.output,
        patient_name=args.patient,
    )

    return {
        "status": "Success",
        "report_path": report_path,
        "volume_cm3": vol_result.get("volume_cm3"),
        "shape_score": shape_result.get("score") if shape_result else None,
    }


def _output(result, fmt):
    """Print result in the requested format."""
    if fmt == 'json':
        print(json.dumps(result, indent=2, default=str))
    else:
        for key, val in result.items():
            if isinstance(val, dict):
                print(f"\n{key}:")
                for k, v in val.items():
                    print(f"  {k}: {v}")
            else:
                print(f"{key}: {val}")


if __name__ == '__main__':
    main()
