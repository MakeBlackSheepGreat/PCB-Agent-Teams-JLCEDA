#!/usr/bin/env python3
"""Validate machine-readable physical constraints for a hybrid PCB project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


FORMAT = "pcb-agent-constraints/v1"
MANUFACTURING_FIELDS = (
    "minimum_track_width_mm",
    "minimum_clearance_mm",
    "minimum_via_diameter_mm",
    "minimum_via_drill_mm",
    "board_edge_clearance_mm",
)


def _finding(findings: list[dict[str, str]], severity: str, code: str, message: str) -> None:
    findings.append({"severity": severity, "code": code, "message": message})


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def validate(data: Any) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    report: dict[str, Any] = {"format": FORMAT, "findings": findings}
    if not isinstance(data, dict):
        _finding(findings, "error", "CONSTRAINTS_FORMAT", "Constraint file must contain a JSON object.")
        report["verdict"] = "fail"
        return report
    if data.get("format") != FORMAT:
        _finding(findings, "error", "CONSTRAINTS_VERSION", f"format must be {FORMAT}.")

    board = data.get("board")
    if not isinstance(board, dict):
        _finding(findings, "error", "BOARD_FORMAT", "board must be an object.")
        board = {}
    for field in ("width_mm", "height_mm"):
        value = board.get(field)
        if value is None:
            _finding(findings, "warning", "BOARD_DIMENSION_MISSING", f"board.{field} is not configured.")
        elif not _positive_number(value):
            _finding(findings, "error", "BOARD_DIMENSION_INVALID", f"board.{field} must be a positive number.")
    layer_count = board.get("layer_count")
    if layer_count is None:
        _finding(findings, "warning", "LAYER_COUNT_MISSING", "board.layer_count is not configured.")
    elif not isinstance(layer_count, int) or isinstance(layer_count, bool) or layer_count < 2 or layer_count % 2:
        _finding(findings, "error", "LAYER_COUNT_INVALID", "board.layer_count must be an even integer of at least 2.")

    manufacturing = data.get("manufacturing")
    if not isinstance(manufacturing, dict):
        _finding(findings, "error", "MANUFACTURING_FORMAT", "manufacturing must be an object.")
        manufacturing = {}
    configured: dict[str, float] = {}
    for field in MANUFACTURING_FIELDS:
        value = manufacturing.get(field)
        if value is None:
            _finding(findings, "warning", "MANUFACTURING_LIMIT_MISSING", f"manufacturing.{field} is not configured.")
        elif not _positive_number(value):
            _finding(findings, "error", "MANUFACTURING_LIMIT_INVALID", f"manufacturing.{field} must be a positive number.")
        else:
            configured[field] = float(value)
    if {
        "minimum_via_diameter_mm",
        "minimum_via_drill_mm",
    } <= configured.keys() and configured["minimum_via_drill_mm"] >= configured["minimum_via_diameter_mm"]:
        _finding(findings, "error", "VIA_GEOMETRY", "Via drill must be smaller than via diameter.")

    net_classes = data.get("net_classes")
    if not isinstance(net_classes, list):
        _finding(findings, "error", "NET_CLASSES_FORMAT", "net_classes must be an array.")
    elif not net_classes:
        _finding(findings, "warning", "NET_CLASSES_EMPTY", "No network-level rules are configured.")
    else:
        names: set[str] = set()
        for index, rule in enumerate(net_classes):
            if not isinstance(rule, dict):
                _finding(findings, "error", "NET_CLASS_FORMAT", f"net_classes[{index}] must be an object.")
                continue
            name = rule.get("name")
            if not isinstance(name, str) or not name.strip():
                _finding(findings, "error", "NET_CLASS_NAME", f"net_classes[{index}].name is required.")
            elif name in names:
                _finding(findings, "error", "NET_CLASS_DUPLICATE", f"Duplicate net class: {name}.")
            else:
                names.add(name)
            for field in ("minimum_width_mm", "minimum_clearance_mm", "maximum_length_mm", "maximum_current_a"):
                value = rule.get(field)
                if value is not None and not _positive_number(value):
                    _finding(findings, "error", "NET_CLASS_LIMIT_INVALID", f"net_classes[{index}].{field} must be positive when set.")

    pairs = data.get("differential_pairs")
    if not isinstance(pairs, list):
        _finding(findings, "error", "DIFF_PAIRS_FORMAT", "differential_pairs must be an array.")
    else:
        for index, pair in enumerate(pairs):
            if not isinstance(pair, dict):
                _finding(findings, "error", "DIFF_PAIR_FORMAT", f"differential_pairs[{index}] must be an object.")
                continue
            for field in ("positive_net", "negative_net"):
                if not isinstance(pair.get(field), str) or not pair[field].strip():
                    _finding(findings, "error", "DIFF_PAIR_NET", f"differential_pairs[{index}].{field} is required.")
            for field in ("target_impedance_ohm", "pair_gap_mm", "maximum_skew_mm"):
                value = pair.get(field)
                if value is not None and not _positive_number(value):
                    _finding(findings, "error", "DIFF_PAIR_LIMIT_INVALID", f"differential_pairs[{index}].{field} must be positive when set.")

    severities = {finding["severity"] for finding in findings}
    report["verdict"] = "fail" if "error" in severities else "warning" if "warning" in severities else "pass"
    return report


def validate_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"format": FORMAT, "verdict": "fail", "findings": [{"severity": "error", "code": "CONSTRAINTS_MISSING", "message": f"Constraint file does not exist: {path}"}]}
    except json.JSONDecodeError as exc:
        return {"format": FORMAT, "verdict": "fail", "findings": [{"severity": "error", "code": "CONSTRAINTS_JSON", "message": str(exc)}]}
    report = validate(data)
    report["input"] = str(path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a PCB Agent constraint JSON file.")
    parser.add_argument("constraints", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = validate_file(args.constraints)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if report["verdict"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
