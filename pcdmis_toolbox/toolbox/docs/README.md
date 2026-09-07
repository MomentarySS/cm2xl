# cm2xl 用户文档

本目录为测量房离线部署后的**用户向说明**（非开发文档）。开发约定见仓库根目录 `ARCHITECTURE.md` 与 `pcdmis_toolbox/CLAUDE.md`。

## 文档索引

| 文档 | 内容 |
|------|------|
| [cmm_filler.md](cmm_filler.md) | CMM 报告 OCR 识别、Excel 填充、NG 分析 |
| [pc_to_excel.md](pc_to_excel.md) | PCDMIS 连接、导出、出货表填入、BAS 植入 |

## 快速入口

- **集成模式**：运行 `cm2xl.exe` 或 `python main.py`，左侧切换模块。
- **独立模式**：`python -m modules.cmm_filler` / `python -m modules.pc_to_excel`
- **配置目录**：`%LOCALAPPDATA%\cm2xl\config\`（开发模式为项目 `data/config/`）
- **日志目录**：`%LOCALAPPDATA%\cm2xl\logs\`（**不在**程序安装目录；通常在 C 盘用户文件夹下）
- **查看路径**：顶栏「关于」可查看完整路径，并复制 / 打开日志文件夹
- **维护**：顶栏「设置」→ 日志区「清理日志」/ OCR 区「清理 OCR 缓存」

## 权限与位数

- 须 **64 位 Windows** 与 **64 位 Python**（开发时）。
- PCDMIS 若以管理员启动，本工具也需管理员权限（可用分发包中的 `run_as_admin.bat`，由 `build.bat` 自动打包）。

## 打包后文档位置

安装包会将本目录复制到 `{安装目录}\docs\`，与 `使用说明.txt` 一并分发。
