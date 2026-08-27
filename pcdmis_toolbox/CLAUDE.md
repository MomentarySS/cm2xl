# CLAUDE.md

> 给 AI 编码助手的项目指南 —— cm2xl

## 项目速览

整合两个原独立项目为统一工具箱：
- **CMMFiller**（CMM 三坐标测量报告 OCR 识别 + Excel 自动填充）
- **pc_to_excel**（PCDMIS 数据提取 + 公差判定 + Excel 报告导出）

**核心架构**：左侧导航 Shell + 可切换的功能模块。每个模块既能挂载到 Shell 集成运行，也能独立窗口运行（开发/调试用）。

---

## 开发约定

### Python 环境
- **必须 64-bit Python 3.12+**（PC-DMIS 2026+ 是 64 位应用）
- 主要依赖：`customtkinter`、`paddlepaddle==2.6.2`、`paddleocr==2.10.0`、`pymupdf`、`openpyxl`、`pywin32`、`tkinterdnd2`

### 导入路径
- 本项目所有包用**0 连点**导入（`from utils.paths import paths`，`from toolbox.shell import Shell`）
- **不要**用 4 连点 `from ....utils.*` —— 在 `modules` 作为顶级包时会越界

### 启动顺序（`main.py` 顶部）
```python
import multiprocessing
multiprocessing.freeze_support()             # PyInstaller 多进程必需
# 此后才 import customtkinter / paddleocr / tkinterdnd2
```
`PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION` 由 `modules/cmm_filler/ocr/engine.py` 的 `PaddleOCREngine.__init__()` 局部设置（`setdefault`），不再需要 main.py 全局设置。

### 主题
- **`apply_theme()` 只在 `main.py` 启动最早处调用一次**
- 各模块**禁止**再调 `ctk.set_default_color_theme` 或 `set_appearance_mode`
- 颜色常量统一从 `utils.theme.TOOLBOX_THEME` 取，**不要硬编码**
- **不要**自己调 `_build_theme_json()` —— 由 `apply_theme()` 自动管理

### 模块适配层
每个模块适配层（`gui.py` 或 `module.py`）必须：
```python
from modules import register_module  # 在文件底部
register_module("<module_name>", ModuleClass())
```

### PCDMIS 数据提取核心（已拆分，2026-08-27）
`modules/pc_to_excel/core/data_extractor.py` 曾是 1940 行的 god-file，已拆成：
`data_extractor.py`（入口，仅组合 + re-export）+ `_common.py` + `_command_cache.py` +
`_dimension.py` + `_tolerance.py` + `feature.py` + `_datum.py` + `classification.py`。

- **新增函数请按职责放到对应子模块，不要再塞回 `data_extractor.py`**
- `extract_from_application()` 签名冻结（`pcdmis_connector` 依赖），共享工具放 `_common.py` 避免循环导入
- COM 常量用 `get_const(name, prog_id=None, default=None)`；显式透传 `prog_id` 优先，data_extractor 内部回退到 `_ACTIVE_PROG_ID`（由 `PcdmisConnector.connect()` 的 `set_active_prog_id()` 写入）

### 资源清理
- PDF 句柄：用 `utils.file_io.fitz_open_context()` 上下文管理器
- 工作线程：用 `utils.threading_utils.CancellableWorker`，`daemon=True`
- 配置写：用 `utils.settings.save_settings_json_atomic()` 原子写 + `FileLock`

---

## 关键文件速查

| 关注点 | 文件 |
|--------|------|
| 启动入口 | `pcdmis_toolbox/main.py` |
| 主窗口布局 | `toolbox/shell.py` |
| 模块注册 | `modules/__init__.py` |
| 主题常量 | `utils/theme.py`（dict）+ `utils/theme.json`（CustomTkinter） |
| 配置管理 | `utils/settings.py`（原子写、文件锁、迁移） |
| 错误码体系 | `utils/error_codes.py` |
| 审计日志 | `utils/audit.py` |
| 路径管理 | `utils/paths.py` |
| 模块接口协议 | `toolbox/protocol.py` |
| PCDMIS 数据提取（已拆分） | `modules/pc_to_excel/core/`（`data_extractor.py` 入口 + `_common`/`_command_cache`/`_dimension`/`_tolerance`/`feature`/`_datum`/`classification`） |

---

## ⚠️ 高频踩坑点（重要）

### 1. CTkLabel 必须透明
```python
# theme.json 中
"CTkLabel": {
    "fg_color": "transparent",  # 不要设为 page_bg，否则文字后有色块
    ...
}
```

### 2. CTkFont 必须含 weight
```python
# theme.json 中
"CTkFont": {
    "macOS":   {"family": "SF Pro",   "size": 13, "weight": "normal"},
    "Windows": {"family": "Segoe UI", "size": 13, "weight": "normal"},
    "Linux":   {"family": "Ubuntu",   "size": 13, "weight": "normal"},
}
```
漏掉 `"weight"` → `KeyError('weight')` 状态栏红字

### 3. PyInstaller 不抽本地 __init__.py
外部依赖（cv2/paddleocr）的 `__init__.py` 会自动抽到 `_internal/`，但**本地项目**的 Python 包文件留在 PYZ 归档里。`pkgutil.iter_modules` 扫文件系统找不到子包 → 模块发现失效。

修法：spec `datas` 显式加：
```python
("modules/__init__.py", "modules"),
("modules/cmm_filler/__init__.py", "modules/cmm_filler"),
("modules/pc_to_excel/__init__.py", "modules/pc_to_excel"),
# ... 所有子包
```

### 4. _discover_modules 不能依赖文件系统检查
```python
# 错（打包后 gui.py 不在磁盘上）
entry = "gui" if (pkg_path / name / "gui.py").is_file() else "module"

# 对（用 try-import）
for entry in ("module", "gui"):
    try:
        importlib.import_module(f"modules.{name}.{entry}")
        break
    except ModuleNotFoundError:
        continue
```

### 5. tkinterdnd2 必须显式 _require
`TkinterDnD._require()` 在**两种模式**（独立 + 挂载）下都必须调用；失败时写 WARNING 日志，但不会中断启动。

```python
# cmm_filler/gui.py
try:
    self.root.TkdndVersion = TkinterDnD._require(self.root)
except Exception as e:
    logging.getLogger('CMMFiller').warning(f'TkinterDnD 初始化失败，拖放功能将不可用: {e}')
```

> 注意：挂载模式下 `self.root` 必须指向 CTk window（`parent.winfo_toplevel()`），禁止在 Shell 层初始化。

### 6. theme.json 必须打包
spec `datas` 列表里加：
```python
("utils/theme.json", "utils"),
```
否则冷启动重新生成，可能丢失关键字段。

### 7. 不在 status_bar 用红字 error
`Shell.update_status(text, level)` 的 `level="error"` 显示红色。打包后第一个模块 mount 失败时这个红色会被用户看到且难以关闭。任何模块 mount 都要 try/except。

---

## 工作流程建议

1. **修改前先排查**：用 `python -c "import modules; print(modules.REGISTRY.keys())"` 验证模块发现
2. **先 dev 验证**：所有改动先在 dev 模式测一遍，再打包
3. **打包前清缓存**：删除 `utils/theme.json`、`data/logs/`、`data/config/`，避免脏缓存
4. **打包后真机测**：必须跑 `dist/cm2xl/cm2xl.exe`（不是 `python main.py`）才算验证
5. **dev 模式没色块 ≠ 打包后没色块**：很多 GUI 问题只在 frozen exe 出现

---

## 调试技巧

### 查看 frozen 模式日志
```bash
# 启动 exe 后
cat "dist/cm2xl/data/logs/toolbox.log"

# 或运行中实时
tail -f "dist/cm2xl/data/logs/toolbox.log"
```

### 复现打包后问题
```bash
# 1. 清缓存
rm -rf dist/ build/ "dist/cm2xl/data"

# 2. 重新打包
cd pcdmis_toolbox
python -m PyInstaller pcdmis_toolbox.spec --noconfirm
python build/fix_dist.py
find dist -name "opencv_videoio_ffmpeg*.dll" -delete

# 3. 启动
"./dist/cm2xl/cm2xl.exe"
```

### 强制重新生成 theme.json
```bash
rm utils/theme.json
python -c "from utils.theme import _build_theme_json; _build_theme_json()"
```

---

## Phase 状态

| Phase | 状态 |
|-------|------|
| 0–6 | ✅ 完成 |
| 7 | ✅ 完成（README + CLAUDE.md + 旧入口重定向） |
| 7.5 | ✅ 完成（设置 + 关于对话框，外观/OCR模型/日志级别） |
| 8 | ✅ 完成（100 tests passed；GUI/OCR/PCDMIS 需人工真机验证） |

详细参见 `MIGRATION_STATUS.md`。