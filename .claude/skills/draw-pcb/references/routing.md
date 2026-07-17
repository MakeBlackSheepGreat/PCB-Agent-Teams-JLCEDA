# Phase E — 自动布线(KiCadRoutingTools / KRT)

draw-pcb 的可选收尾阶段:把通过 route-ready 验收的布局板自动布线成全连通 + DRC 干净的成品板。

## KRT 是什么

[KiCadRoutingTools](https://github.com/drandyhaas/KiCadRoutingTools) —— Rust 加速的 A\*
自动布线器,支持 KiCad 9/10。vendored 在 `scripts/vendor/KiCadRoutingTools/`(只保留 CLI
引擎 + Rust 源,去掉了 GUI 插件 / docs / 示例板)。

> 注:zone-constrained 的纯模拟板,Freerouting 通常优于 KRT;KRT 的强项是差分对 / DDR /
> BGA fanout / 多点网。选型由项目决定,本 skill 默认集成 KRT(CLI + 可脚本化)。

## 一次性构建

KRT 的 Rust 核心(`grid_router.so`,pyo3 + abi3-py39)需编译一次:

```bash
PATH="$HOME/.cargo/bin:$PATH" <venv-python> scripts/vendor/KiCadRoutingTools/build_router.py
```

需要 Rust 工具链(`cargo`)。`.so` 编译后随 skill 走,无需重复构建;换平台才需重编。
Python 依赖 `numpy / scipy / shapely` 由工作区 `.venv` 提供。

## 用法

```bash
<venv-python> scripts/tools/route.py <placed.kicad_pcb> \
    [--output X] [--in-place] [--board-edge-clearance 0.6] [--nets PAT ...] \
    [--track-width MM] [--power-nets NET ... --power-nets-widths MM ...] \
    [--ordering {inside_out,mps,original}] [--via-size MM] [--via-drill MM] \
    [--clearance MM] [--layers LAYER ...] [--impedance OHM]
```

- 默认产出 `<stem>_routed.kicad_pcb`,**不覆盖 placement 原件**(布局/布线是两份交付物)。
- `--board-edge-clearance` 默认 0.6mm:`create_pcb` 写的板边设计规则是 0.5mm,留 0.1 余量。
  KRT 默认值不一定匹配该规则 → 不设会出 `copper_edge_clearance` 违例。
- `--nets` 限定要布的网(net 名 pattern);不给则布全部。
- **配方 flag**(`--track-width` / `--power-nets` / `--ordering` / `--impedance` 等):
  KRT 有 ~50 个参数,该工具暴露其中**判断型**的一组转发,未设的吃 KRT 默认。
  哪些网走粗线 / 线宽多少 / 差分对怎么处理 = 电路判断,**先看 `routing_strategy.md`
  分类再定**,不要裸跑吃默认。`--power-nets` 与 `--power-nets-widths` 按位置 1:1 配对。
- 输出 JSON:`routed_single / multipoint_pads / failed / vias / recipe`(`recipe` 回显
  本次用了哪些非默认参数,供打印)。

## 铁律

1. **先过 route-ready 验收再布线**。布局没做好就布线 = 烂地基盖楼;布完再回改布局很麻烦。
2. **布完必跑 `run_drc`**。KRT 自报 `failed=0` 只代表它认为布通了,几何裁判是 DRC——
   `0 violations + 0 unconnected` 才算真的布通。
3. **`copper_edge_clearance` 违例** → 调大 `--board-edge-clearance` 重布(从干净的
   placement 板重新 `route`,不要在已布线的板上叠布)。
4. 重布从 placement 原件起步——`route` 每次拷一份新副本,别在 `_routed` 上反复布。
5. **布完线必重铺 GND 铜**。Phase D 的铜绕的是空板,布线加了走线/过孔后已 stale。
   在 `_routed` 板上重跑 `add_zones`(create+fill 幂等),铜重新绕开走线/过孔,
   过孔做 thermal relief;重铺后再 `run_drc` 复查 clearance。铺哪面/哪个网的判断
   见 `references/copper_pour.md`。

## 已知点

| 现象 | 处理 |
|---|---|
| `grid_router.so missing` | 先跑 `build_router.py`(见上) |
| `copper_edge_clearance` 违例 | `--board-edge-clearance` 调到 0.6+,重布 |
| GND 网被布成细线而非依赖铺铜 | GND 已 `add_zones` 铺铜;KRT 仍会布 GND 走线,冗余但无害;要省可 `--nets` 排除 GND |
| 隔离槽 = Edge.Cuts 内部 cutout | KRT 尊重内部 cutout + 板边,走线不会穿隔离槽 |
