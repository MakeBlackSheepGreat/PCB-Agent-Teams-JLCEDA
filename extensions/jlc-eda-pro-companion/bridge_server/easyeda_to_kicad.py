"""
Convert EasyEDA Pro PCB JSON data to KiCad .kicad_pcb format.
"""

import math
import uuid as uuid_mod
from typing import List, Dict, Tuple

from models import PCBJsonData, ComponentData, PadData, TrackData, ViaData
from coord_transform import mil_to_mm
from layer_mapping import easyeda_layer_to_kicad, set_dynamic_layer_map

_units_mm = False


def _coord(value: float) -> float:
    """Convert coordinate to mm. Pass-through when units_mm is set."""
    if _units_mm:
        return value
    return mil_to_mm(value)


def _uuid() -> str:
    return str(uuid_mod.uuid4())


def _build_layer_section(layer_ids: List[int]) -> str:
    lines = []
    lines.append('\t(layers')
    lines.append(f'\t\t(0 "F.Cu" signal)')
    lines.append(f'\t\t(31 "B.Cu" signal)')

    inner_idx = 1
    for lid in sorted(layer_ids):
        if lid not in (1, 2):
            kicad_name = easyeda_layer_to_kicad(lid)
            if kicad_name and kicad_name != 'F.Cu':
                lines.append(f'\t\t({inner_idx} "{kicad_name}" signal)')
                inner_idx += 1

    lines.append(f'\t\t(32 "B.Adhes" user "B.Adhesive")')
    lines.append(f'\t\t(33 "F.Adhes" user "F.Adhesive")')
    lines.append(f'\t\t(34 "B.Paste" user)')
    lines.append(f'\t\t(35 "F.Paste" user)')
    lines.append(f'\t\t(36 "B.SilkS" user "B.Silkscreen")')
    lines.append(f'\t\t(37 "F.SilkS" user "F.Silkscreen")')
    lines.append(f'\t\t(38 "B.Mask" user "B.Mask")')
    lines.append(f'\t\t(39 "F.Mask" user "F.Mask")')
    lines.append(f'\t\t(44 "Edge.Cuts" user)')
    lines.append(f'\t\t(46 "B.CrtYd" user "B.Courtyard")')
    lines.append(f'\t\t(47 "F.CrtYd" user "F.Courtyard")')
    lines.append(f'\t\t(48 "B.Fab" user)')
    lines.append(f'\t\t(49 "F.Fab" user)')
    lines.append('\t)')
    return '\n'.join(lines)


def _build_net_section(nets: List[str]) -> str:
    lines = []
    lines.append(f'\t(net 0 "")')
    for i, net_name in enumerate(nets, start=1):
        lines.append(f'\t(net {i} "{net_name}")')
    return '\n'.join(lines)


def _net_id_map(nets: List[str]) -> Dict[str, int]:
    mapping = {"": 0}
    for i, name in enumerate(nets, start=1):
        mapping[name] = i
    return mapping


def _pad_shape_to_kicad(shape: str) -> str:
    shape_map = {
        "round": "circle",
        "circle": "circle",
        "rect": "rect",
        "rectangle": "rect",
        "oval": "oval",
        "oblong": "oval",
        "roundrect": "roundrect",
        "polygon": "custom",
    }
    return shape_map.get(shape.lower(), "circle")


def _snap_to_grid(value: float, grid: float = 0.1) -> float:
    """Snap a value to the nearest grid point. Skipped when units_mm is set."""
    if _units_mm:
        return value
    return round(value / grid) * grid


def _build_pad_sexpr(pad: PadData, comp: ComponentData, net_map: Dict[str, int]) -> str:
    net_id = net_map.get(pad.net, 0)
    kicad_shape = _pad_shape_to_kicad(pad.shape)

    # Snap pad global position to 0.1mm grid for clean routing
    abs_x_mm = _snap_to_grid(_coord(pad.x))
    abs_y_mm = _snap_to_grid(_coord(pad.y))
    comp_x_mm = _snap_to_grid(_coord(comp.x))
    comp_y_mm = _snap_to_grid(_coord(comp.y))
    pad_x_mm = abs_x_mm - comp_x_mm
    pad_y_mm = abs_y_mm - comp_y_mm
    # Round pad dimensions to avoid mil→mm noise affecting obstacle expansion
    size_x_mm = round(_coord(pad.width), 2) if pad.width > 0 else 0.5
    size_y_mm = round(_coord(pad.height), 2) if pad.height > 0 else size_x_mm

    is_thru_hole = pad.drill > 0

    if is_thru_hole:
        pad_type = "thru_hole"
        drill_mm = round(_coord(pad.drill), 2)
        drill_str = f'\n\t\t\t(drill {drill_mm:.6f})'
        layers_str = '"*.Cu" "*.Mask"'
    else:
        pad_type = "smd"
        drill_str = ""
        pad_layer = easyeda_layer_to_kicad(pad.layer)
        if pad_layer == 'F.Cu':
            layers_str = '"F.Cu" "F.Paste" "F.Mask"'
        elif pad_layer == 'B.Cu':
            layers_str = '"B.Cu" "B.Paste" "B.Mask"'
        else:
            layers_str = '"*.Cu"'

    # Pad rotation: use pad's own rotation (global) since component rotation is 0
    rotation_str = ""
    if pad.rotation != 0:
        rotation_str = f" {pad.rotation}"

    return (
        f'\t\t(pad "{pad.number}" {pad_type} {kicad_shape}\n'
        f'\t\t\t(at {pad_x_mm:.6f} {pad_y_mm:.6f}{rotation_str})\n'
        f'\t\t\t(size {size_x_mm:.6f} {size_y_mm:.6f}){drill_str}\n'
        f'\t\t\t(layers {layers_str})\n'
        f'\t\t\t(net {net_id} "{pad.net}")\n'
        f'\t\t\t(uuid "{_uuid()}")\n'
        f'\t\t)'
    )


def _build_footprint_sexpr(comp: ComponentData, net_map: Dict[str, int]) -> str:
    comp_x_mm = _snap_to_grid(_coord(comp.x))
    comp_y_mm = _snap_to_grid(_coord(comp.y))
    kicad_layer = easyeda_layer_to_kicad(comp.layer)

    lines = []
    lines.append(f'\t(footprint "bridge:{comp.designator}"')
    lines.append(f'\t\t(layer "{kicad_layer}")')
    lines.append(f'\t\t(uuid "{_uuid()}")')
    # Set rotation to 0 since pad positions are already global offsets
    lines.append(f'\t\t(at {comp_x_mm:.6f} {comp_y_mm:.6f} 0)')

    lines.append(f'\t\t(property "Reference" "{comp.designator}"')
    lines.append(f'\t\t\t(at 0 0)')
    lines.append(f'\t\t\t(layer "{kicad_layer}")')
    lines.append(f'\t\t\t(uuid "{_uuid()}")')
    lines.append(f'\t\t\t(effects (font (size 1 1) (thickness 0.15)))')
    lines.append(f'\t\t)')

    for pad in comp.pads:
        lines.append(_build_pad_sexpr(pad, comp, net_map))

    lines.append(f'\t)')
    return '\n'.join(lines)


def _build_segment_sexpr(track: TrackData, net_map: Dict[str, int]) -> str:
    net_id = net_map.get(track.net, 0)
    layer = easyeda_layer_to_kicad(track.layer)
    sx = _snap_to_grid(_coord(track.startX))
    sy = _snap_to_grid(_coord(track.startY))
    ex = _snap_to_grid(_coord(track.endX))
    ey = _snap_to_grid(_coord(track.endY))
    w = round(_coord(track.width), 2)
    return (
        f'\t(segment\n'
        f'\t\t(start {sx:.6f} {sy:.6f})\n'
        f'\t\t(end {ex:.6f} {ey:.6f})\n'
        f'\t\t(width {w:.6f})\n'
        f'\t\t(layer "{layer}")\n'
        f'\t\t(net {net_id})\n'
        f'\t\t(uuid "{_uuid()}")\n'
        f'\t)'
    )


def _build_via_sexpr(via: ViaData, net_map: Dict[str, int], layer_ids: list = None) -> str:
    net_id = net_map.get(via.net, 0)
    x = _snap_to_grid(_coord(via.x))
    y = _snap_to_grid(_coord(via.y))
    size = round(_coord(via.diameter), 2)
    drill = round(_coord(via.holeDiameter), 2)

    start_layer = easyeda_layer_to_kicad(via.startLayer)
    end_layer = easyeda_layer_to_kicad(via.endLayer)

    # Build the layer list for via span
    if layer_ids:
        all_kicad_layers = [easyeda_layer_to_kicad(lid) for lid in sorted(layer_ids) if lid in (1, 2) or (15 <= lid <= 44)]
    else:
        all_kicad_layers = ['F.Cu', 'B.Cu']

    start_idx = all_kicad_layers.index(start_layer) if start_layer in all_kicad_layers else 0
    end_idx = all_kicad_layers.index(end_layer) if end_layer in all_kicad_layers else len(all_kicad_layers) - 1
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    via_layers = all_kicad_layers[start_idx:end_idx + 1]
    layers_str = ' '.join(f'"{l}"' for l in via_layers)

    return (
        f'\t(via\n'
        f'\t\t(at {x:.6f} {y:.6f})\n'
        f'\t\t(size {size:.6f})\n'
        f'\t\t(drill {drill:.6f})\n'
        f'\t\t(layers {layers_str})\n'
        f'\t\t(net {net_id})\n'
        f'\t\t(uuid "{_uuid()}")\n'
        f'\t)'
    )


def _build_board_outline_sexpr(board_data) -> str:
    """Generate Edge.Cuts geometry from board outline lines and arcs."""
    lines = board_data.outline_lines if hasattr(board_data, 'outline_lines') else []
    arcs = board_data.outline_arcs if hasattr(board_data, 'outline_arcs') else []
    old_points = board_data.outline if hasattr(board_data, 'outline') else []

    parts = []

    # gr_line segments from outline_lines
    for seg in lines:
        sx = _coord(seg.startX)
        sy = _coord(seg.startY)
        ex = _coord(seg.endX)
        ey = _coord(seg.endY)
        parts.append(
            f'\t(gr_line\n'
            f'\t\t(start {sx:.6f} {sy:.6f})\n'
            f'\t\t(end {ex:.6f} {ey:.6f})\n'
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(width 0.100000)\n'
            f'\t\t(uuid "{_uuid()}")\n'
            f'\t)'
        )

    # gr_arc segments from outline_arcs (approximate with line segments)
    for arc in arcs:
        _approximate_arc_to_lines(arc, parts)

    # Fallback: old-style polygon from outline points
    if not parts and len(old_points) >= 3:
        pts = []
        for pt in old_points:
            x_mm = _coord(pt.x)
            y_mm = _coord(pt.y)
            pts.append(f'\t\t\t(xy {x_mm:.6f} {y_mm:.6f})')
        parts.append(
            '\t(gr_poly\n'
            '\t\t(pts\n'
            + '\n'.join(pts) + '\n'
            '\t\t)\n'
            '\t\t(layer "Edge.Cuts")\n'
            '\t\t(width 0.1)\n'
            f'\t\t(uuid "{_uuid()}")\n'
            '\t)'
        )

    return '\n\n'.join(parts)


def _approximate_arc_to_lines(arc, parts: list, num_segments: int = 12):
    """Approximate an arc with line segments on Edge.Cuts."""
    sx, sy = arc.startX, arc.startY
    ex, ey = arc.endX, arc.endY
    angle_deg = arc.arcAngle

    dx = ex - sx
    dy = ey - sy
    chord = math.sqrt(dx * dx + dy * dy)

    if chord < 1e-3 or abs(angle_deg) < 0.1:
        sx_mm = _coord(sx)
        sy_mm = _coord(sy)
        ex_mm = _coord(ex)
        ey_mm = _coord(ey)
        parts.append(
            f'\t(gr_line\n'
            f'\t\t(start {sx_mm:.6f} {sy_mm:.6f})\n'
            f'\t\t(end {ex_mm:.6f} {ey_mm:.6f})\n'
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(width 0.100000)\n'
            f'\t\t(uuid "{_uuid()}")\n'
            f'\t)'
        )
        return

    # Compute arc center
    if abs(abs(angle_deg) - 180) < 0.1:
        cx = (sx + ex) / 2
        cy = (sy + ey) / 2
        radius = chord / 2
    else:
        half_chord = chord / 2
        angle_rad = abs(angle_deg) * math.pi / 180
        radius = half_chord / math.sin(angle_rad / 2)
        h = half_chord / math.tan(angle_rad / 2)

        mx = (sx + ex) / 2
        my = (sy + ey) / 2
        rx = dy / chord
        ry = -dx / chord
        sign = 1 if angle_deg > 0 else -1
        cx = mx + sign * h * rx
        cy = my + sign * h * ry

    # Generate line segments along the arc
    start_angle = math.atan2(sy - cy, sx - cx)
    sweep = angle_deg * math.pi / 180

    prev_x, prev_y = sx, sy
    for i in range(1, num_segments + 1):
        t = i / num_segments
        a = start_angle + t * sweep
        px = cx + radius * math.cos(a)
        py = cy + radius * math.sin(a)

        px_mm = _coord(prev_x)
        py_mm = _coord(prev_y)
        cx_mm = _coord(px)
        cy_mm = _coord(py)
        parts.append(
            f'\t(gr_line\n'
            f'\t\t(start {px_mm:.6f} {py_mm:.6f})\n'
            f'\t\t(end {cx_mm:.6f} {cy_mm:.6f})\n'
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(width 0.100000)\n'
            f'\t\t(uuid "{_uuid()}")\n'
            f'\t)'
        )
        prev_x, prev_y = px, py


def _build_stackup_section(board_data) -> str:
    if not board_data.stackup:
        return ""
    lines = []
    lines.append('\t(setup')
    lines.append('\t\t(pad_to_mask_clearance 0)')
    lines.append('\t\t(allow_soldermask_bridges_in_footprints no)')
    lines.append('\t\t(stackup')
    layers = board_data.stackup
    for i, layer in enumerate(layers):
        if layer.material == 'copper':
            kicad_name = layer.name
            if not kicad_name or kicad_name.startswith('Layer_'):
                # Try to map from position
                kicad_name = 'F.Cu' if i == 0 else f'In{(i // 2) + 1}.Cu' if i < len(layers) - 1 else 'B.Cu'
            lines.append(f'\t\t\t(layer "{kicad_name}" (type copper))')
            lines.append(f'\t\t\t(layer "dielectric {i}" (type core)')
            lines.append(f'\t\t\t\t(thickness {layer.thickness})')
            lines.append(f'\t\t\t\t(material "FR4")')
            lines.append(f'\t\t\t\t(epsilon_r 4.5))')
        else:
            lines.append(f'\t\t\t(layer "dielectric {i}" (type core)')
            lines.append(f'\t\t\t\t(thickness {layer.thickness})')
            lines.append(f'\t\t\t\t(material "{layer.material}"))')
    lines.append('\t\t)')
    lines.append('\t)')
    return '\n'.join(lines)


def convert(pcb_data: PCBJsonData) -> str:
    """Convert EasyEDA PCB JSON to KiCad .kicad_pcb file content."""
    global _units_mm
    _units_mm = pcb_data.routing_config.units_mm

    # Set dynamic layer map based on board's actual layers
    set_dynamic_layer_map(pcb_data.board.layers)

    net_map = _net_id_map(pcb_data.nets)
    layer_ids = pcb_data.board.layers

    parts = []

    parts.append('(kicad_pcb\n\t(version 20241229)\n\t(generator "jlc-eda-design-companion")\n\t(generator_version "0.1.0")')

    parts.append(_build_layer_section(layer_ids))

    stackup_section = _build_stackup_section(pcb_data.board)
    if stackup_section:
        parts.append(stackup_section)
    else:
        parts.append('\t(setup\n\t\t(pad_to_mask_clearance 0)\n\t\t(allow_soldermask_bridges_in_footprints no)\n\t)')

    parts.append(_build_net_section(pcb_data.nets))

    outline_sexpr = _build_board_outline_sexpr(pcb_data.board)
    if outline_sexpr:
        parts.append(outline_sexpr)

    footprint_count = 0
    for comp in pcb_data.components:
        try:
            parts.append(_build_footprint_sexpr(comp, net_map))
            footprint_count += 1
        except Exception as e:
            print(f"[WARN] Failed to convert component {comp.designator}: {e}")
    print(f"[DEBUG convert] Generated {footprint_count} footprints from {len(pcb_data.components)} components")

    for track in pcb_data.existing_tracks:
        parts.append(_build_segment_sexpr(track, net_map))

    for via in pcb_data.existing_vias:
        parts.append(_build_via_sexpr(via, net_map, layer_ids))

    parts.append(')')

    return '\n\n'.join(parts)
