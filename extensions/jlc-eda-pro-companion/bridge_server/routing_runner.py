"""
Invoke KiCadRouting Tools to perform PCB routing.

Supports two modes:
1. Direct API call (default) — imports route.batch_route() directly, faster
2. Subprocess fallback — used if direct import fails
"""

import io
import os
import sys
import subprocess
import tempfile
import time
import threading
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, List, Optional, Tuple

from models import PCBJsonData, RoutingConfig, TrackData, ViaData
from easyeda_to_kicad import convert
from kicad_diff import extract_new_routes
from coord_transform import mil_to_mm
from layer_mapping import easyeda_layer_to_kicad, set_dynamic_layer_map

KICAD_TOOLS_DIR = None
_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'KiCadRoutingTools')),
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'KiCadRoutingTools')),
]
for _candidate in _candidates:
    if os.path.isfile(os.path.join(_candidate, 'route.py')):
        KICAD_TOOLS_DIR = _candidate
        break
if KICAD_TOOLS_DIR is None:
    KICAD_TOOLS_DIR = _candidates[0]

# Add KiCadRoutingTools to path for direct import
if KICAD_TOOLS_DIR not in sys.path:
    sys.path.insert(0, KICAD_TOOLS_DIR)
if os.path.join(KICAD_TOOLS_DIR, 'rust_router') not in sys.path:
    sys.path.insert(0, os.path.join(KICAD_TOOLS_DIR, 'rust_router'))


# --- Local self-patch: fix multi-outline 'outline' UnboundLocalError in the
# downloaded KiCadRoutingTools/routing_common.py (not yet fixed upstream).
# Idempotent: only rewrites the file when the buggy line is present, so it is a
# no-op once patched or once upstream ships the fix.
def _patch_routing_common():
    rc = os.path.join(KICAD_TOOLS_DIR, 'routing_common.py')
    if not os.path.isfile(rc):
        return
    try:
        s = open(rc, encoding='utf-8').read()
        buggy = '_dist_point_to_polygon(x, y, outline) if has_poly'
        fixed = 'min(_dist_point_to_polygon(x, y, o) for o in outlines) if has_poly'
        if buggy in s:
            open(rc, 'w', encoding='utf-8').write(s.replace(buggy, fixed, 1))
            print('[PATCH] routing_common.py: applied multi-outline outline fix')
    except Exception as e:
        print('[PATCH] routing_common.py: skip (%s)' % e)


_patch_routing_common()



# Minimum parameter constraints (in mm) for basic single-ended routing
PARAM_MINIMUMS = {
    'track_width': 0.05,
    'clearance': 0.05,
    'via_size': 0.2,
    'via_drill': 0.1,
    'grid_step': 0.01,
    'board_edge_clearance': 0.5,
}


def _to_mm(value: float, config: RoutingConfig) -> float:
    """Convert value to mm, respecting units_mm flag."""
    if config.units_mm:
        return value
    return mil_to_mm(value)


def _validate_routing_params(config: RoutingConfig):
    """Validate routing parameters against minimum constraints. Raises ValueError on failure."""
    checks = [
        ('track_width', _to_mm(config.track_width, config)),
        ('clearance', _to_mm(config.clearance, config)),
        ('via_size', _to_mm(config.via_size, config)),
        ('via_drill', _to_mm(config.via_drill, config)),
        ('grid_step', _to_mm(config.grid_step, config)),
    ]
    if config.board_edge_clearance > 0:
        checks.append(('board_edge_clearance', _to_mm(config.board_edge_clearance, config)))

    errors = []
    for name, value in checks:
        minimum = PARAM_MINIMUMS.get(name, 0)
        if value < minimum:
            errors.append(f"{name}: {value:.3f}mm < minimum {minimum:.3f}mm")

    if errors:
        raise ValueError("Routing parameter validation failed:\n" + "\n".join(errors))


def _build_net_id_map(nets: List[str]) -> Dict[int, str]:
    mapping = {0: ""}
    for i, name in enumerate(nets, start=1):
        mapping[i] = name
    return mapping


def _cancel_check(cancel_event: Optional[threading.Event]):
    """Create a cancel_check callable for batch_route."""
    if cancel_event is None:
        return None
    return lambda: cancel_event.is_set()


def _resolve_layers(config: RoutingConfig) -> List[str]:
    return [easyeda_layer_to_kicad(lid) for lid in config.layers_to_use]


def _parse_power_nets(config: RoutingConfig):
    """Parse power_nets and power_widths strings into lists."""
    power_nets = None
    power_nets_widths = None
    if config.power_nets.strip():
        power_nets = config.power_nets.strip().split()
        if config.power_widths.strip():
            try:
                if config.units_mm:
                    power_nets_widths = [float(w) for w in config.power_widths.strip().split()]
                else:
                    power_nets_widths = [round(mil_to_mm(float(w)), 4) for w in config.power_widths.strip().split()]
            except ValueError:
                pass
    return power_nets, power_nets_widths


def _parse_layer_costs(config: RoutingConfig) -> Optional[List[float]]:
    """Parse layer_costs string into list of floats."""
    if not config.layer_costs.strip():
        return None
    try:
        return [float(c) for c in config.layer_costs.strip().split()]
    except ValueError:
        return None


def _run_direct_api(
    input_path: str,
    output_path: str,
    config: RoutingConfig,
    nets: List[str],
    cancel_event: Optional[threading.Event],
) -> Tuple[float, str]:
    """Run routing via direct Python API call to batch_route()."""
    try:
        from route import batch_route
    except SystemExit as e:
        raise RuntimeError(
            f"KiCadRoutingTools startup check failed (Rust router not built?). "
            f"Run 'python build_router.py' in KiCadRoutingTools directory. Exit code: {e.code}"
        )

    # Round all params to clean mm values to avoid precision loss from mm→mil→mm conversion
    if config.units_mm:
        track_width_mm = config.track_width
        clearance_mm = config.clearance
        via_size_mm = config.via_size
        via_drill_mm = config.via_drill
        grid_step_mm = config.grid_step
        board_edge_cl_mm = config.board_edge_clearance if config.board_edge_clearance > 0 else 0.0
    else:
        track_width_mm = round(mil_to_mm(config.track_width), 4)
        clearance_mm = round(mil_to_mm(config.clearance), 4)
        via_size_mm = round(mil_to_mm(config.via_size), 4)
        via_drill_mm = round(mil_to_mm(config.via_drill), 4)
        grid_step_mm = round(mil_to_mm(config.grid_step), 2)
        board_edge_cl_mm = round(mil_to_mm(config.board_edge_clearance), 4) if config.board_edge_clearance > 0 else 0.0
    layers = _resolve_layers(config)
    net_names = config.nets_to_route if config.nets_to_route != ['*'] else nets
    power_nets, power_nets_widths = _parse_power_nets(config)
    layer_costs = _parse_layer_costs(config)

    print(f"[TIMING] batch_route params: nets={len(net_names)}, layers={layers}, "
          f"tw={track_width_mm:.3f} cl={clearance_mm:.3f} gs={grid_step_mm:.3f} "
          f"via={via_size_mm:.3f}/{via_drill_mm:.3f} bec={board_edge_cl_mm:.3f}")

    buf_out = io.StringIO()
    buf_err = io.StringIO()

    start_time = time.time()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        successful, failed, elapsed = batch_route(
            input_file=input_path,
            output_file=output_path,
            net_names=net_names,
            ordering_strategy="mps",
            layers=layers,
            track_width=track_width_mm,
            clearance=clearance_mm,
            via_size=via_size_mm,
            via_drill=via_drill_mm,
            grid_step=grid_step_mm,
            via_cost=config.via_cost,
            max_rip_up_count=config.max_ripup,
            enable_layer_switch=config.stub_layer_swap,
            power_nets=power_nets,
            power_nets_widths=power_nets_widths,
            layer_costs=layer_costs,
            board_edge_clearance=board_edge_cl_mm,
            verbose=True,
            cancel_check=_cancel_check(cancel_event),
        )
    total_elapsed = time.time() - start_time
    print(f"[TIMING] batch_route DONE: {successful} routed, {failed} failed in {elapsed:.1f}s (wall: {total_elapsed:.1f}s)")
    log_output = buf_out.getvalue() + '\n' + buf_err.getvalue()
    log_output += f"\nDirect API: {successful} routed, {failed} failed in {elapsed:.1f}s"
    return total_elapsed, log_output


def _run_diff_pair_direct(
    input_path: str,
    output_path: str,
    config: RoutingConfig,
    nets: List[str],
    cancel_event: Optional[threading.Event],
) -> Tuple[float, str]:
    """Run differential pair routing via direct API call."""
    try:
        from route_diff import batch_route_diff_pairs
    except SystemExit as e:
        raise RuntimeError(
            f"KiCadRoutingTools startup check failed (Rust router not built?). "
            f"Run 'python build_router.py' in KiCadRoutingTools directory. Exit code: {e.code}"
        )

    # Round all params to clean mm values to avoid precision loss from mm→mil→mm conversion
    if config.units_mm:
        track_width_mm = config.track_width
        clearance_mm = config.clearance
        via_size_mm = config.via_size
        via_drill_mm = config.via_drill
    else:
        track_width_mm = round(mil_to_mm(config.track_width), 4)
        clearance_mm = round(mil_to_mm(config.clearance), 4)
        via_size_mm = round(mil_to_mm(config.via_size), 4)
        via_drill_mm = round(mil_to_mm(config.via_drill), 4)
    layers = _resolve_layers(config)
    net_names = config.nets_to_route if config.nets_to_route != ['*'] else nets
    dp = config.diff_pair

    buf_out = io.StringIO()
    buf_err = io.StringIO()

    start_time = time.time()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        successful, failed, elapsed = batch_route_diff_pairs(
            input_file=input_path,
            output_file=output_path,
            net_names=net_names,
            layers=layers,
            track_width=track_width_mm,
            clearance=clearance_mm,
            via_size=via_size_mm,
            via_drill=via_drill_mm,
            diff_pair_gap=dp.pair_gap,
            diff_pair_centerline_setback=dp.centerline_setback if dp.centerline_setback > 0 else None,
            min_turning_radius=dp.min_turning_radius,
            max_turn_angle=dp.max_turn_angle,
            max_setback_angle=dp.max_setback_angle,
            fix_polarity=dp.fix_polarity,
            gnd_via_enabled=dp.gnd_via_enabled,
            verbose=True,
            cancel_check=_cancel_check(cancel_event),
        )
    total_elapsed = time.time() - start_time
    log_output = buf_out.getvalue() + '\n' + buf_err.getvalue()
    log_output += f"\nDiff pair API: {successful} pairs routed, {failed} failed in {elapsed:.1f}s"
    return total_elapsed, log_output


def _run_bga_fanout_direct(
    input_path: str,
    output_path: str,
    config: RoutingConfig,
    cancel_event: Optional[threading.Event],
) -> Tuple[float, str]:
    """Run BGA fanout via direct API call."""
    from bga_fanout import fanout_bga

    buf_out = io.StringIO()
    buf_err = io.StringIO()

    start_time = time.time()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        from kicad_parser import parse_kicad_pcb
        pcb_data = parse_kicad_pcb(input_path)
        fanout_result = fanout_bga(
            pcb_data=pcb_data,
            component_ref=config.bga_component,
            exit_margin=config.bga_exit_margin,
        )
        # Write result
        from kicad_writer import generate_kicad_pcb
        output_content = generate_kicad_pcb(pcb_data)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_content)
    total_elapsed = time.time() - start_time
    log_output = buf_out.getvalue() + '\n' + buf_err.getvalue()
    return total_elapsed, log_output


def _run_subprocess(
    input_path: str,
    output_path: str,
    config: RoutingConfig,
    nets: List[str],
    cancel_event: Optional[threading.Event],
) -> Tuple[float, str]:
    """Fallback: run routing via subprocess."""
    layers = _resolve_layers(config)
    # Round all params to clean mm values to avoid precision loss from mm→mil→mm conversion
    if config.units_mm:
        track_width_mm = config.track_width
        clearance_mm = config.clearance
        via_size_mm = config.via_size
        via_drill_mm = config.via_drill
        grid_step_mm = config.grid_step
    else:
        track_width_mm = round(mil_to_mm(config.track_width), 4)
        clearance_mm = round(mil_to_mm(config.clearance), 4)
        via_size_mm = round(mil_to_mm(config.via_size), 4)
        via_drill_mm = round(mil_to_mm(config.via_drill), 4)
        grid_step_mm = round(mil_to_mm(config.grid_step), 2)

    cmd = [
        sys.executable,
        os.path.join(KICAD_TOOLS_DIR, 'route.py'),
        input_path,
        output_path,
        '--track-width', str(track_width_mm),
        '--clearance', str(clearance_mm),
        '--via-size', str(via_size_mm),
        '--via-drill', str(via_drill_mm),
        '--grid-step', str(grid_step_mm),
        '--via-cost', str(config.via_cost),
        '--max-ripup', str(config.max_ripup),
        '--layers'] + layers + [
        '--ordering', 'mps',
        '--verbose',
    ]
    if config.nets_to_route != ['*']:
        cmd.extend(['--nets'] + config.nets_to_route)
    if not config.stub_layer_swap:
        cmd.append('--no-stub-layer-swap')
    if config.power_nets.strip():
        cmd.extend(['--power-nets'] + config.power_nets.strip().split())
        if config.power_widths.strip():
            if config.units_mm:
                cmd.extend(['--power-nets-widths'] + config.power_widths.strip().split())
            else:
                cmd.extend(['--power-nets-widths'] + [str(round(mil_to_mm(float(w)), 4)) for w in config.power_widths.strip().split()])
    if config.layer_costs.strip():
        cmd.extend(['--layer-costs'] + config.layer_costs.strip().split())
    if config.board_edge_clearance > 0:
        if config.units_mm:
            cmd.extend(['--board-edge-clearance', str(config.board_edge_clearance)])
        else:
            cmd.extend(['--board-edge-clearance', str(round(mil_to_mm(config.board_edge_clearance), 4))])

    start_time = time.time()

    env = os.environ.copy()
    env['PYTHONPATH'] = KICAD_TOOLS_DIR + os.pathsep + env.get('PYTHONPATH', '')

    # Redirect stdout+stderr to a temp file (NOT subprocess.PIPE). PIPE without
    # draining deadlocks once verbose routing output fills the 64 KB OS pipe
    # buffer, hanging the subprocess until the client times out.
    out_file = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        cmd,
        stdout=out_file,
        stderr=subprocess.STDOUT,
        cwd=KICAD_TOOLS_DIR,
        env=env,
    )

    # Wait for completion or cancellation
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            print(f"[CANCEL] terminating routing subprocess (pid={proc.pid})", flush=True)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            out_file.close()
            raise RuntimeError("Routing cancelled by user")
        time.sleep(0.5)

    out_file.seek(0)
    log_output = out_file.read().decode('utf-8', errors='replace')
    out_file.close()
    elapsed = time.time() - start_time

    if proc.returncode != 0 and not os.path.exists(output_path):
        raise RuntimeError(
            f"Routing failed (exit code {proc.returncode}):\n{log_output}"
        )

    return elapsed, log_output


def run_routing(pcb_data: PCBJsonData, cancel_event: Optional[threading.Event] = None) -> Tuple[List[TrackData], List[ViaData], float, str]:
    """
    Execute the full routing pipeline:
    1. Convert EasyEDA JSON → .kicad_pcb
    2. Run KiCadRouting Tools (mode determined by routing_config.routing_mode)
    3. Diff results and extract new tracks/vias

    Returns:
        (new_tracks, new_vias, elapsed_seconds, log_output)
    """
    config = pcb_data.routing_config
    mode = config.routing_mode

    # Set dynamic layer map for correct inner layer numbering
    if pcb_data.board.layers:
        set_dynamic_layer_map(pcb_data.board.layers)

    _validate_routing_params(config)

    with tempfile.TemporaryDirectory(prefix='kicad_bridge_') as tmpdir:
        import time as _time
        t0 = _time.time()
        input_path = os.path.join(tmpdir, 'input.kicad_pcb')
        output_path = os.path.join(tmpdir, 'input_routed.kicad_pcb')

        if config.kicad_file_path and os.path.isfile(config.kicad_file_path):
            import shutil
            shutil.copy2(config.kicad_file_path, input_path)
            # Extract net names from the kicad file itself
            from kicad_parser import parse_kicad_pcb
            parsed = parse_kicad_pcb(input_path)
            nets = [parsed.net_id_to_name.get(i, "") for i in range(1, max(parsed.net_id_to_name.keys()) + 1)] if parsed.net_id_to_name else pcb_data.nets
            print(f"[TIMING] direct kicad file copy: {_time.time() - t0:.2f}s, file={config.kicad_file_path}")
        else:
            kicad_content = convert(pcb_data)
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write(kicad_content)
            nets = pcb_data.nets
            print(f"[TIMING] conversion+write: {_time.time() - t0:.2f}s, comps={len(pcb_data.components)}, nets={len(pcb_data.nets)}")

        # Save a copy for debugging
        debug_dir = os.path.join(os.path.dirname(__file__), 'debug_output')
        os.makedirs(debug_dir, exist_ok=True)
        import shutil as _shutil
        _shutil.copy2(input_path, os.path.join(debug_dir, 'input.kicad_pcb'))

        log_output = ""

        if mode == "diff_pair":
            try:
                elapsed, log_output = _run_diff_pair_direct(
                    input_path, output_path,
                    config, nets, cancel_event,
                )
            except ImportError as e:
                log_output = f"Direct API import failed ({e}), falling back to subprocess\n"
                elapsed, sub_log = _run_subprocess(
                    input_path, output_path,
                    config, nets, cancel_event,
                )
                log_output += sub_log

        elif mode == "bga_fanout":
            elapsed, log_output = _run_bga_fanout_direct(
                input_path, output_path,
                config, cancel_event,
            )

        else:  # single_ended (default) — run as a subprocess so the job is
               # killable on cancel/timeout (an in-process batch_route stuck in a
               # Rust A* call cannot be interrupted from Python).
            elapsed, log_output = _run_subprocess(
                input_path, output_path,
                config, nets, cancel_event,
            )

        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Routing cancelled by user")

        if not os.path.exists(output_path):
            raise RuntimeError(f"Routing produced no output:\n{log_output}")

        _shutil.copy2(output_path, os.path.join(debug_dir, 'output_routed.kicad_pcb'))

        offset_x = 0.0
        offset_y = 0.0
        if config.kicad_file_path and os.path.isfile(config.kicad_file_path):
            net_id_map = parsed.net_id_to_name if parsed.net_id_to_name else _build_net_id_map(nets)
            # Compute coordinate offset by matching first component
            if pcb_data.components and parsed.footprints:
                ref_comp = pcb_data.components[0]
                ref_name = ref_comp.designator
                if ref_name in parsed.footprints:
                    kicad_fp = parsed.footprints[ref_name]
                    easyeda_x_mm = mil_to_mm(ref_comp.x) if not config.units_mm else ref_comp.x
                    easyeda_y_mm = mil_to_mm(ref_comp.y) if not config.units_mm else ref_comp.y
                    offset_x = kicad_fp.x - easyeda_x_mm
                    offset_y = kicad_fp.y - easyeda_y_mm
                    print(f"[DEBUG] Coordinate offset: kicad=({kicad_fp.x:.4f},{kicad_fp.y:.4f}) easyeda=({easyeda_x_mm:.4f},{easyeda_y_mm:.4f}) offset=({offset_x:.4f},{offset_y:.4f})")
        else:
            net_id_map = _build_net_id_map(nets)
        new_tracks, new_vias = extract_new_routes(input_path, output_path, net_id_map, units_mm=config.units_mm, offset_x=offset_x, offset_y=offset_y)

        return new_tracks, new_vias, elapsed, log_output
