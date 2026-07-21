---
name: jlc-eda-workflow
description: 嘉立创 EDA PCB 工作流协调技能。用于新建嘉立创 EDA 项目、将电路方案和元件选型落实到嘉立创 EDA、审查 BOM/CPL/Gerber 导出包，或准备嘉立创打样与贴片下单。触发词：嘉立创EDA、立创EDA、EasyEDA、嘉立创打样、BOM、CPL、导出 Gerber、贴片坐标、下单包。
---

# 嘉立创 EDA 工作流

本技能从本仓库的 KiCad Phase 0-5、BOM gate、设计审查与制造交付方式中提取流程约束，图纸编辑交由嘉立创 EDA GUI 完成。

## 边界

- `easyeda/source/` 中的嘉立创 EDA 工程是图纸唯一来源。脚本只读取导出的 CSV 和 ZIP，不直接改写 EDA 工程。
- 原仓库的 `draw-schematic`、`draw-pcb`、`check-schematic`、`check-pcb` 依赖 KiCad 文件格式，嘉立创 EDA 项目不调用这些 KiCad 生成和分析脚本。
- `component-selecting-CN` 可继续用于中国大陆选型；候选料号、LCSC 编号、数据手册链接需落到项目文档后再放入嘉立创 EDA。
- 嘉立创 EDA 的 ERC/DRC、封装预览、3D 检查和制造预览由操作者在 GUI 中完成；检查结论记录到 `review/` 和 `STATUS.md`。
- `extensions/jlc-eda-pro-companion/` 提供可选的 KiCadRouting 自动布线与布线前检查。它只处理明确选择的网络，完成后仍需在 GUI 中审查和执行 DRC。

## 项目骨架

在工作区根目录执行：

```powershell
py .claude/skills/jlc-eda-workflow/scripts/init_project.py buck_5v_3a --goal "12V 输入，5V 3A 输出的降压电源板"
```

生成的关键目录：

```text
Projects/<name>/
  PROJECT.md          设计参数、拓扑、接口、布局约束
  STATUS.md           Phase 状态和变更记录
  easyeda/source/     嘉立创 EDA 原工程与导出快照
  easyeda/exports/    BOM、CPL、Gerber ZIP
  datasheets/         数据手册与选型证据
  review/             ERC、DRC、导出审查记录
  release/            经确认后的下单包
```

## Phase 0-5

| Phase | 工作内容 | 主要产物 |
| --- | --- | --- |
| 0 | 新建项目，记录约束 | `PROJECT.md`、`STATUS.md` |
| 1 | 讨论拓扑、接口、功耗与风险 | 项目参数、连接表、关键计算 |
| 2 | 以 LCSC 为主完成可采购选型 | 候选表、LCSC 编号、替代料 |
| 2.5 | 用数据手册核对封装、引脚与额定值 | 数据手册证据、确认后的采购 BOM |
| 3 | 在嘉立创 EDA 绘制原理图并执行 ERC | 原理图截图、ERC 记录 |
| 3.5 | 审核网络、去耦、极性、接口和关键参数 | `review/schematic_review.md` |
| 4 | 在嘉立创 EDA 布局布线并执行 DRC；可选使用 Design Companion | PCB 工程、预检查结果、3D/DRC 截图 |
| 4.5 | 导出并核对 BOM、CPL、Gerber | `review/export_validation.json` |
| 5 | 在嘉立创下单页面复核工艺、拼板和贴片选项 | `release/` 下单记录 |

每个 Phase 完成或回退时，更新 `STATUS.md` 的状态和变更记录。严重问题必须回到对应上游阶段处理。

## 导出包校验

在嘉立创 EDA 导出以下文件后保存到 `easyeda/exports/`：

- 采购/生产 BOM CSV
- CPL（元件坐标）CSV
- Gerber ZIP

执行：

```powershell
py .claude/skills/jlc-eda-workflow/scripts/validate_export.py `
  --bom Projects/<name>/easyeda/exports/bom.csv `
  --cpl Projects/<name>/easyeda/exports/cpl.csv `
  --gerber Projects/<name>/easyeda/exports/gerbers.zip `
  --output Projects/<name>/review/export_validation.json
```

校验器检查：

- BOM 与 CPL 是否包含可识别的位号列
- CPL 的坐标、层和旋转角是否有效
- CPL 位号是否均存在于 BOM 中
- 生产场景需要所有 BOM 器件都有坐标时，加 `--require-all-cpl`
- Gerber ZIP 是否可读取，是否含板层和钻孔文件

结果 `pass` 可进入下单复核；`warning` 需要逐项确认；`fail` 必须修正后重新导出。对于手焊或仅贴片部分器件，缺少 CPL 位号通常应保留为 `warning` 并在下单前人工确认。

## 嘉立创 EDA 操作清单

### 原理图

1. 为每个采购元件确认 LCSC 编号、封装、引脚数、额定电压/电流和极性。
2. 使用网络标签表达跨页连接；连接器必须写清引脚功能与方向。
3. 运行 ERC，逐条记录接受或修复的原因。
4. 导出 PDF 或截图放入 `review/`，供设计审查使用。

### PCB

1. 先放连接器、功率器件、隔离边界和关键 IC，再放去耦与反馈网络。
2. 高电流回路、开关节点、模拟敏感区、差分线和天线区必须写入 `PROJECT.md` 的布局约束。
3. 使用自动布线前先运行 Design Companion 的“布线前检查”；覆盖已有走线必须在界面中显式勾选。
4. 铺铜后重新运行 DRC；检查丝印压焊盘、极性、安装孔、板框和禁布区。
5. 在嘉立创制造预览中确认层数、板厚、铜厚、阻焊颜色、工艺边和贴片选项。

## 常用请求

- “新建一个嘉立创 EDA 的 USB-C 供电板项目。”
- “按 LCSC 可采购性为这个项目选元件，并给出嘉立创 EDA 放置前的封装核对表。”
- “这是嘉立创 EDA 导出的 BOM 和 CPL，帮我检查位号、坐标与贴片范围。”
- “根据这个 Gerber、BOM 和 CPL 做嘉立创下单前审查。”
