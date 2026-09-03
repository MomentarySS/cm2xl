# PCDMIS 导出（pc_to_excel）

通过 COM 连接 **PC-DMIS 2017 R2–2026.1（64 位）**，提取测量程序数据，导出 Excel 报告或填入出货检验表。主测环境为 2024.1。

形位公差：2017 R2–2020 R2 走 XactMeasure（`IsFCFCommand`）；2022.1+ 走 Geometric Tolerance（`ToleranceCommand`）。多版本同机时只开一套，工具会附着正在运行的那套。

## 使用前准备

1. 启动 **PC-DMIS** 并打开零件程序（PRG）。
2. 本工具与 PCDMIS **权限级别一致**（同为管理员或同为普通用户）。
3. 在模块内点击 **连接**，状态栏应显示 🟢 已连接及版本号。

> 模块激活后每 30 秒自动检测 COM 会话；会话失效时会自动标记为未连接。

## 典型流程

### 一键导出 Excel

1. 连接 PCDMIS → 确认当前零件程序。
2. 设置导出目录与文件名规则（默认 **仅 Mark 命令**）。
3. 点击 **导出 Excel**（列格式与 PC-DMIS 内置报告一致）。

### PC-DMIS 工具栏一键出报告

不改 PRG。在本模块点 **部署工具栏启动器**，然后在 PC-DMIS：

1. **视图 → 工具栏 → 自定义 → 菜单 → 创建项目**
2. 选 `%LOCALAPPDATA%\PCDMIS_ExcelExporter\scripts\cm2xl_toolbar_export.vbs`（不认 vbs 则用同目录 `.bat`）
3. 从「用户自定义命令」拖到工具栏

测完后点该按钮：启动 cm2xl（跳过 OCR）→ 打开「PCDMIS导出」→ 按当前「仅 Mark」设置自动导出 Excel。cm2xl 已在运行时会唤醒现有窗口再导，不另开实例。

开发模式也可：

```bash
python main.py --module pc_to_excel --auto-export
```

### 填入出货表

1. 选择出货检验表模板（.xlsx/.xlsm）。
2. 配置件号、目标列、公差等。
3. 点击 **填入**，生成新文件（不覆盖原表）。

### BAS 命令植入（可选）

1. **部署 BAS 脚本** → 写入 `%LOCALAPPDATA%\PCDMIS_ExcelExporter\scripts\`
2. 在 PCDMIS 中 **植入** `PC2XL_EXPORT` 命令，可在测量程序内一键触发导出。

## 独立模式引导

首次独立运行且未连接时，界面会显示 3 步引导卡片；连接成功后自动隐藏。

## CLI（批量 / 无人值守）

```bash
python -m modules.pc_to_excel.cli export --output ...
python -m modules.pc_to_excel.cli inject
python -m modules.pc_to_excel.cli fill --form ...
```

## 配置位置

`%LOCALAPPDATA%\cm2xl\config\pc_to_excel\settings.json`

旧版独立工具配置可从 `%LOCALAPPDATA%\PCDMIS_ExcelExporter\` 自动迁移。

## 常见问题

- **连接失败 0x80070005**：权限不一致 → 用 `run_as_admin.bat` 或改为与 PCDMIS 相同权限启动。
- **32 位 Python**：PC-DMIS 2017 R2+ 需 64 位，启动时会硬阻断。
- **导出为空**：确认 PRG 中有已执行的尺寸/形位命令，且「仅导出标记项」选项与程序一致。
- **圆柱等多轴只填了一格**：每个序号只写一格，优先取 **D（直径）**；X/Y/Z 仅参考，不会拆成多行。
- **填入 0 格但提取有数据**：检查出货表检具列（默认 G）是否为 `A` 或 `CMM`，以及 A 列序号是否与尺寸名对应（如 `CC_15` → `15`）。

## 维护

顶栏 **设置** → **日志** 分组 → **清理日志文件**（不影响 PCDMIS 连接状态）。
