# Changelog

## v0.1.0 (2026-07-21)

### Added
- Rebranded the imported extension as JLCEDA Design Companion.
- Added a local board preflight dashboard for board outline, components, pads, nets, layers, duplicate designators, power nets, and differential-pair naming.
- Added a dependency-free `/api/review/preflight` bridge endpoint and unit tests.
- Added Apache-2.0 scope, upstream snapshot, and third-party notice documents.

### Changed
- The bridge now listens only on `127.0.0.1:8766`.
- Existing copper on selected networks is preserved by default; replacement requires an explicit checkbox.
- Fixed board-summary outline detection for EasyEDA outline line and arc payloads.

## v1.0.2 (2026-07-20)

### 修复
- **启动脚本崩溃**：修正 Step 4b 括号未转义导致脚本静默崩溃（"第三步自动退出"真因）
- **启动脚本加固**：`pip` → `python -m pip`；`curl` 加 `-f`；pip 安装加清华镜像兜底与超时重试
- **服务启动页嵌入脚本**：更新 service-not-found.html 中 base64 嵌入的 start_server.bat/.sh 为修复版
- **iframe 文案**：修复 DRC / Done / Total / Routing 等动态文案 `${1}` 占位符泄漏
- **多轮廓板布线**：修复 `outline` 变量未绑定导致布线崩溃（自动补丁）
- **子进程管道死锁**：修复布线子进程 stdout 管道填满后死锁导致布线卡死
- **任务中断**：布线超时/取消时真正终止服务端任务，避免僵尸任务阻塞下次布线
- **打包体积**：修正 `.edaignore` 漏配，`.eext` 由 18MB 降到约 1MB

### 新增
- **DRC 默认值预填**：打开对话框时按 DRC 规则自动抬升违规参数到最小合规值
- **固定 KiCadRoutingTools v0.18.0**：源码（`refs/tags/v0.18.0`）+ Rust 二进制（`--tag v0.18.0`）均固定，避免上游更新导致版本不匹配和路由退化
- **通配符解压重命名**：兼容 GitHub tag/branch 的各种目录命名
- **README 示例图**：添加布线界面、布线结果、获取启动脚本、开启外部交互四张示例图

### 文档
- 重写 `CLAUDE.md`（修正端点、单位、路由模式、CI 发布流程等）

## v1.0.1 (2026-06-15)

多语言优化

## v1.0.0 (2026-05-11)

首个正式发布版本。

### 功能

- **单端布线** — 通过桥接服务器调用 KiCadRouting Tools A* 路由引擎
- **差分对布线** — 支持中心线路由、极性交换、GND 过孔放置
- **BGA/QFN 扇出** — 自动逃逸路径生成
- **电源平面** — 自动过孔连接 SMD 焊盘到内层铜皮
- **网络选择** — 支持按名称过滤、通配符匹配、排除模式
- **层配置** — 支持多层布线，每层可设置成本权重
- **参数配置 UI** — iframe 对话框，支持线宽、间距、过孔、网格步长等参数
- **异步布线** — 后台执行，支持进度轮询和取消
- **AI 分析接口** — 板卡概览、电源网络分析、差分对检测、总线组检测、网络统计
- **DRC 参数校验** — 提交前自动校验参数是否满足 EasyEDA DRC 规则
- **自动取消** — 提交新任务自动取消上一个正在运行的任务
- **大型元件分块传输** — 通过 /api/extra-components 分块发送，避免单次请求过大
