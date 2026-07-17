"""Phase D — orchestrate A→B→C and apply via the existing pcbnew helper.

This module is the .venv-side entry point. It:
    1. Parses .kicad_pcb via sexp_parser (no pcbnew dep)
    2. Runs partition (Phase A)
    3. Runs floorplan (Phase B)
    4. Runs SA per region (Phase C)
    5. Calls _kicad_python_helper.py mode=apply_layout to write back

Project hints come from CLAUDE.md placement section. The orchestrator
parses that section deterministically — no LLM in the loop.

CLAUDE.md placement schema (all optional):

    placement:
      algorithm: v2                      # opt-in; default falls back to v1
      orientation: horizontal            # or 'vertical'
      board_min_w: 60                    # mm (chassis fit)
      board_min_h: 45
      anchors:                           # manual region overrides
        J1: HV
        J2: LV
      isolation_slots:
        - between: [HV, ISO]
          width_mm: 4.0
          reason: "AMC1311 reinforced 5kV"
      chains:
        - members: [J1, R1, R2, R3, R4]
          axis: y                        # optional
      decoupling_pairs:
        - [C8, U1]
        - [C11, U1]
      region_regex:                      # only when project diverges from defaults
        HV: "..."
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

# Local imports
# Path updated 2026-05 after skill consolidation: kicad/scripts/ → check-pcb/scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
sys.path.insert(0, str(SCRIPT_DIR.parent.parent.parent / "check-pcb" / "scripts"))

from placement_v2.partition import (
    DEFAULT_REGION_REGEX,
    DEFAULT_VALUE_REGEX,
    partition_components,
    summarize as partition_summarize,
)
from placement_v2.floorplan import (
    Floorplan,
    Rect,
    courtyard_area_by_region,
    plan_floorplan,
)
from placement_v2.layout import (
    PlacementProblem,
    run_layout,
)


# CLAUDE.md parsing --------------------------------------------------------

_YAML_BLOCK_RE = re.compile(
    r"```(?:yaml|yml)\s*\n(.*?)\n```",
    re.DOTALL,
)
_PLACEMENT_HEADING_RE = re.compile(
    r"^##\s*(?:\d+\.\s*)?(?:placement|布局|Placement).*?$\s*(.*?)(?=^##|\Z)",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)


def parse_claude_md_placement(md_path: Optional[Path]) -> Dict:
    """Pull placement config out of project CLAUDE.md.

    Looks for a YAML code block under a heading like '## placement' or
    '## 布局'. Returns {} if no such section. Schema see module docstring.
    """
    if not md_path or not Path(md_path).is_file():
        return {}
    text = Path(md_path).read_text(encoding="utf-8")

    # Try fenced YAML in placement section first.
    section_match = _PLACEMENT_HEADING_RE.search(text)
    if not section_match:
        return {}
    section = section_match.group(1)
    yaml_match = _YAML_BLOCK_RE.search(section)
    if not yaml_match:
        return {}
    raw = yaml_match.group(1)
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw) or {}
    except ImportError:
        # Fallback: hand-parse a tiny subset (key: value, lists with `-`).
        data = _minimal_yaml(raw)
    if not isinstance(data, dict):
        return {}
    # Accept either flat keys or nested under 'placement'
    if "placement" in data and isinstance(data["placement"], dict):
        return data["placement"]
    return data


def _minimal_yaml(raw: str) -> Dict:
    """Fallback when PyYAML isn't available — handles enough of our schema."""
    out: Dict = {}
    stack: List[Tuple[int, dict]] = [(0, out)]
    cur_list = None
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        # Pop deeper frames.
        while stack and stack[-1][0] > indent:
            stack.pop()
        body = line.strip()
        parent = stack[-1][1]
        if body.startswith("- "):
            item_body = body[2:]
            if isinstance(parent, list):
                if ":" in item_body:
                    new = {}
                    parent.append(new)
                    k, v = item_body.split(":", 1)
                    new[k.strip()] = _coerce(v.strip())
                    stack.append((indent + 2, new))
                else:
                    parent.append(_coerce(item_body))
            continue
        if ":" in body:
            k, v = body.split(":", 1)
            k = k.strip()
            v = v.strip()
            if not v:
                # Could be dict or list — peek next line later. Default dict.
                new: object = {}
                if isinstance(parent, dict):
                    parent[k] = new
                stack.append((indent + 2, new))
            else:
                parent[k] = _coerce(v)
    return out


def _coerce(v: str):
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_coerce(x.strip()) for x in inner.split(",")]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v.strip("\"'")


# .kicad_pcb extraction (sexp, no pcbnew) ---------------------------------

def extract_pcb_data(pcb_path: Path) -> Tuple[Dict[str, Set[str]],
                                                Dict[str, str],
                                                Dict[str, Tuple[float, float]]]:
    """Pull (footprint_nets, footprint_values, footprint_sizes) from a .kicad_pcb.

    Sizes use bounding box from (size ...) sexp child; for footprints
    without a (size ...) we approximate from courtyard polyline if any,
    otherwise default 3×3mm.
    """
    sys.path.insert(0, str(SCRIPT_DIR.parent.parent.parent / "check-pcb" / "scripts"))
    from sexp_parser import parse_file
    pcb = parse_file(str(pcb_path))

    fp_nets: Dict[str, Set[str]] = {}
    fp_values: Dict[str, str] = {}
    fp_sizes: Dict[str, Tuple[float, float]] = {}

    def visit(node):
        if not isinstance(node, list):
            return
        if node and node[0] == "footprint":
            ref = None
            value = ""
            nets: Set[str] = set()
            xs: List[float] = []
            ys: List[float] = []
            for c in node:
                if not isinstance(c, list):
                    continue
                head = c[0] if c else None
                if head == "property" and len(c) >= 3:
                    if c[1] == "Reference":
                        ref = c[2]
                    elif c[1] == "Value":
                        value = c[2]
                elif head == "pad":
                    # Walk into pad to find net + collect (at xy) for bbox.
                    for s in c:
                        if not isinstance(s, list):
                            continue
                        if s[0] == "net" and len(s) >= 2:
                            n = s[-1]
                            if isinstance(n, str):
                                nets.add(n)
                        elif s[0] == "at" and len(s) >= 3:
                            try:
                                xs.append(float(s[1]))
                                ys.append(float(s[2]))
                            except (TypeError, ValueError):
                                pass
            if ref:
                fp_nets[ref] = nets
                fp_values[ref] = value
                # Per-class padding: connectors (J*, switches SW*) and TVS-style
                # parts (D* through-hole) have much larger physical bodies than
                # the pad bbox suggests — KiCad courtyard typically extends 2-3mm
                # beyond pads (terminal block bodies are ~10mm tall vs 5mm pad
                # span). SMD passives need only ~1.5mm margin.
                if ref.startswith(("J", "SW")):
                    pad_extra = 6.0   # 5.08mm pitch terminal blocks, headers
                    min_dim = 6.0
                elif ref.startswith("D") and value and any(
                    k in value.upper() for k in ("SMA", "SMB", "TVS", "SMAJ")
                ):
                    pad_extra = 3.5   # SMA/SMB TVS bodies
                    min_dim = 4.0
                elif ref.startswith("U"):
                    pad_extra = 3.5   # IC packages, SOIC/DFN courtyards
                    min_dim = 4.0
                else:
                    pad_extra = 2.5   # SMD passives 0805/1206
                    min_dim = 3.0
                if xs and ys:
                    w = max(xs) - min(xs) + pad_extra
                    h = max(ys) - min(ys) + pad_extra
                    fp_sizes[ref] = (max(w, min_dim), max(h, min_dim))
                else:
                    fp_sizes[ref] = (min_dim, min_dim)
            return
        for child in node:
            visit(child)

    visit(pcb)
    return fp_nets, fp_values, fp_sizes


# Apply via existing helper -----------------------------------------------

def _find_kicad_python() -> str:
    candidates = [
        "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
        "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9",
        "/usr/lib/kicad/python3",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return ""


def _call_helper(spec: Dict, timeout: int = 60) -> Dict:
    helper = SCRIPT_DIR.parent / "_kicad_python_helper.py"
    py = _find_kicad_python()
    if not py or not helper.exists():
        return {"ok": False, "error": "KiCad python or helper not found"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f, ensure_ascii=False)
        spec_path = f.name
    try:
        proc = subprocess.run([py, str(helper), "--input", spec_path],
                                capture_output=True, text=True, timeout=timeout)
    finally:
        Path(spec_path).unlink(missing_ok=True)
    if proc.returncode != 0 and not proc.stdout.strip():
        return {"ok": False, "error": "helper crashed",
                "stderr": proc.stderr[:1000]}
    # KiCad's pcbnew SWIG wrapper may emit "memory leak of type ..." lines
    # to stdout AFTER our JSON when board.Remove() is called. Pick the
    # first line that parses as JSON instead of just lines[-1].
    for ln in proc.stdout.strip().split("\n"):
        ln = ln.strip()
        if ln.startswith("{") and ln.endswith("}"):
            try:
                return json.loads(ln)
            except json.JSONDecodeError:
                continue
    return {"ok": False, "error": "no JSON line in helper output",
            "stdout": proc.stdout[:1000]}


# Main entry ---------------------------------------------------------------

def run_placement_v2(pcb_path: Path,
                     claude_md: Optional[Path] = None,
                     output_pcb: Optional[Path] = None,
                     seed: int = 42,
                     verbose: bool = True) -> Dict:
    """Run the full v2 pipeline. Returns a result dict with diagnostics."""
    pcb_path = Path(pcb_path)
    cfg = parse_claude_md_placement(claude_md)
    if verbose:
        print(f"[v2] Project hints: {list(cfg.keys()) or '(none)'}")

    fp_nets, fp_values, fp_sizes = extract_pcb_data(pcb_path)
    if verbose:
        print(f"[v2] Extracted {len(fp_nets)} footprints")

    # ----- Phase A: partition -----
    region_regex = cfg.get("region_regex") or DEFAULT_REGION_REGEX
    value_regex = cfg.get("value_regex") or DEFAULT_VALUE_REGEX
    anchors = cfg.get("anchors") or {}
    fp_nets_for_partition = {r: ns for r, ns in fp_nets.items()}
    assignments, diag = partition_components(
        fp_nets_for_partition,
        footprint_values=fp_values,
        region_regex=region_regex,
        value_regex=value_regex,
        anchors=anchors,
    )
    region_hist = partition_summarize(assignments)
    if verbose:
        print(f"[v2] Phase A partition: {region_hist}")

    # ----- Phase B: floorplan -----
    region_areas = courtyard_area_by_region(assignments, fp_sizes)
    fp = plan_floorplan(
        region_areas=region_areas,
        isolation_gaps=cfg.get("isolation_slots") or [],
        orientation=cfg.get("orientation", "horizontal"),
        aspect_ratio=float(cfg.get("aspect_ratio", 1.4)),
        pack_density=float(cfg.get("pack_density", 0.55)),
        board_margin=float(cfg.get("board_margin", 2.5)),
        region_order=cfg.get("region_order"),
        min_w=cfg.get("board_min_w"),
        min_h=cfg.get("board_min_h"),
    )
    if verbose:
        print(f"[v2] Phase B floorplan: board={fp.board.w:.1f}×{fp.board.h:.1f}mm "
              f"slots={len(fp.slots)}")

    # ----- Phase C: deterministic region layout (no SA) -----
    chains_cfg = cfg.get("chains") or []
    decap_cfg = cfg.get("decoupling_pairs") or []

    placements: Dict[str, Tuple[float, float, float]] = {}
    region_counts: Dict[str, int] = {}
    for region, rect in fp.regions.items():
        refs_in = [r for r, reg in assignments.items() if reg == region]
        if not refs_in:
            continue
        # Subset chains / decap pairs to this region only.
        chains_here = [
            [r for r in chain.get("members", []) if r in refs_in]
            for chain in chains_cfg if isinstance(chain, dict)
        ]
        chains_here = [c for c in chains_here if len(c) >= 2]
        decap_here = [
            (a, b) for (a, b) in (
                tuple(p) if isinstance(p, list) else (p[0], p[1])
                for p in decap_cfg
                if isinstance(p, (list, tuple)) and len(p) == 2
            ) if a in refs_in and b in refs_in
        ]
        keepouts = []
        for slot in fp.slots:
            kx = slot.x_mm - slot.width_mm / 2
            ky = slot.y_start
            kw = slot.width_mm
            kh = slot.y_end - slot.y_start
            keepouts.append((kx, ky, kw, kh))
        problem = PlacementProblem(
            refs=refs_in,
            fp_sizes={r: fp_sizes[r] for r in refs_in},
            region_rect=(rect.x, rect.y, rect.w, rect.h),
            chains=chains_here,
            decoupling_pairs=decap_here,
            keepouts=keepouts,
        )
        result, _ = run_layout(problem, seed=seed)
        placements.update(result)
        region_counts[region] = len(result)
    if verbose:
        for r, n in region_counts.items():
            print(f"[v2] Phase C layout {r}: {n} footprints placed")

    # ----- Phase D: writeback via existing helper -----
    # mode_apply_layout schema: placements as dict {ref: (x,y,rot)} and
    # board as {x_left,y_top,x_right,y_bot,margin,slot_x,slot_w} with a
    # single slot. v2 may produce 0 or N slots — for now we honor only
    # the first slot (matches the common galvanic-isolation case). Multi-
    # slot writeback is future work in a new helper mode.
    helper_placements = {ref: list(p) for ref, p in placements.items()}
    margin = float(cfg.get("board_margin", 2.5))
    if fp.slots:
        first = fp.slots[0]
        slot_x = first.x_mm - first.width_mm / 2
        slot_w = first.width_mm
    else:
        # No isolation slot — push slot outside the board so the helper's
        # slot edge lines fall outside the outer rect (visually invisible
        # because they coincide with / lie outside the outline). Better
        # long-term fix is a no-slot variant in the helper.
        slot_x = fp.board.w + 5.0
        slot_w = 0.5
    apply_spec = {
        "mode": "apply_layout",
        "pcb_path": str(pcb_path),
        "placements": helper_placements,
        "board": {
            "x_left": fp.board.x + margin,
            "y_top": fp.board.y + margin,
            "x_right": fp.board.right - margin,
            "y_bot": fp.board.bottom - margin,
            "margin": margin,
            # Multi-slot list (primary) + single-slot fallback the helper
            # also accepts.
            "slots": [s.to_dict() for s in fp.slots],
            "slot_x": slot_x,
            "slot_w": slot_w,
        },
        # v2: SA already enforced no-overlap via hard_overlap×1000 cost term.
        # Post-process pad sweep is unnecessary and breaks under some pcbnew
        # SWIG wrappers ('SwigPyObject has no Pads').
        # Phase 2.75 (resolve_pad_conflicts) in pipeline.py runs the pad sweep
        # in a fresh helper process — keep apply_layout's inline sweep skipped
        # to avoid the macOS SWIG 'SwigPyObject has no Pads' regression.
        "skip_pad_resolve": True,
        "output_pcb": str(output_pcb or pcb_path),
    }
    applied = _call_helper(apply_spec)
    if verbose:
        if applied.get("ok"):
            print(f"[v2] Phase D applied: {applied.get('footprints_placed','?')} footprints")
        else:
            print(f"[v2] Phase D apply error: {applied.get('error')}")

    return {
        "ok": applied.get("ok", False),
        "phase_a": {"region_histogram": region_hist,
                    "diagnostics": diag},
        "phase_b": {"floorplan": fp.to_dict()},
        "phase_c": {"region_counts": region_counts,
                    "placements": {r: list(p) for r, p in placements.items()}},
        "phase_d": applied,
    }


def main():
    import argparse
    p = argparse.ArgumentParser(description="placement v2 orchestrator")
    p.add_argument("pcb_path")
    p.add_argument("--claude-md")
    p.add_argument("--output")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    out = run_placement_v2(
        Path(args.pcb_path),
        claude_md=Path(args.claude_md) if args.claude_md else None,
        output_pcb=Path(args.output) if args.output else None,
        seed=args.seed,
        verbose=not args.quiet,
    )
    print()
    print(json.dumps({"ok": out["ok"], "summary": {
        "phase_a": out["phase_a"]["region_histogram"],
        "phase_b_board": out["phase_b"]["floorplan"]["board"],
        "phase_b_slots": len(out["phase_b"]["floorplan"]["slots"]),
        "phase_c_counts": out["phase_c"]["region_counts"],
        "phase_d_ok": out["phase_d"].get("ok"),
    }}, indent=2, ensure_ascii=False))
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
