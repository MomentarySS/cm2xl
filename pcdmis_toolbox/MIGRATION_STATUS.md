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

## Phase 3 — CMMFiller 迁移 ⏳ 待做

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 11.3 Phase 3 | 迁移 `cmm_filler_v10.py` → `modules/cmm_filler/core/filler.py` | ⏳ | — | — |
| 3.46 相对导入 | 批量改绝对导入为相对导入 | ⏳ | — | — |
| 3.46 sys.path 清理 | 删除所有 `sys.path.insert(0, _ROOT)` | ⏳ | — | — |
| 3.39 PDF 大小写 | `glob('*.PDF')` → `suffix.lower() == '.pdf'` | ⏳ | — | — |
| 3.43 PDF 句柄 | `fitz.open()` → `with fitz_open_context()` | ⏳ | — | — |
| 3.38 OCR 缓存 | `_cleanup_cache()` 补全 `ocr_cache.json` 按数量清理 | ⏳ | — | — |
| 3.45 主题冲突 | 删除 `ctk.set_default_color_theme("blue")` | ⏳ | — | — |
| 3.42 线程取消 | `threading.Thread(daemon=True)` → `CancellableWorker` | ⏳ | — | — |
| 3.3 模块接口 | 写 `modules/cmm_filler/gui.py` CMMFillerModule | ⏳ | — | — |
| 3.1 独立入口 | 写 `modules/cmm_filler/main.py` 独立运行入口 | ⏳ | — | — |
| 3.17 模板向导 | 搬移 `template_wizard.py` → `modules/cmm_filler/wizard.py` | ⏳ | — | — |
| 3.29 CLI | 写 `modules/cmm_filler/cli.py` | ⏳ | — | — |
| 3.8 版本 | 写 `modules/cmm_filler/app_meta.py` 从 toolbox 导入 | ⏳ | — | — |
| — | 搬移 `templates/`、`models/paddleocr/` | ⏳ | — | — |
| — | 写 `requirements/cmm_filler.txt` | ⏳ | — | — |

---

## Phase 4 — pc_to_excel 迁移 ⏳ 待做

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 11.3 Phase 4 | 搬移 `core/`、`connector/`、`export/`、`inject/` | ⏳ | — | — |
| 3.46 相对导入 | 批量改绝对导入 | ⏳ | — | — |
| 3.46 sys.path 清理 | 删除所有 `sys.path.insert` | ⏳ | — | — |
| 3.35 错误码接入 | `format_user_error` 改为接收 `ToolboxError` | ⏳ | — | — |
| 3.42 线程取消 | 所有 `daemon=True` → `CancellableWorker` | ⏳ | — | — |
| 3.45 主题冲突 | 删除 `ctk.set_default_color_theme("green")` | ⏳ | — | — |
| 3.3 模块接口 | 写 `modules/pc_to_excel/gui.py` PCToExcelModule | ⏳ | — | — |
| 3.1 独立入口 | 写 `modules/pc_to_excel/main.py` | ⏳ | — | — |
| 3.8 版本 | 写 `modules/pc_to_excel/app_meta.py` | ⏳ | — | — |
| 3.29 CLI | 写 `modules/pc_to_excel/cli.py` | ⏳ | — | — |
| 3.7 BAS 脚本 | 搬移 `scripts/export_current.bas` | ⏳ | — | — |
| 3.14 admin 启动器 | `run_as_admin.bat` 整合 | ⏳ | — | — |
| — | 写 `requirements/pc_to_excel.txt` | ⏳ | — | — |

---

## Phase 5 — 配置迁移 ⏳ 待做

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 3.9 基础迁移 | `migrate_settings_if_needed()` 首次启动时调用 | ⏳ | — | — |
| 3.9.1 版本升级 | 所有 settings.json 加 `_version` 字段 | ⏳ | — | — |
| 3.9.1 迁移函数 | `migrate_cmm_filler_1_0_to_2_0()` + `migrate_pc_to_excel_1_4_to_2_0()` | ⏳ | — | — |
| 3.9.1 迁移主流程 | `load_and_migrate_settings()` 含备份 + 沿链升级 | ⏳ | — | — |
| 3.9.2 降级导出 | `export_legacy_settings()` | ⏳ | — | — |
| — | 合并 `toolbox/app_meta.py` 和 `utils/theme.py` 的 `TOOLBOX_THEME` 重复定义 | ⏳ | — | — |

---

## Phase 5.5 — 应用层修复 ⏳ 待做

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 3.40 原子写 | 替换所有 `json.dump` 直接写 → `save_settings_json_atomic` | ⏳ | — | — |
| 3.41 文件锁 | Shell 启动时检测并发（`FileLock`） | ⏳ | — | — |
| 3.38 OCR 缓存 | 补全 `ocr_cache.json` 按数量清理 | ⏳ | — | — |
| 3.39 PDF 大小写 | CMFiller `glob('*.PDF')` 修复 | ⏳ | — | — |
| 3.43 PDF 句柄 | 所有 `fitz.open()` 改 `with` 形式 | ⏳ | — | — |
| 3.42 线程取消 | 所有 `daemon=True` → `CancellableWorker` | ⏳ | — | — |
| 3.45 主题统一 | Shell 主入口调一次 `set_default_color_theme`，模块内删除 | ⏳ | — | — |
| 3.42 atexit | `atexit.register(cleanup_on_exit)` | ⏳ | — | — |

---

## Phase 6 — 打包整合 ⏳ 待做

| ARCHITECTURE 章节 | 任务 | 状态 | 偏差 | Bug/修复 |
|-------------------|------|------|------|---------|
| 3.0 依赖拆分 | 创建 `requirements/cmm_filler.txt` + `requirements/pc_to_excel.txt` | ⏳ | — | — |
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
