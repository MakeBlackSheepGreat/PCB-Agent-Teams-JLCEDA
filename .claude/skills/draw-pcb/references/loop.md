# 布局回路详细 — A→D + 判断标准

SKILL.md 的回路速览的展开。读这份再跑回路。

## 总图

```
A 理解电路 ──→ B 按电路布局 ──→ C 验证迭代 ──┐
                    ↑                          │
                    └──────── 修问题 ←─────────┘
                                              │ route-ready 验收逐条全过
                                              ▼
                                          D 收尾
```

布局的对象是 `Projects/<name>/kicad/<name>/<name>.kicad_pcb`。所有工具在 `scripts/tools/`,
用工作区 `.venv` 的 python 跑。

## Phase A — 理解电路

1. `init_pcb <project>/kicad/<name>` — sch → 空 `.kicad_pcb`(38 件全在原点)。已存在则跳过。
2. `placement_brief <pcb>` — 拿电路事实 JSON。
3. Read 项目 `CLAUDE.md` 的 `placement` 段(人工声明的意图:板宽 / 隔离槽 / anchors / decoupling_pairs / chains)。字段表 → `claude_md_constraints.md`。
4. **合并成布局意图**,并**打印**出来:
   - 域划分:每件属 HV / ISO / LV
   - barrier 器件:哪些件横跨隔离屏障 + 各自 pad→net(屏障 x 在 Phase B `init_layout` 画槽后才定)
   - 去耦对 / cap-IC 链接:哪个 cap 该贴哪个 IC
   - chains:按序的串联链(分压链等)
   - `geometry_uncertain` 件(若有):courtyard 退化的件,extent 不可靠,后面 DRC 重点看

`placement_brief` 给的是**机械事实**。哪条回路 EMC 敏感、间距具体多少 mm,是你在事实上做的**判断**——
项目 CLAUDE.md 的声明优先于 brief 的推断。

## Phase B — 按电路布局

1. `init_layout <pcb> --claude-md <project>/CLAUDE.md` — 出确定性区域种子(别从原点零开始)。
2. `get_geometry <pcb>` — 读当前每件 center / courtyard / pad。
3. **按电路判断摆**,不是铺格子。优先级:

   **① 隔离屏障 + barrier 器件定向(最高)**
   - 屏障是竖线,x = `init_layout` 输出 JSON 的 `slots[].x_mm`(画槽时算的,对应项目
     CLAUDE.md 的 `isolation_slots` 中心)。后续 `check_placement` / `render` 的 `--barrier-x`
     都用这个值。(`placement_brief` 的 `barrier_x` 是摆好后的复核值,空板上为 null。)
   - barrier 器件(如隔离放大器、隔离 DC-DC)必须**横跨**屏障。旋转推理见下节。
   - 非 barrier 件**不许**穿屏障——HV 件全在屏障左,LV 件全在右。

   **② 连接器 / 开关贴板边**
   - `placement_brief` 的 `edge_devices`(J* 连接器 + SW* 开关)必须摆到板**周边**——
     courtyard 离 Edge.Cuts ≤3mm。线缆 / 螺丝端子从板边引线,开关要能拨。
   - 连接器摆板内 = 线缆横跨整块板。项目 CLAUDE.md 常指定哪个连接器靠哪条边
     (HV 端子左、daisy-chain 上等),按它来;没指定就按域就近的板边。
   - 指示 LED 尽量也靠边,便于观察。

   **③ 回路收紧 / 去耦贴 IC**
   - 去耦 / 旁路电容:**最近 pad 到 IC pad ≤2mm**。配对按项目 CLAUDE.md 的
     `decoupling_pairs` 声明,**不是**按 net 猜(net 推断会配错 IC)。
   - 但 pad-to-pad **别 < 0.5mm**——那是阻焊 web 下限,太近 KiCad DRC 会报
     `solder_mask_bridge` / `shorting_items`。贴紧 ≈ 0.5–1.5mm,不是越近越好。
   - 电流回路(iso DC-DC 输入回路、整流回路等)的成员聚成一簇,回路面积小 = EMI 小。
   - 高 di/dt 的别拉长。

   **④ chain 按序**
   - chain 成员沿一条直线、按 `members` 顺序排,相邻 courtyard 间距 ~1–2mm。

   **⑤ 区域内其余件**:同域的尽量靠近其连接的件(看 `net_pads`),别乱撒。

4. `move <pcb> --moves-json <file>` 落子。一次可移多件。
5. **打印**:这一轮移了哪些件,每个一句话为什么(如"C6 贴 U1 东侧——iso 供电去耦")。

### barrier 器件旋转推理(信条 3 的展开)

`placement_brief` 的 `barrier_devices[]` 给每个 pad 的 net。步骤:

1. 把 pad 按 net 的域分两组:接 HV 侧网(HV_GND / 高压 sense)的 = HV 组;接 LV 侧网(LV_GND / 低压供电 / 输出)的 = LV 组。
2. 屏障是竖线。目标:HV 组 pad 落在屏障**左**(x 小),LV 组 pad 落在屏障**右**。
3. **`get_geometry` 读该件每个 pad 的真实 x/y——别凭封装名假设引脚布局。** 实测同一个 SOIC-8 footprint 引脚可能是上下两排(不是常识里的左右两排);凭"SOIC = 左右排"假设 rot=0 会让 HV·LV 两排都横跨竖直屏障。对 ∈ {0,90,180,270} 逐个 `move` 试,每次 `get_geometry` 复核,选能让 HV 组平均 x < LV 组平均 x 的那个。
4. `move` 时带上这个 rot,落子后再 `get_geometry` 确认 HV 组 pad 全在屏障左、LV 组全在右。

**禁止默认 rot=0,也禁止凭封装名推 rot。** 引脚物理位置只有 `get_geometry` 说了算。
确定性兜底:`_kicad_python_helper.py` 的 `check_slot_clearance` mode 会自动转 ISO IC——但你应主动推理,别依赖兜底。

## Phase C — 验证迭代

1. `check_placement <pcb> --barrier-x <X> --decoupling-pairs <CLAUDE.md 声明的 cap:IC>` —
   合法性闸门。看 `hard_fail` + `violations[]` + `warnings[]`。`--decoupling-pairs`
   传 Phase A 从项目 CLAUDE.md 提的 `decoupling_pairs`(如 `C6:U1,C10:U1,C5:U3`);
   不传则 `cap_far_from_ic` 退回 net 推断配对,可能配错 IC。
2. `render <pcb> --barrier-x <X> --ratsnest -o <png>` — 标注图。**必须 Read 这张 PNG**。
3. **判断**(打印结论):
   - 闸门:`hard_fail` 真 → 有重叠 / 越界 / 间距 / 非隔离件穿屏障,必修。
   - `warnings`:`connector_not_on_edge` → 连接器没贴边,必修;`geometry_uncertain` → 该件 extent 不可靠,Phase D DRC 重点看。
   - 回路:对照 brief 看飞线(灰线)——去耦对的飞线该极短;某域的件飞线大量射到别的域 = 没按回路摆。
   - 视觉:看 PNG——挤成团 / 大片空 / 大件压小件 / 连接器是否都贴板边。
   - HPWL(`metrics.hpwl_mm`):跨轮记录,**下降 = 在收紧**;但 HPWL 是参考不是目标,别为压它牺牲③④。
4. 把判断出的**具体问题**变成下一批 move,回 Phase B。

**不要**把 `check_placement` 的 score 当成要最小化的数。score=100 只代表合法。回路紧不紧、好不好看,是你看 brief + PNG 得出的判断。

## Phase D — 收尾

1. `refit_board <pcb>` — 把 Edge.Cuts + 隔离槽缩到元件实际范围 + margin。板框尺寸是
   `init_layout` 按 CLAUDE.md `pack_density` 一次性定的;回路把元件收紧后板框就偏大,
   refit 让它贴合。输出 `board` 尺寸 + `fill_ratio`(紧凑度)。**必须在 bridge_slot /
   add_zones 之前**——这两步都从 Edge.Cuts 读尺寸。`fill_ratio` 偏低 / 终图有大空洞 →
   回 B 把松散的区收紧,再 refit。
2. `bridge_slot <pcb>` — 隔离槽在每个跨槽 barrier 器件下方留实体桥。THT 隔离 DC-DC 的 pad pitch < 槽宽,不桥接槽会切穿 pad → DRC `copper_edge_clearance`;器件自身即屏障,桥接是正解。**必须在元件摆定 + refit 后跑**(桥按 barrier 器件最终位置画)。
3. `add_zones <pcb>` — GND 铺铜。
4. `run_drc <pcb>` — kicad-cli DRC。**`run_drc` 是几何最终裁判**:`check_placement` 用 courtyard / pad-bbox,可能漏判 `geometry_uncertain` 件的重叠,DRC 用真 footprint 几何会抓到。
   - `unconnected_items` 大量 = 预期(还没走线),忽略。
   - `courtyard` / `clearance` / `hole` 类违例 = **真问题**,不是预期——回 Phase B 修。
5. `render <pcb> -o <final>.png` — 终图。
6. **打印**:板框尺寸 + fill_ratio + DRC 各类违例数 + 终图路径 + 一句话布局总结。
7. 交回用户:KiCad GUI 手画走线 → `check-pcb`。

## route-ready 验收(回路退出条件,逐条全过才算交付)

布局做完到能直接布线的硬清单。SKILL.md 只点名,判断标准在这里:

1. `check_placement` `hard_fail=false`——0 重叠 / 0 间距违例 / 0 越界 / 非隔离件 0 穿屏障。
2. `run_drc` 无 `courtyard` / `clearance` / `hole` 类违例(`unconnected` 是预期,忽略)。
3. 隔离器件跨屏障且旋转正确——`get_geometry` 复核各域 pad 落在屏障对应侧。
4. 连接器 / 开关贴板边——`check_placement` 无 `connector_not_on_edge`。
5. 去耦 HF 电容 pad-to-pad ≤2mm 贴 IC(`cap_far_from_ic`);bulk 大容量可适当远。
6. **退化 courtyard 件**(电解电容等)按 footprint 名查真实体积复核——别信 pad-bbox 估计。
   这些件 `placement_brief` 会标 `geometry_uncertain`,courtyard 退化时 pad-bbox 远小于实体,
   靠它判间距会假阴性(看着没撞、实际撞);Phase D 的 `run_drc` 用真 footprint 几何兜底。
7. **紧凑度**:Phase D 跑 `refit_board` 让板框缩到元件实际范围;看 `fill_ratio`
   (courtyard 面积 / 板面积)+ 终图。有大片空洞 / `fill_ratio` 偏低就回 B 把对应区收紧再 refit。
   经验值:带通孔连接器的混合板 ~0.2 正常,纯 SMD 板可到 ~0.35。
8. Read 终图:三域分明、信号链按序、无明显挤团 / 大空洞。

任一条不过 → 回 B 修。

## 停止条件 + keep-best

- **停**:上面「route-ready 验收」清单**逐条全过**——`hard_fail=false` / `run_drc` 无 courtyard·clearance·hole 违例 / 隔离器件旋转正确(`get_geometry` 复核 pad 落对域)/ 连接器贴边 / 去耦 HF 电容 ≤2mm 贴 IC / 退化 courtyard 件按真实体积复核 / fill_ratio 达标 / 终图三域分明信号链按序。任一条不过就不算完工。
- ⚠️ `check_placement` 闸门干净 **≠** DRC 干净:闸门对 `geometry_uncertain` 件可能误判,Phase D 的 `run_drc` 才是几何裁判。score=100 不代表完工。
- **硬上限**:Phase B-C 最多 **6 轮**。到顶仍有验收项不过 → 停,在报告里逐条点名剩余问题交用户,**布局不甩给 GUI 补摆**(GUI 只用来走线)。
- **keep-best**:每轮 C 之后存一份 `<pcb>.round<N>.kicad_pcb` + 记 (hard_fail, hpwl)。
  收敛失败时取:先 hard_fail=false 的,再其中 hpwl 最低的——不取最后一轮。
- 回路会原地打转。同一个问题修 2 轮没改善 → 停,在报告里点名,别死磕。

## 完成报告(给用户)

跑了几轮 / 最终 score + hard_fail / DRC 违例数 / 终图路径 / route-ready 验收逐条结果 / 仍需用户处理的点。
合法 ≠ route-ready——如实说哪些验收项你没做到、为什么。
