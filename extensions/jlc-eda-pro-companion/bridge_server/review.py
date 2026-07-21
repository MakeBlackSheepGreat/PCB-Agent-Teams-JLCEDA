"""Fast, dependency-free preflight checks for EasyEDA Pro PCB payloads."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _finding(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _net_name(value: Any) -> str:
    return str(value or "").strip()


def _diff_pair_bases(nets: set[str]) -> list[str]:
    bases: set[str] = set()
    for net in nets:
        upper = net.upper()
        for positive, negative in (("_P", "_N"), ("+", "-")):
            if upper.endswith(positive) and f"{net[:-len(positive)]}{negative}" in nets:
                bases.add(net[:-len(positive)])
    return sorted(bases)


def build_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic checks before routing or exporting a PCB."""
    board = payload.get("board") if isinstance(payload.get("board"), dict) else {}
    components = payload.get("components") if isinstance(payload.get("components"), list) else []
    nets = {_net_name(net) for net in payload.get("nets", []) if _net_name(net)}
    tracks = payload.get("existing_tracks") if isinstance(payload.get("existing_tracks"), list) else []
    vias = payload.get("existing_vias") if isinstance(payload.get("existing_vias"), list) else []
    findings: list[dict[str, str]] = []

    outline_count = len(board.get("outline", [])) + len(board.get("outlineLines", [])) + len(board.get("outline_lines", []))
    outline_count += len(board.get("outlineArcs", [])) + len(board.get("outline_arcs", []))
    layers = board.get("layers", []) if isinstance(board.get("layers"), list) else []

    designators: list[str] = []
    pad_count = 0
    pads_without_net: list[str] = []
    unknown_pad_nets: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            continue
        designator = _net_name(component.get("designator"))
        if designator:
            designators.append(designator)
        for pad in component.get("pads", []) if isinstance(component.get("pads"), list) else []:
            if not isinstance(pad, dict):
                continue
            pad_count += 1
            net = _net_name(pad.get("net"))
            pad_label = f"{designator or '<unnamed>'}.{_net_name(pad.get('number')) or '?'}"
            if not net:
                pads_without_net.append(pad_label)
            elif net not in nets:
                unknown_pad_nets.add(net)

    duplicates = sorted(name for name, count in Counter(designators).items() if count > 1)
    if not outline_count:
        findings.append(_finding("error", "BOARD_OUTLINE_MISSING", "No board outline was supplied by EasyEDA Pro."))
    if not components:
        findings.append(_finding("error", "COMPONENTS_MISSING", "The PCB payload contains no components."))
    if not nets:
        findings.append(_finding("error", "NETS_MISSING", "The PCB payload contains no routable nets."))
    if not layers:
        findings.append(_finding("error", "LAYERS_MISSING", "The PCB payload contains no copper layers."))
    if duplicates:
        findings.append(_finding("error", "DUPLICATE_DESIGNATOR", f"Duplicate component designators: {', '.join(duplicates)}"))
    if pads_without_net:
        findings.append(_finding("warning", "PADS_WITHOUT_NET", f"Pads without a net: {', '.join(pads_without_net[:12])}"))
    if unknown_pad_nets:
        findings.append(_finding("error", "UNKNOWN_PAD_NET", f"Pad nets absent from the board net list: {', '.join(sorted(unknown_pad_nets))}"))
    if pad_count == 0:
        findings.append(_finding("warning", "PADS_MISSING", "No component pads were collected; routing and analysis will be incomplete."))
    if not tracks:
        findings.append(_finding("warning", "NO_TRACKS", "No existing tracks were collected. Confirm that this is an unrouted board."))

    power_nets = sorted(net for net in nets if any(token in net.upper() for token in ("GND", "VCC", "VDD", "VBUS", "VIN", "VOUT", "3V3", "5V")))
    diff_pairs = _diff_pair_bases(nets)
    routing = payload.get("routing_config") if isinstance(payload.get("routing_config"), dict) else {}
    requested_nets = {_net_name(net) for net in routing.get("nets_to_route", []) if _net_name(net) and net != "*"}
    missing_requested = sorted(requested_nets - nets)
    if missing_requested:
        findings.append(_finding("error", "UNKNOWN_TARGET_NET", f"Requested routing nets are absent: {', '.join(missing_requested)}"))

    severities = {finding["severity"] for finding in findings}
    verdict = "fail" if "error" in severities else "warning" if "warning" in severities else "pass"
    score = max(0, 100 - 40 * sum(item["severity"] == "error" for item in findings) - 10 * sum(item["severity"] == "warning" for item in findings))
    return {
        "verdict": verdict,
        "readiness_score": score,
        "summary": {
            "components": len(components),
            "pads": pad_count,
            "nets": len(nets),
            "tracks": len(tracks),
            "vias": len(vias),
            "copper_layers": len(layers),
            "outline_primitives": outline_count,
            "power_nets": power_nets,
            "differential_pair_bases": diff_pairs,
        },
        "findings": findings,
    }
