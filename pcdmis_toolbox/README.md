# PCDMIS Toolbox 2.0

> 整合 `CMMFiller`（CMM 报告 OCR 识别 + Excel 自动填充）和 `pc_to_excel`（PCDMIS 数据提取 + 公差判定 + 报告导出）两个独立工具的**统一工具箱**，同时保留各模块独立运行能力。

![Architecture](preview/index.html)（启动本地 HTTP 服务 `python -m http.server 8765` 在 `preview/` 目录查看 UI 修复对比预览）

---

## 快速开始

### 开发模式

```bash
# 安装依赖（拆分安装：base + 模块可选）
pip install -r requirements/base.txt
pip install -r requirements/cmm_filler.txt   # CMMFiller 模块
pip install -r requirements/pc_to_excel.txt  # pc_to_excel 模块

# 启动 Toolbox 集成模式
cd pcdmis_toolbox
python main.py

# 启动各模块独立模式
python -m modules.cmm_filler
python -m modules.pc_to_excel
```

### 打包（测量房离线部署）

```bash
cd pcdmis_toolbox

# Step 1: PyInstaller 打包（10-20 分钟）
build.bat
# 产物：dist/PCDMIS Toolbox/PCDMIS Toolbox.exe

# Step 2: 生成安装包（需先安装 Inno Setup 6）
build_installer.bat
# 产物：installer/output/PCDMIS Toolbox_Setup_2.0.0.exe
```

打包前确保：
- `CMMFiller/models/paddleocr/` 已下载 OCR 模型（`inference.pdmodel` 文件存在）
- 安装了 `customtkinter`、`paddlepaddle==2.6.2`、`paddleocr==2.10.0` 等依赖

---

## 目录结构

```
pcdmis_toolbox/
├── main.py                       # Toolbox 统一入口
├── pcdmis_toolbox.spec           # PyInstaller 打包规格
├── build.bat / build_installer.bat
├── installer/Toolbox.iss         # Inno Setup 安装脚本
├── preview/index.html            # UI 修复对比预览（开发辅助）
├── scripts/export_current.bas*   # PCDMIS BAS 脚本模板
├── requirements/
│   ├── base.txt                  # GUI / Excel / PyInstaller
│   ├── cmm_filler.txt            # OCR + PDF 渲染
│   └── pc_to_excel.txt           # pywin32 COM
├── toolbox/                      # Shell + 协议 + 元数据
│   ├── shell.py                  # 主窗口（顶栏/侧栏/状态栏）
│   ├── protocol.py               # ModuleProtocol + ShellProtocol
│   └── app_meta.py               # APP_TITLE / APP_VERSION
├── modules/                      # 功能模块（pkgutil 自动发现）
│   ├── cmm_filler/               # OCR 报告填充
│   │   ├── main.py               # 独立入口
│   │   ├── gui.py                # 适配层（含 CMMFillerModule + register_module）
│   │   ├── core/filler.py        # 报告填充逻辑
│   │   └── ocr/engine.py         # PaddleOCR 引擎
│   └── pc_to_excel/              # PCDMIS 数据导出
│       ├── main.py               # 独立入口
│       ├── module.py             # 适配层（含 PCToExcelModule + register_module）
│       ├── gui/main_window.py    # 主窗口
│       ├── connector/            # PCDMIS COM 适配
│       ├── core/                 # 数据提取 + 公差判定
│       ├── export/               # Excel 报告导出
│       ├── inject/               # PCDMIS 命令植入
│       └── utils/                # admin 权限 / 本地配置
├── utils/                        # 通用工具
│   ├── paths.py                  # 路径管理（frozen/dev）
│   ├── theme.py                  # 主题常量 + theme.json 生成
│   ├── theme.json                # CustomTkinter 主题（打包进 _internal/）
│   ├── logging.py                # 日志（含 GuiLogHandler）
│   ├── audit.py                  # 审计日志
│   ├── error_codes.py            # ErrorCode + ToolboxError
│   ├── settings.py               # 原子写 + FileLock + 迁移
│   ├── threading_utils.py        # CancellableWorker
│   └── file_io.py                # glob_pdfs + fitz_open_context
└── data/                         # 用户数据（运行时创建）
    ├── config/cmm_filler/        # 模块配置
    ├── logs/                     # 日志
    └── cache/                    # 临时缓存
```

---

## 核心模块

### `toolbox/shell.py` — Shell 主窗口

实现 `ShellProtocol`：
- 顶栏：标题 + "导出旧版配置"按钮
- 左侧导航栏：自动发现 `modules/` 下所有注册的模块
- 内容区：当前激活模块的 GUI
- 状态栏：PCDMIS 连接状态 + 模块名 + 消息

### `modules/__init__.py` — 模块注册表

使用 `pkgutil.iter_modules` 自动发现 `modules/<name>/` 子包，对每个子包：
1. 优先 `module.py`（含 `register_module` 的适配层）
2. 再尝试 `gui.py` / `gui/` 子包（GUI 实现）

注册后通过 `from modules import REGISTRY` 获取。

### `utils/theme.py` — 主题系统

- `TOOLBOX_THEME` dict：颜色常量
- `_build_theme_json()`：生成 CustomTkinter 主题 JSON（含 CTkFont 三平台段 + weight）
- `apply_theme()`：启动时调用一次

**关键约束**（避免 GUI 渲染问题）：
- `CTkLabel.fg_color` 必须为 `"transparent"`，否则文字后会有色块
- `CTkFont` 每个平台段都必须含 `"weight": "normal"`，否则 `KeyError('weight')`

---

## 模块开发指南

### 添加新模块

1. 创建 `modules/<name>/__init__.py`（可空）
2. 创建 `modules/<name>/main.py`（独立运行入口，可选）
3. 创建 `modules/<name>/gui.py` 或 `module.py`：
   ```python
   from modules import register_module

   class MyModule(ModuleProtocol):
       title = "我的模块"
       icon = "🛠️"
       version = "1.0.0"

       def mount(self, parent): ...
       def unmount(self): ...
       def on_activate(self): ...

   register_module("my_module", MyModule())
   ```
4. 启动 `python main.py` ——新模块自动出现在侧栏

### 独立运行模式

每个模块支持独立窗口运行（无 Shell），便于调试：
```bash
python -m modules.cmm_filler    # 仅 CMM 报告填充
python -m modules.pc_to_excel   # 仅 PCDMIS 导出
```

适配层 (`CMMFillerGUI`、`MainWindow`) 通过 `__init__(parent=None)` 参数区分模式：
- `parent=None`：自建 `ctk.CTk()` 根窗口
- `parent=Frame`：挂载到 Shell 的内容区

---

## 离线部署约束（测量房无网）

参见 [offline-deployment-constraints.md](../ARCHITECTURE.md#离线部署约束)。

关键点：
1. **打包后体积 600-700 MB**：PaddlePaddle ~200MB + cv2/lmdb/lxml ~150MB + PaddleOCR 模型 18MB
2. **PaddleOCR 模型**：必须预下载到 `CMMFiller/models/paddleocr/`，打包进 `_internal/models/paddleocr/`
3. **环境变量**（`main.py` 顶部）：
   ```python
   os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
   ```
4. **multiprocessing.freeze_support()**：必须在所有 import 之前
5. **PyInstaller 后处理**：`build/fix_dist.py` 复制完整 paddleocr + patch 4 个文件

---

## 常见问题

### `加载失败: 'weight'` 错误

`utils/theme.json` 缺 `CTkFont.weight` 键。修法：
```python
# utils/theme.py:_build_theme_json()
"CTkFont": {
    "macOS":   {"family": "SF Pro",   "size": 13, "weight": "normal"},
    "Windows": {"family": "Segoe UI", "size": 13, "weight": "normal"},
    "Linux":   {"family": "Ubuntu",   "size": 13, "weight": "normal"},
}
```

### 模块不显示

打包后 `modules/` 子包在 `_internal/` 没有 `__init__.py`（PyInstaller 默认只抽外部依赖）。修法：spec 的 `datas` 列表里显式加 `modules/**/__init__.py`。

### 打包后体积过大

`dist/PCDMIS Toolbox/_internal/cv2/opencv_videoio_ffmpeg*.dll` 占 58MB，OCR 永远不用。build.bat 已自动清理。

### 中文路径报错

不要将工具放在含空格或中文路径下。BAS 脚本部署路径也禁含空格（PCDMIS Basic 解释器限制）。

---

## 迁移进度

| Phase | 内容 | 状态 |
|-------|------|------|
| 0 | 基础设施骨架（utils/toolbox/modules 初始化） | ✅ |
| 1 | Shell 主窗口 | ✅ |
| 2 | 模块注册机制 | ✅ |
| 3 | CMMFiller 模块迁移 | ✅ |
| 4 | pc_to_excel 模块迁移 | ✅ |
| 5 | 配置迁移 + 原子写 + 文件锁 | ✅ |
| 5.5 | 错误码 + 审计全覆盖 | ✅ |
| 6 | 打包整合（spec / hooks / fix_dist / Inno Setup） | ✅ |
| 7 | 旧入口重定向 + README + CLAUDE.md | ✅ |
| 8 | 测试（独立运行 + 集成运行 + 异常路径） | ⏳ |

详细进度参见 [`MIGRATION_STATUS.md`](MIGRATION_STATUS.md)。

---

## 版本

`2.0.0` —— Phase 7 完成 2026-08-27

定义在 [`toolbox/app_meta.py`](toolbox/app_meta.py)。