# 项目 CLAUDE.md 约束读取

placement v2 (`scripts/placement_v2/orchestrator.py::parse_claude_md_placement`)
解析项目 CLAUDE.md 里**带标题**的 YAML 块拿提示。位置约束：

1. 标题必须匹配 `## placement` / `## 布局` / `## Placement`（大小写无关）
2. 紧随其后必须是 ` ```yaml ` 围栏代码块
3. 块内键值见下表；找不到则用默认值

```markdown
## placement

\`\`\`yaml
placement:
  board:
    margin: 2.5
  slots:
    - x_mm: 30.0
      width_mm: 1.5
  anchors:
    U1: ISO
  chains: []
  decoupling_pairs: []
\`\`\`
```

## 字段（v2 schema）

| 字段 | 含义 | 默认 |
|---|---|---|
| `board.margin` | 板内 inset (mm)，给走线留 keepout | 2.5 |
| `slots[].x_mm` | 隔离槽中心 X (mm) | — |
| `slots[].width_mm` | 隔离槽宽 (mm) | — |
| `anchors{ref: region}` | 强制把元件钉在 HV/LV/ISO | 自动分类 |
| `chains` | R 链 / 差分对链——layout 按声明顺序成直线 | [] |
| `decoupling_pairs` | (IC, cap) 配对——cap 紧贴 IC 东侧 (≤1mm) | [] |

> 板宽 / 板高由 v2 floorplan 根据 footprint 总面积估算，无需手填。
> 如果项目 CLAUDE.md 没有 `## placement` 块，pipeline 用默认值（自动 HV/LV 分区，无 slot，无 chain）。
> **`chains` 和 `decoupling_pairs` 是"提前放近"的声明**——layout 不做能量优化，只按声明 snap。

## CLAUDE.md 自动发现路径（preflight 优先级）

1. `<project_dir>/CLAUDE.md`
2. `<project_dir>/../CLAUDE.md`（典型场景：`Projects/<name>/CLAUDE.md` 在 `kicad/` 父级）
3. rglob 兜底
