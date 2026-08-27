# cm2xl — 迁移进度跟踪

> **状态**: v1.0.0 已发布。Phase 0–8 全部完成。本文档作为迁移过程归档保留。
> 重点保留 **ARCHITECTURE 偏差记录**与 **关键 Bug 修复时间线**，供后续维护排错参考。
>
> 历史对应章节、提交 hash、详细偏差：见 git log 与 `ARCHITECTURE.md`。

---

## 一、阶段总览

| Phase | 内容 | 状态 | 关键提交 | 关键产物 |
|-------|------|:----:|----------|----------|
| **0** | 基础设施骨架 | ✅ | `c810735`, `9b9319c` | `utils/`（theme/paths/logging/audit/error_codes）、`toolbox/{app_meta,protocol}.py`、`main.py` |
| **1** | 壳主窗口 | ✅ | `9b9319c` | `toolbox/shell.py`、`utils/{settings,threading_utils,file_io}.py` |
| **2** | 模块注册机制 | ✅ | `9b9319c` | `modules/__init__.py`（`pkgutil.iter_modules` 自动发现） |
| **3** | CMMFiller 迁移 | ✅ | `3ae11d0`, `2c1bef2` | `modules/cmm_filler/`（含 18MB OCR 模型、2 个 Excel 模板） |
| **4** | pc_to_excel 迁移 | ✅ | `f3ba93f` | `modules/pc_to_excel/`（含 `connector/core/export/inject/gui/utils` + BAS 脚本） |
| **5** | 配置迁移 | ✅ | `a046ec9` | `migrate_settings_if_needed()`、版本升级链、legacy 导出 |
| **5.5** | 应用层修复 | ✅ | `ff1d551`, `b7e6de6`, `9d45c4d`, `276e5ea` | 原子写、文件锁、日志落盘、审计分离、错误码接入 |
| **6** | 打包整合 | ✅ | `f108ba1` | `pcdmis_toolbox.spec`、`build/fix_dist.py`、`build/hooks/`、`installer/Toolbox.iss`、`build.bat` |
| **7** | 保留独立入口 | ✅ | `c963bda` | 旧入口重定向脚本、`README.md`、`CLAUDE.md` |
| **7.5** | 设置与关于对话框 | ✅ | `567ca07`, `5e5450c` | `toolbox/{settings_dialog,about_dialog}.py`、运行时外观/日志切换 |
| **8** | 测试 | ✅ | `db00d57`, `e0ec729` | `tests/phase8_smoke.py`（30 用例）＋ `tests/test_report_filter.py`（41 用例）＋ `tests/test_local_settings.py`（15 用例）＋ `tests/test_command_injector.py`（13 用例），**100 passed, 0 failed** |

### 打包产物

- **路径**：`dist/cm2xl/cm2xl.exe`（30 MB），总 601 MB
- **离线打包实测**：PaddleOCR 模型内置、PyInstaller 多进程兼容、theme.json 打包、ffmpeg DLL 剔除（节省 82 MB）

---

## 二、关键 Bug 修复时间线

后续排错时可优先来这里查根因。

### 2026-08-26 — 迁移后 P0 修复

| 问题 | 根因 | 修法 |
|------|------|------|
| **所有 PDF 处理失败** | `utils/file_io.fitz_open_context` 缺 `@contextmanager` 装饰器，`with` 语句实际抛 `TypeError: generator object does not support the context manager protocol` | 补装饰器 |
| **pc_to_excel 测试无法收集** | `connector/base.py:8` 用 `from core.models` 绝对导入，阻塞全部测试 | 改相对导入 |
| **权限检测静默失效** | `com_detector.py:13/180/192` 绝对导入异常被 `try/except` 吞掉 | 改相对导入 |
| **CMMFiller 导入层级错** | `cmm_filler/gui.py:16/17/18` 用 `..core.filler`/`..app_meta`/`utils.settings`（无 load_settings） | 统一改 0 连点导入 |
| **4 连点导入越界** | 5 个文件 `....utils.*` 与全树 0 连点约定互斥（`modules` 作顶级包时越界） | 全部改相对导入 |
| **适配层与包同名冲突** | `modules/pc_to_excel/gui.py`（适配层）与 `gui/`（子包）同名，包优先导致 `PCToExcelModule` 死代码、pc_to_excel 永不注册 | 适配层改名 `module.py`，`modules/__init__.py` 支持 `gui.py`/`module.py` 双入口 |
| **挂载模式关模块连带关 Shell** | `MainWindow._on_close` 无 `if self._owns_root` 守卫 | 加守卫（保存设置/断开 COM 保留） |
| **BAS 脚本部署双重目录** | `deploy_bas_script` 部署到 `.../scripts/scripts/`（`paths.bas_deploy_dir` 已含 scripts 段） | 去掉重复段；`_bundled_bas_source` dev 模式补搜根 |
| **迁移函数缺失裸 RuntimeError** | 缺中间版本时链式步进崩溃 | `ToolboxError(ErrorCode.CONFIG_MIGRATION_FAIL, E6002)` |
| **CMMFiller 日志读不到** | `gui.py`「查看日志」按 `CMMFiller.log` 大小写查，文件实际为 `cmm_filler.log` | 路径对齐 |
| **审计日志混入普通日志** | `setup_logging` 给普通 logger 挂 `{name}.audit.log`，文件名误导实际是按天副本 | 移除 TimedRotatingFileHandler；`setup_audit_logging` 独立挂专用 handler + `propagate=False` |

### 2026-08-27 — Phase 6 打包后 GUI 修复

| 问题 | 根因 | 修法 |
|------|------|------|
| **状态栏"加载失败: 'weight'"** | `_build_theme_json()` 生成的 `CTkFont` 段缺 `"weight"` 键。CustomTkinter 5.x `load_theme()` 把 CTkFont 按平台拍扁成 `{family, size, weight}`，然后 `ctk_font.py:41` 读 `["weight"]` → KeyError | 给三个平台段都补 `"weight": "normal"` + `utils/theme.json` 加进 spec 的 `datas` |
| **CMM报告填充 模块不显示** | 打包后 `modules/` 子包在 `_internal/` 没有 `__init__.py`（只在 PYZ 归档里），`pkgutil.iter_modules` 扫不到 → 自动发现失效 | spec `datas` 把所有本地 `__init__.py` 显式抽出；同时改 `_discover_modules()` 不做文件系统判断，改用 try-import |
| **GUI 太白 + 文字后色块** | `CTkLabel` 默认 fg_color 是 `page_bg`，每个 label 后有灰色矩形 | `theme.json` 中 `CTkLabel.fg_color` 改为 `"transparent"`；`card_bg`/`page_bg` 改暖灰白/暖灰 |
| **unmount 阻塞不退出** | Shell.on_close() 卡在模块 unmount | 加 2 秒 watchdog，任何 unmount 阻塞都强制退出 |

### 2026-08-27 — pc_to_excel 架构重构（拆分 + 常量隔离 + 注册层解耦）

| 问题 | 根因 | 修法 |
|------|------|------|
| **常量缓存不更新** | `pcdlrn_constants._CONSTANTS_SINGLETON` 全局单例首次加载后永不失效，不同 PCDMIS 版本 typelib 常量值冲突 | 改 `_CONSTANTS_BY_PROGID` 按 ProgID 隔离；`get_const` 增 prog_id；connector `connect()` 成功后 `set_active_prog_id()` |
| **data_extractor god-file** | 1940 行 / 70+ 函数，五类职责耦合 | 拆 8 子模块（`_common`/`_command_cache`/`_dimension`/`_tolerance`/`feature`/`_datum`/`classification` + 入口 `data_extractor.py`），逻辑与函数名未变 |
| **module.py 反向依赖 GUI** | 注册层 import 业务 GUI | `mount()` 改 `_create_window()` 工厂方法延迟 import（未加 `_create_connector`，因 `MainWindow` 内部自建 connector） |

---

## 三、ARCHITECTURE.md 偏差记录

实现与原设计的差异及原因。后续维护若发现"代码和 ARCHITECTURE 对不上"，先来这里查。

| 章节 | 原设计 | 实际实现 | 原因 |
|------|--------|---------|------|
| **3.4 主题自定义路径** | `utils/theme.py` TOOLBOX_THEME 常量 | 完整自定义 JSON 主题（19 key，基于 green 字段表） | CustomTkinter 对主题字段要求严格，需完整实现所有 key |
| **3.41 文件锁** | 使用 `fcntl` | 基于 `O_EXCL` 跨平台实现 | `fcntl` 仅 Unix，Windows 不兼容 |
| **2 目录结构** | 仅有框架描述 | 新增 `utils/__init__.py` 统一导出 | 便于 `from utils import *` 批量导入 |
| **3.6 日志** | GuiLogHandler 设计 | 与设计一致 | — |
| **3.3 协议** | ModuleProtocol + ShellProtocol | 补充 `shell` 属性到 ModuleProtocol | 代码审查发现接口不完整 |
| **11.2 模块注册** | 各模块显式调用 `register_module` | `pkgutil.iter_modules` 自动发现 + import 执行注册 | 更自动化，减少模块维护负担 |
| **六 适配层命名** | `modules/pc_to_excel/gui.py` 适配层 + `gui/` 子包 | 适配层改名 `module.py`，发现逻辑支持双入口 | `gui.py` 与 `gui/` 包同名冲突，包优先导致适配层死代码、模块永不注册（2026-08-26 发现并修复） |
| **3.9.1 迁移链** | `_next_version` 末段+1 链式步进 | 每个 from_version 一次性升到当前 schema | 链式依赖注册表连续键，缺中间版本抛 RuntimeError（2026-08-26 调整） |
| **3.46 导入根** | `....utils.*` 指向 toolbox 层 | 统一 0 连点（`from utils.paths import paths`） | 4 连点在 `modules` 为顶级包时越界，与 `main.py`/`cmm_filler` 的 0 连点约定互斥（2026-08-26 统一） |
| **3.50/11.2 data_extractor 单文件** | 1940 行 god-file「禁止重构核心逻辑」 | 拆为 8 子模块，入口 `data_extractor.py` 仅组合 + re-export | 五类职责耦合（2026-08-27 重构，核心逻辑未变，见 3.51） |

---

## 四、后续维护入口

- **项目结构与开发约定**：`pcdmis_toolbox/CLAUDE.md`
- **快速开始与打包**：`pcdmis_toolbox/README.md`
- **变更日志**：`pcdmis_toolbox/CHANGELOG.md`
- **架构设计**：`ARCHITECTURE.md`（97 KB，项目主体设计文档）
- **代码考古**：本文件 + git log

---

*本归档完成于 2026-08-27。后续如新增 Phase 9+，建议在本文档追加简表即可，详细过程直接写在 commit message 里。*