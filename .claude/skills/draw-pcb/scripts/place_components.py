#!/usr/bin/env python3
"""Plan + apply component placement on a .kicad_pcb file.

Thin CLI wrapper around the deterministic v2 pipeline
(`placement_v2.orchestrator.run_placement_v2`) — partition → floorplan
→ region layout → writeback. Project CLAUDE.md may add a `## placement`
YAML block to refine the result (anchors / chains / decoupling_pairs /
isolation_slots); without it the pipeline uses sane defaults.

Usage:
  python place_components.py <pcb_file> [--claude-md <md>] [--output <pcb>]
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

SCRIPT_DIR = Path(__file__).resolve().parent


def run_placement(pcb_path: Path, claude_md_path: Optional[Path] = None,
                  board_w: Optional[float] = None, board_h: Optional[float] = None,
                  output_path: Optional[Path] = None) -> Dict:
    """Plan placement → apply to PCB via the v2 pipeline."""
    print(f"  PCB: {pcb_path}")

    sys.path.insert(0, str(SCRIPT_DIR))
    from placement_v2.orchestrator import run_placement_v2
    v2 = run_placement_v2(pcb_path, claude_md=claude_md_path,
                          output_pcb=output_path)
    return {
        "ok": v2.get("ok", False),
        "output_path": str(output_path or pcb_path),
        "zones": v2["phase_a"]["region_histogram"],
        "board": v2["phase_b"]["floorplan"]["board"],
        "slots": v2["phase_b"]["floorplan"]["slots"],
        "region_counts": v2["phase_c"]["region_counts"],
        "footprints_placed": v2["phase_d"].get("footprints_placed", 0),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pcb_file", type=Path)
    parser.add_argument("--claude-md", type=Path, default=None)
    parser.add_argument("--board-w", type=float, default=None)
    parser.add_argument("--board-h", type=float, default=None)
    parser.add_argument("--output", "-o", type=Path, default=None)
    args = parser.parse_args()

    result = run_placement(args.pcb_file, args.claude_md, args.board_w, args.board_h, args.output)

    out = dict(result)
    out.pop("placements", None)
    print("\n--- JSON ---")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)
