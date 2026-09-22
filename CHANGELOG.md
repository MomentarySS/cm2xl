# Changelog — PCDMISToolbox

所有版本升级记录。格式：`## [版本] — 日期`，按模块分小节，方便追踪每个模块的变更。

---

## [1.1.0] — 2026-09-22

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.1.0`
- 安装包输出文件名同步为 `cm2xl_Setup_1.1.0.exe`
- **界面卡顿专项优化**（详见 `docs/PERF_UI_LATENCY.md`）：深色/浅色切换、模块切换、PCDMIS 状态刷新三条路径的主线程阻塞均大幅下降

### 性能

| 场景 | 修复前 | 修复后 | 根因 |
|------|-------:|-------:|------|
| 切到 PCDMIS 模块 | ~560 ms | 194 ms（2s 内命中缓存 ~0.001 ms） | `_perm_text()` 内 3 次 `get_pcdmis_pid()`，等价 spawn 3 个 `tasklist.exe`（单次实测 190 ms） |
| 已连接时每次激活/轮询 | ~620 ms | 45 ms | `dispatch_pcdmis()` 内部调 `is_pcdmis_running()`，每次 dispatch 付一次 tasklist；`get_active_part_name()` 因 `ensure_session()` 重复 dispatch |
| 外观切换（2000 widget） | 361 ms | — | `ctk.set_appearance_mode()` 同步遍历全部存活 widget，O(n) |
| 打开设置/关于（第二次起） | 71 / 82 ms | ~0.4 ms | 每次重开都重建全部 CustomTkinter widget（Settings 28 个 / About 60 个） |

- `_perm_text()`：合并为单次 `get_pcdmis_pid()` + 2 秒 TTL 缓存；`elevated` 为 `None` 时显式显示「PCDMIS:?」，不再误报「普通」
- `dispatch_pcdmis()`：固定「先 `GetActiveObject`、失败转 `Dispatch`」顺序，删掉 `is_pcdmis_running()` 前置判断（该判断只影响异常路径开销，不影响功能正确性）
- `get_active_part_name()`：去掉内部 `ensure_session()` 自愈，改为纯轻量读取 + 缓存兜底；导出前的会话自愈路径 `_ensure_connected()` 未改动
- CMMFiller 预览窗口：`_build_preview_card()` 删除内层 `cols` Frame，把 `label` + `desc` 合并为单个 Label，**保留 tol 独立列**（灰色 / size 12 / 右对齐）以维持表格可读性
- `settings_dialog._save()`：`set_appearance_mode()` 改走 `after_idle`，不再在「保存」按钮回调里同步执行

### 缺陷修复

- **外观切换失效**：`set_appearance_mode()` 的 `after_idle` 原挂在设置对话框自身上，而 `_save()` 结尾会 destroy 该窗口，Tk 随之取消其未执行的 after 回调，导致模式切换永不执行（设置已写盘、下次启动才生效）。改挂 Shell 主窗口
- **模块切换黑白闪屏**：`_activate_module()` 对旧 host `pack_forget()`、对新 host `pack()`，中间 `_content_frame` 短暂空出，暴露区域只有 `page_bg` 一色——浅色模式下是一块白、深色模式下是近黑。改为所有 host 用 `place()` 铺满内容区，靠 `lift()`/`lower()` 切换堆叠，任何时刻都不 unmap
- watcher 的 after id 在触发后未清零，`_stop_status_watcher()` 会去取消已执行的 id；现触发即置 `None`

### 测试

- `modules/pc_to_excel/tests`：128 passed
- 新增 dispatch 顺序/回退/双失败用例，`Fix 4-B` 专项 5 个（含 `com_call_lock` 为 `RLock`、需跨线程持锁才能制造抢锁失败）
- 新增对话框复用与 after-idle 生命周期校验；模块切换零 unmapped 校验
- `tests/phase8_smoke.py`：1 个**既有**失败（`TestCrashLog::test_exception_written` 断字面量 `MODEL_MISSING`，而 `ToolboxError.__str__` 只输出 `[E1003]`），与本次改动无关

---

## [1.0.12] — 2026-09-03

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.12`
- 安装包输出文件名同步为 `cm2xl_Setup_1.0.12.exe`

### pc_to_excel 模块

- **二次导出不再卡死**：抽数与界面探测共用 `com_call_lock`；导出进行中状态轮询不再抢 COM
- **已运行的 PC-DMIS 禁止 `EnsureDispatch`**：只 `GetActiveObject` / `Dispatch` 附着，避免 gencache 重建导致假死
- Tk 的 `main thread is not in main loop` 不再误判为 COM 失效去重连
- 「部署工具栏启动器」放到「一键导出 Excel」同一行，不必展开折叠区
- 抽数结束后清空命令缓存，避免多件连续导出占内存

### 文档

- 用户手册、`toolbox/docs/pc_to_excel.md`、`docs/ARCHITECTURE.md` 补充 COM 串行化与二次导出说明

---

## [1.0.11] — 2026-09-03

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.11`
- 安装包输出文件名同步为 `cm2xl_Setup_1.0.11.exe`
- **启动参数**：`cm2xl.exe --module pc_to_excel --auto-export` 跳过 OCR 启动画面，直接进入 PCDMIS 导出

### pc_to_excel 模块

- **PC-DMIS 工具栏一键出 Excel**：部署 `.vbs`/`.bat` 启动器，挂到 PC-DMIS 自定义工具栏后一点即导出（默认仅 Mark）
- 已有 cm2xl 实例时通过文件 IPC 唤醒现有窗口再导，不另开第二份
- 启动器优先指向 Inno 安装的 `cm2xl.exe`（本机常见 `D:\PF\cm2xl\`）
- **COM 兼容**：支持 PC-DMIS **2017 R2–2026.1**，优先附着正在运行的实例

### 文档

- 用户手册与 `toolbox/docs/pc_to_excel.md` 补充工具栏挂载步骤

---

## [1.0.10] — 2026-08-31

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.10`
- 安装包输出文件名同步为 `cm2xl_Setup_1.0.10.exe`
- **壳层 UI 精炼**：深色模式 token 收口至 `TOOLBOX_THEME`；新增 `toolbox/ui_components.py` 共享配色/字体/分组标题/按钮样式
- **主窗口 / 设置 / 关于 / 启动画面**：去除散落硬编码色值，设置弹窗内容区可滚动

---

## [1.0.9] — 2026-08-29

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.9`
- 安装包输出文件名同步为 `cm2xl_Setup_1.0.9.exe`
- **关于弹窗**：预览颜色图例与路径区重排，便于对照 OCR 预览含义

### pc_to_excel 模块

- **出货表多轴取 D**：圆柱等 X/Y/D 同时存在时，填入出货表优先写 **D（直径）**，XYZ 仅作参考；单轴角度/距离（A/M）不受影响
- **填入结果保留序号冲突**：写入后摘要与预览一致，不再把「后写覆盖」丢掉
- **空填入提示**：无 CMM 行时不再误提示「确认已 Mark」

### CMMFiller 模块

- **孤儿推断**：两个标签之间多个缺失序号按 AX 表头分块配对，不再共用第一块数据
- **角度轴**：描述含「角度」时优先取 A，不再把形位「至」当成角度从而误取 D

### 文档 / 规划

- **多轴拆行（待开发）**：`docs/PDF_ENHANCEMENT_PLAN.md` Phase 6，记录圆柱 X/Y/D 分行填入的需求；当前默认仍每序号取一轴（D）
- `toolbox/docs/cmm_filler.md`、`pc_to_excel.md` 补充多轴默认取 D 的说明

---

## [1.0.8] — 2026-08-29

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.8`
- 安装包输出文件名同步为 `cm2xl_Setup_1.0.8.exe`
- 全项目自动化测试 **194 passed**（phase8 26 + cmm_filler 58 + pc_to_excel 110）
- **用户文档**：新增 `toolbox/docs/`（README、cmm_filler、pc_to_excel），打包进 `dist/docs/`
- **日志维护**：启动超 100MB 自动裁剪；设置面板可手动清理日志
- **OCR 缓存**：设置面板 + CMM 处理页可清理；`utils/ocr_cache.py`
- **配置迁移**：扩展旧版路径检测（CMMFiller / PCDMIS_ExcelExporter AppData）；首次迁移弹窗告知
- **关于**：说明日志在 AppData 不在安装目录；复制/打开日志文件夹

### pc_to_excel 模块

- **PCDMIS 状态轮询**：模块激活后每 30 秒检测 `session_alive()`，失效自动断开并刷新状态栏

### cm2xl 工具箱

- `toolbox/settings_dialog.py`：日志/OCR 维护入口并入设置（顶栏不再单独「维护」按钮）
- `utils/startup_migrations.py` + `toolbox/startup_notices.py`：统一启动迁移与弹窗

---

## [1.0.7] — 2026-08-29

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.7`
- 安装包输出文件名同步为 `cm2xl_Setup_1.0.7.exe`
- 全项目自动化测试 **158 passed**（cmm_filler 58 项）

### CMMFiller 模块

- **PDF 提取与解析**：新增 `pdf_extract.py`、`parse_measurements.py`、`report_profile.py`；多页扫描、文字层快通道、OCR bbox 表格对齐；支持多前缀/多子编号（FAI、CC、DIM 等）
- **模板写入**：默认按模板 A 列序号定位行（`fixed_page_layout.py`）；规格/公差与实测值同步写入
- **样品超额拆分**：样品数超过模板列数时自动输出多个 Excel（如 `_样品1-6.xlsx`、`_样品7-10.xlsx`）
- **PC-DMIS 专项**：公差归一化（形位下公差=0、尺寸对称修正）、模板 G 列轴偏好、CC 序号间隙推断
- **子编号冲突**：`sub_item_conflict.py` + 预览紫色高亮；动态选项（FAI_1-1…FAI_1-N / 都不填 / 较差 NG），不限子项数量
- **NG 分析**：`ng_analysis.py` + GUI「NG 分析」页 + CLI `ng-stats`
- **可选能力**：`pdf_table_import.py`（pdfplumber）、`requirements/cmm_filler_optional.txt`
- **CLI**：新增 `ng-stats`、`tables` 子命令；支持 `--profile` / `--roi` / `--extra-prefix`
- **GUI**：移除固定分页/动态扩展切换；OCR 预览可编辑实测值；子编号冲突选择区

### 文档

- `docs/PDF_ENHANCEMENT_PLAN.md`：Phase 1–5 全部标记完成，补充子编号冲突与 overflow 边界说明

---

## [1.0.6] — 2026-08-28

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.6`
- **P0 修复**：CustomTkinter 6.0 的 `CTkImage` 不再接受路径字符串，`utils/app_icon.py` 改为传入 `PIL.Image` 对象，修复启动即崩溃（`light_image must be instance of PIL.Image.Image`）
- `utils/app_icon.py`：窗口图标设置改用 `after_idle` + `wm iconbitmap`；优先从 exe 同级加载 `cm2xl.ico`
- `build/fix_dist.py`：打包后将 `cm2xl.ico` / `assets/app_logo.png` 复制到 exe 同级（快捷方式图标 + 标题栏图标）
- `installer/cm2xl.iss`：桌面/开始菜单快捷方式显式指定 `IconFilename: {app}\cm2xl.ico`；卸载项图标同步

---

## [1.0.5] — 2026-08-28

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.5`
- 应用图标：`cm2xl.ico` 换新；新增 `utils/app_icon.py` 统一窗口标题栏图标与界面 Logo（Splash / 关于 / 顶栏 / 子窗口）
- `assets/app_logo.png`：界面内 Logo 资源；`pcdmis_toolbox.spec` 打包 `cm2xl.ico` 与 `assets/app_logo.png`
- 浅色主题「暖灰纸感」：`utils/theme.py` 调整页面/卡片/边框/输入框对比度，修复勾选框白勾不可见（`CTkCheckBox.fg_color` 改回品牌青绿）
- `build/generate_theme_preview.py`：主题改善前后对比预览图生成脚本

### pc_to_excel 模块

- `gui/main_window.py`：导出/填入板块复选框无法点击 → 新增 `_checkbox()`（自动宽度 + 背景 canvas 绑点击）
- `gui/main_window.py`：挂载 Shell 时同步底栏 PCDMIS 连接状态灯

### cm2xl 工具箱

- `toolbox/shell.py` / `splash.py` / `about_dialog.py` / `settings_dialog.py`：接入统一图标与 Logo
- `main.py` / `modules/cmm_filler/gui.py` / `template_wizard.py`：子窗口设置标题栏图标

---

## [1.0.4] — 2026-08-28

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.4`
- `pcdmis_toolbox.spec`：补打包 `Cython/Utility`（含 `CppSupport.cpp`），修复安装后 OCR 报 `Cython\Utility\CppSupport.cpp` 错误
- `build/fix_dist.py`：打包后校验 `CppSupport.cpp` 是否存在

---

## [1.0.3] — 2026-08-28

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.3`
- 安装包文件名同步为 `cm2xl_Setup_1.0.3.exe`

### CMMFiller 模块

- `modules/cmm_filler/gui.py` **P0**: OCR/填充流程中 5 处懒加载 `from ..core.filler` 错误解析为 `modules.core`，导致安装后点识别/填充报 `No module named 'modules.core'` → 改为 `from .core.filler`
- `pcdmis_toolbox.spec`：补打包 `modules/pc_to_excel/gui/__init__.py`（PyInstaller 子包发现）
- `tests/phase8_smoke.py`：新增 `test_cmm_filler_gui_lazy_core_import` 回归测试

---

## [1.0.2] — 2026-08-27

### 整体

- `toolbox/app_meta.py`：`APP_VERSION` 统一为 `1.0.2`
- 文档版本号、安装包文件名、测试数量与代码对齐
- `main.py` / `cmm_filler/main.py`：移除全局 `PROTOCOL_BUFFERS`（由 `ocr/engine.py` 局部 `setdefault`）
- `pcdmis_toolbox.spec`：OCR 模型优先 `modules/cmm_filler/models/paddleocr/`
- `tests/phase8_smoke.py`：修正 `ROOT` 路径与 `test_defaults` 隔离
- `docs/ARCHITECTURE.md`：补「离线部署约束」章节（修复 README 死链）；安装脚本名/版本/路径与代码对齐
- `build.bat`：OCR 模型优先模块内路径；清理只删 `build\pcdmis_toolbox`（避免误删 `hooks/` 与 `fix_dist.py`）；`fix_dist.py` 调用路径修正
- `build_installer.bat`：补充 `%LOCALAPPDATA%\Programs\Inno Setup 6` 探测
- `installer/cm2xl.iss`：去掉未随 Inno Setup 6 分发的 `ChineseSimplified.isl`（避免编译失败；向导按钮为英文，自定义文案仍为中文）；旧版检测改为 CMMFiller GUID `...7890`（带 `_is1`），不再与自身 AppId 相同导致重装误报
- `build/hooks/`：保留 `hook-customtkinter.py` + `hook-paddleocr_pre.py`；不提交会回写 site-packages 的 `hook-paddleocr.py` 及未引用的 `paddleocr_fix.py` / `rth_paddleocr_fix.py`（paddleocr patch 由 `fix_dist.py` 打到 dist 副本）
- `build/generate_icon.py`：删除（图标以已入库的 `cm2xl.ico` 为准）
- `utils/settings.py`：明确 `CONFIG_SCHEMA_VERSION`（2.0.0）与 `APP_VERSION` 独立

### pc_to_excel 模块

**代码审查修复（2026-08-27晚）**

- `export/inspection_form_fill.py` **P0-3**: 关键字检测（"检验/判定/检具/OK/NG"）从数据行移至 `header_scan_row`（第5行），避免 "OK-001"/"检验件-A1" 等真实序号被误跳过
- `export/pcdmis_style_report.py` **P0-5**: `_compute_outtol()` 有偏差无公差时返回 `None` 而非 `0.0`，语义修正
- `gui/main_window.py` **P1-4**: `_on_error()` 移除无效的 `msg.startswith('【')` 分支（所有调用方已预格式化）

### cm2xl 工具箱

**UI 改进（2026-08-27晚）**

- `toolbox/shell.py`: 状态栏 PCDMIS 连接状态加🟢🔴图标（`update_pcdmis_status()`）
- `modules/pc_to_excel/gui/main_window.py`: 独立模式首次运行显示 3 步引导面板（检测 PCDMIS 状态 + 连接按钮），连接成功后自动隐藏
- `modules/cmm_filler/gui.py`: 结果 tab 文件列表从 card 叠堆改为表格视图（状态/文件名/文件夹/复制路径），失败文件红色高亮

---

## [1.0.1] — 2026-08-27

### 整体

- `.gitignore`: 新增 `pcdmis_toolbox/cm2xl_preview.png`（commit `0a358b4`）

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
- `docs/ARCHITECTURE.md`: PROTOCOL_BUFFERS 描述更新为 engine 局部 setdefault；Tkdnd 初始化逻辑更新；wizard.py 路径修正
- `CLAUDE.md`: PROTOCOL_BUFFERS 注释同步更新；TkinterDnD 描述更新
- `README.md`: PROTOCOL_BUFFERS 不再列为 main.py 必要配置
- `docs/MIGRATION_ARCHIVE.md`: PROTOCOL_BUFFERS 清单项更新

### pc_to_excel 模块

**代码审查修复（2026-08-27）**

- `core/data_extractor.py` **P0**: `normalize_feature_element()` 子串匹配误判 → 改用 token 集合精确匹配，避免 `"CIRCLE"` 匹配到 `"AUTOCIRCLE"`、`"SLOT"` 匹配到 `"KEY_SLOT"` 等问题
- `inject/command_injector.py` **P0**: `_find_export_command()` 中 `BAS_FILENAME in name` 子串匹配 → 改用 `name.lower().endswith(BAS_FILENAME.lower())`，避免 `export_current.bas` 被 `export_current_backup.bas` 误匹配
- `export/template_report.py` **P0**: `export_report()` 中 `template_path`/`tolerance` 参数被 `_ =` 静默丢弃 → 传入非 None 值时显式发出 `DeprecationWarning`
- `connector/com_detector.py` **P1**: `python_bitness()` 每次调用重新计算 → 改为模块级常量 `_PYTHON_POINTER_BITS`，在导入时确定一次
- `utils/local_settings.py` **P1**: `load_settings()` 中全量 `except Exception` 掩盖配置损坏错误 → 分层异常处理：`JSONDecodeError`/`OSError` → `logger.warning`；`UnicodeDecodeError` → `logger.error`；各字段解析失败加 `logger.debug`
- `gui/main_window.py` **P1**: `_refresh_connection_ui()` 无异常防护 → 整体包裹 `try/except`，失败时 `logger.exception` 记录，不阻断 UI 刷新
- `export/inspection_form_fill.py` **P1**: `resolve_input_form()` 链式续填文件不验证有效性 → 增加 `.xlsx`/`.xlsm` 扩展名校验 + `load_workbook()` 完整性验证，失败时 warn 并回退到 `--form` 指定路径
- `core/data_extractor.py` **P1**: `_safe_float()` 对 NaN 返回 `float('nan')` 而非 `None` → 加 `math.isnan()` 检查，NaN 转为 `None`，避免 NaN 数据静默写入 Excel
- `export/inspection_form_fill.py` **P1**: `_resolve_target_col()` 列选择两条件优先级歧义 → 拆为两个独立循环，优先选**全空列**，再选**半数空列**，消除歧义
- `core/report_filter.py` **P2**: `_is_cmd_marked()` 异常时默认返回 `True` → 改为默认返回 `False`（保守策略：新版 PCDMIS COM 若缺少 `Marked` 属性，不误将命令保留在报告中）
- `core/tolerance.py` **P2**: `summarize_results()` 中 `total = len(judged)` 语义不明确 → 改为 `total = passed + failed`，加注释说明 NA 状态不计入合格率
- `export/inspection_form_fill.py` **P0-2**: 多 sheet 出货表仅首 sheet 写入件号 → 新增 `piece_written` 标志位，`write_piece_id` 条件增加 `and not piece_written`，避免同一件号重复写入（commit `55f585b`）

**架构重构（2026-08-27）**

- `core/data_extractor.py`（1940 行 / 70+ 函数）拆分为 8 个子模块：`data_extractor.py`（入口组合 + re-export）+ `_common.py` + `_command_cache.py` + `_dimension.py` + `_tolerance.py` + `feature.py` + `_datum.py` + `classification.py`。`extract_from_application()` 签名与返回值不变，内部 `_` 前缀函数名与逻辑全部保留
- `core/__init__.py` 统一导出 `extract_from_application`
- `connector/pcdlrn_constants.py`：`_CONSTANTS_SINGLETON` 全局单例 → `_CONSTANTS_BY_PROGID` 按 ProgID 隔离缓存；`get_const(name, prog_id=None, default=None)` 二级缓存键 `(prog_id, name)`；新增 `set_active_prog_id()`
- `connector/pcdmis_connector.py`：`connect()` 成功后 `set_active_prog_id(prog_id)`，`disconnect()` 清空
- `inject/command_injector.py`：`_find_export_command` / `_configure_script_command` / `inject_export_command` / `check_export_command` 增加 `prog_id` 参数透传
- `gui/main_window.py`、`cli.py`：注入/检查调用点传入 `prog_id=connector.prog_id`
- `module.py`：`mount()` 改 `_create_window()` 工厂方法，注册层不再 import GUI/connector

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
