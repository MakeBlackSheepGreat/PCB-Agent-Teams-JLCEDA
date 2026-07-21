# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

The EasyEDA Pro extension + Python bridge server half of the KiRouting integration. It collects PCB state from EasyEDA Pro, sends it to a local FastAPI server, which converts it to KiCad format, invokes the **KiCadRoutingTools** A* router (Rust-accelerated), diffs the result, and writes the new tracks/vias back into EasyEDA. The router engine itself lives in a sibling directory (`../KiCadRoutingTools/`) and is **not** part of this repo — this repo only consumes it.

## Build & Development Commands

```bash
# Compile TypeScript → dist/index.js (esbuild, IIFE, browser platform, no minify)
npm run compile

# Full build: compile + package .eext ZIP into build/dist/
npm run build

# Watch mode (rebuild on change)
npx ts-node ./config/esbuild.prod.ts --watch

# Lint + format (runs on commit via husky/lint-staged)
npm run fix

# Start the bridge server (from ./bridge_server/)
cd bridge_server && python server.py
# or: bridge_server/start_server.bat   (Windows — also auto-provisions deps, see below)
# or: bridge_server/start_server.sh    (Linux/macOS)
```

The shippable artifact is `build/dist/kirouting-integration_v{version}.eext` — a ZIP of everything **not** matched by `.edaignore` (notably: `dist/`, `locales/`, `iframe/`, `images/`, `extension.json`, README). Source/config/build dirs are excluded from the package.

There is **no JS test suite** in this repo. Routing correctness is verified via the integration tests in `../KiCadRoutingTools/tests/`.

### Bridge server provisioning (`start_server.bat` / `.sh`)

The start scripts are designed for end-users who cloned only this repo. On first run they:
1. Download any missing `bridge_server/*.py` from the GitHub `main` branch.
2. Download + extract `KiCadRoutingTools` into `bridge_server/KiCadRoutingTools/` (gitignored).
3. Run `python build_router.py` to build the Rust `grid_router.pyd` if absent.
4. `pip install -r requirements.txt` if imports fail, then start `server.py`.

When developing locally with the full workspace checked out, `routing_runner.py` resolves `KiCadRoutingTools` from `../KiCadRoutingTools/` or `../../KiCadRoutingTools/` — you can usually just run `python server.py` directly.

## Architecture

### Extension (TypeScript — `src/index.ts`)

Single entry compiled to `dist/index.js`, loaded inside EasyEDA Pro. Key pieces:

- **`BridgeClient`** — HTTP client to `http://localhost:8765`. Methods map 1:1 to server endpoints. Uses `eda.sys_ClientUrl.request`.
- **`collectFullPCBData(config)`** — walks EasyEDA's `pcb_Primitive*` APIs to build the PCB JSON: components+pads, standalone pads, existing tracks/vias, net names, and the board outline. This is the most fragile part — EasyEDA returns proxied objects, so pad geometry is parsed from raw `pad` arrays (`[shape, w, h]` or polygon point lists) and board outline polylines from `R`/`CIRCLE`/`L`/`ARC`/`CARC`/`C` source commands on layer 11.
- **`applyResults(result, netsToRoute, unitsMm)`** — for each target net, **deletes** existing lines+vias first, then creates the routed ones in parallel batches (concurrency 50). Coordinates are converted mm→mil on write unless `units_mm`.
- **MessageBus bridge to the iframe UI** — topics are prefixed `kirouting-integration.`. `onIframeMessage`/`sendToIframe` wrap `eda.sys_MessageBus`. Inbound topics the extension handles: `start-routing`, `cancel-routing`, `get-nets`, `get-components`, `get-layers`, `get-drc-limits`, `retry-connection`.
- **Generation guard** — handlers check `_G.__kicadBridgeGeneration` and bail if it doesn't match, so a hot-reloaded extension doesn't stack duplicate subscribers. Preserve this pattern when adding handlers.
- **DRC pre-check** — before submitting, `start-routing` validates track/via/clearance/edge values against `pcb_Drc.getCurrentRuleConfiguration()` and blocks submission (throws `__DRC_BLOCKED__`) on violation.

`extension.json` registers a PCB header menu → `autoRouteAll()` (checks server health, else shows `iframe/service-not-found.html`, else opens `iframe/index.html`).

### Bridge Server (Python/FastAPI — `bridge_server/`)

Job-based async routing. One job runs at a time (`_routing_lock`); submitting a new job sets `cancelled` on the previous active one.

- **`server.py`** — FastAPI app. `POST /api/route` parses the body into `PCBJsonData`, spawns a daemon thread running `_run_routing_job`, returns a `job_id`. **Job state machine:** `pending → converting → routing → converting_back → completed | failed | cancelled`.
- **`routing_runner.py`** — `run_routing()` orchestrates: validate params → convert EasyEDA→KiCad → dispatch by `routing_mode` → diff. Three modes, each with a direct-import path and a subprocess fallback:
  - `single_ended` (default) → `route.batch_route()`
  - `diff_pair` → `route_diff.batch_route_diff_pairs()`
  - `bga_fanout` → `bga_fanout.fanout_bga()`

  A `SystemExit` on import usually means the Rust router isn't built — the error message tells you to run `python build_router.py` in `KiCadRoutingTools/`.
- **`easyeda_to_kicad.py`** — `convert(pcb_data)` → KiCad S-expression `.kicad_pcb`.
- **`kicad_diff.py`** — `extract_new_routes()` compares input vs output `.kicad_pcb`, returns only newly-added tracks/vias, converted back to EasyEDA coordinate space.
- **`analysis.py`** — powers the `/api/analyze/*` endpoints (board summary, power nets, diff-pair detection, bus groups, net stats) by converting to KiCad format and reusing KiCadRoutingTools' analysis modules.

**Debugging artifacts:** every job copies its `input.kicad_pcb` and `output_routed.kicad_pcb` into `bridge_server/debug_output/` (gitignored). Check there first when a route looks wrong.

### Standalone pads flow

Pads not attached to a component (mounting holes, test points) are collected with synthetic `_PAD{N}` designators and sent **separately** via `POST /api/extra-components` in chunks of 20 (`clear: true` on the first). The server stashes them in `pending_extra["latest"]` and merges them into the next `/api/route` body. Net names must be preserved.

## Bridge Server API

All routing endpoints take `job_id` as a **path parameter** (not query string):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/test` | Health check (`{status:"ok"}`) |
| `POST` | `/api/extra-components` | Pre-send standalone pads (chunked) |
| `POST` | `/api/route` | Submit routing job → `{job_id, status:"pending"}` |
| `GET` | `/api/status/{job_id}` | Poll job state |
| `GET` | `/api/result/{job_id}` | Fetch `RoutingResult` (tracks/vias/stats) |
| `POST` | `/api/cancel/{job_id}` | Cancel a running job |
| `GET` | `/api/config/defaults` | Default params (mils) |
| `POST` | `/api/analyze/{board-summary,power-nets,diff-pairs,bus-groups,net-stats}` | AI board analysis (body = full PCB JSON) |

## Key Conventions

- **Units — the `units_mm` flag.** The default and historical unit is **mils** (1 mil = 0.0254 mm). `RoutingConfig` model defaults are mils (`track_width=10`, `clearance=8`, `via_size=24`, `via_drill=12`, `grid_step=6`). When `units_mm` is `false` (default), the server converts mil→mm before calling the router; the router **always** works in mm. Set `units_mm=true` to pass mm values straight through. The extension mirrors this flag in both directions. `coord_transform.py` does the rounding (`mil_to_mm` → 6 dp, `mm_to_mil` → 3 dp).
- **Coordinate systems.** EasyEDA: mils, top-left origin. KiCad: mm, bottom-left origin. The `y`-flip happens in `easyeda_to_kicad.convert()`.
- **Layer mapping.** EasyEDA layer IDs: `1`=F.Cu, `2`=B.Cu, `15–44`=In1–In30.Cu. Inner-layer numbering is **dynamic** (`layer_mapping.set_dynamic_layer_map`): inner IDs are renumbered `In1.Cu, In2.Cu, …` by their sorted position in the board's layer stack, not by their raw EasyEDA ID. The extension collects only layers that are `type=SIGNAL, layerStatus=1` (plus F.Cu/B.Cu always).
- **Pydantic models accept both camelCase and snake_case** (`models.py` uses `AliasChoices` everywhere). The extension sends camelCase (`startX`, `outlineLines`); either is valid server-side.
- **`kicad_file_path`** (optional) — pass a native `.kicad_pcb` path to bypass EasyEDA→KiCad conversion entirely. The runner then computes a coordinate `offset_x/offset_y` by matching the first component's position between the two origins and subtracts it during diffing.
- **Parameter minimums** (`routing_runner.PARAM_MINIMUMS`, in mm): track_width≥0.05, clearance≥0.05, via_size≥0.2, via_drill≥0.1, grid_step≥0.01, board_edge_clearance≥0.5. The extension additionally validates against EasyEDA's live DRC rules before submission.
- **Board edge clearance ≥ 0.5mm** avoids staircase routing artifacts near the outline.

## CI / Release (`.github/workflows/build.yml`)

On push to `main`/`master`: `npm run build`, then if tag `v{version}` (from `extension.json`) doesn't already exist, create it and publish a GitHub Release with **two** locale-specific artifacts:
- `kirouting-integration_v{version}_zh-cn.eext` — Chinese README + `locales/extensionJson/zh-Hans.json` swapped into `extension.json`.
- `kirouting-integration_v{version}_global.eext` — English README + `locales/extensionJson/en.json`.

Release notes are extracted from the matching version section of `CHANGELOG.md`. The un-suffixed base `.eext` is deleted — only the two locale variants ship. To cut a release, bump `version` in `extension.json` and add a `## v{version}` section to `CHANGELOG.md`.

## When Editing

- **Don't run `cargo build` directly** for the Rust router — use `python build_router.py` in `KiCadRoutingTools/` (it handles the Python extension build). Bump `rust_router/Cargo.toml` version + README when touching `rust_router/`.
- After changing `extension.json` `version`, update `CHANGELOG.md` or CI will fall back to a generic release note.
- The iframe UI (`iframe/index.html` + `app.js`) communicates only via MessageBus — there is no direct function call into the extension. Add new UI↔extension interactions as new prefixed topics.
- `eda`, `uuid` (the extension UUID), and the `@jlceda/pro-api-types` globals are provided by the EasyEDA runtime at load time; `tsconfig.json` includes the API types from `node_modules`.
