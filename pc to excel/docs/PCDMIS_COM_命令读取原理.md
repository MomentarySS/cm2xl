# PC-DMIS 测量程序命令读取原理

> 本文档描述如何通过 **COM 自动化接口** 从 PC-DMIS 读取当前测量程序（`.PRG`）中的命令与实测数据。  
> 适用于外部工具（Python/C#/VB 等）或 PC-DMIS 内部 BASIC 脚本二次开发。  
> 本仓库 `pcdmis_excel_exporter` 的实现即遵循此模型。

---

## 1. 核心概念

### 1.1 读的是什么？

| 方式 | 说明 |
|------|------|
| **COM 内存对象（推荐）** | 读取 PCDMIS **已打开、已在内存中** 的测量程序对象，含名义值、实测值、偏差、Bonus 等运行时数据 |
| **解析 .PRG 文本文件（不推荐）** | `.PRG` 主要是命令定义与参数；完整实测结果以 COM 运行时状态为准，文本解析易漏、易错、无统一格式 |

**结论：二次开发应通过 COM 访问 `ActivePartProgram.Commands`，而不是解析磁盘上的 PRG 源码。**

### 1.2 技术栈

- **接口**：Windows COM（Component Object Model）
- **类型库**：`Pcdlrn.tlb` / `INTEROP.PCDLRN.DLL`
- **ProgID**：`PCDLRN.Application` 或带版本号如 `PCDLRN.Application.2024.1`
- **Python**：`pywin32`（`win32com.client`）
- **PC-DMIS 内部**：BASIC Script（同一套对象模型）

---

## 2. 对象模型

```
PCDLRN.Application                 ← 应用程序根对象
├── VersionString                  版本字符串
├── ActivePartProgram              当前活动测量程序（须已打开 .PRG）
│   ├── Name                       程序名（如 本体1.PRG）
│   ├── PartName / SerialNumber    零件名、序列号
│   ├── PartProgramSettings        程序设置（如负公差显示方式）
│   └── Commands                   命令集合（1-based 索引）
│       ├── Count                  命令总数
│       └── Item(i) / (i)          第 i 条 Command
│           ├── ID                 命令标识符（如 FAI_12-1、FCF圆柱度1）
│           ├── TypeDescription    类型描述（如「尺寸位置」「2D 距离」）
│           ├── Marked             是否 Mark（输出到报告）
│           ├── IsFeature          是否为特征命令
│           ├── IsDimension        是否为评价尺寸
│           ├── IsToleranceCommand 是否为形位公差（2022.2+）
│           ├── FeatureCommand     特征子对象（IsFeature 时）
│           ├── DimensionCommand   尺寸子对象（部分版本可用）
│           ├── ToleranceCommand   形位公差子对象（2022.2+）
│           ├── GetFieldValue(f, idx)  按字段枚举读数值
│           └── GetText(f, idx)        按字段枚举读文本
```

**索引约定**：`Commands` 从 **1** 开始编号，与编辑窗口命令顺序一致。

---

## 3. 连接 PCDMIS

### 3.1 最小示例（Python）

```python
import win32com.client as wc

# 方式 A：Dispatch（常用）
app = wc.Dispatch("PCDLRN.Application.2024.1")  # 或 PCDLRN.Application

# 方式 B：附着已运行实例（ROT 已注册时）
# app = wc.GetActiveObject("PCDLRN.Application.2024.1")

print(app.VersionString)

part = app.ActivePartProgram
if part is None:
    raise RuntimeError("请先在 PCDMIS 中打开测量程序")

cmds = part.Commands
print(f"命令数: {cmds.Count}")
```

### 3.2 权限与位数

| 要求 | 说明 |
|------|------|
| **权限一致** | PCDMIS 与外部工具必须同为普通用户或同为管理员，否则 COM 连接失败或阻塞 |
| **64 位** | PC-DMIS 2022+ 为 64-bit，Python/exe 也须 64 位 |
| **COM 注册** | 新装 PCDMIS 建议以管理员运行一次，完成 COM 注册 |

### 3.3 ProgID 发现

- 注册表：`HKEY_CLASSES_ROOT` 下搜索 `PCDLRN.Application`
- 常见形式：`PCDLRN.Application.2022.1` … `PCDLRN.Application.2026.1`
- 多版本并存时，优先附着**当前正在运行**的实例对应 ProgID

---

## 4. 读取流程（标准模式）

```
连接 Application
    → 取 ActivePartProgram
    → 遍历 Commands（建议先全量缓存，减少跨进程 COM 调用）
    → 按 IsFeature / IsDimension / IsToleranceCommand 等分类
    → 用 GetFieldValue / GetText / 子对象 API 提取字段
    → （可选）按 Marked、是否有实测值、报告类别过滤
    → 输出到 Excel / CSV / 数据库等
```

### 4.1 遍历命令

```python
cmds = part.Commands
count = int(cmds.Count)

cache = []
for idx in range(1, count + 1):
    try:
        cmd = cmds.Item(idx)
    except Exception:
        cmd = cmds(idx)  # 部分环境仅支持调用式索引
    cache.append((idx, cmd))
```

**性能建议**：大程序（数千条命令）应**单次遍历缓存**，再在本进程内多次解析，避免每条命令多次 COM 往返。

---

## 5. 命令类型与读取方式

### 5.1 特征（IsFeature）

用于圆、平面、圆柱、直线等几何元素。

```python
if cmd.IsFeature:
    feat = cmd.FeatureCommand
    name = cmd.ID  # 或 feat.ID

    # 质心坐标：GetPoint(点类型, 数据类型, x, y, z)
    # 数据类型：FDATA_THEO=理论, FDATA_MEAS=实测
    # 详见类型库 FPOINT_CENTROID 等常量
```

常用字段（`GetFieldValue`）：

| 字段常量 | 含义 |
|----------|------|
| `THEO_DIAM` / `MEAS_D` | 理论/实测直径 |
| `THEO_LENGTH` / `MEAS_LENGTH` | 理论/实测长度 |
| `THEO_I`, `THEO_J`, `THEO_K` | 矢量分量 |

### 5.2 评价尺寸（IsDimension）

用于 2D 距离、尺寸位置、角度、直径位置等。

```python
if cmd.IsDimension:
    dim_id = cmd.ID
    nominal   = cmd.GetFieldValue(NOMINAL, 0)
    measured  = cmd.GetFieldValue(DIM_MEASURED, 0)
    plus_tol  = cmd.GetFieldValue(F_PLUS_TOL, 0)
    minus_tol = cmd.GetFieldValue(F_MINUS_TOL, 0)
    axis      = cmd.GetText(AXIS, 0)
    bonus     = cmd.GetFieldValue(DIM_BONUS, 0)
```

**注意**：

- 一条报告尺寸可能对应 **多条相邻** `IsDimension` 命令（如「尺寸位置」头行 + 「直径位置」配对行），需按 `TypeDescription` 合并后再展示。
- 部分版本（如 2024.1）`DimensionCommand` 子对象可能不可用，应优先 `GetFieldValue`，子对象作回退。
- 实测值字段可能为 `DIM_MEASURED`、`DIM_LENGTH`、`DIM_HALF_ANGLE` 等，需按类型探测。

### 5.3 形位公差 — 新版（IsToleranceCommand，2022.2+）

2022.2 起引入 `ToleranceCommand` 封装对象，旧版 `GetText`/`LINE1_*` 字段方式在新版 FCF 上可能失效。

```python
if cmd.IsToleranceCommand:
    tol = cmd.ToleranceCommand
    symbol = tol.gdtSymbol          # 位置度、圆柱度等
    seg_count = tol.SegmentCount
    feat_count = tol.FeatureCount

    # 大小尺寸区
    for j in range(1, tol.sizeCountCombined + 1):
        nom = tol.sizeNominal(j)
        meas = tol.sizeMeasured(j)
        # ...

    # 区段 × 被测特征
    for k in range(1, seg_count + 1):
        for j in range(1, feat_count + 1):
            meas = tol.SegmentDimMeasured(k, j)
            # ...
```

### 5.4 形位公差 — 旧版（FCF / Legacy）

2019 R2 及更早路径：无 `ToleranceCommand`，需用 `GetFieldValue` / `GetText` 读 `LINE1_*`、`LINE2_*`、`LINE3_*` 表格字段（见下文常量表）。

### 5.5 报告过滤

与 PCDMIS 报告窗口对齐时，通常只保留：

1. **`cmd.Marked == True`** — 用户勾选 Mark、输出到报告
2. **有实测值** — `DIM_MEASURED` 等可读，或名义+偏差可算
3. **类别** — 已评价尺寸、形位公差、大小尺寸（非原始特征定义行、非纯基准定义行）

---

## 6. 字段常量（ENUM_FIELD_TYPES）

PC-DMIS 通过**整数枚举**标识字段，而非字符串属性名。

### 6.1 常用常量

| 名称 | 典型值 | 用途 |
|------|--------|------|
| `ID` | 2 | 命令 ID |
| `REF_ID` | 3 | 关联特征 ID |
| `DISPLAY_ID` | 184 | 显示用 ID（勿与尺寸 ID 混淆） |
| `AXIS` | 132 | 轴字母 X/Y/Z/D 等 |
| `NOMINAL` | 166 | 名义值 |
| `F_PLUS_TOL` | 167 | 上公差 |
| `F_MINUS_TOL` | 168 | 下公差 |
| `DIM_MEASURED` | 328 | 评价尺寸实测 |
| `DIM_DEVIATION` | 340 | 偏差 |
| `DIM_BONUS` | 324 | Bonus |
| `DIM_OUTTOL` | 344 | 超差 |
| `DIM_LENGTH` | 173 | 长度类实测 |
| `GDT_SYMBOL` | 708 | 形位公差符号 |
| `LINE1_FEATNAME` | 645 | FCF 第 1 行特征名 |
| `LINE1_MEAS` | 647 | FCF 第 1 行实测 |

> 完整列表见安装目录 `Pcdlrn.tlb` 或 Hexagon Automation Objects 文档。  
> 各版本数值基本一致，建议从本机类型库加载，失败再用硬编码回退。

### 6.2 加载常量（Python）

**方式一：动态加载（开发灵活）**

```python
import win32com.client.gencache as gencache
from win32com.client import constants

PCDLRN_TYPELIB = "{10C96EB9-ED97-492D-BC67-700C7F18E394}"
gencache.EnsureModule(PCDLRN_TYPELIB, 0, 19, 1)  # major/minor 按本机版本调整
NOMINAL = constants.NOMINAL
```

**方式二：makepy 导出（打包分发推荐）**

使用 `win32com\client\makepy.py` 对 `Pcdlrn.tlb` 生成 Python 常量模块，随项目分发，避免目标机无类型库时失败。

详见参考文章 [IYATT：PC-DMIS 2019 R2 Python 二次开发](https://blog.iyatt.com/?p=18363) 中「使用 COM 组件中的常量」一节。

### 6.3 读取封装

```python
def field_value(cmd, const, index=0):
    try:
        v = cmd.GetFieldValue(const, index)
        return None if v is False else v
    except Exception:
        return None

def text_value(cmd, const, index=0):
    try:
        return str(cmd.GetText(const, index) or "").strip()
    except Exception:
        return ""
```

`GetFieldValue` 失败时 COM 常返回 `False`，需单独判断。

---

## 7. 两种实现路径

| 路径 | 运行位置 | 典型用途 |
|------|----------|----------|
| **外部 COM** | 独立进程（Python exe、C# 工具） | 一键导出、MES 对接、批量报表 |
| **内部 BASIC** | PCDMIS 进程内（SCRIPT 命令调用 `.bas`） | 测完一件在程序内导出；与 PCDMIS 权限天然一致 |

内部 BASIC 示例骨架：

```vb
Sub Main
    Dim part As Object
    Set part = Application.ActivePartProgram
    Dim cmds As Object
    Set cmds = part.Commands

    Dim i As Long, cmd As Object
    For i = 1 To cmds.Count
        Set cmd = cmds(i)
        If cmd.Marked Then
            ' readDimension / readFcf ...
        End If
    Next i
End Sub
```

外部与内部使用的是**同一套 COM 对象模型**，字段常量相同。

---

## 8. 版本差异摘要

| 版本 | 变化 |
|------|------|
| **2019 R2 及更早** | 形位公差主要靠 `GetFieldValue` + `LINE1/2/3_*` |
| **2022.2+** | 新增 `IsToleranceCommand` / `ToleranceCommand`，形位公差应优先此路径 |
| **2023.2+** | 旧 FCF 字段读取方式在新命令上可能失效 |
| **2024.1** | 部分尺寸命令 `DimensionCommand` 属性不稳定，优先 `GetFieldValue` |

**负公差显示**：读取下公差时需读 `PartProgramSettings.MinusTolerancesShowNegative`，决定下公差是否带负号。

---

## 9. 常见问题

| 现象 | 可能原因 |
|------|----------|
| `无效的类字符串` (-2147221005) | ProgID 错误、COM 未注册、PCDMIS 未安装 |
| 连接阻塞无响应 | 权限不一致（一方管理员一方普通） |
| `ActivePartProgram` 为空 | 未打开 .PRG |
| 读不到实测值 | 程序未执行到该尺寸；或命令未 Mark |
| 形位公差全空 | 2022.2+ 仍用旧 LINE1 字段，应改用 `ToleranceCommand` |
| 浮点差 0.001 | COM 双精度 vs 界面四舍五入，通常可接受 |

---

## 10. 最小可运行示例（读所有 Mark 尺寸）

```python
import win32com.client as wc

# 常量可替换为从 Pcdlrn.tlb 加载
ID, NOMINAL = 2, 166
F_PLUS_TOL, F_MINUS_TOL = 167, 168
DIM_MEASURED = 328

app = wc.Dispatch("PCDLRN.Application")
part = app.ActivePartProgram
if not part:
    raise SystemExit("请先打开测量程序")

for i in range(1, part.Commands.Count + 1):
    cmd = part.Commands.Item(i)
    if not cmd.IsDimension:
        continue
    if not cmd.Marked:
        continue
    meas = cmd.GetFieldValue(DIM_MEASURED, 0)
    if meas is False:
        continue
    print(
        cmd.ID,
        cmd.TypeDescription,
        "NOM=", cmd.GetFieldValue(NOMINAL, 0),
        "MEAS=", meas,
        "+TOL=", cmd.GetFieldValue(F_PLUS_TOL, 0),
        "-TOL=", cmd.GetFieldValue(F_MINUS_TOL, 0),
    )
```

---

## 11. 参考资源

### 官方文档

| 资源 | 链接 |
|------|------|
| Automation Objects（2024.1） | https://docs.hexagonmi.com/pcdmis/2024.1/en/helpcenter/mergedProjects/automationobjects/webframe.html |
| 其他版本 | 将 URL 中 `2024.1` 替换为对应版本号 |

### 社区实践（强烈推荐）

| 主题 | 链接 | 说明 |
|------|------|------|
| Python 读写特征与评价尺寸 | https://blog.iyatt.com/?p=18363 | 连接 COM、导出枚举常量、特征 `GetPoint`、尺寸 `GetFieldValue`、修改评价尺寸 |
| Python 读取 ToleranceCommand（2023.2+） | https://blog.iyatt.com/?p=18719 | 2022.2 起形位公差新 API，含完整 Python 示例 |
| 开源导出工具参考 | https://github.com/IYATT-yx/pcdmis-export-data | 基于上述文章的 GUI 导出工具雏形 |
| 自动请求管理员权限 | https://blog.iyatt.com/?p=18238 | 独立 exe 与管理员版 PCDMIS 对接时使用 |

### 本仓库实现对照

| 模块 | 路径 | 职责 |
|------|------|------|
| COM 连接 | `connector/com_detector.py` | ProgID 发现、权限检查、Dispatch |
| 数据提取 | `core/data_extractor.py` | 遍历 Commands、分类解析 |
| 字段常量 | `connector/pcdlrn_constants.py` | 类型库加载与回退 |
| 报告过滤 | `core/report_filter.py` | Mark / 实测值 / 报告类别 |
| 内部脚本 | `scripts/export_current.bas` | PCDMIS 内 CSV 导出 |

### 历史参考（本仓库 `参考内容`）

- `参考内容/数据导出工具/PcdDimToCsvExporter.bas` — 早期 BAS 尺寸导出示例

---

## 12. 给其他项目的集成建议

1. **只依赖 COM，不解析 PRG 文本**，除非仅需读静态名义值且无 PCDMIS 运行环境。
2. **抽象一层 `MeasurementReader` 接口**，底层可以是 Python COM、C# Interop 或 BAS，上层业务只消费统一的「尺寸记录」结构。
3. **常量与版本**：启动时探测 `VersionString`，按版本分支形位公差读取逻辑（Legacy FCF vs `ToleranceCommand`）。
4. **连接策略**：先 `GetActiveObject`，再 `Dispatch`；多件测量时定期探测会话是否仍有效并重连。
5. **与报告一致**：默认过滤 `Marked` + 有实测；需要全量调试数据时再开 `scope=all`。
6. **许可**：COM 接口随 PC-DMIS 安装提供，二次开发需遵守 Hexagon 软件许可；分发工具时不要捆绑 PCDMIS 安装文件。

---

*文档版本：1.0 · 与 pcdmis_excel_exporter 代码库同步 · 2026-08*
