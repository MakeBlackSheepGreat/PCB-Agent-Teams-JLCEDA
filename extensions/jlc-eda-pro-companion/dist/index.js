"use strict";
var edaEsbuildExportName = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // src/index.ts
  var src_exports = {};
  __export(src_exports, {
    about: () => about,
    autoRouteAll: () => autoRouteAll,
    runBoardPreflight: () => runBoardPreflight
  });
  var uuid = "f7a6e2e44d4a4a2a9e3d65d84a1d5c71";
  var _G = globalThis;
  var _bridgeInitDone = !!_G.__jlcEdaCompanionLoaded;
  var MSG_PREFIX = "jlc-eda-design-companion.";
  var BRIDGE_CONFIG = {
    port: 8766,
    host: "localhost",
    pollInterval: 2e3,
    timeout: 6e5
  };
  function dbg(label, obj) {
    console.log("[JlcEdaCompanion][ext] " + label, obj !== void 0 ? obj : "");
  }
  function mil_to_mm(value) {
    return value * 0.0254;
  }
  function mm_to_mil(value) {
    return value / 0.0254;
  }
  function t(key, ...args) {
    return eda.sys_I18n.text(key, uuid, void 0, ...args);
  }
  var EASYEDA_TO_KICAD_LAYER = {
    1: "F.Cu",
    2: "B.Cu",
    15: "In1.Cu",
    16: "In2.Cu",
    17: "In3.Cu",
    18: "In4.Cu",
    19: "In5.Cu",
    20: "In6.Cu",
    21: "In7.Cu",
    22: "In8.Cu",
    23: "In9.Cu",
    24: "In10.Cu",
    25: "In11.Cu",
    26: "In12.Cu",
    27: "In13.Cu",
    28: "In14.Cu",
    29: "In15.Cu",
    30: "In16.Cu",
    31: "In17.Cu",
    32: "In18.Cu",
    33: "In19.Cu",
    34: "In20.Cu",
    35: "In21.Cu",
    36: "In22.Cu",
    37: "In23.Cu",
    38: "In24.Cu",
    39: "In25.Cu",
    40: "In26.Cu",
    41: "In27.Cu",
    42: "In28.Cu",
    43: "In29.Cu",
    44: "In30.Cu"
  };
  var BridgeClient = class {
    baseUrl;
    constructor() {
      this.baseUrl = `http://${BRIDGE_CONFIG.host}:${BRIDGE_CONFIG.port}`;
    }
    async checkServer() {
      try {
        const resp = await eda.sys_ClientUrl.request(`${this.baseUrl}/api/test`);
        if (!resp.ok) return false;
        const data = await resp.json();
        return data?.status === "ok";
      } catch {
        return false;
      }
    }
    async submitExtraComponents(components) {
      const CHUNK_SIZE = 20;
      for (let i = 0; i < components.length; i += CHUNK_SIZE) {
        const chunk = components.slice(i, i + CHUNK_SIZE);
        const body = JSON.stringify({ components: chunk, clear: i === 0 });
        const resp = await eda.sys_ClientUrl.request(`${this.baseUrl}/api/extra-components`, "POST", body);
        if (!resp.ok) {
          console.error("[JlcEdaCompanion] extra-components chunk failed");
        }
      }
    }
    async submitRoutingJob(pcbData) {
      const body = JSON.stringify(pcbData);
      console.log(`[JlcEdaCompanion] Submit body size: ${body.length} bytes, components in JSON: ${JSON.parse(body).components.length}`);
      const resp = await eda.sys_ClientUrl.request(`${this.baseUrl}/api/route`, "POST", body);
      if (!resp.ok) throw new Error(await resp.text() || "Failed to submit");
      const data = await resp.json();
      if (!data?.job_id) throw new Error(data?.error ?? "No job_id");
      return data.job_id;
    }
    async pollStatus(jobId) {
      const resp = await eda.sys_ClientUrl.request(`${this.baseUrl}/api/status/${jobId}`);
      if (!resp.ok) return "unknown";
      const data = await resp.json();
      return data?.status ?? "unknown";
    }
    async getResult(jobId) {
      const resp = await eda.sys_ClientUrl.request(`${this.baseUrl}/api/result/${jobId}`);
      if (!resp.ok) throw new Error("Failed to get result");
      return await resp.json();
    }
    async postJson(path, payload) {
      const resp = await eda.sys_ClientUrl.request(
        `${this.baseUrl}${path}`,
        "POST",
        JSON.stringify(payload)
      );
      if (!resp.ok) throw new Error(await resp.text() || `Request failed: ${path}`);
      return await resp.json();
    }
    async cancelJob(jobId) {
      await eda.sys_ClientUrl.request(`${this.baseUrl}/api/cancel/${jobId}`, "POST");
    }
  };
  async function collectLayers() {
    const result = [];
    const layers = await eda.pcb_Layer.getAllLayers();
    for (const layer of layers) {
      const layerAny = layer;
      const id = layerAny.layerId ?? layerAny.id;
      if (id === void 0) continue;
      if (id === 1 || id === 2) {
        result.push({ id, name: EASYEDA_TO_KICAD_LAYER[id] });
      } else if (EASYEDA_TO_KICAD_LAYER[id]) {
        const layerType = (layerAny.type ?? "").toUpperCase();
        const layerStatus = String(layerAny.layerStatus ?? "");
        if (layerType === "SIGNAL" && layerStatus === "1") {
          result.push({ id, name: EASYEDA_TO_KICAD_LAYER[id] });
        }
      }
    }
    if (result.length === 0) {
      result.push({ id: 1, name: "F.Cu" });
      result.push({ id: 2, name: "B.Cu" });
    }
    return result;
  }
  async function collectFullPCBData(config) {
    const layers = await collectLayers();
    const components = [];
    const allComps = await eda.pcb_PrimitiveComponent.getAll();
    for (const comp of allComps) {
      const compAny = comp;
      const primitiveId = compAny.primitiveId ?? compAny.id ?? "";
      const designator = compAny.designator ?? compAny.name ?? "";
      const x = compAny.x ?? 0;
      const y = compAny.y ?? 0;
      const layer = compAny.layer ?? 1;
      const rotation = compAny.rotation ?? 0;
      const pads = [];
      if (primitiveId) {
        const pins = await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(primitiveId);
        if (pins) {
          let debuggedFirst = components.length > 0;
          for (const pin of pins) {
            let pinData;
            try {
              pinData = JSON.parse(JSON.stringify(pin));
            } catch (e) {
              pinData = pin;
            }
            const padArr = pinData.pad;
            let padShape = "round";
            let padWidth = 0;
            let padHeight = 0;
            if (Array.isArray(padArr) && padArr.length >= 2) {
              padShape = (padArr[0] || "round").toString().toLowerCase();
              if (typeof padArr[1] === "number") {
                padWidth = padArr[1] || 0;
                padHeight = padArr.length >= 3 && typeof padArr[2] === "number" ? padArr[2] || padWidth : padWidth;
              } else if (Array.isArray(padArr[1])) {
                const raw = padArr[1];
                const nums = [];
                for (let pi = 0; pi < raw.length; pi++) {
                  if (typeof raw[pi] === "number") nums.push(raw[pi]);
                }
                let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
                for (let pi = 0; pi < nums.length - 1; pi += 2) {
                  if (nums[pi] < minX) minX = nums[pi];
                  if (nums[pi] > maxX) maxX = nums[pi];
                  if (nums[pi + 1] < minY) minY = nums[pi + 1];
                  if (nums[pi + 1] > maxY) maxY = nums[pi + 1];
                }
                if (minX !== Infinity) {
                  padWidth = maxX - minX;
                  padHeight = maxY - minY;
                }
                padShape = "rect";
              }
            }
            if (!debuggedFirst) {
              console.log("[JlcEdaCompanion] COLLECT pad raw:", JSON.stringify(padArr), "parsed w:", padWidth, "h:", padHeight);
              debuggedFirst = true;
            }
            let drill = 0;
            const holeData = pinData.hole;
            if (Array.isArray(holeData) && holeData.length >= 2) {
              drill = holeData[1] || 0;
            }
            pads.push({
              number: pinData.padNumber ?? pinData.number ?? "",
              x: pinData.x ?? 0,
              y: pinData.y ?? 0,
              net: pinData.net ?? "",
              layer: pinData.layer ?? layer,
              shape: padShape,
              width: padWidth,
              height: padHeight,
              drill,
              rotation: pinData.rotation ?? 0
            });
          }
        }
      }
      components.push({ designator, x, y, layer, rotation, pads });
    }
    const netNames = await eda.pcb_Net.getAllNetsName();
    try {
      const padApi = eda.pcb_PrimitivePad;
      if (padApi && typeof padApi.getAll === "function") {
        const standalonePads = await padApi.getAll();
        if (standalonePads && standalonePads.length > 0) {
          const existingPositions = /* @__PURE__ */ new Set();
          for (const comp of components) {
            for (const pad of comp.pads || []) {
              const key = `${Math.round(pad.x * 10)},${Math.round(pad.y * 10)}`;
              existingPositions.add(key);
            }
          }
          let spIdx = 0;
          for (const sp of standalonePads) {
            let spData;
            try {
              spData = JSON.parse(JSON.stringify(sp));
            } catch (e) {
              spData = sp;
            }
            const spX = spData.x ?? 0;
            const spY = spData.y ?? 0;
            const posKey = `${Math.round(spX * 10)},${Math.round(spY * 10)}`;
            if (existingPositions.has(posKey)) continue;
            const padArr = spData.pad;
            let padShape = "round";
            let padWidth = 0;
            let padHeight = 0;
            if (Array.isArray(padArr) && padArr.length >= 2) {
              padShape = (padArr[0] || "round").toString().toLowerCase();
              if (typeof padArr[1] === "number") {
                padWidth = padArr[1] || 0;
                padHeight = padArr.length >= 3 && typeof padArr[2] === "number" ? padArr[2] || padWidth : padWidth;
              } else if (Array.isArray(padArr[1])) {
                const raw = padArr[1];
                const nums = [];
                for (let pi = 0; pi < raw.length; pi++) {
                  if (typeof raw[pi] === "number") nums.push(raw[pi]);
                }
                let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
                for (let pi = 0; pi < nums.length - 1; pi += 2) {
                  if (nums[pi] < minX) minX = nums[pi];
                  if (nums[pi] > maxX) maxX = nums[pi];
                  if (nums[pi + 1] < minY) minY = nums[pi + 1];
                  if (nums[pi + 1] > maxY) maxY = nums[pi + 1];
                }
                if (minX !== Infinity) {
                  padWidth = maxX - minX;
                  padHeight = maxY - minY;
                }
                padShape = "rect";
              }
            }
            let drill = 0;
            const holeData = spData.hole;
            if (Array.isArray(holeData) && holeData.length >= 2) {
              drill = holeData[1] || 0;
            }
            components.push({
              designator: `_PAD${spIdx}`,
              x: spX,
              y: spY,
              layer: spData.layer ?? 1,
              rotation: 0,
              pads: [{
                number: spData.padNumber ?? "1",
                x: spX,
                y: spY,
                net: spData.net ?? "",
                layer: spData.layer ?? 1,
                shape: padShape,
                width: padWidth,
                height: padHeight,
                drill,
                rotation: spData.rotation ?? 0
              }]
            });
            spIdx++;
          }
          console.log("[JlcEdaCompanion] Standalone pads: added", spIdx, "truly standalone (filtered from", standalonePads.length, "total)");
        }
      }
    } catch (e) {
      console.log("[JlcEdaCompanion] standalone pad collection error:", e?.message ?? e);
    }
    const existingTracks = [];
    const allLines = await eda.pcb_PrimitiveLine.getAll();
    for (const line of allLines) {
      const lineAny = line;
      const net = lineAny.net ?? "";
      if (!net) continue;
      existingTracks.push({
        net,
        layer: lineAny.layer ?? 1,
        startX: lineAny.startX ?? 0,
        startY: lineAny.startY ?? 0,
        endX: lineAny.endX ?? 0,
        endY: lineAny.endY ?? 0,
        width: lineAny.lineWidth ?? lineAny.width ?? 10
      });
    }
    const existingVias = [];
    const allVias = await eda.pcb_PrimitiveVia.getAll();
    for (const via of allVias) {
      const viaAny = via;
      const net = viaAny.net ?? "";
      if (!net) continue;
      existingVias.push({
        net,
        x: viaAny.x ?? 0,
        y: viaAny.y ?? 0,
        holeDiameter: viaAny.holeDiameter ?? 12,
        diameter: viaAny.diameter ?? 24,
        startLayer: viaAny.startLayer ?? 1,
        endLayer: viaAny.endLayer ?? 2
      });
    }
    const lineLayers = /* @__PURE__ */ new Set();
    for (const line of allLines) {
      const lineAny = line;
      const l = lineAny.layer ?? 0;
      if (l > 0) lineLayers.add(l);
    }
    console.log("[JlcEdaCompanion] Line layers found:", Array.from(lineLayers).sort().join(","));
    const BOARD_OUTLINE_LAYER = 11;
    const outlineLines = [];
    for (const line of allLines) {
      const lineAny = line;
      if ((lineAny.layer ?? 0) === BOARD_OUTLINE_LAYER) {
        outlineLines.push({
          startX: lineAny.startX ?? 0,
          startY: lineAny.startY ?? 0,
          endX: lineAny.endX ?? 0,
          endY: lineAny.endY ?? 0
        });
      }
    }
    const outlineArcs = [];
    try {
      const allArcs = await eda.pcb_PrimitiveArc.getAll();
      if (allArcs) {
        for (const arc of allArcs) {
          const arcAny = arc;
          if ((arcAny.layer ?? 0) === BOARD_OUTLINE_LAYER) {
            outlineArcs.push({
              startX: arcAny.startX ?? 0,
              startY: arcAny.startY ?? 0,
              endX: arcAny.endX ?? 0,
              endY: arcAny.endY ?? 0,
              arcAngle: arcAny.arcAngle ?? 0
            });
          }
        }
      }
    } catch (e) {
      console.log("[JlcEdaCompanion] board outline arcs error:", e?.message ?? e);
    }
    try {
      const allPolylines = await eda.pcb_PrimitivePolyline.getAll();
      if (allPolylines) {
        console.log("[JlcEdaCompanion] Total polylines:", allPolylines.length);
        for (const poly of allPolylines) {
          const polyAny = poly;
          let polyLayer = polyAny.layer ?? 0;
          if (polyLayer === 0 && typeof polyAny.getState_Layer === "function") {
            polyLayer = polyAny.getState_Layer();
          }
          if (polyLayer !== BOARD_OUTLINE_LAYER) continue;
          const polyX = polyAny.x ?? 0;
          const polyY = polyAny.y ?? 0;
          console.log("[JlcEdaCompanion] Polyline x,y:", polyX, polyY);
          try {
            const allProps = JSON.parse(JSON.stringify(polyAny));
            console.log("[JlcEdaCompanion] Polyline keys:", Object.keys(allProps).join(","));
            console.log("[JlcEdaCompanion] Polyline obj (no polygon):", JSON.stringify(
              Object.fromEntries(Object.entries(allProps).filter(([k]) => k !== "polygon" && k !== "polygonSource"))
            ));
          } catch (e2) {
            console.log("[JlcEdaCompanion] serialize err:", e2);
          }
          console.log("[JlcEdaCompanion] First comp pos:", components.length > 0 ? components[0].x + "," + components[0].y : "none");
          let src = [];
          try {
            const polygon = typeof polyAny.getState_Polygon === "function" ? polyAny.getState_Polygon() : null;
            if (polygon && typeof polygon.getSource === "function") {
              src = polygon.getSource() || [];
            }
          } catch (_) {
          }
          if (src.length === 0) {
            try {
              const s = JSON.parse(JSON.stringify(polyAny));
              const po = s.polygon ?? s.polygonSource;
              src = Array.isArray(po) ? po : po?.source ?? [];
            } catch (_) {
            }
          }
          console.log("[JlcEdaCompanion] Outline source (" + src.length + "):", JSON.stringify(src.slice(0, 20)));
          if (src.length === 0) continue;
          if (src[0] === "R" && src.length >= 7) {
            const rx = src[1], ry = src[2], rw = src[3], rh = src[4];
            outlineLines.push(
              { startX: rx, startY: ry, endX: rx + rw, endY: ry },
              { startX: rx + rw, startY: ry, endX: rx + rw, endY: ry - rh },
              { startX: rx + rw, startY: ry - rh, endX: rx, endY: ry - rh },
              { startX: rx, startY: ry - rh, endX: rx, endY: ry }
            );
            continue;
          }
          if (src[0] === "CIRCLE" && src.length >= 4) {
            const cx = src[1], cy = src[2], r = src[3];
            const n = 24;
            for (let j = 0; j < n; j++) {
              const a1 = 2 * Math.PI * j / n;
              const a2 = 2 * Math.PI * (j + 1) / n;
              outlineLines.push({
                startX: cx + r * Math.cos(a1),
                startY: cy + r * Math.sin(a1),
                endX: cx + r * Math.cos(a2),
                endY: cy + r * Math.sin(a2)
              });
            }
            continue;
          }
          let curX = 0, curY = 0, hasStart = false;
          let si = 0;
          while (si < src.length) {
            const el = src[si];
            if (typeof el === "number") {
              if (!hasStart) {
                curX = el;
                curY = src[si + 1];
                hasStart = true;
                si += 2;
              } else {
                outlineLines.push({ startX: curX, startY: curY, endX: el, endY: src[si + 1] });
                curX = el;
                curY = src[si + 1];
                si += 2;
              }
            } else if (el === "L") {
              si++;
            } else if (el === "ARC" || el === "CARC") {
              si++;
              const aa = src[si], ex = src[si + 1], ey = src[si + 2];
              outlineArcs.push({ startX: curX, startY: curY, arcAngle: aa, endX: ex, endY: ey });
              curX = ex;
              curY = ey;
              si += 3;
            } else if (el === "C") {
              si++;
              let bx = curX, by = curY;
              while (si + 3 < src.length && typeof src[si] === "number") {
                si += 2;
                if (si + 1 < src.length && typeof src[si] === "number") {
                  bx = src[si];
                  by = src[si + 1];
                  si += 2;
                }
              }
              outlineLines.push({ startX: curX, startY: curY, endX: bx, endY: by });
              curX = bx;
              curY = by;
            } else {
              si++;
            }
          }
        }
      }
    } catch (e) {
      console.log("[JlcEdaCompanion] board outline polylines error:", e?.message ?? e);
    }
    console.log("[JlcEdaCompanion] Board outline: " + outlineLines.length + " lines, " + outlineArcs.length + " arcs");
    return {
      board: { layers: layers.map((l) => l.id), outline: [], outlineLines, outlineArcs, stackup: [], boardThickness: 1.6 },
      components,
      nets: netNames.filter((n) => n && !n.startsWith("unconnected-")),
      existing_tracks: existingTracks,
      existing_vias: existingVias,
      routing_config: {
        routing_mode: "single_ended",
        nets_to_route: config.nets_to_route || ["*"],
        track_width: config.track_width || 10,
        clearance: config.clearance || 8,
        board_edge_clearance: config.board_edge_clearance || 0,
        via_size: config.via_size || 24,
        via_drill: config.via_drill || 12,
        layers_to_use: config.layers_to_use || [1, 2],
        grid_step: config.grid_step || 6,
        via_cost: config.via_cost || 30,
        max_ripup: config.max_ripup || 5,
        stub_layer_swap: config.stub_layer_swap !== false,
        power_nets: config.power_nets || "",
        power_widths: config.power_widths || "",
        layer_costs: config.layer_costs || "",
        units_mm: !!config.units_mm,
        kicad_file_path: config.kicad_file_path || ""
      }
    };
  }
  async function parallelBatch(items, fn, concurrency = 50) {
    let ok = 0;
    for (let i = 0; i < items.length; i += concurrency) {
      const batch = items.slice(i, i + concurrency);
      const results = await Promise.allSettled(batch.map(fn));
      ok += results.filter((r) => r.status === "fulfilled").length;
    }
    return ok;
  }
  async function applyResults(result, netsToRoute, unitsMm = false, replaceExisting = false) {
    const netsSet = new Set(netsToRoute);
    let tracksRemoved = 0;
    if (replaceExisting) {
      try {
        const [allLines, allVias] = await Promise.all([
          eda.pcb_PrimitiveLine.getAll(),
          eda.pcb_PrimitiveVia.getAll()
        ]);
        const lineIdsToDelete = (allLines || []).filter((l) => netsSet.has(l.net ?? "")).map((l) => l.primitiveId ?? l.id ?? "").filter((id) => id);
        const viaIdsToDelete = (allVias || []).filter((v) => netsSet.has(v.net ?? "")).map((v) => v.primitiveId ?? v.id ?? "").filter((id) => id);
        tracksRemoved = await parallelBatch(lineIdsToDelete, async (id) => {
          await eda.pcb_PrimitiveLine.delete(id);
        });
        await parallelBatch(viaIdsToDelete, async (id) => {
          await eda.pcb_PrimitiveVia.delete(id);
        });
      } catch (e) {
        console.log("[JlcEdaCompanion] cleanup error:", e?.message ?? e);
      }
    }
    const tracks = result.tracks || [];
    const vias = result.vias || [];
    console.log(`[JlcEdaCompanion] Creating ${tracks.length} tracks, ${vias.length} vias (parallel batch, unitsMm=${unitsMm})`);
    const tracksCreated = await parallelBatch(tracks, async (track) => {
      const sx = unitsMm ? Math.round(mm_to_mil(track.startX)) : Math.round(track.startX);
      const sy = unitsMm ? Math.round(mm_to_mil(track.startY)) : Math.round(track.startY);
      const ex = unitsMm ? Math.round(mm_to_mil(track.endX)) : Math.round(track.endX);
      const ey = unitsMm ? Math.round(mm_to_mil(track.endY)) : Math.round(track.endY);
      const w = unitsMm ? Math.round(mm_to_mil(track.width)) : Math.round(track.width);
      await eda.pcb_PrimitiveLine.create(
        track.net,
        track.layer,
        sx,
        sy,
        ex,
        ey,
        w,
        false
      );
    });
    const viasCreated = await parallelBatch(vias, async (via) => {
      const x = unitsMm ? mm_to_mil(via.x) : via.x;
      const y = unitsMm ? mm_to_mil(via.y) : via.y;
      const hole = unitsMm ? mm_to_mil(via.holeDiameter) : via.holeDiameter;
      const dia = unitsMm ? mm_to_mil(via.diameter) : via.diameter;
      await eda.pcb_PrimitiveVia.create(
        via.net,
        x,
        y,
        hole,
        dia
      );
    });
    return { tracksCreated, viasCreated };
  }
  function sendToIframe(topic, data) {
    const fullTopic = MSG_PREFIX + topic;
    if (typeof eda.sys_MessageBus.publish === "function") {
      eda.sys_MessageBus.publish(fullTopic, JSON.stringify(data));
    } else if (typeof eda.sys_MessageBus.push === "function") {
      eda.sys_MessageBus.push(fullTopic, JSON.stringify(data));
    }
  }
  function onIframeMessage(topic, handler) {
    const fullTopic = MSG_PREFIX + topic;
    eda.sys_MessageBus.subscribe(fullTopic, (msg) => {
      try {
        handler(typeof msg === "string" ? JSON.parse(msg) : msg);
      } catch (e) {
        console.error("MessageBus parse error:", e);
      }
    });
  }
  var currentJobId = _G.__jlcEdaCompanionJobId ?? null;
  var isRoutingInProgress = _G.__jlcEdaCompanionRouting ?? false;
  var _generation = (_G.__jlcEdaCompanionGeneration ?? 0) + 1;
  _G.__jlcEdaCompanionGeneration = _generation;
  _G.__jlcEdaCompanionLoaded = true;
  onIframeMessage("start-routing", async (config) => {
    if (_G.__jlcEdaCompanionGeneration !== _generation) return;
    dbg("start-routing received");
    if (isRoutingInProgress) {
      sendToIframe("routing-complete", { error: t("Another routing task is already running, please wait or cancel first.") });
      return;
    }
    isRoutingInProgress = true;
    _G.__jlcEdaCompanionRouting = true;
    try {
      const client = new BridgeClient();
      const serverOk = await client.checkServer();
      if (!serverOk) {
        sendToIframe("routing-complete", { error: t("Bridge server not running. Please start: cd bridge_server && python server.py") });
        return;
      }
      try {
        const drcApi = eda.pcb_Drc ?? eda.PCB_Drc;
        if (drcApi && typeof drcApi.getCurrentRuleConfiguration === "function") {
          const drcData = await drcApi.getCurrentRuleConfiguration();
          const cfg = drcData?.config;
          if (cfg) {
            console.log("[JlcEdaCompanion] DRC rule name:", cfg.name);
            const errors = [];
            const drcToMm = (value, unit) => {
              if (!unit || unit === "mm") return value;
              if (unit === "mil") return value * 0.0254;
              if (unit === "inch" || unit === "in") return value * 25.4;
              return value;
            };
            const DRC_EPSILON = 1e-3;
            const lessThan = (a, b) => a < b - DRC_EPSILON;
            const trackSection = cfg.Physics?.Track?.copperThickness1oz;
            const trackUnit = trackSection?.unit;
            const trackData = trackSection?.form?.data?.["1"];
            const minTrackWidth = drcToMm(trackData?.minValue ?? 0, trackUnit);
            if (minTrackWidth > 0 && lessThan(mil_to_mm(config.track_width || 0), minTrackWidth)) {
              errors.push(`Track Width (${mil_to_mm(config.track_width || 0).toFixed(3)}mm) < DRC minimum (${minTrackWidth.toFixed(3)}mm)`);
            }
            const viaSection = cfg.Physics?.["Via Size"]?.viaSize;
            const viaUnit = viaSection?.unit;
            const viaData = viaSection?.form;
            const minViaOuter = drcToMm(viaData?.viaOuterdiameterMin ?? 0, viaUnit);
            const minViaDrill = drcToMm(viaData?.viaInnerdiameterMin ?? 0, viaUnit);
            if (minViaOuter > 0 && lessThan(mil_to_mm(config.via_size || 0), minViaOuter)) {
              errors.push(`Via Size (${mil_to_mm(config.via_size || 0).toFixed(3)}mm) < DRC minimum (${minViaOuter.toFixed(3)}mm)`);
            }
            if (minViaDrill > 0 && lessThan(mil_to_mm(config.via_drill || 0), minViaDrill)) {
              errors.push(`Via Drill (${mil_to_mm(config.via_drill || 0).toFixed(3)}mm) < DRC minimum (${minViaDrill.toFixed(3)}mm)`);
            }
            const spacingSection = cfg.Spacing?.["Safe Spacing"]?.copperThickness1oz;
            const spacingUnit = spacingSection?.unit;
            const spacingTable = spacingSection?.tables?.["1"]?.content;
            if (Array.isArray(spacingTable) && spacingTable.length > 11) {
              const boardOutlineRow = spacingTable[11];
              const minEdgeClearance = drcToMm(Array.isArray(boardOutlineRow) ? boardOutlineRow[0] : 0, spacingUnit);
              const effectiveMinEdge = minEdgeClearance + mil_to_mm(config.track_width || 0) / 2;
              const userEdgeClearance = mil_to_mm(config.board_edge_clearance || 0);
              if (userEdgeClearance > 0 && lessThan(userEdgeClearance, effectiveMinEdge)) {
                errors.push(`Board Edge Clearance (${userEdgeClearance.toFixed(3)}mm) < effective minimum (${effectiveMinEdge.toFixed(3)}mm = ${minEdgeClearance.toFixed(3)}mm DRC + ${(mil_to_mm(config.track_width || 0) / 2).toFixed(3)}mm half track width)`);
              }
            }
            if (Array.isArray(spacingTable) && spacingTable.length > 0) {
              const minClearance = drcToMm(spacingTable[0]?.[0] ?? 0, spacingUnit);
              if (minClearance > 0 && lessThan(mil_to_mm(config.clearance || 0), minClearance)) {
                errors.push(`Clearance (${mil_to_mm(config.clearance || 0).toFixed(3)}mm) < DRC minimum (${minClearance.toFixed(3)}mm)`);
              }
            }
            if (errors.length > 0) {
              const errorMsg = "DRC validation failed:\n" + errors.join("\n");
              console.log("[JlcEdaCompanion] DRC BLOCKED:", errorMsg);
              eda.sys_Dialog.showInformationMessage(errorMsg, "DRC Validation");
              sendToIframe("routing-complete", { error: errorMsg });
              throw new Error("__DRC_BLOCKED__");
            }
          } else {
            console.log("[JlcEdaCompanion] DRC config is empty, skipping validation");
          }
        } else {
          console.log("[JlcEdaCompanion] pcb_Drc API not available, skipping DRC validation");
        }
      } catch (e) {
        if (e?.message === "__DRC_BLOCKED__") throw e;
        console.log("[JlcEdaCompanion] DRC validation skipped:", e?.message ?? e);
      }
      const t_start = Date.now();
      sendToIframe("routing-progress", { percent: 10, message: t("Collecting PCB data...") });
      try {
        const padApi = eda.pcb_PrimitivePad;
        const padApi2 = eda.pcb_Pad;
        console.log("[JlcEdaCompanion] pcb_PrimitivePad exists:", !!padApi);
        console.log("[JlcEdaCompanion] pcb_Pad exists:", !!padApi2);
        if (padApi && typeof padApi.getAll === "function") {
          const allPads = await padApi.getAll();
          console.log("[JlcEdaCompanion] PrimitivePad.getAll count:", allPads ? allPads.length : 0);
          if (allPads && allPads.length > 0) {
            console.log("[JlcEdaCompanion] STANDALONE PAD:", JSON.stringify(allPads[0]));
          }
        }
        if (padApi2 && typeof padApi2.getAll === "function") {
          const allPads2 = await padApi2.getAll();
          console.log("[JlcEdaCompanion] Pad.getAll count:", allPads2 ? allPads2.length : 0);
          if (allPads2 && allPads2.length > 0) {
            console.log("[JlcEdaCompanion] PAD2:", JSON.stringify(allPads2[0]));
          }
        }
      } catch (e) {
        console.log("[JlcEdaCompanion] pad API error:", e);
      }
      let pcbData;
      try {
        pcbData = await collectFullPCBData(config);
        console.log(`[TIMING] collect: ${Date.now() - t_start}ms`);
      } catch (e) {
        sendToIframe("routing-complete", { error: t("Data collection failed: ${1}", e?.message ?? e) });
        return;
      }
      if (pcbData.nets.length === 0) {
        sendToIframe("routing-complete", { error: t("No unrouted nets found") });
        return;
      }
      sendToIframe("routing-progress", { percent: 15, message: t("Submitting to routing engine...") });
      const regularComps = pcbData.components.filter((c) => !c.designator.startsWith("_PAD"));
      const standalonePadComps = pcbData.components.filter((c) => c.designator.startsWith("_PAD"));
      let jobId;
      try {
        if (standalonePadComps.length > 0) {
          await client.submitExtraComponents(standalonePadComps);
          console.log(`[JlcEdaCompanion] Sent ${standalonePadComps.length} standalone pads as obstacles`);
        }
        pcbData.components = regularComps;
        jobId = await client.submitRoutingJob(pcbData);
        console.log(`[TIMING] submit: ${Date.now() - t_start}ms`);
        currentJobId = jobId;
        _G.__jlcEdaCompanionJobId = jobId;
      } catch (e) {
        sendToIframe("routing-complete", { error: t("Submit failed: ${1}", e?.message ?? e) });
        return;
      }
      sendToIframe("routing-progress", { percent: 20, message: t("Routing in progress...") });
      const startTime = Date.now();
      let finalStatus = "";
      while (Date.now() - startTime < BRIDGE_CONFIG.timeout) {
        const status = await client.pollStatus(jobId);
        if (status === "completed" || status === "failed" || status === "cancelled") {
          finalStatus = status;
          break;
        }
        const progressMap = { pending: 25, converting: 30, routing: 60, converting_back: 85 };
        const pct = progressMap[status] ?? 50;
        sendToIframe("routing-progress", { percent: pct, message: t("Status: ${1}", status) });
        await new Promise((resolve) => {
          eda.sys_Timer.setTimeoutTimer("poll-timer", BRIDGE_CONFIG.pollInterval, () => resolve());
        });
      }
      if (!finalStatus) {
        finalStatus = await client.pollStatus(jobId);
        console.log(`[JlcEdaCompanion] Poll timeout, final status: ${finalStatus}`);
      }
      if (finalStatus !== "completed") {
        try {
          await client.cancelJob(jobId);
        } catch (_) {
        }
        let errorDetail = "";
        try {
          const res = await client.getResult(jobId);
          errorDetail = res?.error || res?.log || "";
        } catch (_) {
        }
        const elapsed = Math.round((Date.now() - startTime) / 1e3);
        const msg = errorDetail ? t("Routing failed") + ": " + errorDetail : t("Routing not completed (status: ${1}, waited ${2}s), PCB may be too complex.", finalStatus, elapsed.toString());
        console.log(`[JlcEdaCompanion] Routing failed: status=${finalStatus}, error=${errorDetail}`);
        sendToIframe("routing-complete", { error: msg });
        currentJobId = null;
        _G.__jlcEdaCompanionJobId = null;
        return;
      }
      let result;
      try {
        console.log(`[TIMING] route+poll: ${Date.now() - t_start}ms`);
        result = await client.getResult(jobId);
        console.log(`[JlcEdaCompanion] Result received: status=${result.status}, tracks=${(result.tracks || []).length}, vias=${(result.vias || []).length}`);
      } catch (e) {
        sendToIframe("routing-complete", { error: t("Get result failed: ${1}", e?.message ?? e) });
        currentJobId = null;
        _G.__jlcEdaCompanionJobId = null;
        return;
      }
      if (result.status === "failed" || result.status === "cancelled") {
        sendToIframe("routing-complete", { error: result.error || t("Routing failed") });
        currentJobId = null;
        _G.__jlcEdaCompanionJobId = null;
        return;
      }
      sendToIframe("routing-progress", { percent: 90, message: t("Applying routing results...") });
      let tracksCreated = 0;
      let viasCreated = 0;
      try {
        const netsToRoute = config.nets_to_route || [];
        const t_apply0 = Date.now();
        const applied = await applyResults(result, netsToRoute, !!config.units_mm, config.replace_existing === true);
        console.log(`[TIMING] applyResults: ${Date.now() - t_apply0}ms`);
        tracksCreated = applied.tracksCreated;
        viasCreated = applied.viasCreated;
      } catch (e) {
        sendToIframe("routing-complete", { error: t("Write failed: ${1}", e?.message ?? e) });
        currentJobId = null;
        _G.__jlcEdaCompanionJobId = null;
        return;
      }
      console.log("[TIMING] total: " + (Date.now() - t_start) + "ms");
      currentJobId = null;
      _G.__jlcEdaCompanionJobId = null;
      sendToIframe("routing-complete", {
        stats: {
          nets_routed: result.stats?.nets_routed ?? 0,
          tracks_added: tracksCreated,
          vias_added: viasCreated,
          time_seconds: result.stats?.time_seconds ?? 0
        }
      });
    } finally {
      isRoutingInProgress = false;
      _G.__jlcEdaCompanionRouting = false;
    }
  });
  onIframeMessage("cancel-routing", async () => {
    if (_G.__jlcEdaCompanionGeneration !== _generation) return;
    if (currentJobId) {
      const client = new BridgeClient();
      try {
        await client.cancelJob(currentJobId);
      } catch {
      }
      currentJobId = null;
      _G.__jlcEdaCompanionJobId = null;
    }
    isRoutingInProgress = false;
    _G.__jlcEdaCompanionRouting = false;
    sendToIframe("routing-complete", { error: t("Operation cancelled") });
  });
  onIframeMessage("get-nets", async () => {
    if (_G.__jlcEdaCompanionGeneration !== _generation) return;
    try {
      const netNames = await eda.pcb_Net.getAllNetsName();
      const nets = [];
      for (const name of netNames) {
        if (!name || name.startsWith("unconnected-")) continue;
        const length = await eda.pcb_Net.getNetLength(name);
        nets.push({ name, isConnected: length !== void 0 && length > 0 });
      }
      sendToIframe("nets-list", { nets });
    } catch (e) {
      sendToIframe("nets-list", { nets: [], error: e?.message ?? String(e) });
    }
  });
  onIframeMessage("get-components", async () => {
    if (_G.__jlcEdaCompanionGeneration !== _generation) return;
    try {
      const result = [];
      const allComps = await eda.pcb_PrimitiveComponent.getAll();
      for (const comp of allComps) {
        const compAny = comp;
        const des = compAny.designator ?? compAny.name ?? "";
        const primId = compAny.primitiveId ?? compAny.id ?? "";
        let padCount = 0;
        if (primId) {
          const pins = await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(primId);
          if (pins) padCount = pins.length;
        }
        if (des) result.push({ designator: des, padCount });
      }
      sendToIframe("components-list", { components: result });
    } catch (e) {
      sendToIframe("components-list", { components: [], error: e?.message ?? String(e) });
    }
  });
  onIframeMessage("get-layers", async () => {
    if (_G.__jlcEdaCompanionGeneration !== _generation) return;
    try {
      const layers = await collectLayers();
      sendToIframe("layers-list", { layers });
    } catch (e) {
      sendToIframe("layers-list", { layers: [], error: e?.message ?? String(e) });
    }
  });
  onIframeMessage("get-drc-limits", async () => {
    if (_G.__jlcEdaCompanionGeneration !== _generation) return;
    try {
      const drcApi = eda.pcb_Drc ?? eda.PCB_Drc;
      if (!drcApi || typeof drcApi.getCurrentRuleConfiguration !== "function") {
        sendToIframe("drc-limits", {});
        return;
      }
      const drcData = await drcApi.getCurrentRuleConfiguration();
      const cfg = drcData?.config;
      if (!cfg) {
        sendToIframe("drc-limits", {});
        return;
      }
      const drcToMm = (value, unit) => {
        if (!unit || unit === "mm") return value;
        if (unit === "mil") return value * 0.0254;
        if (unit === "inch" || unit === "in") return value * 25.4;
        return value;
      };
      const trackSection = cfg.Physics?.Track?.copperThickness1oz;
      const trackUnit = trackSection?.unit;
      const trackData = trackSection?.form?.data?.["1"];
      const minTrackWidth = drcToMm(trackData?.minValue ?? 0, trackUnit);
      const viaSection = cfg.Physics?.["Via Size"]?.viaSize;
      const viaUnit = viaSection?.unit;
      const viaData = viaSection?.form;
      const minViaOuter = drcToMm(viaData?.viaOuterdiameterMin ?? 0, viaUnit);
      const minViaDrill = drcToMm(viaData?.viaInnerdiameterMin ?? 0, viaUnit);
      const spacingSection = cfg.Spacing?.["Safe Spacing"]?.copperThickness1oz;
      const spacingUnit = spacingSection?.unit;
      const spacingTable = spacingSection?.tables?.["1"]?.content;
      let minClearance = 0;
      if (Array.isArray(spacingTable) && spacingTable.length > 0) {
        minClearance = drcToMm(spacingTable[0]?.[0] ?? 0, spacingUnit);
      }
      let minEdgeClearance = 0;
      if (Array.isArray(spacingTable) && spacingTable.length > 11) {
        const boardOutlineRow = spacingTable[11];
        minEdgeClearance = drcToMm(Array.isArray(boardOutlineRow) ? boardOutlineRow[0] : 0, spacingUnit);
      }
      sendToIframe("drc-limits", {
        minTrackWidth,
        minViaOuter,
        minViaDrill,
        minClearance,
        minEdgeClearance
      });
    } catch (e) {
      console.log("[JlcEdaCompanion] get-drc-limits error:", e?.message ?? e);
      sendToIframe("drc-limits", {});
    }
  });
  var IFRAME_ID = "jlc-eda-routing-dialog";
  var SERVICE_DIALOG_ID = "jlc-eda-service-not-found";
  var PREFLIGHT_DIALOG_ID = "jlc-eda-design-preflight";
  var latestPreflight = null;
  function showServiceNotFoundDialog() {
    try {
      eda.sys_IFrame.openIFrame("/iframe/service-not-found.html", 520, 420, SERVICE_DIALOG_ID, {
        maximizeButton: false,
        minimizeButton: false,
        grayscaleMask: true
      });
    } catch (e) {
      eda.sys_Dialog.showInformationMessage(
        t("Bridge server is not running"),
        t("JLCEDA Design Companion")
      );
    }
  }
  async function openRoutingDialog() {
    try {
      await eda.sys_IFrame.openIFrame("/iframe/index.html", 860, 600, IFRAME_ID, {
        maximizeButton: true,
        minimizeButton: true,
        grayscaleMask: true
      });
    } catch (e) {
      eda.sys_Dialog.showInformationMessage(
        `Failed to open dialog: ${e?.message ?? e}`,
        t("JLCEDA Design Companion")
      );
    }
  }
  async function collectPreflight() {
    const client = new BridgeClient();
    const serverOk = await client.checkServer();
    if (!serverOk) {
      showServiceNotFoundDialog();
      return null;
    }
    const pcbData = await collectFullPCBData({ units_mm: false });
    latestPreflight = await client.postJson("/api/review/preflight", pcbData);
    return latestPreflight;
  }
  async function openPreflightDialog() {
    try {
      await eda.sys_IFrame.openIFrame("/iframe/dashboard.html", 720, 560, PREFLIGHT_DIALOG_ID, {
        maximizeButton: true,
        minimizeButton: true,
        grayscaleMask: true
      });
    } catch (e) {
      eda.sys_Dialog.showInformationMessage(
        `Failed to open preflight dialog: ${e?.message ?? e}`,
        "JLCEDA Design Companion"
      );
    }
  }
  async function autoRouteAll() {
    const client = new BridgeClient();
    const serverOk = await client.checkServer();
    if (!serverOk) {
      showServiceNotFoundDialog();
      return;
    }
    await openRoutingDialog();
  }
  async function runBoardPreflight() {
    try {
      await collectPreflight();
      if (latestPreflight) await openPreflightDialog();
    } catch (e) {
      eda.sys_Dialog.showInformationMessage(
        `Preflight failed: ${e?.message ?? e}`,
        "JLCEDA Design Companion"
      );
    }
  }
  onIframeMessage("dashboard-ready", () => {
    if (latestPreflight) sendToIframe("dashboard-data", latestPreflight);
  });
  onIframeMessage("dashboard-refresh", async () => {
    try {
      await collectPreflight();
      if (latestPreflight) sendToIframe("dashboard-data", latestPreflight);
    } catch (e) {
      sendToIframe("dashboard-error", { error: e?.message ?? String(e) });
    }
  });
  onIframeMessage("retry-connection", async () => {
    if (_G.__jlcEdaCompanionGeneration !== _generation) return;
    const client = new BridgeClient();
    const serverOk = await client.checkServer();
    if (serverOk) {
      sendToIframe("retry-result", { success: true });
      try {
        eda.sys_IFrame.closeIFrame(SERVICE_DIALOG_ID);
      } catch {
      }
      await openRoutingDialog();
    } else {
      sendToIframe("retry-result", { success: false });
    }
  });
  function about() {
    eda.sys_Dialog.showInformationMessage(
      `JLCEDA Design Companion v0.1.0

Open-source EasyEDA Pro companion built on KiRouting Integration.
Includes safe routing workflows and board preflight review.

Bridge server: http://${BRIDGE_CONFIG.host}:${BRIDGE_CONFIG.port}`,
      t("About")
    );
  }
  return __toCommonJS(src_exports);
})();
