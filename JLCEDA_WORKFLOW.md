# 嘉立创 EDA 工作流

## 定制目标

本 fork 以嘉立创 EDA Pro 扩展作为主要操作方式：Agent 通过原理图和 PCB API 直接修改嘉立创 EDA Pro 工程，完成规则检查、制造预览、BOM/CPL/Gerber 导出和下单。KiCad 用于可选的外部分析与路由能力复用。

## 当前能力

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 项目骨架 | 可用 | `jlc-eda-workflow/scripts/init_project.py` |
| 中国大陆选型 | 可用 | 复用 `component-selecting-CN` 的 LCSC 选型思路 |
| 数据手册与封装核对 | 可用 | 以项目 BOM、数据手册和嘉立创 EDA 元件属性为依据 |
| EasyEDA Pro 原理图 Agent | 开发中 | 基于 `sch_*` API 选库、放置器件、连线、写网络标签和执行 ERC |
| EasyEDA Pro PCB Agent | 部分可用 | Design Companion 已支持 PCB 预检查、选网布线和走线回写 |
| ERC 与 DRC | GUI 与 API | 设计主线由嘉立创 EDA Pro 执行；扩展调用 API 提取和执行规则检查 |
| KiCad 外部验证 | 可选 | `prepare_kicad_handoff.py` 记录快照、约束和 KiCad ERC/DRC 报告 |
| BOM/CPL/Gerber 一致性检查 | 可用 | `validate_export.py` |
| 可选自动布线与布线前检查 | 可用 | `extensions/jlc-eda-pro-companion/` |
| 嘉立创打样和贴片下单 | 人工复核 | 由制造预览和下单页面完成最终确认 |

## 与上游 KiCad 流程的对应关系

| 上游概念 | 嘉立创 EDA 定制实现 |
| --- | --- |
| `.kicad_sch` 生成 | 可选的离线分析快照 |
| KiCad ERC | 可选的交叉验证 |
| `.kicad_pcb` 自动布局 | 可选的路由和离线检查快照 |
| KiCad DRC | 可选的交叉验证 |
| KiCad 生产 BOM/CPL | 嘉立创 EDA 导出的 BOM 与 CPL |
| Gerber 导出和 release | 嘉立创 EDA Gerber ZIP 加导出包校验与下单记录 |

## 第一次项目的最小路径

```powershell
cd C:\Users\876762330\Desktop\projects\PCB-Agent-Teams-JLCEDA
py .claude/skills/jlc-eda-workflow/scripts/init_project.py led_driver_12v --goal "12V 输入 LED 恒流驱动板"
```

随后按以下节奏工作：

1. 在 `Projects/led_driver_12v/PROJECT.md` 和 `constraints/board_constraints.json` 填写电压、电流、接口、尺寸、制造能力和物理约束，并运行 `validate_board_constraints.py`。
2. 完成拓扑与元件选型，记录 LCSC 编号、数据手册、封装和替代料。
3. 在嘉立创 EDA Pro 内通过 Agent 扩展生成原理图、执行 ERC、更新 PCB，再执行布局、布线和 DRC。
4. 需要外部验证时，将快照保存到 `kicad/`，运行 `prepare_kicad_handoff.py --run-checks`，保存 KiCad 报告。
5. 在嘉立创 EDA Pro 内完成 3D 和制造预览。
6. 导出 BOM、CPL 和 Gerber ZIP 到 `easyeda/exports/`。
7. 运行校验器，修复 `fail` 条目，逐项确认 `warning` 条目。
8. 将最终下单文件复制到 `release/`，更新 `STATUS.md`。

## 可选自动布线

`extensions/jlc-eda-pro-companion/` 是本 fork 自制的 EasyEDA Pro 扩展。它继承 KiRouting Integration 的本地桥接结构，通过 KiCadRoutingTools 对选定网络自动布线，并增加布线前检查和默认保留已有铜箔的保护策略。

在图纸摆件、板框、层叠和规则已经确认后，启动 `extensions/jlc-eda-pro-companion/bridge_server/start_server.bat`，在 EasyEDA Pro 中开启“外部交互”，安装构建得到的 `.eext`。自动布线结束后必须回到 EasyEDA Pro 进行走线审查和 DRC。

## 导出校验

```powershell
py .claude/skills/jlc-eda-workflow/scripts/validate_export.py `
  --bom Projects/led_driver_12v/easyeda/exports/bom.csv `
  --cpl Projects/led_driver_12v/easyeda/exports/cpl.csv `
  --gerber Projects/led_driver_12v/easyeda/exports/gerbers.zip `
  --require-all-cpl `
  --output Projects/led_driver_12v/review/export_validation.json
```

当只需要 SMT 贴片坐标时，去掉 `--require-all-cpl`。连接器、安装孔和手焊 THT 元件没有 CPL 坐标时会报告为 `warning`，需要结合下单方式确认。

## 后续定制方向

- 解析嘉立创 EDA 的 BOM/CPL 实际导出样本，扩展 CSV 别名和字段规则。
- 为常见板型建立布局审查模板，例如 Buck、USB-C、STM32 最小系统、继电器隔离板。
- 接入嘉立创 EDA 的稳定开放接口后，实现导入后工程元件属性、设计规则与 ECO 的自动读取。
- 针对真实下单失败案例补充可复用规则和测试样本。
