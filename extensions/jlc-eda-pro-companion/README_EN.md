# KiRouting Integration

English | [中文](README.md)

A complete solution bridging **KiCadRouting Tools** (Rust-accelerated A* autorouter) to **EasyEDA Pro**.

## Project Links

| Project | URL | Description |
|---------|-----|-------------|
| This project (Extension + Bridge Server) | https://github.com/easyeda/eext-kirouting-integration | EasyEDA Pro extension and Python bridge server |
| KiCadRouting Tools (Routing Engine) | https://github.com/drandyhaas/KiCadRoutingTools/tree/main#command-line-interface | Rust-accelerated A* router (original project) |

## System Architecture

```
┌─────────────────────┐     HTTP (localhost:8765)     ┌──────────────────────┐
│  EasyEDA Pro Editor  │ ◄──────────────────────────► │   Bridge Server      │
│                      │                              │   (Python/FastAPI)   │
│  ┌───────────────┐  │                              │  ┌────────────────┐  │
│  │ TypeScript     │  │  ← Collect PCB data /        │  │ Format         │  │
│  │ Extension      │  │    Write back results →       │  │ Conversion     │  │
│  │ (kirouting-    │  │                              │  │ EasyEDA ↔ KiCad│  │
│  │  integration)  │  │                              │  └───────┬────────┘  │
│  └───────────────┘  │                              │          │           │
└─────────────────────┘                              │          ▼           │
                                                     │  ┌────────────────┐  │
                                                     │  │ KiCadRouting   │  │
                                                     │  │ Tools Engine   │  │
                                                     │  │ (Python + Rust)│  │
                                                     │  └────────────────┘  │
                                                     └──────────────────────┘
```

## Quick Start (User Installation)

Two steps to get started:

### Step 1: Install the Extension

Search for **KiRouting Integration** in the **Extension Marketplace** of EasyEDA Pro and install it.

Alternatively, download the `.eext` file from [GitHub Releases](https://github.com/easyeda/eext-kirouting-integration/releases/latest) and import it via **Extensions** → **Extension Manager** → **Install from Local**.

### Step 2: Get the Startup Script

Clone the bridge server from this repository:

```bash
git clone https://github.com/easyeda/eext-kirouting-integration.git
```

Or click **Code** → **Download ZIP** on the [project page](https://github.com/easyeda/eext-kirouting-integration) and extract it.

The startup script is located at `bridge_server/start_server.bat`.

### Step 3: Start the Bridge Server

Double-click `bridge_server/start_server.bat`. The script will automatically:

1. Detect Python environment; install via winget if not found
2. Detect and install Python dependencies (fastapi, uvicorn, pydantic, numpy)
3. Detect KiCadRoutingTools; clone from GitHub if not found
4. Detect Rust router build artifacts; compile if not built (falls back to pure Python if Rust is unavailable)
5. Start the bridge server (listening at `http://localhost:8765`)

> First run requires internet to download dependencies. Subsequent runs will skip completed steps.

### Step 4: Start Using

1. Open a PCB file
2. Click **KiRouting Autorouter** → **Open Routing Tool...** in the top menu bar
3. Select nets, configure parameters, and click **Start Routing** in the dialog
4. Wait for routing to complete; results are automatically written back to the PCB

> If the server is not running, the extension will show a guided dialog with download links and instructions.

## Routing Features

- **Single-ended Routing** — A* pathfinding with MPS net ordering, rip-up and reroute, bus detection
- **Differential Pair Routing** — Centerline + offset, automatic polarity swap, GND via placement
- **Power Planes** — Automatic via connection from SMD pads to inner copper, Voronoi partitioning
- **BGA Fanout** — Automatic escape path generation
- **QFN Fanout** — QFN/QFP pad extension
- **Length Matching** — DDR4 byte lane auto-grouping, serpentine routing
- **Impedance Control** — Per-layer trace width calculation based on stackup
- **Target Swap Optimization** — Hungarian algorithm for crossover minimization

## Routing Workflow (Data Flow)

```
1. Extension reads PCB data from EasyEDA Pro (components, pads, nets, existing tracks, board outline)
       ↓
2. Large component lists sent in chunks → POST /api/extra-components
       ↓
3. Full PCB data + routing parameters → POST /api/route
       ↓
4. Server format conversion: EasyEDA JSON → .kicad_pcb (coordinate system, units, layer mapping)
       ↓
5. Invoke KiCadRoutingTools to execute A* routing
       ↓
6. Diff input/output .kicad_pcb to extract new tracks and vias
       ↓
7. Convert back to EasyEDA coordinate system
       ↓
8. Extension polls GET /api/status/{job_id} until completion
       ↓
9. Extension fetches results via GET /api/result/{job_id}
       ↓
10. Write new tracks/vias into EasyEDA Pro PCB editor
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/test` | Health check, confirm server is running |
| POST | `/api/extra-components` | Send large component lists in chunks |
| POST | `/api/route` | Submit routing job (async, returns job_id) |
| GET | `/api/status/{job_id}` | Query job status |
| GET | `/api/result/{job_id}` | Get routing results (tracks + vias) |
| POST | `/api/cancel/{job_id}` | Cancel a running job |
| GET | `/api/config/defaults` | Get default routing parameters |
| POST | `/api/analyze/board-summary` | Board overview analysis |
| POST | `/api/analyze/power-nets` | Power net analysis |
| POST | `/api/analyze/diff-pairs` | Differential pair detection |
| POST | `/api/analyze/bus-groups` | Bus group detection |
| POST | `/api/analyze/net-stats` | Net statistics |

## Developer Guide

The following content is for developers who need to modify source code or build from source.

### Directory Structure

```
KICAD Routing-intergration/
├── KiCadRoutingTools/              # Routing engine (Rust-accelerated A* router)
│   ├── route.py                    # Single-ended routing CLI
│   ├── route_diff.py               # Differential pair routing CLI
│   ├── route_planes.py             # Power/ground plane CLI
│   ├── rust_router/                # Rust A* implementation
│   └── ...
├── kirouting-integration/           # EasyEDA Pro extension + bridge server
│   ├── src/index.ts                # Extension entry point (TypeScript)
│   ├── iframe/                     # Extension UI (parameter configuration dialog)
│   ├── bridge_server/              # Python bridge server
│   │   ├── server.py               # FastAPI server (port 8765)
│   │   ├── start_server.bat        # One-click startup script (auto-installs dependencies)
│   │   ├── routing_runner.py       # Routing orchestration (calls KiCadRoutingTools)
│   │   ├── easyeda_to_kicad.py     # EasyEDA JSON → KiCad format conversion
│   │   ├── kicad_diff.py           # Diff input/output to extract new tracks
│   │   ├── coord_transform.py      # Coordinate system conversion (mil ↔ mm)
│   │   ├── layer_mapping.py        # Layer mapping (EasyEDA ↔ KiCad)
│   │   ├── models.py               # Pydantic data models
│   │   ├── analysis.py             # AI analysis (power nets, differential pairs, etc.)
│   │   └── requirements.txt        # Python dependencies
│   ├── extension.json              # Extension manifest
│   ├── package.json                # Node.js project config
│   └── tsconfig.json               # TypeScript config
└── README.md                       # This file
```

### Requirements

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.8+ | Bridge server |
| Node.js | 20.5.0+ | Compile extension |
| Rust | stable | Compile router (optional, falls back to pure Python) |
| EasyEDA Pro | 2.3.0+ | Run extension |

### Development Commands

```bash
# === Extension Development ===
cd kirouting-integration
npm install                  # Install frontend dependencies
npm run compile              # Compile TypeScript
npm run build                # Compile + package .eext
npm run fix                  # Code formatting + lint

# === Bridge Server ===
cd kirouting-integration/bridge_server
pip install -r requirements.txt  # Install Python dependencies
python server.py                 # Start server

# === Routing Engine ===
cd KiCadRoutingTools
python build_router.py       # Compile Rust router (do not use cargo build directly)

# === Testing ===
cd KiCadRoutingTools
python tests/test_fanout_and_route.py --all        # Full integration test
python tests/test_fanout_and_route.py --all --quick  # Quick mode

# === Validation ===
cd KiCadRoutingTools
python check_drc.py output.kicad_pcb               # DRC check
python check_connected.py output.kicad_pcb         # Connectivity check
```

## Notes

- The bridge server can only run one routing job at a time; submitting a new job automatically cancels the previous one
- Board edge clearance (board_edge_clearance) should be ≥ 0.5mm to avoid staircase routing artifacts
- Unit conversion chain: EasyEDA UI (mm) → Extension internal (mil) → Server (mil→mm) → Routing engine (mm)
- After modifying the Rust router, update the version number in `rust_router/Cargo.toml`

## License

- KiCadRoutingTools: MIT License
- kirouting-integration: Apache-2.0 License
