# Changelog — PCDMISToolbox

所有版本升级记录。格式：`## [版本] — 日期`，按模块分小节，方便追踪每个模块的变更。

---

## [未发布] — 2026-08-27

### CMMFiller 模块

**代码审查修复（2026-08-27）**

- `core/filler.py` **P0**: `bare except:` 静默吞噬数字解析异常 → 改为 `except (ValueError, TypeError)` + `logger.debug`
- `core/filler.py` **P0**: OCR 缓存 key 从 basename 改为完整路径 MD5，解决不同路径同名 PDF 互相覆盖的问题
- `core/filler.py` **P0**: 行号上限 buffer 从 +5 增至 +50；新增 `_compute_required_max_row()` 动态取所有 PDF 的最大测量编号，batch 时自动扩展上限，不再截断有效数据
- `gui.py` **P0**: mount 模式下 `self.root` 改为统一指向 CTk window（`parent.winfo_toplevel()`），`_container` 指向挂载 Frame；消除 unmount 时 `winfo_children()` 误删 Shell 子窗口的问题
- `gui.py` **P2**: `TkinterDnD._require()` 失败时写 WARNING 日志，不再静默降级
- `core/filler.py` **P2**: `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION` 从模块顶层移除，改为 `ocr/engine.py` 的 `PaddleOCREngine.__init__()` 局部 `setdefault`，不再污染全局进程
- `core/filler.py` **P1**: 日期解析从单一中文格式扩展为 4 种（ISO `2024-01-02`、分隔符 `2024/01/02`、中文年月日 `2024年1月2日`、中文月份名 `十二月 2, 2024`）
- `template_wizard.py` **P1**: 样品序号匹配格式（`'1#'`/`'NO.1'`/`'No.1'`/`'no.1'`）与 `filler.py _auto_detect_template` 拉齐，解决向导自动检测失败的问题
- `template_wizard.py` **P3**: Combobox 绑定 `<<ComboboxSelected>>` 回调中 `int(var.get())` 包裹 `try/except (ValueError, TclError)`，防止非整数输入崩溃
- `core/filler.py` **Bugfix**: 修复日期多格式正则修改时遗留的 regression（解析成功后仍误 append `warnings`）
- `core/filler.py` **Cleanup**: 移除未使用的 `from abc import ABC, abstractmethod` 导入

**文档更新**
- `ARCHITECTURE.md`: PROTOCOL_BUFFERS 描述更新为 engine 局部 setdefault；Tkdnd 初始化逻辑更新；wizard.py 路径修正
- `CLAUDE.md`: PROTOCOL_BUFFERS 注释同步更新；TkinterDnD 描述更新
- `README.md`: PROTOCOL_BUFFERS 不再列为 main.py 必要配置
- `MIGRATION_STATUS.md`: PROTOCOL_BUFFERS 清单项更新

---

## [1.0.0] — 2026-08-26

> 首个整合版本。CMMFiller + pc_to_excel 合并为统一工具箱，支持 Shell 挂载模式和独立运行。

### 整体
- 新增 `pcdmis_toolbox/` 主目录，统一管理两个模块
- `ModuleProtocol` 抽象：各模块实现 `mount()`/`unmount()`/`on_activate()`，支持 Shell 动态挂载
- 新增 `toolbox/shell.py`（Shell 主窗口）、`toolbox/settings_dialog.py`（设置）、`toolbox/about_dialog.py`（关于）
- 统一日志：`utils/logging.py` 替代各模块自行配置；审计日志 `utils/audit.py`
- 统一主题：`utils/theme.py` 管理 dark/light 切换
- 统一路径：`utils/paths.py`（PathManager）区分 frozen/dev 模式，资源文件统一从 bundle 加载

### CMMFiller 模块
- 从旧项目 `CMMFiller/` 迁移至 `modules/cmm_filler/`
- 相对导入全部改为模块内绝对路径
- PDF glob 从 `glob('*.PDF')` 改为大小写不敏感 `suffix.lower() == '.pdf'`
- PDF 句柄泄漏：`fitz.open()` 全部改为 `fitz_open_context()` 上下文管理器
- OCR 缓存清理：`_cleanup_cache()` 新增按数量限制（>10000 条按字母序删旧）
- 原子写：所有 `json.dump` 直接写改为 `save_settings_json_atomic()`
- 线程取消：`CancellableWorker` 替代 bare `threading.Thread`
- 模板向导从 `wizard.py` 迁至 `template_wizard.py`

### pc_to_excel 模块
- 独立入口 `main.py` 保留（Shell 集成用新入口 `shell.py`）
- `utils/paths.py` 接管所有路径逻辑，废弃 `toolbox/__init__.py` 中的旧路径
- BAS 脚本重定向：frozen 模式下 `BAS_DEPLOY_DIR` 改为 `%LOCALAPPDATA%/PCDMIS_ExcelExporter/scripts`

### 打包
- PyInstaller `build.spec`：新增 `dist/cm2xl/` onefile 模式
- `build/fix_dist.py` 后处理：搬移完整 paddleocr 源码，patch 4 个文件（archive 加载问题）
- Inno Setup 7 安装包：`installer/output/cm2xl_Setup_1.0.0.exe`，支持卸载
