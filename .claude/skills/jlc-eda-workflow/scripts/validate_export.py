#!/usr/bin/env python3
"""Validate BOM, CPL, and Gerber exports produced by JLCEDA."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import sys
import zipfile


HEADER_ALIASES = {
    "designator": {"designator", "designators", "ref", "refdes", "referencedesignator"},
    "quantity": {"quantity", "qty", "components", "count"},
    "x": {"x", "midx", "centerx", "posx"},
    "y": {"y", "midy", "centery", "posy"},
    "layer": {"layer", "side", "boardlayer"},
    "rotation": {"rotation", "rot", "angle"},
}


def normalized(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"Cannot decode CSV: {path}") from last_error

    dialect = csv.excel
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        pass
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    headers = reader.fieldnames or []
    return headers, [{key: value or "" for key, value in row.items() if key} for row in reader]


def resolve_headers(headers: list[str], required: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in required:
        matches = HEADER_ALIASES[field]
        for header in headers:
            if normalized(header) in matches:
                result[field] = header
                break
    return result


def expand_designators(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\s]+", value) if item.strip()]


def is_number(value: str) -> bool:
    try:
        float(value.strip().removesuffix("mm").strip())
        return True
    except ValueError:
        return False


def add_finding(findings: list[dict[str, str]], severity: str, code: str, message: str) -> None:
    findings.append({"severity": severity, "code": code, "message": message})


def validate(bom_path: Path, cpl_path: Path, gerber_path: Path | None, require_all_cpl: bool) -> dict[str, object]:
    findings: list[dict[str, str]] = []
    report: dict[str, object] = {
        "inputs": {"bom": str(bom_path), "cpl": str(cpl_path), "gerber": str(gerber_path) if gerber_path else None},
        "findings": findings,
    }

    for path, kind in ((bom_path, "BOM"), (cpl_path, "CPL")):
        if not path.is_file():
            add_finding(findings, "error", f"{kind}_MISSING", f"{kind} file does not exist: {path}")
    if gerber_path and not gerber_path.is_file():
        add_finding(findings, "error", "GERBER_MISSING", f"Gerber archive does not exist: {gerber_path}")
    if any(item["severity"] == "error" for item in findings):
        report["verdict"] = "fail"
        return report

    try:
        bom_headers, bom_rows = read_csv(bom_path)
        cpl_headers, cpl_rows = read_csv(cpl_path)
    except ValueError as exc:
        add_finding(findings, "error", "CSV_DECODE", str(exc))
        report["verdict"] = "fail"
        return report

    bom_fields = resolve_headers(bom_headers, {"designator"})
    cpl_fields = resolve_headers(cpl_headers, {"designator", "x", "y", "layer", "rotation"})
    if "designator" not in bom_fields:
        add_finding(findings, "error", "BOM_HEADER", "BOM needs a Designator or RefDes column.")
    missing_cpl_fields = sorted({"designator", "x", "y", "layer", "rotation"} - cpl_fields.keys())
    if missing_cpl_fields:
        add_finding(findings, "error", "CPL_HEADER", f"CPL lacks required columns: {', '.join(missing_cpl_fields)}")
    if any(item["severity"] == "error" for item in findings):
        report["verdict"] = "fail"
        return report

    bom_refs: set[str] = set()
    for row in bom_rows:
        bom_refs.update(expand_designators(row[bom_fields["designator"]]))
    if not bom_refs:
        add_finding(findings, "error", "BOM_EMPTY", "BOM contains no designators.")

    cpl_refs: set[str] = set()
    duplicates: set[str] = set()
    invalid_coordinates: list[str] = []
    for row in cpl_rows:
        refs = expand_designators(row[cpl_fields["designator"]])
        for ref in refs:
            if ref in cpl_refs:
                duplicates.add(ref)
            cpl_refs.add(ref)
        if not is_number(row[cpl_fields["x"]]) or not is_number(row[cpl_fields["y"]]):
            invalid_coordinates.extend(refs or ["<blank>"])
        if not row[cpl_fields["layer"]].strip():
            add_finding(findings, "error", "CPL_LAYER", f"CPL row has no layer: {', '.join(refs or ['<blank>'])}")
        if not is_number(row[cpl_fields["rotation"]]):
            add_finding(findings, "error", "CPL_ROTATION", f"CPL row has invalid rotation: {', '.join(refs or ['<blank>'])}")

    if duplicates:
        add_finding(findings, "error", "CPL_DUPLICATE", f"Duplicate CPL designators: {', '.join(sorted(duplicates))}")
    if invalid_coordinates:
        add_finding(findings, "error", "CPL_COORDINATE", f"Invalid CPL coordinates: {', '.join(sorted(set(invalid_coordinates)))}")

    missing_from_bom = cpl_refs - bom_refs
    if missing_from_bom:
        add_finding(findings, "error", "CPL_UNKNOWN_REF", f"CPL references absent from BOM: {', '.join(sorted(missing_from_bom))}")
    missing_from_cpl = bom_refs - cpl_refs
    if missing_from_cpl:
        severity = "error" if require_all_cpl else "warning"
        add_finding(findings, severity, "CPL_MISSING_REF", f"BOM references absent from CPL: {', '.join(sorted(missing_from_cpl))}")

    report["bom"] = {"rows": len(bom_rows), "designators": len(bom_refs)}
    report["cpl"] = {"rows": len(cpl_rows), "designators": len(cpl_refs)}

    if gerber_path and gerber_path.is_file():
        if not zipfile.is_zipfile(gerber_path):
            add_finding(findings, "error", "GERBER_ARCHIVE", "Gerber export must be a ZIP archive.")
        else:
            with zipfile.ZipFile(gerber_path) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
            extensions = {Path(name).suffix.casefold() for name in names}
            if not names:
                add_finding(findings, "error", "GERBER_EMPTY", "Gerber archive is empty.")
            if not ({".gbr", ".gtl", ".gbl", ".gko", ".gm1"} & extensions):
                add_finding(findings, "error", "GERBER_LAYERS", "Gerber archive has no recognized board layer files.")
            if not ({".drl", ".txt"} & extensions):
                add_finding(findings, "warning", "GERBER_DRILL", "No recognized drill file was found in the archive.")
            report["gerber"] = {"files": len(names), "extensions": sorted(extensions)}

    severities = {item["severity"] for item in findings}
    report["verdict"] = "fail" if "error" in severities else "warning" if "warning" in severities else "pass"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a JLCEDA export package.")
    parser.add_argument("--bom", required=True, type=Path)
    parser.add_argument("--cpl", required=True, type=Path)
    parser.add_argument("--gerber", type=Path)
    parser.add_argument("--require-all-cpl", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = validate(args.bom, args.cpl, args.gerber, args.require_all_cpl)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if report["verdict"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
