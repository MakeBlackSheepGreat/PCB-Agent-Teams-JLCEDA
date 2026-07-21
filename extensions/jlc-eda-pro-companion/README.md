# JLCEDA Design Companion

面向嘉立创 EDA Pro 的本地设计协同扩展。它继承 KiRouting Integration 的 EasyEDA Pro 到 KiCadRoutingTools 桥接能力，并增加计划驱动的原理图生成、布线前检查、独立本地桥接和保守的走线回写策略。

## 功能

- 在原理图编辑器执行可审查的 JSON 设计计划：LCSC 器件解析、放置、属性写入、导线、网络标识、端口、ERC、网表和保存
- 在任何器件解析或运行时写入失败时，按逆序回滚本次创建的图元并报告结果
- 对选定网络调用 KiCadRoutingTools A* 路由器
- 支持单端网络、差分对、BGA/QFN 扇出、长度匹配与多层参数
- 从当前 PCB 收集元件、焊盘、网络、已有走线、过孔、板框和层信息
- 布线前检查：板框、元件、焊盘、网络、铜层、重复位号、未知网络、关键电源网络和差分对命名
- 读取嘉立创 EDA Pro 的 DRC 参数，阻止小于最小线宽、间距、过孔或板边距离的布线请求
- 默认保留所选网络已有铜箔；勾选“覆盖所选网络的已有走线与过孔”后才会删除并重写

## 架构

```text
JLCEDA Pro extension
  -> http://127.0.0.1:8766
  -> bundled FastAPI bridge
  -> temporary KiCad PCB representation
  -> KiCadRoutingTools v0.18.0
  -> new tracks and vias returned to JLCEDA Pro
```

临时 KiCad PCB 仅用于路由和分析。它不会作为嘉立创 EDA 工程迁移器使用，也不会替代原理图、DRC、3D 检查和制造预览。

## 安装与启动

1. 使用 EasyEDA Pro `3.2.0` 或更高版本，在设置中开启“外部交互”。
2. 从本仓库构建 `.eext`，或安装对应 Release 包。
3. 在 `bridge_server/` 运行 `start_server.bat`。
4. 在原理图或 PCB 编辑器菜单打开 `JLCEDA Design Companion`。

首次启动会安装 Python 依赖、下载 KiCadRoutingTools `v0.18.0` 并准备 Rust 路由器。桥接服务仅监听 `127.0.0.1:8766`。

## 推荐流程

1. 选型和拓扑冻结后，生成原理图设计计划并在原理图 Agent 中验证、执行和审查 ERC。
2. 更新 PCB，确认摆件、板框、层叠、禁布区和关键电源/高速约束。
3. 执行“运行布线前检查”，修复 `fail` 项目。
4. 对普通或明确指定的网络运行自动布线。
5. 在 EasyEDA Pro 内人工审查走线、铺铜、过孔和回流路径，随后执行 DRC。
6. 导出 BOM、CPL、Gerber 后，用仓库的 `jlc-eda-workflow` 校验下单包。

原理图设计计划和完整架构见 [JLCEDA_EXTENSION_ARCHITECTURE.md](../../docs/JLCEDA_EXTENSION_ARCHITECTURE.md)。

高 di/dt 电源回路、模拟敏感区、射频、USB/DDR 等高速链路、隔离区应以人工布线和设计规则为主。

## 开发

```powershell
npm install
npm run build
```

桥接服务依赖：

```powershell
cd bridge_server
python -m pip install -r requirements.txt
python server.py
```

测试快速检查：

```powershell
python -m unittest discover -s bridge_server/tests -v
```

## 开源与来源

本目录内 MakeBlackSheepGreat 新增和修改的文件按 [Apache-2.0](LICENSE) 提供。上游 KiRouting Integration 快照、KiCadRoutingTools 和父仓库适用各自许可证；详细范围与归属见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [UPSTREAM.md](UPSTREAM.md)。
