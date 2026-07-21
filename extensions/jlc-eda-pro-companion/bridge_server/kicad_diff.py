"""
Diff routed .kicad_pcb against input to extract new tracks/vias,
then convert back to EasyEDA coordinate space.
"""

import sys
import os

_kicad_tools_candidates = [
    os.path.join(os.path.dirname(__file__), '..', 'KiCadRoutingTools'),
    os.path.join(os.path.dirname(__file__), '..', '..', 'KiCadRoutingTools'),
]
for _c in _kicad_tools_candidates:
    _c = os.path.abspath(_c)
    if os.path.isfile(os.path.join(_c, 'route.py')):
        sys.path.insert(0, _c)
        break
else:
    sys.path.insert(0, os.path.abspath(_kicad_tools_candidates[0]))

from kicad_parser import parse_kicad_pcb, Segment, Via
from coord_transform import mm_to_mil
from layer_mapping import kicad_layer_to_easyeda
from models import TrackData, ViaData


def _segment_key(seg: Segment) -> tuple:
    return (
        round(seg.start_x, 4), round(seg.start_y, 4),
        round(seg.end_x, 4), round(seg.end_y, 4),
        round(seg.width, 4), seg.layer, seg.net_id,
    )


def _via_key(via: Via) -> tuple:
    return (
        round(via.x, 4), round(via.y, 4),
        round(via.size, 4), round(via.drill, 4),
        via.net_id,
    )


def extract_new_routes(input_pcb_path: str, output_pcb_path: str, net_id_to_name: dict, units_mm: bool = False, offset_x: float = 0, offset_y: float = 0) -> tuple:
    """
    Compare input and output .kicad_pcb files, return new tracks and vias
    in EasyEDA coordinate space (mils) or mm if units_mm=True.

    offset_x, offset_y: offset to subtract from KiCad coordinates (in mm)
    before converting to output units. Used when kicad_file_path has a
    different origin than EasyEDA.

    Returns:
        (tracks: List[TrackData], vias: List[ViaData])
    """
    input_pcb = parse_kicad_pcb(input_pcb_path)
    output_pcb = parse_kicad_pcb(output_pcb_path)

    existing_segments = set(_segment_key(s) for s in input_pcb.segments)
    existing_vias = set(_via_key(v) for v in input_pcb.vias)

    def _conv_coord(val: float, is_width: bool = False) -> float:
        adjusted = val if is_width else val - (offset_x if False else 0)
        if units_mm:
            return adjusted
        return mm_to_mil(adjusted)

    def _conv_x(val: float) -> float:
        if units_mm:
            return val - offset_x
        return mm_to_mil(val - offset_x)

    def _conv_y(val: float) -> float:
        if units_mm:
            return val - offset_y
        return mm_to_mil(val - offset_y)

    def _conv_size(val: float) -> float:
        if units_mm:
            return val
        return mm_to_mil(val)

    new_tracks = []
    for seg in output_pcb.segments:
        if _segment_key(seg) not in existing_segments:
            net_name = net_id_to_name.get(seg.net_id, "")
            easyeda_layer = kicad_layer_to_easyeda(seg.layer)
            new_tracks.append(TrackData(
                net=net_name,
                layer=easyeda_layer,
                startX=_conv_x(seg.start_x),
                startY=_conv_y(seg.start_y),
                endX=_conv_x(seg.end_x),
                endY=_conv_y(seg.end_y),
                width=_conv_size(seg.width),
            ))

    new_vias = []
    for via in output_pcb.vias:
        if _via_key(via) not in existing_vias:
            net_name = net_id_to_name.get(via.net_id, "")
            new_vias.append(ViaData(
                net=net_name,
                x=_conv_x(via.x),
                y=_conv_y(via.y),
                holeDiameter=_conv_size(via.drill),
                diameter=_conv_size(via.size),
            ))

    return new_tracks, new_vias
