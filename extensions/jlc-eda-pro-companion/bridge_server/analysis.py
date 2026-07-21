"""
AI-powered PCB analysis using KiCadRouting Tools analysis modules.

Provides:
- Power net analysis (component classification, current path tracing, track width recommendations)
- Differential pair detection
- Bus group detection
- Net statistics (unrouted nets, net counts by type)
"""

import os
import sys
import tempfile
from typing import Dict, List, Any

from models import PCBJsonData
from easyeda_to_kicad import convert
from layer_mapping import easyeda_layer_to_kicad

_kicad_tools_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'KiCadRoutingTools')),
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'KiCadRoutingTools')),
]
KICAD_TOOLS_DIR = None
for _c in _kicad_tools_candidates:
    if os.path.isfile(os.path.join(_c, 'route.py')):
        KICAD_TOOLS_DIR = _c
        break
if KICAD_TOOLS_DIR is None:
    KICAD_TOOLS_DIR = _kicad_tools_candidates[0]
if KICAD_TOOLS_DIR not in sys.path:
    sys.path.insert(0, KICAD_TOOLS_DIR)
if os.path.join(KICAD_TOOLS_DIR, 'rust_router') not in sys.path:
    sys.path.insert(0, os.path.join(KICAD_TOOLS_DIR, 'rust_router'))


def _parse_pcb(pcb_data: PCBJsonData):
    """Convert and parse PCB data into KiCadRoutingTools PCBData object."""
    from kicad_parser import parse_kicad_pcb
    kicad_content = convert(pcb_data)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.kicad_pcb', delete=False, encoding='utf-8') as f:
        f.write(kicad_content)
        tmppath = f.name
    try:
        return parse_kicad_pcb(tmppath)
    finally:
        os.unlink(tmppath)


def analyze_power_nets(pcb_data: PCBJsonData) -> Dict[str, Any]:
    """Analyze power nets: detect power patterns, classify components, trace current paths."""
    from analyze_power_paths import (
        extract_components_for_analysis,
        trace_power_paths,
        get_power_net_recommendations,
    )

    pcb = _parse_pcb(pcb_data)
    components = extract_components_for_analysis(pcb)

    # Classify obvious components (resistors, capacitors, inductors get auto-classified)
    comp_list = []
    for ref, info in components.items():
        comp_list.append({
            "reference": info.ref,
            "value": info.value,
            "footprint": info.footprint_name,
            "pad_count": info.pad_count,
            "role": info.role.name if hasattr(info.role, 'name') else str(info.role),
            "nets": list(info.net_connections.keys()) if info.net_connections else [],
        })

    # Trace power paths
    try:
        paths = trace_power_paths(pcb, components)
        path_list = []
        for p in paths:
            path_list.append({
                "source": p.source_component,
                "sink": p.sink_component,
                "nets": p.nets_in_path,
                "components": p.components_in_path,
                "current_ma": p.estimated_current_ma,
            })
    except Exception:
        path_list = []

    # Get width recommendations
    try:
        recommendations = get_power_net_recommendations(pcb, components, paths)
        rec_list = [{"net": net, "width_mm": w} for net, w in recommendations.items()]
    except Exception:
        rec_list = []

    return {
        "components": comp_list,
        "power_paths": path_list,
        "width_recommendations": rec_list,
    }


def analyze_diff_pairs(pcb_data: PCBJsonData) -> Dict[str, Any]:
    """Detect differential pairs from net names."""
    from net_queries import find_differential_pairs

    pcb = _parse_pcb(pcb_data)
    pairs = find_differential_pairs(pcb, patterns=["*"])

    pair_list = []
    for base_name, pair_info in pairs.items():
        pair_list.append({
            "base_name": base_name,
            "positive_net": pair_info.pos_net_name if hasattr(pair_info, 'pos_net_name') else pair_info.get('pos_net', ''),
            "negative_net": pair_info.neg_net_name if hasattr(pair_info, 'neg_net_name') else pair_info.get('neg_net', ''),
            "positive_net_id": pair_info.pos_net_id if hasattr(pair_info, 'pos_net_id') else 0,
            "negative_net_id": pair_info.neg_net_id if hasattr(pair_info, 'neg_net_id') else 0,
        })

    return {
        "total_pairs": len(pair_list),
        "pairs": pair_list,
    }


def analyze_bus_groups(pcb_data: PCBJsonData) -> Dict[str, Any]:
    """Detect bus groups (clusters of parallel nets)."""
    from bus_detection import detect_bus_groups

    pcb = _parse_pcb(pcb_data)
    all_net_ids = list(pcb.nets.keys())

    buses = detect_bus_groups(pcb, all_net_ids)

    bus_list = []
    for bus in buses:
        bus_list.append({
            "name": bus.name if hasattr(bus, 'name') else f"Bus_{len(bus_list)}",
            "net_ids": bus.net_ids if hasattr(bus, 'net_ids') else [],
            "net_count": len(bus.net_ids) if hasattr(bus, 'net_ids') else 0,
        })

    return {
        "total_buses": len(bus_list),
        "buses": bus_list,
    }


def analyze_net_stats(pcb_data: PCBJsonData) -> Dict[str, Any]:
    """Get net statistics: total nets, unrouted, routed, power nets."""
    from net_queries import get_all_unrouted_net_ids, identify_power_nets

    pcb = _parse_pcb(pcb_data)

    total_nets = len([n for n in pcb.nets.values() if n.name and not n.name.startswith("unconnected-")])
    unrouted_ids = get_all_unrouted_net_ids(pcb)
    unrouted_count = len(unrouted_ids)

    power_patterns = ["*GND*", "*VCC*", "*VDD*", "*3V3*", "*5V*", "*3.3V*", "*1.8V*"]
    power_nets = identify_power_nets(pcb, patterns=power_patterns, widths=[0.4]*len(power_patterns))
    power_net_names = [pcb.nets[nid].name for nid in power_nets if nid in pcb.nets]

    net_details = []
    for net in pcb.nets.values():
        if not net.name or net.name.startswith("unconnected-"):
            continue
        net_details.append({
            "name": net.name,
            "net_id": net.net_id,
            "pad_count": len(net.pads),
            "is_power": net.net_id in power_nets,
        })

    return {
        "total_nets": total_nets,
        "unrouted_nets": unrouted_count,
        "routed_nets": total_nets - unrouted_count,
        "power_net_count": len(power_net_names),
        "power_nets": power_net_names,
        "nets": net_details,
    }


def analyze_board_summary(pcb_data: PCBJsonData) -> Dict[str, Any]:
    """Quick board summary: component count, layer count, net count, board outline."""
    layers = [easyeda_layer_to_kicad(lid) for lid in pcb_data.board.layers]
    component_count = len(pcb_data.components)
    pad_count = sum(len(c.pads) for c in pcb_data.components)
    net_count = len([n for n in pcb_data.nets if n and not n.startswith("unconnected-")])

    bga_components = []
    for comp in pcb_data.components:
        pad_count_comp = len(comp.pads)
        if pad_count_comp >= 100:
            bga_components.append({
                "designator": comp.designator,
                "pad_count": pad_count_comp,
            })

    return {
        "component_count": component_count,
        "pad_count": pad_count,
        "net_count": net_count,
        "layers": layers,
        "layer_count": len(layers),
        "bga_components": bga_components,
        "has_outline": bool(pcb_data.board.outline_lines or pcb_data.board.outline_arcs) or len(pcb_data.board.outline) >= 3,
        "track_count": len(pcb_data.existing_tracks),
        "via_count": len(pcb_data.existing_vias),
    }
