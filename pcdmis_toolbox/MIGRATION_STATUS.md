# PCDMIS Toolbox 2.0 — 迁移进度跟踪

> 对应 ARCHITECTURE.md 各章节，完成一个阶段更新一次。
> 偏差（Deviation）栏记录实现与原设计的差异及原因。
> 缺陷（Bug）栏记录发现和修复的问题。

---

## Phase 0 — 基础设施骨架 ✅ 完成

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 3.4 主题统一策略 | 写 `utils/theme.py` + 自定义青绿主题 JSON | ✅ | 设计用 `TOOLBOX_THEME` dict + `theme.json` 两种方式；实际只用 `theme.json`（dict 仍保留在 `TOOLBOX_THEME` 常量中供其他模块引用） | 最初 `fg_color` 用 `"transparent"`，CustomTkinter 不认 → 改用父容器背景色；主题缺 19 个 key 中的多个字段 → 参考 `customtkinter/assets/themes/green.json` 补全全部 19 key（`border_width`、`text_color_disabled`、`top_fg_color` 等）|
| 3.5 路径管理 | 写 `utils/paths.py` PathManager | ✅ | 与设计一致 | — |
| 3.6 日志系统 | 写 `utils/logging.py` 含 RotatingFileHandler + GuiLogHandler | ✅ | 与设计一致 | `audit.py` 中 `import utils.logging as ulog` 循环导入 → 改为 `from utils.logging import setup_logging` 本地导入 |
| 3.36 审计日志 | 写 `utils/audit.py` | ✅ | 与设计一致 | 同上循环导入修复 |
| 3.35 错误码体系 | 写 `utils/error_codes.py` ErrorCode + ToolboxError | ✅ | 与设计一致 | — |
| 3.0 依赖分条件安装 | 创建 `requirements/base.txt` | ✅ | 只创建了 `base.txt`；`cmm_filler.txt` 和 `pc_to_excel.txt` 留待 Phase 6 | — |
| 3.8 版本文件统一 | 写 `toolbox/app_meta.py` | ✅ | 与设计一致；`TOOLBOX_THEME` 在 `app_meta.py` 和 `utils/theme.py` 各有一份（重复），后续 Phase 5 统一 | — |
| 3.3 模块接口协议 | 写 `toolbox/protocol.py` | ✅ | ShellProtocol 注入约定在协议中补充了 `shell` 属性声明（ARCH 设计中写在 4.3） | 审查发现 ModuleProtocol 缺 `shell` 属性声明 → 补充 `shell: "ShellProtocol"` |
| 3.47 启动参数入口 | 写 `main.py`（multiprocessing.freeze_support + 64位检测 + 主题单次调用） | ✅ | 与设计一致 | `audit` 函数漏导入导致 `NameError` → 补充导入；`_check_bitness` 在全局命名空间残留 → 加 `del _check_bitness` 清理 |
| — | 写 `toolbox/__init__.py` | ✅ | 无设计说明，自动完成 | — |

**Phase 0 提交:** `9b9319c` — 12 files, 922 insertions

---

## Phase 1 — 壳主窗口 ✅ 完成

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 4.1–4.5 Shell 主窗口 | 写 `toolbox/shell.py` | ✅ | 与设计一致 | `place_forget()` 在 placeholder 已 destroy 后调用 → 删掉该行；`_active_module.__name__` 总是 `"?"` → 加 `_active_module_name` 跟踪当前模块名 |
| 3.40 原子写 | 写 `utils/settings.py` `save_settings_json_atomic()` | ✅ | 与设计一致 | — |
| 3.41 文件锁 | 写 `utils/settings.py` `FileLock` | ✅ | Unix `fcntl` 在 Windows 不可用 → 完全重写为基于 `O_EXCL` 的跨平台实现，不依赖 fcntl | `fcntl` ImportError → 替换为纯 Windows-compatible 实现 |
| 3.9 配置迁移 | 写 `utils/settings.py` `migrate_settings_if_needed()` | ✅ | 与设计一致 | `fcntl` 导入导致 Windows 报 `ModuleNotFoundError` → 移除 fcntl |
| 3.42 线程取消 | 写 `utils/threading_utils.py` `CancellableWorker` | ✅ | 与设计一致 | — |
| 3.43 PDF 句柄泄漏 | 写 `utils/file_io.py` `fitz_open_context()` | ✅ | 与设计一致 | — |
| 3.39 PDF 大小写 | 写 `utils/file_io.py` `glob_pdfs()` | ✅ | 与设计一致 | — |

**Phase 1 提交:** `9b9319c`（与 Phase 0 合并提交）

---

## Phase 2 — 模块注册机制 ✅ 完成

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 11.2 模块注册 | 写 `modules/__init__.py` | ✅ | ARCH 设计是各模块在 `__init__.py` 中显式调用 `register_module`；实际改为 `pkgutil.iter_modules` 自动发现 + 底部 import 执行注册，更自动化 | 审查发现模块加载失败时静默跳过 → 改为 `logger.error` 并附异常信息 |
| 11.2 模块注册 | 写 `modules/cmm_filler/gui.py` + `modules/pc_to_excel/gui.py` stub | ✅ | Phase 1 stub 实现，Phase 3/4 替换为真实迁移 | 同上模块加载失败修复 |

**Phase 2 提交:** `9b9319c`（与 Phase 0-1 合并提交）

---

## Phase 3 — CMMFiller 迁移 ✅ 完成

**Phase 3 提交:** `2c1bef2`（合并 Phase 0-2 提交后新一轮提交）

| 新增/变更文件 | 说明 |
|-------------|------|
| `modules/cmm_filler/__init__.py` | 模块包初始化 |
| `modules/cmm_filler/app_meta.py` | 从 `toolbox.app_meta` 导入版本 |
| `modules/cmm_filler/main.py` | 独立运行入口（含 freeze_support + apply_theme） |
| `modules/cmm_filler/cli.py` | CLI 入口（process/export-template/summary 子命令） |
| `modules/cmm_filler/gui.py` | 完整 GUI（1281行）+ CMMFillerModule 适配层 |
| `modules/cmm_filler/core/__init__.py` | core 包初始化 |
| `modules/cmm_filler/core/filler.py` | 核心逻辑（含 glob_pdfs、fitz_open_context、OCR缓存补全） |
| `modules/cmm_filler/ocr/__init__.py` | ocr 包初始化 |
| `modules/cmm_filler/ocr/engine.py` | PaddleOCR 引擎（含 bootstrap 和多引擎抽象） |
| `modules/cmm_filler/template_wizard.py` | 模板向导（直接从 CMMFiller 复制） |
| `modules/cmm_filler/templates/` | 模板文件（模板1.xlsx、模板2.xlsx） |
| `modules/cmm_filler/models/paddleocr/` | PaddleOCR 模型文件（~18MB） |
| `requirements/cmm_filler.txt` | CMMFiller 专用依赖 |

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 11.3 Phase 3 | 迁移 `cmm_filler_v10.py` → `modules/cmm_filler/core/filler.py` | ✅ | 与设计一致 | — |
| 3.46 相对导入 | 批量改绝对导入为相对导入 | ✅ | `from ocr_engine` → `from ..ocr.engine`；删除 `sys.path.insert` | — |
| 3.46 sys.path 清理 | 删除所有 `sys.path.insert(0, _ROOT)` | ✅ | 原 gui.py 第17行 `sys.path.insert` 已删除；`cmm_filler_v10.py` 无此问题 | — |
| 3.39 PDF 大小写 | `glob('*.PDF')` → `glob_pdfs()` 大小写不敏感 | ✅ | `_scan_and_parse` 和 `export_standard_template` 中的 `sorted(Path(...).glob('*.PDF'))` 全部替换为 `glob_pdfs(Path(...))` | — |
| 3.43 PDF 句柄 | `fitz.open()` → `with fitz_open_context()` | ✅ | `pdf_to_image` 方法改用 `with fitz_open_context()` | **2026-08-26 修复**：`utils/file_io.fitz_open_context` 缺 `@contextmanager` 装饰器，`with` 语句实际抛 `TypeError: generator object does not support the context manager protocol`（每个 PDF 都会处理失败）→ 补装饰器 |
| 3.38 OCR 缓存 | `_cleanup_cache()` 补全 `ocr_cache.json` 按数量清理 | ✅ | 新增 `ocr_cache.json` 按数量清理逻辑（>10000条按字母序删旧） | — |
| 3.45 主题冲突 | 删除 `ctk.set_default_color_theme("blue")` | ✅ | gui.py 顶部的 `ctk.set_default_color_theme("blue")` 调用已删除；保留 `ctk.set_appearance_mode`（由 Shell 统一管理） | — |
| 3.42 线程取消 | `threading.Thread(daemon=True)` → `CancellableWorker` | ✅ | gui.py 中 5 处 `threading.Thread(target=..., daemon=True)` 全部替换为 `CancellableWorker()` + `.start(...)` | — |
| 3.3 模块接口 | 写 `modules/cmm_filler/gui.py` CMMFillerModule | ✅ | 实现 `ModuleProtocol`，含 `mount/unmount/on_activate`；`TkinterDnD` 初始化加条件判断（仅独立窗口模式） | — |
| 3.1 独立入口 | 写 `modules/cmm_filler/main.py` 独立运行入口 | ✅ | 含 `multiprocessing.freeze_support()` + `apply_theme()` | — |
| 3.17 模板向导 | 搬移 `template_wizard.py` → `modules/cmm_filler/template_wizard.py` | ✅ | 直接复制，原样保留（内部使用原生 tkinter，与模块低耦合） | — |
| 3.29 CLI | 写 `modules/cmm_filler/cli.py` | ✅ | 支持 `process`/`export-template`/`summary` 三个子命令 | — |
| 3.8 版本 | 写 `modules/cmm_filler/app_meta.py` 从 toolbox 导入 | ✅ | 从 `toolbox.app_meta` 导入 `APP_VERSION` | — |
| — | 搬移 `templates/`、`models/paddleocr/` | ✅ | 模板2个 + PaddleOCR 模型（~18MB）完整复制 | — |
| — | 写 `requirements/cmm_filler.txt` | ✅ | 含 tkinterdnd2、pymupdf、paddlepaddle、paddleocr | — |

---

## Phase 4 — pc_to_excel 迁移 ✅ 完成

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 11.3 Phase 4 | 搬移 `core/`、`connector/`、`export/`、`inject/` | ✅ | 与设计一致 | — |
| 3.46 相对导入 | 批量改绝对导入为相对导入 | ✅ | `from connector.base` → `from .base`；`from config` → `from ..app_meta`；`from utils.admin` → 相对导入（4 连点 `....utils.*` 后被复查统一为 0 连点，见下一行） | `utils/settings.py` 重命名为 `utils/local_settings.py` 避免与 toolbox 层冲突 |
| 3.46 相对导入（复查） | — | ✅ | — | **2026-08-26 修复 9 处迁移后导入缺陷**：`connector/base.py:8`（`from core.models` 绝对导入，阻塞全部测试收集）、`com_detector.py:13/180/192`（`from app_meta`/`from utils.admin`，权限检测被 try/except 吞掉静默失效）、`main_window.py:30`（`...utils.admin` 三连点指向 `modules.utils`）、`cmm_filler/gui.py:16/17/18`（`..core.filler`/`..app_meta` 层级错、`utils.settings` 无 load_settings）、`cmm_filler/cli.py:14`、5 个文件 4 连点导入（`....utils.*`）与全树 0 连点约定互斥 → 全部改为相对导入 |
| 3.3 模块接口 | 写 `modules/pc_to_excel/gui.py` PCToExcelModule | ✅ | 实现 `ModuleProtocol`，含 `mount/unmount/on_activate`；`on_activate` 刷新 PCDMIS 连接状态 | **2026-08-26 修复**：适配层 `gui.py` 与 `gui/` 包同名冲突（包优先），`PCToExcelModule` 成死代码、pc_to_excel 永不注册进 Shell → 适配层改名 `module.py`，`modules/__init__.py` 发现逻辑支持 `gui.py`/`module.py` 双入口；`on_activate` 改为静默刷新（原直接 `_connect` 每次切模块弹"连接失败"框） |
| 3.46 sys.path 清理 | 删除所有 `sys.path.insert` | ✅ | 原 `main.py`/`cli.py`/`gui/main_window.py` 及各子模块的 `sys.path.insert(0, ...)` 已全部删除 | — |
| 3.35 错误码接入 | `format_user_error` 改为接收 `ToolboxError` | ✅ | `action_hints.format_user_error` 签名改为 `exc: BaseException \| str \| ToolboxError`，新增 `ToolboxError` 分支提取 `[code] message` 格式 | — |
| 3.42 线程取消 | 所有 `daemon=True` → `CancellableWorker` | ✅ | `gui/main_window.py` 中 5 处 `threading.Thread(target=work, daemon=True)` 全部替换为 `CancellableWorker().start(work)` | — |
| 3.45 主题冲突 | 删除 `ctk.set_default_color_theme("green")` | ✅ | `gui/main_window.py` 第36行 `ctk.set_default_color_theme("green")` 已删除 | — |
| 3.1 独立入口 | 写 `modules/pc_to_excel/main.py` | ✅ | 独立 GUI 入口含权限检测 | — |
| 3.8 版本 | 写 `modules/pc_to_excel/app_meta.py` | ✅ | 从 `toolbox.app_meta` 导入 `APP_VERSION`；`PROG_ID_CANDIDATES`/`DEFAULT_TOLERANCE`/`EXPORT_CMD_ID`/`OBTYPE_BASIC_SCRIPT` 等常量迁入 | — |
| 3.29 CLI | 写 `modules/pc_to_excel/cli.py` | ✅ | 支持 `export`/`fill-form`/`inject` 三个子命令 | — |
| 3.7 BAS 脚本 | 搬移 `scripts/export_current.bas` | ✅ | 复制 `export_current.bas` + `export_current.bas.template` | — |
| 3.14 admin 启动器 | `run_as_admin.bat` 整合 | ⏳ | 待 Phase 6（打包阶段）整合 | — |
| — | 写 `requirements/pc_to_excel.txt` | ✅ | 含 pywin32 | — |
| — | 挂载生命周期修复 | ✅ | — | **2026-08-26 修复**：`MainWindow._on_close` 无守卫 `root.destroy()`，挂载模式切模块会关掉整个 Shell → 加 `if self._owns_root` 守卫（保存设置/断开 COM 保留） |
| 3.7 BAS 部署 | 搬移 `scripts/` | ✅ | — | **2026-08-26 修复**：`deploy_bas_script` 部署到 `.../scripts/scripts/` 双重目录（`paths.bas_deploy_dir` 已含 scripts 段）→ 去掉重复段；`_bundled_bas_source` dev 模式搜 `root/scripts` 找不到（脚本在 `modules/pc_to_excel/scripts/`）→ 补搜索根 |
| 3.35 错误码接入（补充） | 裸 `RuntimeError` → `ToolboxError` | ✅ | 2026-08-26 补充：`pcdmis_connector`（E2001/E2002/E2004）、`com_detector.dispatch_pcdmis`（E2002）、`command_injector` 占位符缺失（E5001）、main_window 导出/填入 0 条（E2004）替换为 ToolboxError；`data_extractor` 内部保留（核心 pipeline，由 connector 捕获后包装）；root `utils/error_codes.format_user_error` 补关键字回退；`cmm_filler/ocr/engine.py` 模型缺失（E1003） | — |

---

## Phase 5 — 配置迁移 ✅ 完成（2026-08-26）

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 3.9 基础迁移 | `migrate_settings_if_needed()` 首次启动时调用 | ✅ | 2026-08-26 接线：cmm_filler 路径统一到 `config_dir/cmm_filler`（settings.json + template_config.json 旧路径 `data/cmm_filler` 自动迁移，旧文件改 `.bak`）；template_wizard 残留的 `%LOCALAPPDATA%/CMMFiller` 路径同步清理 | — |
| 3.9.1 版本升级 | 所有 settings.json 加 `_version` 字段 | ✅ | 2026-08-26：main.py 启动时 `_migrate_module_settings()` 调用 `load_and_migrate_settings` 写入 | — |
| 3.9.1 迁移函数 | `migrate_cmm_filler_1_0_to_2_0()` + `migrate_pc_to_excel_1_4_to_2_0()` | ✅ | 2026-08-26 实现并注册；迁移链改为「每个 from_version 一次性升到当前 schema」（原 `_next_version` 末段+1 步进在缺中间版本时抛 RuntimeError） | — |
| 3.9.1 迁移主流程 | `load_and_migrate_settings()` 含备份 + 升级 | ✅ | 无 `_version` 字段的旧文件按模块默认旧版本（1.0.0 / 1.4.5）走迁移；备份 `.v{from}.bak`（with_suffix 替换原后缀：cmm.json → cmm.v1.0.0.bak） | **2026-08-26 修复**：迁移函数缺失时抛裸 `RuntimeError` → `ToolboxError(ErrorCode.CONFIG_MIGRATION_FAIL, E6002)` |
| 3.9.2 降级导出 | `export_legacy_settings()` | ✅ | 2026-08-26：Shell 顶栏「导出旧版配置」按钮，每模块导出单独文件（legacy_settings_{module}.json）；cmm_filler 分支改为按顶层字段导出 | — |
| — | 合并 `toolbox/app_meta.py` 和 `utils/theme.py` 的 `TOOLBOX_THEME` 重复定义 | ✅ | 2026-08-26：app_meta.py 改为 `from utils.theme import TOOLBOX_THEME`，utils/theme.py 为唯一定义点 | — |

---

## Phase 5.5 — 应用层修复 ✅ 完成（2026-08-26）

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 3.40 原子写 | 替换所有 `json.dump` 直接写 → `save_settings_json_atomic` | ✅ | 2026-08-26：filler.py×3、template_wizard、local_settings、command_injector×2、export_legacy_settings；新增 `utils/file_io.atomic_write_text` 通用原子文本写 | — |
| 3.41 文件锁 | Shell 启动时检测并发（`FileLock`） | ✅ | 2026-08-26：main.py `_acquire_instance_lock()` 启动检测，超时 5s 弹窗询问是否启动第二个 | — |
| 3.38 OCR 缓存 | 补全 `ocr_cache.json` 按数量清理 | ✅ | Phase 3 已落地（filler.py `_cleanup_cache` >10000 条按字母序删旧） | — |
| 3.39 PDF 大小写 | CMFiller `glob('*.PDF')` 修复 | ✅ | Phase 3 已落地（glob_pdfs 大小写不敏感） | — |
| 3.43 PDF 句柄 | 所有 `fitz.open()` 改 `with` 形式 | ✅ | Phase 3 已落地；2026-08-26 补 `@contextmanager` 装饰器使其真正可用 | — |
| 3.42 线程取消 | 所有 `daemon=True` → `CancellableWorker` | ✅ | 2026-08-26：filler 4 处取消点（cancel_check 回调）+ GUI 5 处 worker 引用维护、关闭/卸载时 `request_cancel`+`wait(5)` | — |
| 3.45 主题统一 | Shell 主入口调一次 `set_default_color_theme`，模块内删除 | ✅ | Phase 0-1 已落地 | — |
| 3.42 atexit | `atexit.register(cleanup_on_exit)` | ✅ | Phase 0 已落地（main.py 清理 *.tmp.pdf + logging.shutdown） | — |
| 3.6 日志落盘 | CMMFiller / pc_to_excel logger 接文件 handler | ✅ | 2026-08-26：CMMFiller：`main.py` + `cmm_filler/main.py` 初始化 `setup_logging("CMMFiller")`；gui.py「查看日志」路径对齐大小写 `CMMFiller.log`（原 `cmm_filler.log` 读不到）。**pc_to_excel 补**：`main.py` + `pc_to_excel/main.py` 初始化 `setup_logging("pc_to_excel")`；`main_window.py` 5 个 work except 处加 `logger.exception`（填入/填入写入/导出/部署/植入），连接/导出/植入/部署异常均有完整堆栈落到 `pc_to_excel.log` | — |
| 3.36 审计日志分离 | audit logger 不冒泡 + 普通 logger 不挂 audit handler | ✅ | 2026-08-26：`setup_logging` 移除 TimedRotatingFileHandler（不再给普通 logger 挂 `{name}.audit.log`，该文件名误导实际装的是普通日志按天副本）；`setup_audit_logging` 独立挂专用 handler（写 `toolbox.audit.audit.log`）+ 设 `propagate=False`。效果：audit() 只写专用 audit 文件；普通日志不混入 audit；CMMFiller 日志不污染 toolbox 日志 | — |

---

## Phase 6 — 打包整合 ⏳ 待做

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 3.0 依赖拆分 | 创建 `requirements/cmm_filler.txt` + `requirements/pc_to_excel.txt` | ✅ | 已于 Phase 3/4 创建（base.txt / cmm_filler.txt / pc_to_excel.txt） | — |
| 3.10 PyInstaller spec | 合并 spec | ⏳ | — | — |
| 3.11 fix_dist.py | 搬移 `fix_dist.py` → `build/`，加 `PATCH_MARKER` | ⏳ | — | — |
| 3.13 自定义 Hooks | 搬移 `hooks/` → `build/hooks/` | ⏳ | — | — |
| 3.28 Inno Setup | 写 `installer/PCDMIS_Toolbox.iss` | ⏳ | — | — |
| — | 写 `build.bat` | ⏳ | — | — |

---

## Phase 7 — 保留独立入口 ⏳ 待做

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 4.4 独立入口兼容 | `CMMFiller/cmm_filler_gui.py` → 重定向到 `modules.cmm_filler` | ⏳ | — | — |
| 4.4 独立入口兼容 | `pc to excel/main.py` → 重定向到 `modules.pc_to_excel` | ⏳ | — | — |
| 3.18 用户文档 | 写 `pcdmis_toolbox/README.md` | ⏳ | — | — |
| 3.31 CLAUDE.md | 写 `pcdmis_toolbox/CLAUDE.md` | ⏳ | — | — |

---

## Phase 8 — 测试 ⏳ 待做

| 任务 | 状态 |
|------|------|
| CMMFiller 独立运行 `python -m modules.cmm_filler` | ⏳ |
| pc_to_excel 独立运行 `python -m modules.pc_to_excel` | ⏳ |
| Toolbox 集成运行 `python main.py` | ⏳ |
| CMMFiller OCR 测试（samples/） | ⏳ |
| PCDMIS 连接（admin 模式） | ⏳ |
| 异常处理 crash.log 验证 | ⏳ |
| 原子写验证（kill 中途模拟） | ⏳ |
| 文件锁验证（同时启动两个） | ⏳ |
| 配置迁移验证（旧 settings → 新路径） | ⏳ |
| 配置版本升级链验证 | ⏳ |
| 降级导出验证 | ⏳ |

---

## ARCHITECTURE.md 偏差记录

| 章节 | 原设计 | 实际实现 | 原因 |
|------|--------|---------|------|
| 3.4 主题自定义路径 | `utils/theme.py` TOOLBOX_THEME 常量 | 完整自定义 JSON 主题（19 key，基于 green 字段表） | CustomTkinter 对主题字段要求严格，需完整实现所有 key |
| 3.41 文件锁 | 使用 `fcntl` | 基于 `O_EXCL` 跨平台实现 | `fcntl` 仅 Unix，Windows 不兼容 |
| 2 目录结构 | 仅有框架描述 | 新增 `utils/__init__.py` 统一导出 | 便于 `from utils import *` 批量导入 |
| 3.6 日志 | GuiLogHandler 设计 | 与设计一致 | — |
| 3.3 协议 | ModuleProtocol + ShellProtocol | 补充 `shell` 属性到 ModuleProtocol | 代码审查发现接口不完整 |
| 11.2 模块注册 | 各模块显式调用 `register_module` | pkgutil 自动发现 + import 执行注册 | 更自动化，减少模块维护负担 |
| 六 适配层命名 | `modules/pc_to_excel/gui.py` 适配层 + `gui/` 子包 | 适配层改名 `module.py`，发现逻辑支持双入口 | `gui.py` 与 `gui/` 包同名冲突，包优先导致适配层死代码、模块永不注册（2026-08-26 发现并修复） |
| 3.9.1 迁移链 | `_next_version` 末段+1 链式步进 | 每个 from_version 一次性升到当前 schema | 链式依赖注册表连续键，缺中间版本抛 RuntimeError（2026-08-26 调整） |
| 3.46 导入根 | `....utils.*` 指向 toolbox 层 | 统一 0 连点（`from utils.paths import paths`） | 4 连点在 `modules` 为顶级包时越界，与 `main.py`/`cmm_filler` 的 0 连点约定互斥（2026-08-26 统一） |
