# CMM 三坐标测量报告自动填充工具

从 CMM 三坐标测量 PDF 报告中自动 OCR 识别数据，按日期分组填充到 Excel 检验模板。内置 OCR 模型，完全离线运行。

## 文件清单

| 文件 | 说明 |
|---|---|
| `cmm_filler_v10.py` | 核心逻辑（PDF→OCR→解析→Excel 填充） |
| `cmm_filler_gui.py` | GUI 界面（拖拽 / 识别预览 / NG 统计） |
| `template_wizard.py` | 模板配置向导（GUI 内模态运行，也可独立打开） |
| `ocr_engine.py` | OCR 引擎封装（PaddleOCR，强校验内置模型） |
| `version.py` | 版本信息 |
| `template_config.json` | 模板配置（实际生效的是 %LOCALAPPDATA% 那份） |
| `build.bat` | PyInstaller 打包脚本（含瘦身步骤） |
| `fix_dist.py` | 打包后 paddleocr 修复脚本 |
| `CMMFiller.spec` | PyInstaller 打包配置 |
| `hooks/` | PyInstaller hooks（paddleocr/customtkinter） |
| `installer/CMMFiller.iss` | Inno Setup 安装包脚本 |
| `samples/` | 测试用 CMM 扫描件（50 个 PDF） |
| `templates/` | Excel 模板（模板1、模板2） |
| `docs/` | 安装与使用说明 |

## 目录结构

```
.
├── build.bat                  # 打包脚本（一键：模型检查→打包→修复→瘦身→校验）
├── launch.bat                 # 启动 GUI 快捷方式
├── fix_dist.py                # 打包后修复
├── CMMFiller.spec             # PyInstaller 配置
├── hooks/                     # PyInstaller hooks
├── installer/                 # Inno Setup 安装包脚本
├── cache/ → %LOCALAPPDATA%\CMMFiller\cache\   # OCR 图片缓存
├── outputs/                   # 程序输出
├── samples/                   # 测试 PDF 样本
├── templates/                 # Excel 模板
├── models/paddleocr/          # 内置 OCR 模型（约 18MB，git 忽略）
├── docs/                      # 用户文档
├── cmm_filler_v10.py          # 核心逻辑
├── cmm_filler_gui.py          # GUI
├── template_wizard.py         # 模板向导
├── ocr_engine.py              # OCR 引擎
└── requirements.txt           # 依赖
```

## 运行方式

```bash
# 方式1：命令行（直接处理）
set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
python cmm_filler_v10.py

# 方式2：GUI 界面（推荐）
set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
python cmm_filler_gui.py

# 方式3：模板配置向导
python template_wizard.py
```

## GUI 功能（v1.0.0）

- **拖拽**：把文件夹直接拖到「PDF 文件夹」输入框上即可；模板 xlsx 也可拖入
- **处理前预览**（默认开启）：识别完成后弹出预览表，核对每份 PDF 的零件名/
  日期/每项测量值；识别错的数据**取消勾选**即可剔除，确认后才写入 Excel
- **NG 超差提示**：实测值超出公差的项红色高亮并带 NG 徽章，结果页有统计汇总
- **结果页**：处理完成自动切换，显示成功/失败/跳过/NG 统计和生成文件列表
- **日志**：按级别着色（错误红/成功绿/警告橙），「查看日志」弹内置窗口

## 配置说明

`template_config.json` 控制所有映射关系（向导可视化配置，存于
`%LOCALAPPDATA%\CMMFiller\`）：

- `template_path`: 模板文件路径
- `sheet_name`: 工作表名称
- `data_start_row`: 数据起始行
- `sample_row`: 样品序号行
- `max_data_row`: 数据区最后一行（可选，缺省时自动扫描模板）
- `columns`: 列映射（规格、上公差、下公差）
- `sample_cols`: 样品列（1#=H, 2#=I...）
- `field_locations`: 字段位置（品名=D5, 日期=P4）

## 输出文件

运行后生成：
- `{日期}_项目汇总.xlsx` — 各样品实测数据（1#-5# 主表，6#+ Sheet B）
- `标准模板_{日期}_已填描述.xlsx` — 带规格公差的模板

## 依赖

```bash
pip install -r requirements.txt
```

PaddlePaddle 为 CPU 版本（约 200MB）；OCR 模型（约 18MB）打包前运行
`python download_ocr_models.py` 下载到 `models/paddleocr/`。
protobuf 冲突时设置 `set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python`。

## 打包

```bash
build.bat
```

产物 `dist\CMMFiller\`（约 627MB），已做瘦身（剔除 JIT/绘图/训练侧依赖）。
**分发时必须拷贝整个文件夹**（exe 依赖 `_internal` 目录），只拷 exe 会因
模型缺失无法离线识别。
