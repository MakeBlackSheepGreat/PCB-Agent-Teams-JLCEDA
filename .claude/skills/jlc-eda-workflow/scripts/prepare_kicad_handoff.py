#!/usr/bin/env python3
"""Prepare a checked KiCad design snapshot for EasyEDA Pro import.

The script never converts or overwrites an EasyEDA Pro project. It records the
exact KiCad source files, hashes, board metrics, and optional kicad-cli check
reports so an agent can hand a reviewed KiCad design to EasyEDA Pro without
losing traceability.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_board_constraints import validate_file


HANDOFF_FORMAT = "jlceda-kicad-handoff/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _select_source(kicad_dir: Path, suffix: str, project_name: str | None) -> Path:
    candidates = sorted(kicad_dir.glob(f"*{suffix}"))
    if project_name:
        candidate = kicad_dir / f"{project_name}{suffix}"
        if candidate.is_file():
            return candidate
        raise ValueError(f"Expected {candidate.name} in {kicad_dir}.")
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"No {suffix} file found in {kicad_dir}.")
    rendered = ", ".join(path.name for path in candidates)
    raise ValueError(f"Multiple {suffix} files found in {kicad_dir}: {rendered}. Use --project.")


def _relative(project_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(path)


def board_metrics(board_path: Path) -> dict[str, int]:
    text = board_path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "footprints": r"(?m)^\s*\(footprint(?:\s|\")",
        "nets": r"(?m)^\s*\(net\s+\d+\s+\"",
        "tracks": r"(?m)^\s*\(segment(?:\s|$)",
        "vias": r"(?m)^\s*\(via(?:\s|$)",
        "zones": r"(?m)^\s*\(zone(?:\s|$)",
        "edge_primitives": r"(?m)^\s*\(gr_(?:line|arc|rect|poly|circle)(?:\s|$)",
    }
    return {name: len(re.findall(pattern, text)) for name, pattern in patterns.items()}


def _run_command(command: list[str], report_path: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "unavailable", "command": command, "reason": "kicad-cli not found"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "command": command, "reason": "timed out after 180 seconds"}

    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "command": command,
        "exit_code": completed.returncode,
        "report": str(report_path) if report_path.is_file() else None,
        "stderr": completed.stderr[-1200:] if completed.stderr else "",
    }


def run_kicad_checks(kicad_cli: str, schematic: Path, board: Path, checks_dir: Path) -> dict[str, Any]:
    checks_dir.mkdir(parents=True, exist_ok=True)
    executable = shutil.which(kicad_cli) or kicad_cli
    erc_report = checks_dir / "kicad_erc.json"
    drc_report = checks_dir / "kicad_drc.json"
    return {
        "erc": _run_command(
            [executable, "sch", "erc", "--output", str(erc_report), str(schematic)],
            erc_report,
        ),
        "drc": _run_command(
            [executable, "pcb", "drc", "--output", str(drc_report), str(board)],
            drc_report,
        ),
    }


def prepare_handoff(
    project_dir: Path,
    *,
    project_name: str | None = None,
    run_checks: bool = False,
    kicad_cli: str = "kicad-cli",
    output: Path | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    kicad_dir = project_dir / "kicad"
    if not kicad_dir.is_dir():
        raise ValueError(f"KiCad directory does not exist: {kicad_dir}")

    schematic = _select_source(kicad_dir, ".kicad_sch", project_name)
    board = _select_source(kicad_dir, ".kicad_pcb", project_name)
    candidate_project = kicad_dir / f"{schematic.stem}.kicad_pro"
    project_file = candidate_project if candidate_project.is_file() else None

    handoff_dir = project_dir / "handoff"
    checks_dir = handoff_dir / "kicad_checks"
    constraints = validate_file(project_dir / "constraints" / "board_constraints.json")
    checks: dict[str, Any]
    if run_checks:
        checks = run_kicad_checks(kicad_cli, schematic, board, checks_dir)
        for check in checks.values():
            report = check.get("report")
            if report:
                report_path = Path(report)
                check["report"] = _relative(project_dir, report_path)
    else:
        checks = {"erc": {"status": "not_run"}, "drc": {"status": "not_run"}}

    source_files = {
        "schematic": {"path": _relative(project_dir, schematic), "sha256": sha256(schematic)},
        "board": {"path": _relative(project_dir, board), "sha256": sha256(board)},
    }
    if project_file:
        source_files["project"] = {"path": _relative(project_dir, project_file), "sha256": sha256(project_file)}

    manifest: dict[str, Any] = {
        "format": HANDOFF_FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_of_truth": "kicad",
        "easyeda_role": "imported manufacturing mirror",
        "source_files": source_files,
        "board_metrics": board_metrics(board),
        "constraints": constraints,
        "checks": checks,
        "easyeda_import_requirements": [
            "Import the recorded KiCad schematic and PCB into EasyEDA Pro as one reviewed snapshot.",
            "Run EasyEDA Pro ERC and DRC after import because its rules and libraries can differ from KiCad.",
            "Record every EasyEDA Pro edit as an ECO and apply the same change to KiCad before the next handoff.",
            "Use the JLCEDA Design Companion only after placement, board stackup, and constraints are confirmed.",
        ],
    }

    output = output or handoff_dir / "kicad_to_easyeda.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a KiCad to EasyEDA Pro handoff manifest.")
    parser.add_argument("project_dir", type=Path, help="Project directory containing kicad/.")
    parser.add_argument("--project", help="KiCad file stem when kicad/ holds multiple designs.")
    parser.add_argument("--run-checks", action="store_true", help="Run kicad-cli ERC and DRC before writing the manifest.")
    parser.add_argument("--require-complete-constraints", action="store_true", help="Fail when constraints contain errors or unconfigured fields.")
    parser.add_argument("--require-clean-checks", action="store_true", help="Fail when requested KiCad ERC or DRC checks do not pass.")
    parser.add_argument("--kicad-cli", default="kicad-cli")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        manifest = prepare_handoff(
            args.project_dir,
            project_name=args.project,
            run_checks=args.run_checks,
            kicad_cli=args.kicad_cli,
            output=args.output,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.require_complete_constraints and manifest["constraints"]["verdict"] != "pass":
        print("Error: physical constraints are incomplete or invalid.", file=sys.stderr)
        return 1
    if args.require_clean_checks and any(check.get("status") != "pass" for check in manifest["checks"].values()):
        print("Error: KiCad ERC or DRC did not pass.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
