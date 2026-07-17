# 工具箱参考 — 参数 + 输出 schema

所有工具在 `scripts/tools/`,用工作区 `.venv` 的 python 跑,**JSON 打到 stdout**。
失败一律 `{"ok": false, "error": "..."}`。

```bash
PY=".venv/bin/python"
T=".claude/skills/draw-pcb/scripts/tools"
```

## init_pcb — sch → 空 .kicad_pcb

底层 `scripts/sch_to_pcb.py`(非 tools/ 下)。

```bash
"$PY" .claude/skills/draw-pcb/scripts/sch_to_pcb.py <dir-containing-.kicad_sch>
```
输出:`pcb_path` / `footprints_added` / `nets_added`。已存在则 draw-pcb 回路里跳过。

## placement_brief — 电路事实

```bash
"$PY" $T/placement_brief.py <pcb>
```
输出字段:
- `domains` — `{HV:[refs], ISO:[...], LV:[...]}`
- `footprint_domain` — `{ref: domain}`
- `barrier_x` — 隔离屏障 x(隔离器件中心均值)。**仅元件摆好后有效**,空板为 null;Phase A/B 的 `--barrier-x` 取 `init_layout` 输出的 `slots[].x_mm`
- `barrier_devices[]` — `{ref, value, bridges_grounds[], pads:[{number,net}], note}`(跨 ≥2 地网的隔离器件;旋转推理就靠 `pads`)
- `edge_devices[]` — J* 连接器 + SW* 开关,必须贴板边
- `cap_ic_links[]` — `{cap, ic, via_net, gnd}`(cap 该贴哪个 IC,机械事实)
- `chains[]` — `{members:[有序], domain, kind}`(串联链,members 已按串联顺序)
- `net_pads` — `{net: [ref.pad]}`
- `power_nets` / `ground_nets`

## init_layout — 确定性区域种子

底层 `scripts/place_components.py`。

```bash
"$PY" .claude/skills/draw-pcb/scripts/place_components.py <pcb> --claude-md <project>/CLAUDE.md
```
读项目 CLAUDE.md 的 `placement` 段,出区域分区 + 板框 + 隔离槽。当回路起点,不是终点。

## get_geometry — 每件几何

```bash
"$PY" $T/get_geometry.py <pcb> [--refs R1,U1] [--no-pads]
```
输出 `footprints[]`,每件:`ref / value / x,y / center[cx,cy] / angle / layer / type /
courtyard{min_x,min_y,max_x,max_y,w,h} / pads[{number,x,y,w,h,net}] / nets[]`。
`board` = Edge.Cuts bbox(没有则 null)。**`center` 就是 `move` 的目标点。**

## move — 移动 / 旋转

```bash
"$PY" $T/move.py <pcb> --move "R1:42,18,90" --move "C8:50,20" ...
"$PY" $T/move.py <pcb> --moves-json moves.json     # {"R1":[42,18,90],...}
```
target (x,y) = body-bbox 中心。rot 可省(保持原旋转)。输出 `moved[] / not_found[]`。
只动 footprint 位置,不碰 Edge.Cuts / 走线 / zone——可在回路里反复调。

## check_placement — 合法性闸门

```bash
"$PY" $T/check_placement.py <pcb> [--min-clearance 0.2] [--barrier-x 31.8] \
      [--barrier-exempt R1,U2] [--decoupling-pairs C6:U1,C10:U1,C5:U3]
```
`--decoupling-pairs` 传项目 CLAUDE.md 声明的 cap:IC 对(权威配对);`cap_far_from_ic`
按它 + 真实 pad-to-pad 距离判,不传则退回 net 推断(可能配错 IC)。
输出:
- `hard_fail` — **闸门信号**,true = 有硬违例
- `score` — 0-100,合法性进度(非质量,别当目标函数)
- `metrics` — `{hpwl_mm, courtyard_overlaps, out_of_board, pad_clearance_violations, barrier_crossings}`
- `violations[]` — `{type, severity, refs, detail}`(硬违例)
- `warnings[]` — `{type, refs, detail}`:`connector_not_on_edge`(连接器没贴板边)、`geometry_uncertain`(courtyard 退化,extent 不可靠)。**非 hard_fail,但必须逐条处理。**

`--barrier-x` 给了会自动调 `placement_brief` 豁免真隔离器件;`--barrier-exempt` 手动补。

## render — 标注 PNG

```bash
"$PY" $T/render.py <pcb> -o out.png [--ratsnest] [--barrier-x 31.8] [--label-pads]
```
蓝=F.Cu 正面,绿=B.Cu 背面,红框=courtyard 重叠,橙虚线=隔离屏障,灰线=飞线(--ratsnest)。
输出 `png / overlap_count / overlaps[]`。**回路里必须 Read 这张图做视觉判断。**

## refit_board — 板框贴合布局(Phase D,最先跑)

```bash
"$PY" $T/refit_board.py <pcb> [--margin 2.5]
```
把 Edge.Cuts 外框 + 隔离槽缩到所有 footprint 的实际范围 + margin。板框是
`init_layout` 按 CLAUDE.md `pack_density` 一次性定死的,回路收紧元件后板框不会自己跟着缩——
refit 补这一步。隔离槽按检测到的 x 重画为连续槽(留 3mm 上下桥),之后再跑 `bridge_slot`。
**必须在 `bridge_slot` / `add_zones` 之前**(两者都读 Edge.Cuts)。
输出 `board{x,y,w,h} / slot_x_mm / fill_ratio`。`fill_ratio` = courtyard 总面积 / 板面积,
紧凑度指标(见 SKILL.md route-ready 验收)。

## bridge_slot — 隔离槽留桥(Phase D)

```bash
"$PY" $T/bridge_slot.py <pcb> [--margin 1.0]
```
重画隔离槽,在每个跨槽 barrier 器件(自动从 `placement_brief` 取)下方留实体桥。
**元件摆定 + refit_board 后才跑**。输出 `slot_x_mm / bridges[] / slot_segments_drawn`。

## add_zones — GND 铺铜(Phase D + Phase E 重铺)

底层 `_kicad_python_helper.py` 的 `add_ground_zones` mode。create+fill 幂等一步,
幂等粒度 `(net, layer)`。**铺哪面 / 哪个网 / 铺不铺由 AI 按 `copper_pour.md` 判断**,
工具只执行。

```bash
"$PY" $T/add_zones.py <pcb> [--layers B.Cu,F.Cu] [--nets LV_GND HV_GND] [--clearance 0.3]
```

- `--layers`:逗号分隔铜层,默认 `B.Cu`。
- `--nets`:限定只铺名字含这些子串的 GND 网;不给则铺全部 GND-like 网。
  多 GND 网按域分开调用 —— 如 `--layers F.Cu --nets LV_GND` 只在正面铺低压地。
- Phase E 布线后在 `_routed` 板上**重跑一次**,铜绕开新走线 / 过孔。

## check_zones — 隔离屏障铜跨槽校验(Phase D,add_zones 之后)

底层 `_kicad_python_helper.py` 的 `validate_zones` mode。只读,不存板。

```bash
"$PY" $T/check_zones.py <pcb> [--tol 0.05]
```
断言**没有任何铜 zone 跨隔离屏障**:取每个已填充 zone 的填充铜 X 跨度,
若同一 zone 既有铜在槽左又有铜在槽右 → 跨屏障 → 退出码 1 + `crossings[]`。
net/电压/网名无关,**任意单竖直隔离槽通用**。无槽 → 跳过(`slot_detected=False`,
不误报)。横向/多段屏障未覆盖。**铺完铜跑(DRC clearance 之外的专门防线)**。

## run_drc — kicad-cli DRC(Phase D)

```bash
"$PY" $T/run_drc.py <pcb>
```
输出 `violation_count / unconnected_count / by_type`。

## route — 自动布线(Phase E,可选)

```bash
"$PY" $T/route.py <placed-pcb> [--output X] [--in-place] \
      [--board-edge-clearance 0.6] [--nets PAT ...] \
      [--track-width MM] [--power-nets NET ... --power-nets-widths MM ...] \
      [--ordering {inside_out,mps,original}] [--via-size MM] [--via-drill MM] \
      [--clearance MM] [--layers LAYER ...] [--impedance OHM]
```
底层 vendored KiCadRoutingTools(KRT)。默认产出 `<stem>_routed.kicad_pcb`(不覆盖
placement 原件)。输出 `routed_single / multipoint_pads / failed / vias / recipe / output_pcb`。
**配方 flag(线宽 / 电源网 / 差分对 / ordering)是电路判断,先按 `routing_strategy.md`
给 net 分类再定**,未设的吃 KRT 默认。**布完必跑 `run_drc`**,再 `add_zones` 重铺铜。
需先 `build_router.py` 编译 KRT 的 Rust 模块。详见 `routing.md` + `routing_strategy.md`。
