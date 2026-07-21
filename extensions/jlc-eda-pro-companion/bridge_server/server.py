"""
Bridge Server — FastAPI application that mediates between
EasyEDA Pro extension and KiCadRouting Tools.
"""

import json
import os
import sys
import uuid as uuid_mod
import traceback
import threading
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import PCBJsonData, RoutingResult, RoutingStats
import analysis as analysis_module
from review import build_preflight

app = FastAPI(title="JLCEDA Design Companion Bridge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Job Store ───

class Job:
    def __init__(self, job_id: str, pcb_data: PCBJsonData):
        self.job_id = job_id
        self.pcb_data = pcb_data
        self.status = "pending"
        self.result: RoutingResult = RoutingResult()
        self.log = ""
        self.cancelled = threading.Event()
        self.process = None  # subprocess handle for cancellation

jobs: Dict[str, Job] = {}
_routing_lock = threading.Lock()
_active_job_id: str = ""


def _run_routing_job(job: Job):
    """Background thread that runs the routing pipeline."""
    global _active_job_id
    if not _routing_lock.acquire(timeout=30):
        job.status = "failed"
        job.result = RoutingResult(status="failed", error="Another routing job is already running")
        print(f"[ERROR] Job {job.job_id}: failed to acquire lock")
        return
    try:
        _active_job_id = job.job_id
        job.status = "converting"
        print(f"[DEBUG] Job {job.job_id}: status=converting, importing routing_runner...")
        print(f"[DEBUG] Job {job.job_id}: __file__={os.path.abspath(__file__)}")
        print(f"[DEBUG] Job {job.job_id}: cwd={os.getcwd()}")
        print(f"[DEBUG] Job {job.job_id}: sys.path[:5]={sys.path[:5]}")
        from routing_runner import run_routing, KICAD_TOOLS_DIR
        print(f"[DEBUG] Job {job.job_id}: KICAD_TOOLS_DIR={KICAD_TOOLS_DIR}")
        print(f"[DEBUG] Job {job.job_id}: route.py exists={os.path.isfile(os.path.join(KICAD_TOOLS_DIR, 'route.py'))}")

        if job.cancelled.is_set():
            job.status = "cancelled"
            return

        job.status = "routing"
        print(f"[DEBUG] Job {job.job_id}: status=routing, calling run_routing...")
        print(f"[DEBUG] Job {job.job_id}: pcb_data components={len(job.pcb_data.components)}, nets={len(job.pcb_data.nets)}")
        new_tracks, new_vias, elapsed, log_output = run_routing(job.pcb_data, job.cancelled)
        job.log = log_output
        print(f"[DEBUG] Job {job.job_id}: routing done, tracks={len(new_tracks)}, vias={len(new_vias)}, elapsed={elapsed:.1f}s")
        print(f"[DEBUG] Job {job.job_id}: log_output={log_output[:500]}")

        if job.cancelled.is_set():
            job.status = "cancelled"
            job.result = RoutingResult(status="cancelled", error="Cancelled by user")
            return

        job.status = "converting_back"

        nets_routed = len(set(t.net for t in new_tracks if t.net))
        job.result = RoutingResult(
            status="completed",
            stats=RoutingStats(
                nets_routed=nets_routed,
                nets_failed=0,
                tracks_added=len(new_tracks),
                vias_added=len(new_vias),
                time_seconds=round(elapsed, 2),
            ),
            tracks=new_tracks,
            vias=new_vias,
        )
        job.status = "completed"

    except BaseException as e:
        if job.cancelled.is_set():
            print(f"[CANCEL] job {job.job_id} cancelled by client — subprocess killed, lock released", flush=True)
            job.status = "cancelled"
            job.result = RoutingResult(status="cancelled", error="Cancelled by user")
        else:
            import traceback
            error_detail = traceback.format_exc()
            job.log += f"\n\nERROR: {error_detail}"
            job.result = RoutingResult(
                status="failed",
                error=str(e),
            )
            job.status = "failed"
            print(f"[ERROR] Job {job.job_id}: EXCEPTION: {e}")
            print(f"[ERROR] Job {job.job_id}: TRACEBACK:\n{error_detail}")
    finally:
        _active_job_id = ""
        _routing_lock.release()


# ─── Endpoints ───

@app.post("/api/extra-components")
async def receive_extra_components(request: Request):
    """Receive additional components (standalone pads) before the main route request."""
    raw_body = await request.body()
    try:
        body_str = raw_body.decode('utf-8')
        data = json.loads(body_str)
    except Exception as e:
        return {"error": f"Invalid JSON: {e}"}
    comps = data.get('components', [])
    is_first = data.get('clear', False)
    if is_first:
        pending_extra["latest"] = comps
    else:
        pending_extra.setdefault("latest", []).extend(comps)
    print(f"[DEBUG] Extra components: +{len(comps)} (clear={is_first}, total: {len(pending_extra['latest'])})")
    return {"status": "ok", "count": len(pending_extra["latest"])}


@app.get("/api/test")
async def health_check():
    return {"status": "ok", "version": "1.0.0", "ready": True}


# ─── Temporary storage for multi-part submissions ───
pending_extra: Dict[str, list] = {}


@app.post("/api/route")
async def submit_routing_job(request: Request):
    # Cancel any active routing job before starting a new one
    if _active_job_id and _active_job_id in jobs:
        old_job = jobs[_active_job_id]
        if old_job.status in ("pending", "converting", "routing"):
            old_job.cancelled.set()
            print(f"[DEBUG] Cancelled previous job {_active_job_id}")

    raw_body = await request.body()
    print(f"[DEBUG] Raw body size: {len(raw_body)} bytes")
    try:
        body_str = raw_body.decode('utf-8')
        data = json.loads(body_str)
    except Exception as e:
        return {"error": f"Invalid JSON: {e}"}

    # Check if there are pending extra components for this session
    extra_key = "latest"
    extra_comps = pending_extra.pop(extra_key, [])
    if extra_comps:
        data.setdefault('components', []).extend(extra_comps)
        print(f"[DEBUG] Merged {len(extra_comps)} extra components from /api/extra-components")

    # Debug: check raw JSON component count vs parsed
    raw_comp_count = len(data.get('components', []))
    print(f"[DEBUG] Raw JSON components: {raw_comp_count}")

    pcb_data = PCBJsonData(**data)

    print(f"[DEBUG] Parsed components: {len(pcb_data.components)}")

    # Debug: board outline
    board = pcb_data.board
    outline_lines = board.outline_lines if hasattr(board, 'outline_lines') else []
    outline_arcs = board.outline_arcs if hasattr(board, 'outline_arcs') else []
    print(f"[DEBUG] Board outline: {len(outline_lines)} lines, {len(outline_arcs)} arcs")
    raw_board = data.get('board', {})
    print(f"[DEBUG] Raw board keys: {list(raw_board.keys())}")
    print(f"[DEBUG] Raw outlineLines count: {len(raw_board.get('outlineLines', raw_board.get('outline_lines', [])))}")
    print(f"[DEBUG] Raw outlineArcs count: {len(raw_board.get('outlineArcs', raw_board.get('outline_arcs', [])))}")

    # Debug: print coordinate info
    print(f"\n=== DEBUG: Received PCB Data ===")
    print(f"Nets: {len(pcb_data.nets)}, Components: {len(pcb_data.components)}")
    print(f"Routing config: mode={pcb_data.routing_config.routing_mode}, "
          f"nets_to_route={pcb_data.routing_config.nets_to_route[:5]}..., "
          f"track_width={pcb_data.routing_config.track_width}, "
          f"clearance={pcb_data.routing_config.clearance}, "
          f"board_edge_clearance={pcb_data.routing_config.board_edge_clearance}, "
          f"grid_step={pcb_data.routing_config.grid_step}, "
          f"layers={pcb_data.routing_config.layers_to_use}")
    if pcb_data.components:
        c = pcb_data.components[0]
        print(f"First component: {c.designator} pos=({c.x}, {c.y}) rotation={c.rotation}")
        if c.pads:
            for p in c.pads[:3]:
                print(f"  Pad {p.number}: pos=({p.x}, {p.y}) net={p.net} size=({p.width}x{p.height}) drill={p.drill}")
    print(f"=== END DEBUG ===\n")

    job_id = str(uuid_mod.uuid4())[:8]
    job = Job(job_id, pcb_data)
    jobs[job_id] = job

    thread = threading.Thread(target=_run_routing_job, args=(job,), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "pending"}


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return {"status": "not_found", "error": f"Job {job_id} not found"}
    return {"job_id": job_id, "status": job.status}


@app.get("/api/result/{job_id}")
async def get_job_result(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return RoutingResult(status="not_found", error=f"Job {job_id} not found")
    return job.result


@app.post("/api/cancel/{job_id}")
async def cancel_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return {"status": "not_found"}
    job.cancelled.set()
    if job.process is not None:
        try:
            job.process.terminate()
        except Exception:
            pass
    return {"status": "cancelled"}


@app.get("/api/config/defaults")
async def get_default_config():
    return {
        "track_width": 10,
        "clearance": 8,
        "via_size": 24,
        "via_drill": 12,
        "layers_to_use": [1, 2],
    }


@app.post("/api/review/preflight")
async def review_preflight(request: Request):
    """Run fast checks that do not depend on the KiCadRoutingTools runtime."""
    try:
        raw = await request.body()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Expected a PCB JSON object.")
        return build_preflight(payload)
    except Exception as exc:
        return {"verdict": "fail", "readiness_score": 0, "findings": [_preflight_error(exc)]}


def _preflight_error(exc: Exception):
    return {"severity": "error", "code": "PREFLIGHT_REQUEST", "message": str(exc)}


# ─── AI Analysis Endpoints ───

async def _parse_pcb_data(request: Request):
    """Helper to parse PCB JSON from request body."""
    import json as _json
    raw = await request.body()
    data = _json.loads(raw.decode('utf-8'))
    return PCBJsonData(**data)


@app.post("/api/analyze/board-summary")
async def analyze_board_summary(request: Request):
    """Quick board overview: components, layers, nets, BGA detection."""
    try:
        pcb_data = await _parse_pcb_data(request)
        return analysis_module.analyze_board_summary(pcb_data)
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/analyze/power-nets")
async def analyze_power_nets(request: Request):
    """AI power net analysis: component roles, current paths, track width recommendations."""
    try:
        pcb_data = await _parse_pcb_data(request)
        return analysis_module.analyze_power_nets(pcb_data)
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/analyze/diff-pairs")
async def analyze_diff_pairs(request: Request):
    """Detect differential pairs from net naming conventions."""
    try:
        pcb_data = await _parse_pcb_data(request)
        return analysis_module.analyze_diff_pairs(pcb_data)
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/analyze/bus-groups")
async def analyze_bus_groups(request: Request):
    """Detect bus groups (clusters of parallel nets with clustered endpoints)."""
    try:
        pcb_data = await _parse_pcb_data(request)
        return analysis_module.analyze_bus_groups(pcb_data)
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/analyze/net-stats")
async def analyze_net_stats(request: Request):
    """Net statistics: total, unrouted, power nets, per-net details."""
    try:
        pcb_data = await _parse_pcb_data(request)
        return analysis_module.analyze_net_stats(pcb_data)
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    print("Starting JLCEDA Design Companion Bridge on http://127.0.0.1:8766")
    print("Press Ctrl+C to stop")
    uvicorn.run(app, host="127.0.0.1", port=8766)
