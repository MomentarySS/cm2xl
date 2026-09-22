# 核心代码缺陷修复计划（长期）

> **范围**：cm2xl 两个模块的核心逻辑层 —— `modules/pc_to_excel/core/`、`modules/cmm_filler/core/` + `ocr/`、
> `connector/` + `export/` + `inject/` + `utils/`（模块内）、根 `utils/` + `toolbox/` + `main.py` + `modules/__init__.py`。
>
> **来源**：2026-09-22 全量**只读**审查（4 个代码域并行深查 → 逐条回源码与真实调用点核对）。
>
> **回归基线**：裸跑即可 —— 收集范围由 `pytest.ini` 的 `testpaths` 限定，
> `tests/phase8_smoke.py` 也已纳入（见 P3-7，2026-09-22 修复）。
>
> ```powershell
> D:\AI\miniconda3\envs\paddleocr_gpu\python.exe -m pytest -q
> ```
>
> 当前全量 **278 passed**（`tests/` 42 + `modules/*/tests` 236）。
> 审查当时的基线是 233 —— 也就是说：**下列缺陷全部落在现有测试覆盖之外**。
>
> **用法**：长期跟踪文档。每条独立 commit，做完把 TL;DR 表的「状态」和文末「变更记录」一起更新。
> 每条开工前先读「语义边界」—— 那是本计划里最容易被忽略、也最容易改出回归的部分。

---

## 待办与进度总览

> 这一节是**入口速览**：要你做的事、我还能做什么、整体进度。
> 每条缺陷的详细改法 / 语义边界 / 实施记录在下面各自的章节里；逐次变更流水见文末「变更记录」。
> 状态以 TL;DR 表为准，本节只做汇总，不重复细节。

### 一、要你做的事（真机验证 —— 我无法代劳）

这些项代码已改完、单测已过，但**只有真机能证明有效**。按「最省事 → 最费事」排：

| # | 要做什么 | 前置条件 | 通过判据 | 代码提交 |
|---|---------|---------|---------|---------|
| **P1-2** | 启动 app **两次** | 无 | 只弹一次「配置已自动迁移」；`report_profile` / `custom_item_prefixes` / `ocr_roi` 三个字段仍在 | `0331696` |
| **P1-4** | ① 重新点一次「部署 BAS 脚本」 ② PC-DMIS 内执行 `PC2XL_EXPORT` | 编码修复**不会自动生效**，必须先重新部署 | `pcdmis_partial_export.csv` 生成（**新路径** `D:\AI\work\cm2xl\data\reports\`） | `05f4e61` |
| **P1-1** | 跑一份 **>50 项**的 PDF 导出 | 需要这样一份 PDF | 序号 51+ 被写入 | `fcbc19c` |
| **P1-3** | 汇总导出选**两个不同目录的同名 PDF** | 需要两个同名 PDF | 第二个 Sheet 不是第一个零件的值 | `9d1957d` |
| **P2-1** | 构造「下公差读不到」的行 | **当前那份程序复现不了**（已实测 42 条里 0 条），需另找/另造 | 不丢行、无假超差 | `22a532f` + `66560d9` |
| **P2-2** | 多轴项核对报告 | 样本已有（本机 `CC_15` / `CC_16`） | 各轴按**自己的**限判定与打印 | 未开始（需先补设计决策） |

**P2-1 的排查抓手**（不必再手工找）：

```powershell
D:\AI\miniconda3\envs\paddleocr_gpu\python.exe -m modules.pc_to_excel.cli dump-tols --filter <前缀> -o dump.txt
```

看末尾「下公差不可用（`minus_tol is None`）」与「COM 抛异常」两个汇总数字。

### 二、我还能做什么（按推荐顺序）

| 顺序 | 项 | 类型 | 为什么排这里 |
|:---:|----|------|------------|
| **1** | **P2-2** | 判定错 | 唯一「现场样本已找到 + 分析已完成」的项。**但改法本身要先补设计决策**：`AxisValues.tolerance` 每轴只存一个数、`FeatureRecord` 只有标量 ±，装不下 `+0.10/−0.04`，照原计划改会造出假合格窗口（详见 P2-2 节「现场实测补充」） |
| 2 | P3-5 | 丢报告 | 同秒两次导出静默覆盖；改法明确（保存侧唯一化）、无需设计决策、碰的面小 |
| 3 | P3-2 / P3-4 / P3-1 / P3-3 | 健壮性 / 可诊断性 | 都小而独立，适合批量清 |
| 4 | P2-3 | 判定错 | 价值高，但根因分析还没到「可照着写代码」 |
| 5 | P3-6 | 架构 | 今天不可利用（埋雷 API），优先级最低 |
| — | P2-4 | 逻辑矛盾 | **实测未触发**，已降级 |

**并行/冲突**：P2-2 碰 `_dimension.py` / `tolerance.py` / `export/pcdmis_style_report.py`；
P3-5 也碰 `export/pcdmis_style_report.py`（保存侧）—— 两者同文件但不同函数，
可同版本合入，只是**不要同时开两条线改同一个文件**。P3 其余各项互不重叠。

### 三、整体进度（截至 2026-09-22）

**已完成 7 / 16，未开始 9 / 16。** 基线 233 → **278 passed**（`tests/` 42 + `modules/*/tests` 236）。

| 项 | 做了什么 | commit |
|----|---------|--------|
| P1-2 | 配置迁移保留未知键 + 保存盖章 | `0331696` |
| P2-5 | `get_report_header_info()` 补 `com_call_lock`（+ AST 源码守卫） | `56e3770` |
| — | 建立本计划 + CLAUDE.md 同步 | `d607e11` |
| P1-1 | 数据区下界改按序号列推断（模板2 序号 51+ 不再丢） | `fcbc19c` |
| P3-7 | 新增 `pytest.ini`，找回 42 个静默不跑的测试 | `169e3ea` |
| P1-3 | OCR 缓存图片名纳入源路径与 ROI | `9d1957d` |
| — | 记录提交编码陷阱 + 「回归测试要有牙」的验证方法 | `6f77f72` |
| P2-1 | 下公差补 COM 失败防护（假超差 + 静默丢行） | `22a532f` |
| P2-1 续 | 补「COM 抛异常」路径 + 新增 `dump-tols` 诊断子命令 | `66560d9` |
| — | P2-1 续与真机实测结论（P2-2 现成样本 + 两个新边界） | `fe5e107` |
| P1-4 | `export_config.txt` 改按 UTF-16（带 BOM）写 | `05f4e61` |
| — | P1-4 实施记录与真机前置事实 | `98e7997` |

**发布前还要做**（详见文末「真机验证清单」末两条）：写 CHANGELOG ——
① OCR 缓存图片名变更 → 历史缓存图片全部失效；
② `export_config.txt` 改 UTF-16 → **已部署机器必须重新部署 BAS 脚本**。

---

## TL;DR

| # | 问题 | 位置 | 类型 | 真机 | 状态 |
|---|------|------|------|:---:|------|
| P1-1 | 模板数据区上限截断（序号 >50 静默丢弃） | `cmm_filler/core/filler.py:858-882` | 静默丢数据 | ✅ | ✅ **已完成**（真机待验） |
| P1-2 | 配置迁移每次启动重跑，CMMFiller 丢 3 字段 | `utils/settings.py:292-311` + 两处 save | 静默丢配置 | ✅ | ✅ **已完成**（真机待验） |
| P1-3 | 同名 PDF 的 OCR 缓存串号 | `cmm_filler/core/pdf_extract.py:118` | 静默错值 | ✅ | ✅ **已完成**（真机待验） |
| P1-4 | BAS `export_config.txt` 编码不匹配 | `inject/command_injector.py:82-85` | 功能不可用 | ✅ | ✅ **已完成**（真机待验） |
| P2-1 | 下公差未做 COM 失败防护 | `pc_to_excel/core/_tolerance.py:201,283` | 假超差/丢行 | ✅ | ✅ **已完成**（真机待验） |
| P2-2 | 多轴记录按首轴 ± 判定 | `pc_to_excel/core/tolerance.py:67-72` | 判定错 | ✅ | ⬜ 未开始 |
| P2-3 | 「最差 NG 子项」只比一个样品 | `cmm_filler/core/sub_item_conflict.py:17-21` | 判定错 | ✅ | ⬜ 未开始 |
| P2-4 | 数字含逗号致整份 PDF 解析失败 | `cmm_filler/core/parse_measurements.py:108-117` | 逻辑矛盾（**实测未触发**，见该节判定依据） | ❌ | ⬜ 未开始 |
| P2-5 | `get_report_header_info()` 漏进 `com_call_lock` | `connector/pcdmis_connector.py:184-241` | 并发 | ❌ | ✅ **已完成** |
| P3-1 | splash 吞初始化异常，fail-fast 是死代码 | `toolbox/splash.py:74` | 可诊断性 | ❌ | ⬜ 未开始 |
| P3-2 | IPC 命令被静默丢弃 | `utils/ipc.py:65-66` | 可靠性 | ✅ | ⬜ 未开始 |
| P3-3 | 依赖缺失被当成「入口不存在」 | `modules/__init__.py:31-34` | 可诊断性 | ❌ | ⬜ 未开始 |
| P3-4 | 不捕 `UnicodeDecodeError` | `utils/settings.py:210,380` | 健壮性 | ❌ | ⬜ 未开始 |
| P3-5 | 导出文件名秒级时间戳无去重 | `export/pcdmis_style_report.py:377` | 丢报告 | ❌ | ⬜ 未开始 |
| P3-6 | COM 对象逃出 apartment（埋雷 API） | `connector/com_detector.py:427-432` | 架构 | ❌ | ⬜ 未开始 |
| P3-7 | `tests/` 目录默认不被 pytest 收集（42 个测试静默不跑） | `pytest.ini`（新建） | 测试可信度 | ❌ | ✅ **已完成** |

状态取值：⬜ 未开始 / 🟡 进行中 / ✅ 已完成 / ⏸ 暂缓（附原因）

---

## 每条修复的验证约定

1. **回归测试必须「有牙」**：写完新测试后，用 `git stash push -- <实现文件>` 退回修复前的
   实现，跑同一组测试确认它**会失败**，再 `git stash pop` 恢复。
   只断言「现在通过」无法区分真守卫与空壳。本项目 P1-1 / P1-3 / P2-5 都做了这一步，
   并把「修复前的失败信息」写进了各自的实施记录。
2. **期望值优先从被测对象自身推导**，不要硬编码快照 —— 例如 P1-1 的随包模板用例是
   「找出最后一个像序号的行」再断言覆盖到它，模板更新后不会变成假失败。
3. **提交中文 commit message 用 `git commit -F <utf8文件>`**，不要用 `-m`
   （PowerShell 5.1 会按 ANSI 编码传参，把 GBK 写进历史；仓库既有提交是 UTF-8）。
4. **保持 CRLF**：本仓库 `core.autocrlf=true`，Python 与文档文件在工作区是 CRLF。
   编辑后可用字节统计自查（bareLF 应为 0）。

---

## 修复编排

### Phase 0 — 准备

```powershell
git switch -c fix/core-defects
# 基线对照（当前 248 passed；裸跑即可，收集范围见 pytest.ini）
D:\AI\miniconda3\envs\paddleocr_gpu\python.exe -m pytest -q
# 真机验证前快照，方便比对「配置是否被改坏」
copy "%LOCALAPPDATA%\cm2xl\config\cmm_filler\settings.json" settings.before.json
```

**不要合成一个大 commit**：P1-1 与 P1-3 都会改变索引/缓存行为，混在一起出问题时无法二分。

---

## Phase 1 — 静默数据 / 配置丢失

### P1-1 模板数据区上限截断

**现象** — 随包 `modules/cmm_filler/templates/模板2.xlsx` 的序号列：**序号 1..100 落在第 10–109 行**
（另有 8 个说明性文字单元格在第 1–7 行，如「图纸版本:」）。
但 `_get_max_data_row()` 返回 **59**，`build_sheet_row_index()` 只建到序号 **50**
（实测 indexed keys=54，末键 `'50'`）—— 即序号 51..100 共 50 项全部漏掉。
这些项的规格/公差在 `filler.py:786-787` **静默 `continue`**；实测值在 `filler.py:838-842`
只写一条 warning 并计入 `unmatched`。

**根因** — `_get_max_data_row()` 以**规格列**（B 列）最后一个非空单元格为锚点。
空白报告表的规格列只有表头（该模板为第 9 行），锚点落在表头 → `min(9+50, 6+200) = 59`。
触发条件：模板规格列未预填 + 未显式配 `max_data_row`（当前 `data/config/cmm_filler/template_config.json` 正是此状态）。

**改法** — 锚点改为「序号列 ∪ 规格列」取 `max`，且序号列**只把能解析成序号的单元格算有效**
（复用 `core/fixed_page_layout.py` 的 `serial_cell_keys`）。保留 `+50` 缓冲与 `min(..., data_start+200)` 上界。

**语义边界**
1. 序号列第 6–9 行是说明性文字（`图纸版本:`、`注：测量仪器代号…`）。不解析就把锚点拉到第 9 行 —— **等于没修**。
2. 序号跳号（该模板实际缺序号 2）→ 取 `max` 而非 `count`。
3. 显式配置 `max_data_row` 时的短路优先级**不能动**。
4. 扫描上界 `data_start+200` 本次不动，避免一个 commit 改两件事。

**验证** — 新增单测断言 `模板2.xlsx` 的 `_get_max_data_row() >= 109`；另加「规格列有值」用例断言仍走原路径。
真机：跑一份 >50 项的 PDF，核对序号 51+ 是否写入。

**实施记录（2026-09-22）**

| 文件 | 改动 |
|------|------|
| `cmm_filler/core/filler.py` | 新增模块级 `_looks_like_serial()` + `_SERIAL_CELL_RE`；`_get_max_data_row()` 锚点改为「序号列 ∪ 规格列」取 max，并覆盖全部模板 Sheet |
| `modules/cmm_filler/tests/test_fixed_page_layout.py` | +4 条测试 |

**实测效果（随包模板）**

| 模板 | max_data_row 修复前 → 后 | 索引到的序号 |
|------|:---:|------|
| `模板2.xlsx` | 59 → **159** | 54 键（末键 `'50'`）→ **104 键（末键 `'100'`）** |
| `模板1.xlsx` | 34 → 80 | 29 键 → 29 键（本就覆盖，无回归） |

**实施时的两个决定**

1. **扫描范围从「配置的单个 Sheet」扩到 `_get_template_sheet_names()` 的全部 Sheet。**
   理由：`max_data_row` 的消费方 `build_sheet_row_index()` 就是按这个列表逐 Sheet 建索引的，
   只看一个 Sheet 推断出的下界对其它 Sheet 不成立。随包模板都是单 Sheet，所以实测无差异。
2. **顺带把 `wb.close()` 挪进 `try/finally`。** 原实现若 `wb[sheet_name]` 抛 KeyError
   （模板缺 Sheet），`close()` 永不执行 → 工作簿句柄泄漏。属于被重写的那几行内部，
   未扩大范围；如不想要可以单独回退这两行。

**验证（含「守卫是否有牙」的证明）**

- 4 条测试：`_looks_like_serial` 正反例、合成空白表（规格列只有表头 + 序号 1..100）、
  随包 `模板2.xlsx` 全覆盖、显式配置短路优先级。
- 随包模板那条的期望值**从模板自身推导**（找出最后一个像序号的行），
  模板更新后不会变成假失败。
- **证明有效**：`git stash` 把 `filler.py` 退回修复前，同一份模板上
  旧 `_get_max_data_row()` 返回 **59**，而新断言要求 `>= 109` → **FAIL**；
  恢复后 → PASS。
- 全量 `248 passed`（244 + 新增 4）。

---

### P1-2 配置迁移每次启动重跑

**现象** — CMMFiller 的 `report_profile` / `custom_item_prefixes` / `ocr_roi` 每次启动被抹掉，
并每次弹「配置已自动迁移」+ 生成 `.v1.0.0.bak`。

**根因** — 两条链合起来才成立：
- `gui._save_paths()`（`cmm_filler/gui.py:124-131`）写 6 个键，`filler.save_settings()`（`core/filler.py:139-145`）原样落盘，**都不带 `_version`**；
- 启动时 `_version` 缺失 → 视为 `0.0.0` → 按 `_LEGACY_DEFAULT_VERSION["cmm_filler"]="1.0.0"` 走迁移 → `migrate_cmm_filler_1_0_to_2_0()` 只白名单 3 个键。

`_save_paths()` 在 `gui.py` 有 15 处调用（含退出 `:171`、卸载 `:1788`），必然触发。
`pc_to_excel` 侧同构（`utils/local_settings.py:99-105` 也不写 `_version`），只是它的 6 个键恰好都在白名单里，
暂不丢数据但同样每次弹窗 + 生成 `.bak`。

**改法** — 两条腿都要，只改一条无效：
- (a) 两个迁移函数保留未知键：`new = {**old, **_default_settings(...)}`（白名单 → 黑名单）；
- (b) 模块保存时带上 `_version` / `_schema`，让迁移不再每次重跑。

**语义边界**
1. `{**old, **defaults}` 的**顺序**决定 `_updated_at` 被刷新成现在（想要）还是保留旧值 —— 写反就静默失效。
2. 保留未知键 ⇒ 历史废弃字段会长期留在配置里。倾向接受（配置是用户数据，多留比丢好），但需在 CHANGELOG 写明这个取舍。
3. 已被抹掉的 3 个字段**无法恢复**。已核对 `gui.py:89-97` 三者都有合理默认值 ⇒ 后果是「回到默认」而非崩溃。这个前提成立才敢修。
4. 本 commit **不做**「统一 save helper」重构，只补 `_version`。

**验证** — 断言 `migrate_cmm_filler_1_0_to_2_0({6 键})` 保留全部键；断言「保存 → 重载 → 迁移」幂等
（`run_startup_migrations()` 第二次返回空 notices）。真机：启动两次，确认只弹一次且 3 个字段仍在。

**实施记录（2026-09-22，方案 A + B-1）**

| 文件 | 改动 |
|------|------|
| `utils/settings.py` | 新增 `stamp_settings()`；`_default_settings()` 改为复用它；两个迁移函数改为 `{**old, **_default_settings(...)}`；`export_legacy_settings()` 改用 `_LEGACY_EXPORT_KEYS` 白名单（B-1） |
| `modules/cmm_filler/core/filler.py:139` | `save_settings()` 保存时盖章 |
| `modules/pc_to_excel/utils/local_settings.py:99` | `save_settings()` 保存时盖章 |
| `tests/phase8_smoke.py` | +6 条回归测试 |
| `modules/pc_to_excel/tests/test_local_settings.py` | +1 条回归测试（盖章后能原样读回） |

实施时核实过的边界（都已确认**不受影响**）：

1. `gui.py:867` 的 `if not load_settings():` 真值判断 —— 首次运行仍是空文件 → 仍弹引导；
   写入后本来就是 6 个业务键（非空），加 `_` 前缀键不改变真值。
2. `local_settings.load_settings()` 用的是 `data.get(...)` 逐字段读取，**不是** `AppSettings(**data)`，
   所以多出的 `_` 前缀键不会 TypeError。
3. `export_legacy_settings()` 的两个调用方（`settings_dialog.py:314`、`shell.py:575`）传的都是
   `load_and_migrate_settings()` 的完整结果，白名单过滤后输出与改动前**逐字节一致**
   （因为 2.0 文件里恰好只有那 6 个业务键）。
4. 已 grep 确认每个配置文件**只有一个写入方**（cmm_filler → `filler.save_settings`；
   pc_to_excel → `local_settings.save_settings`），不存在漏盖章的旁路写入。
5. `stamp_settings()` 用 `dict(data)` 复制，不修改调用方传入的字典。

验证结果：`240 passed`（基线 233 + 新增 7），行尾保持 CRLF。**真机待验**。

---

### P1-3 同名 PDF 的 OCR 缓存串号

**现象** — 不同目录下的同名 PDF，第二个 Sheet 被填成第一个零件的测量值。

**根因** — `pdf_extract.pdf_to_images()` 的 PNG 名只由 `pdf_path.stem` 决定（`:103`、`:118`），
而 `filler._cache_key()`（`:1001-1004`）按**图片路径** MD5 缓存。
`_cache_key` 的 docstring 声称「避免同名 PDF 不同路径冲突」，但路径本身是从 `stem` 派生的 —— **没有避免**。

**改法** — PNG 名加入「解析后完整路径」的短哈希：`f'{stem}_{pathhash}{page_suffix}{roi_suffix}.png'`。

**语义边界**
1. 哈希一变，**所有历史缓存图片变孤儿**。`_cleanup_cache()` 按 30 天 mtime 兜底，不会立刻膨胀，但 CHANGELOG 要提。
2. `stem` 必须保留在文件名里 —— 先 grep 有没有别处按 PNG 文件名反查 stem（`CACHE_DIR.glob` / 解析文件名）。
3. `dpi` **明确不做**（保持原计划边界）：它由构造参数固定为 300，GUI / CLI 都没有入口，
   不构成实际冲突。已在代码 docstring 写明「若将来开放 dpi 设置，此处需一并补上」。
4. `_roi` 后缀**从「保持现状」改为「一并修」** —— 见下方实施记录。它不是范围外的改动，
   而是同一个缺陷（缓存标识不完整）的第二种触发方式，且用户能从 GUI 直接触发。

**验证** — 单测：两个不同目录的同名 PDF 走 `pdf_to_images()`，断言生成两个不同路径。
真机：汇总导出选两个同名 PDF，核对第二个 Sheet 的值。

**实施记录（2026-09-22）**

| 文件 | 改动 |
|------|------|
| `cmm_filler/core/pdf_extract.py` | 新增 `_path_cache_suffix()`；文件名改为 `{stem}_{路径哈希}{_pN}{_roi_...}.png`；ROI 后缀由布尔 `_roi` 改为带实际比例 |
| `modules/cmm_filler/tests/test_pdf_extract.py` | +3 条测试 |

**实施时的新发现：`roi_cache_suffix()` 是死代码**

`report_profile.roi_cache_suffix()`（`report_profile.py:178`）的 docstring 写着
「ROI 配置的短哈希后缀，用于 OCR 缓存 key」，但全仓**零引用** —— 作者本来就打算把 ROI
纳入缓存标识，只是没接上。而旧实现用的是布尔 `_roi` 后缀：**把 ROI 从 0.2 改成 0.3，
文件名不变 → 命中旧 OCR 结果**（图片会重新渲染，但 OCR 按文件名取缓存）。

这不是范围外的新问题，而是同一个缺陷（缓存标识不完整）的第二种触发方式，且用户能从
GUI 的 ROI 输入框直接触发。所以本次一并接上，复用了那个现成的 helper。

**边界核实**

- grep 确认**没有任何地方反查 PNG 文件名**：只有 `filler._cleanup_cache()` 用
  `CACHE_DIR.glob('*.png')` 按 mtime 删 30 天前的文件，不解析名字。`stem` 保留在
  文件名里（并加了测试守住），人工排查与日志仍可认图。
- 哈希一变，历史缓存图片全部变孤儿；`_cleanup_cache()` 的 30 天 mtime 兜底，不会立刻膨胀。

**验证（含「守卫是否有牙」的证明）**

- 3 条测试：同名不同目录 → 不同图片；不同 ROI 值 → 不同图片；文件名保留 stem。
- **证明有效**：`git stash` 退回修复前跑同一组测试 → **2 failed**，失败信息正是
  `001.png == 001.png` 与 `roi_roi.png == roi_roi.png`（第三条是守卫，旧代码本就通过）。
- 全量 `251 passed`（248 + 新增 3）。

---

### P1-4 BAS 配置编码不匹配

**现象** — 在 PC-DMIS 内执行 `PC2XL_EXPORT` 弹「写入文件失败」，`pcdmis_partial_export.csv` 从不生成。

**根因** — writer 走 `atomic_write_text()`（`utils/file_io.py:25`，UTF-8 **无 BOM**；已核对本机实际部署的
`%LOCALAPPDATA%\PCDMIS_ExcelExporter\scripts\export_config.txt` 是 74 字节单字节编码）；
reader 是 `OpenTextFile(CONFIG_PATH, 1, False, -1)`（`scripts/export_current.bas.template:115`），`-1` = TristateTrue = UTF-16。
单字节内容按 UTF-16 解析后 `\n` 会与后一个字节拼成一个码元 ⇒ 断不开行 ⇒ `outPath` 乱码且非空
⇒ `readExportConfig` 返回 True ⇒ `saveCsv` 失败。

**改法** — `atomic_write_text(config_path, text, encoding="utf-16")`。

**语义边界**
1. 必须用 `utf-16`（**带 BOM**）而非 `utf-16-le`（不带）—— FSO 的 TristateTrue 在无 BOM 时行为不确定。
2. **不选**「改 BAS 第 4 参」那条路：会影响脚本里其他读配置的地方，风险更大。
3. 已部署的机器需重新点一次「部署 BAS 脚本」才拿到新配置。是否加自检提示建议先不做，CHANGELOG 说明即可。

**验证** — 单测断言文件以 BOM 开头、用 utf-16 能读回两行。
真机：PC-DMIS 内跑一次 `PC2XL_EXPORT` —— **这条没有单测替代**。

**实施记录（2026-09-22）**

| 文件 | 改动 |
|------|------|
| `inject/command_injector.py:82` | `atomic_write_text(config_path, ..., encoding="utf-16")`，并就地写明「为何必须带 BOM、为何不改 BAS 第 4 参」 |
| `modules/pc_to_excel/tests/test_command_injector.py` | +1 条 BOM/解码契约用例；**修正**原有 `test_deploy_bas_script_creates_export_config` 的读法 |

**根因在本机的复核（改动前）**

| 指标 | 实测 |
|------|------|
| 已部署 `export_config.txt` 字节数 | **74** |
| 前 4 字节 | `44 3A 5C 41` = ASCII 的 `D:\A`（单字节编码） |
| 是否 UTF-16 BOM | **否** |
| 按 utf-8 读 | `D:\AI\work\a1\pcdmis_toolbox\data\reports\pcdmis_partial_export.csv` / `YES` |
| 写入方数量（全仓 grep） | **1**（`command_injector.py`），无旁路 |

**两个实施细节**

1. **必须顺手修正原有那条测试的读法。** `test_deploy_bas_script_creates_export_config`
   原先按 `encoding="utf-8"` 读回 —— 那正是缺陷本身（写 UTF-8、读 UTF-16）。
   它过去「通过」恰恰是这个 bug 一直没被发现的原因。新用例内留了一条反向守卫，
   断言「干净两行 + 第二行 YES」这个契约在旧写法下**不成立**（本机实测那份连行都断不开，
   只解出 1 行 —— 这正是 `readExportConfig` 把乱码路径当有效值返回 True 的机制）。
   反向守卫只断言契约不成立，不锁死具体失效形态（它取决于字节内容）。
2. **不动 BAS 第 4 参**（边界 2 已定），也不加自检提示（边界 3 已定，改为在发布前的
   CHANGELOG 条目里说明，已登记进「真机验证清单」末条）。

**验证（含「守卫是否有牙」的证明）**

- **证明有效**：`git stash push -- inject/command_injector.py` 退回修复前实现，
  跑同一组测试 → **2 failed**：
  - `test_export_config_is_utf16_with_bom`：`assert b'C:' == b'\xff\xfe'` —— 旧文件开头是路径本身；
  - `test_deploy_bas_script_creates_export_config`：按 utf-16 读不回两行。
  两条失败都直接指向「写侧编码错」这一个根因，没有夹带无关失败。
- 全量 `278 passed`（277 + 1），行尾保持 CRLF。

**真机验证的两个前置事实（避免白跑一趟）**

1. 编码修复**不会自动生效**：已部署的机器必须重新点一次「部署 BAS 脚本」。
2. 本机已部署配置的第 1 行指向**旧项目路径**
   `D:\AI\work\a1\pcdmis_toolbox\data\reports\...`。重新部署会把它改成
   `D:\AI\work\cm2xl\data\reports\pcdmis_partial_export.csv`
   （`paths.pc_excel_reports` = `data_dir/reports`，dev 下 `data_dir` = 仓库根 `data/`）。
   也就是说：**重新部署同时会换掉 CSV 的落盘位置** —— 这是期望行为，但核对时要按新路径找文件。

---

## Phase 2 — 判定与并发正确性

### P2-1 下公差未做 COM 失败防护

**现象** — 读不到下公差时，整行从报告里消失；或出现假超差。

**根因** — `_tolerance.py:201-202` 与 `:283-284` 直接 `-minus_raw`，没有 `_safe_float` / `_normalize_minus_tol`：
- `None` → `TypeError` 被 `:249` 的 `except Exception: continue` 吞掉，而 `indices.add(idx)`（`:184`）**已认领该命令**
  ⇒ 该行静默消失；
- `False`（本包约定的 COM 失败值，见 `_common._com_failed`）→ `-False == 0` → 下公差被当成真实下限参与
  `_check_plus_minus()`（`tolerance.py:21-35`）⇒ 偏差 −0.04 被判**超差**。

同文件的 FCF 分支（`:365-368`）用的正是 `_safe_float` + `_normalize_minus_tol`（`_common.py:55-75`）——
同一文件内两种写法，说明这两处是遗漏而非设计。

**改法** — 对齐 FCF 分支写法：`minus_tol = _normalize_minus_tol(_safe_float(tol_cmd.sizeMinusTol(j)), show_negative)`。

**语义边界**
1. `_safe_float(False)` → `None`，**这是行为变化**（原来 `False` 会变成 `0` 并造成假超差）。
   要确认 `plus` 有值时 `_tolerance_from_limits()`（`_common.py:151-177`）仍正确构造 `tolerance`
   —— 已核对：`current is None` 时才 set，OK。
2. 修好后「读不到下公差」的行不再消失。要确认这类行**应该保留**（有 plus 也算有效数据），并补一条 debug 日志。
3. `indices.add(idx)` 在读取之前（`:184`）—— **不要动**，挪位置会改变 `skip_indices` 去重语义，属于扩大范围。
4. 顺手全文件 grep 一遍所有 `tol_cmd.` 直接调用，列出还有没有别的漏 `_safe_float` 的点，一次改完。

**验证** — mock `sizeMinusTol` 返回 `None` / `False`，断言记录不丢、`minus_tol is None`、`apply_tolerance()` 不产生假超差。

**实施记录（2026-09-22）**

| 文件 | 改动 |
|------|------|
| `pc_to_excel/core/_tolerance.py` | 新增模块级 `logger`（`getLogger("pc_to_excel")`，与 `gui`/`connector` 同款）；尺寸区与区段区两处下公差改走 `_normalize_minus_tol(_safe_float(...), show_negative)`，并在 `minus_tol is None` 时补一条 debug 日志 |
| `modules/pc_to_excel/tests/test_gdt_extraction.py` | +14 条测试（新增 `_SizeTolCmd` / `_SegMinusOverride` 两个可注入 COM 失败值的替身） |

**边界核实（对应上文 4 条语义边界）**

1. **`plus` 有值时 `tolerance` 仍正确构造** —— 已回源码确认 `_tolerance_from_limits()`
   （`_common.py:151-177`）是 `plus is not None` 时先 set、`minus` 只在 `current is None` 时 set；
   `minus=None` 时 `tol.d == plus`。已写成断言，不是靠读代码。
2. **「读不到下公差」的行现在保留** —— 有 plus 也算有效数据。日志文案刻意写成
   「COM 返回 False/None **或未设置**」：`_safe_float` 无法区分「COM 失败」与「该项本就无下公差」，
   两种都落 `None`，不假装能分辨。
3. **`indices.add(idx)`（`:184`）未动** —— 位置与去重语义保持原样。
4. **全文件 `tol_cmd.` 直接调用已逐条清点**（修复后 27 处），无第三处漏网：
   | 类别 | 处数 | 行号（修复后） |
   |------|:---:|------|
   | 已在 `_safe_float` 内 | 12 | `207`、`226`、`227`、`228`、`231`、`235`、`299`、`312`、`313`、`314`、`317`、`321` |
   | 包在 `try/except` 的 int/str 读取 | 8 | `91`、`96`、`119`、`190`、`198`、`269`、`274`、`288` |
   | 包在 `try/except` 的 outtol getter（lambda） | 4 | `238`、`239`、`326`、`327` |
   | 文本读取，已有 `or` 兜底 | 3 | `218`、`223`、`297` |

**实施时的新发现：`show_negative=False` 才是「丢行」那条路径**

第一版测试矩阵只参数化了 `minus_value`（`None` / `False`），跑「有牙」验证时发现
`None` 的两个用例在修复前**也通过** —— 因为 `show_negative=True` 时
`minus_tol = minus_raw`（`None` 直接赋值，不取负）⇒ **不抛 TypeError**。
只有 `show_negative=False` 才会走 `-minus_raw` ⇒ `-None` ⇒ TypeError ⇒ 被吞 ⇒ 丢行。

而 `_minus_tol_show_negative()`（`data_extractor.py:71-75`）在异常时**回落 `False`** ——
即现场默认走的就是这条丢行路径。测试矩阵因此补上 `show_negative` 维度（2×2 + 2×2）。

**验证（含「守卫是否有牙」的证明）**

- 文件内 17 条测试（3 条原有 + 14 条新增）。
- **证明有效**：`git stash push -- modules/pc_to_excel/core/_tolerance.py` 退回修复前实现，
  跑同一组测试 → **10 failed, 7 passed**。失败构成：
  | 探针 | 失败用例 |
  |------|------|
  | 尺寸区丢行 | `[None-False]` `[False-True]` `[False-False]` |
  | 尺寸区假超差 | `[True]` `[False]` |
  | 区段区丢行 | `[None-False]` `[False-True]` `[False-False]` |
  | debug 日志 | `[True]` `[False]` |

  通过的 7 条 = 3 条原有用例 + 2 条符号约定守卫 + 2 条 `None + show_negative=True`
  （后者旧代码本就保留该行、`minus_tol` 本就是 `None`）—— **守卫与探针可区分**。
- 全量 `265 passed`（251 + 新增 14），行尾保持 CRLF（bareLF=0）。

**遗留观察 → 已结案（2026-09-22 真机）** — `tol_cmd.SegmentAxis(j)` 的单参调用在
PC-DMIS 2024.1 上**正常返回**（`SegmentAxis(1)` → `'M'`）。若真实签名是
`(segmentIndex, featureIndex)`，少传一个位置参数会抛 TypeError —— 没有抛，说明**单参是合法的**。
但该程序 `SegmentCount=1`，所以「多段时它取的是段还是特征」仍未验证；
要定性需一个多段（`SegmentCount>1`）的程序。**本次不再作为疑点挂账**。

---

**P2-1 续（2026-09-22 晚）：补「COM 抛异常」路径 + 落地真机诊断子命令**

前一版修复只覆盖「COM **返回** `False`/`None`」。若 COM 是**抛异常**，
`tol_cmd.sizeMinusTol(j)` 的调用点仍在 `try` 内 ⇒ 异常冒到外层
`except Exception: continue` ⇒ **该行照样丢**。FCF 分支对此免疫（走 `_field_value()`，自带
try/except），两分支曾不对称。

| 文件 | 改动 |
|------|------|
| `core/_common.py` | 新增 `_safe_com_float(getter)` —— 包住**直接调用**：抛异常与返回失败值都归 `None`，并统一过 `_safe_float` |
| `core/_tolerance.py` | 两处下公差读取改为 `_normalize_minus_tol(_safe_com_float(lambda: ...), show_negative)` |
| `cli.py` | **新增 `dump-tols` 子命令**（只读诊断，见下） |
| `tests/test_gdt_extraction.py` | +7 条（抛异常矩阵 6 条 + `_safe_com_float` 契约 1 条） |
| `tests/test_cli_dump_tols.py` | **新建**，+5 条 |

**`dump-tols` 子命令**

```powershell
python -m modules.pc_to_excel.cli dump-tols --filter CC_ -o dump.txt
```

只读：连上运行中的 PC-DMIS → 逐命令转储上/下公差的 COM 读取结果
（原值 + 类型 + `ok`/`COM_FAILED`/`RAISED:<异常名>`），末尾汇总
「哪些行的 `minus_tol` 不可用」。存在理由：真机清单那条「构造下公差读不到的行」
**没法从 UI 手工制造 COM 故障**；有了它，验证从「碰运气找」变成「跑一次拿清单」。

实现上的两个决定：

1. **`ok` / `COM_FAILED` / `RAISED` 三态必须分开报。** 布尔属性（`IsFcfCommand`）返回 `False`
   是**正常值**不是失败 —— 第一版探针拿 `_com_failed` 去判定，把所有 `False` 都标成 FAILED，
   属于自欺。诊断里只有数值/字段读取才用 `_com_failed`。
2. **下公差必须先 `_safe_float` 再 `_normalize_minus_tol`。** COM 读回的常是**字符串**
   （`'  -0.010'`）；第一版直接把原值喂进去，报出 `minus_tol = '  -0.010'` 这种误导性结果。
   已由 `test_dump_minus_converts_com_string_to_float` 守住。

**真机实测（2026-09-22，PC-DMIS 2024.1 / `马丁测试-2026-08-28-B版.PRG`）**

| 指标 | 实测 |
|------|------|
| 命令总数 | 242 |
| `MinusTolerancesShowNegative` | **True** |
| `scope=report, require_marked=True` 提取 | 42 条（全部是 `CC_*`） |
| **`minus_tol is None`** | **0 条** |
| COM 抛异常 | **0 处** |
| 判 FAIL | 0 条（`apply_tolerance` 口径） |

⇒ **该程序无法复现 P2-1 的条件**（既没有失败值也没有抛异常）。这本身是有用结论：
P2-1 的真机验证需要**另找或另造**含「下公差未定义」项的程序，不能拿手头这份顶。

分命令看：

| 命令 | 类型 | 下公差来源 | 实测 |
|------|------|-----------|------|
| `CC_1`–`CC_4` | ISO 几何公差命令（垂直度） | **区段区** `segmentDimMinusTol(1,1)` | 真值 `0.0`（float，**非** `False`）→ `minus_tol=0.0`，判**合格** ✓ |
| `CC_15`/`CC_16` | 尺寸位置（头行） | 尺寸区 `F_MINUS_TOL` | `'   0.000'` 可读 → `minus_tol=0.0`；但 `DIM_DEVIATION`/`DIM_OUTTOL` 返回 **`False`** |

`CC_1`–`CC_4` 的价值：它们是**被本次改动直接覆盖的那条分支**（区段区），
且下公差是真值 `0.0`。若改动把 `0.0` 误判成 COM 失败（`_com_failed` 用的是 `is False`
而非 `==`，`0.0 is False` 为假 ⇒ 不算失败），这四条会从「合格」翻成别的结果 ——
实测仍为**合格**，说明健康路径没被改坏。

**顺带确认的一个实现前提**：本机 `cmds.Item(i)` 对每个索引都抛 **TypeError**，
必须靠 `_get_command_at()` 的回退链（`Item` → 调用式 → `[]`）才能取到命令。
诊断子命令复用了它，没有另写一套。

**验证（含「有牙」证明）**

- 全量 `277 passed`（265 + 新增 12）。
- **证明 A —— 回退到 HEAD（`22a532f`，已修 None/False、未修抛异常）**：
  `git stash push -- core/_tolerance.py` → **6 failed / 23 passed**，失败的正是 6 条抛异常用例
  （尺寸区 4 + 区段区 2），其余（含 `_safe_com_float` 契约测试）全过 ⇒ **抛异常这条修复确实有牙**。
- **证明 B —— 回退到 `6f77f72`（P2-1 修复前）**：`git checkout 6f77f72 -- core/_tolerance.py`
  → **16 failed / 13 passed**。失败 16 条 = 尺寸区丢行 3 + 尺寸区假超差 2 + 区段区丢行 3
  + 日志 2 + **抛异常 6** ⇒ 两轮修复合起来把三种失效路径（返回 `None` / 返回 `False` / 抛异常）
  全部覆盖。通过 13 条 = 3 条原有用例 + 2 条符号约定守卫 + 2 条 `None+show_negative=True`
  + 5 条 `test_cli_dump_tols.py`（与 `_tolerance.py` 无关，本就不该受影响）—— 分类可解释。
- 行尾保持 CRLF。

---

### P2-2 多轴记录按首轴 ± 判定

**现象** — 多轴合并记录的每个轴都按**第一条轴**的 ± 判定。

**根因** — `_apply_dimension_report_meta()`（`_dimension.py:157-160`）只在 `is None` 时写入标量
`plus_tol` / `minus_tol` ⇒ 合并记录保留首行标量；`apply_tolerance()` 的 `use_pm` 分支（`tolerance.py:67-72`）
对每个轴都用这同一个标量，忽略 `feature.tolerance.x/y/z`。

**改法** — `use_pm` 分支优先取逐轴值 `getattr(feature.tolerance, axis)`，非 `None` 用对称判定，否则回退标量 plus/minus。

**语义边界**
1. 这是**判定语义变更**，导出侧必须同步：`export/pcdmis_style_report.py` 的 `_axis_tol_values` 现在优先 `rec.plus_tol`。
   只改一处会造成「判定用逐轴、打印用标量」。要么两边一起改，要么走第 4 条。
2. 单轴记录必须**完全不受影响**：`tolerance` 只有 `d` 有值时 `getattr(tolerance, 'x') is None` → 回退标量。这条要写死断言。
3. 别和 `_axis_limit_key()`（`tolerance.py:38-41`）的回退逻辑重复/冲突。
4. 现场**确实存在**「各轴公差不同」的合并记录（2026-09-22 用户确认「有时候真的会有」）
   ⇒ 判定侧与导出侧**都要改**，不能只改一处；第 1 条因此从「可选」变为「必须」。

**验证** — 构造多轴不同公差的 `FeatureRecord`，断言各轴按自己的限判定。真机：找一个多轴项核对报告。

**现场实测补充（2026-09-22 晚，PC-DMIS 2024.1 / `马丁测试-2026-08-28-B版.PRG`）**

用 `dump-tols` + 真实提取跑出来的 `CC_15` / `CC_16`，是 P2-2 的**现成样本**，
且比原描述多暴露两处：

| 项 | `CC_15` | `CC_16` |
|----|---------|---------|
| 头行 idx | 150（`尺寸位置`，ID=`CC_15`） | 155（同上） |
| 配对行 | 151 `X 轴位置` / 152 `Y 轴位置` / **153 `直径位置`** | 156 / 157 / **158** |
| `X 轴位置` ± | +0.05 / −0.05 | +0.02 / −0.06 |
| `Y 轴位置` ± | +0.01 / −0.01 | +0.04 / −0.04 |
| **`直径位置` ±** | **+0.10 / −0.04** | **+0.05 / −0.01** |
| `直径位置` 偏差 / PC-DMIS `OutTol` | +0.192 / **0.092（NG）** | +0.192 / **0.142（NG）** |
| 合并记录 `plus_tol` / `minus_tol` | **+0.050 / −0.050**（= X 轴） | **+0.020 / −0.060**（= X 轴） |
| 合并记录 `tolerance` | `d=+0.10 x=+0.05 y=+0.01` | `d=+0.05 x=+0.02 y=+0.04` |
| 合并记录 `outtol` | **0.0**（= X 轴的 0.0） | **0.0** |
| 本工具判定 | FAIL（`dev.d=0.192 > plus=0.05`） | FAIL（同） |

**两个新边界（原计划没写）**

5. **标量 plus/minus 与 `deviation.d` 不同源。** `deviation.d = 0.192` 来自 `直径位置` 行，
   而标量 `plus_tol = +0.05` 来自**第一个**配对行 `X 轴位置`。于是「判定用的公差」与
   「被判定的值」来自不同的行 —— 本例两者恰好同判 FAIL（0.192 同时超过 0.05 和 0.10），
   **但这是巧合**：若 `直径位置` 偏差为 0.06，按它自己的 +0.10/−0.04 应**合格**，
   按 X 轴的 ±0.05 却会判**超差**（假 NG）。修 P2-2 时这条必须一并处理。
6. **`outtol` 也吃「首个写入者优先」。** `_apply_dimension_report_meta()` 对 `outtol` 用的是
   同一个 `if rec.outtol is None` 模式（`:164-165`），所以合并记录的 `outtol` 取自
   `X 轴位置` 的 **0.0**，而 PC-DMIS 对 `直径位置` 行报的 **0.092 / 0.142 被丢掉**。
   后果：`apply_tolerance()` 开头「COM 已给出超差量时优先采信」的短路（`tolerance.py:55-60`）
   对这类合并记录**失效**，判定退回标量 ± 路径 —— 本例结论未变，但机制已不是设计意图。
   `outtol` 的合并策略要一起定（取最差？取逐轴？），别只改 plus/minus。

**未改变结论**：本例两条记录 PC-DMIS 与本工具都判 NG，所以**当前没有实际误判**；
上面两点是「会在什么条件下误判」的机制性缺口，属于修 P2-2 时要覆盖的边界。

---

### P2-3 「最差 NG 子项」只比一个样品

**现象** — 某子项只在较早样品 NG 时，它的 NG 不可见 ⇒ 选错子项，且被放弃子项的 NG 在所有样品里都不填。

**根因** — `detect_parent_row_conflicts()`（`sub_item_conflict.py:67`）存进 `candidates` 的已是
`_unique_candidates()` 的结果（`:17-21`，按 key 覆盖 = **保留最后一个样品**），
`pick_worst_ng_candidate()`（`:24-41`）又在这批「代表值」上比；
而 `resolve_parent_picks()`（`:115`）默认就是 `WORST_NG_SUB_ITEM`。

**改法** — 聚合时保留**最差**代表（复用现有 `_severity`），或让 `detect_parent_row_conflicts()` 同时保留 raw 供选取使用。

**语义边界**
1. `_unique_candidates()` 还被 `build_parent_auto_picks()`（`:95`）使用，那里靠 `len(candidates) == 1` 判断
   「唯一子项自动选定」⇒ **必须保证聚合后 key 数不变**（只换代表值，不合并 key），否则唯一子项会被误判成冲突。
2. 先确认 `measure_dict_key()` 是否含样品号 —— 含的话聚合直接失效。
3. 「最差」的定义复用 `_severity`，不要新写一套。

**验证** — 两个样品、两个子项、NG 分布在不同样品，断言选中 NG 那个。真机：多件连续测 + 子编号冲突弹窗。

---

### P2-4 数字含逗号致整份 PDF 解析失败

> **2026-09-22 修正：严重度下调。** 用本机真实 OCR 缓存实测（见「判定依据」），
> 该触发条件在真实数据中**不存在** —— 它是代码内部的逻辑矛盾（该修），
> 但**不是正在发生的丢数据故障**。

**现象** — 若 OCR 输出一个「通过数字判定但含逗号」的 token，`float()` 抛 `ValueError`
⇒ 整份 PDF 解析失败、全部测量项丢失。

**根因** — `_is_numeric_cell()`（`parse_measurements.py:104`）先 `replace(',', '')` 再匹配，
`_numeric_values_from_cells()`（`:108-117`）却对原始文本 `float(t)` ⇒ 判定通过、转换抛 `ValueError`，且无兜底。
同一文件内两种处理方式，是遗漏而非设计。

**判定依据（实测，非推测）** — 扫描 `%LOCALAPPDATA%\cm2xl\cache\ocr_cache.json`（本机真实报告的 OCR 结果）：

| 指标 | 实测值 |
|------|--------|
| OCR token 总数 | 2988 |
| 通过数字判定的 token | 1107（**全部**为点号小数或整数：`24.000` / `-0.200` / `0.003` …） |
| **同时通过判定且含逗号的 token** | **0** |
| 含逗号的 token | 仅 3 个，全是日期（`七月27,2026`），因含中文不通过数字判定 |

**结论** — 该报告体系的小数分隔符是 `.`（1107 : 0）。数字里出现逗号只可能是 OCR 把 `.` 误读成 `,`，
**不存在千分位用法**。

**改法**
1. **必须**：`_numeric_values_from_cells()` 加 `try/except`，转换失败跳过该单元格（+ WARNING 日志）。
   仅这一条就消除了「整份 PDF 失败」这个失效模式。
2. **建议**：单个逗号且两侧均为数字 ⇒ 视为小数点误读（`1,234` → `1.234`），并写 WARNING 便于审计。
3. **明确不做**：把逗号当千分位（`1,234` → `1234`）—— 会造出 1000× 的错误值，且实测数据里不存在该用法。

**语义边界**
1. 第 2 条的取舍：若将来真出现千分位，会被误读成小数。依据是实测 0 千分位；一旦出现，WARNING 日志可追溯。
2. **保守替代**：不做第 2 条，含逗号的 token 一律跳过 —— 结果是该项缺失而非错值。
   两条都能消除故障，选哪个取决于「宁可缺项，还是宁可猜」。
3. `_is_numeric_cell` 允许 `+`/`-` 前缀与 `1.` 形式，`float('1.')` 合法，不用动。
4. 多逗号（`1,2,3`）应跳过。

**验证** — 单测覆盖：`1,234`（按第 2 条 → 1.234）、`1,2,3`（跳过）、
以及「转换失败不中断整份 PDF」。

---

### P2-5 `get_report_header_info()` 漏进 `com_call_lock`

**现象** — 该方法的 COM 段可与其它线程的 COM 访问交错。

**根因** — 同类方法里**只有它**没有锁：

| 方法 | 位置 | `com_call_lock` |
|------|------|:---:|
| `session_alive` | `pcdmis_connector.py:123-133` | ✅ 非阻塞 |
| `get_active_part_name` | `:162-176` | ✅ 非阻塞 |
| `extract_features` | `:257-258` | ✅ 阻塞 |
| `try_connect_with_app` | `com_detector.py:427-428` | ✅ 阻塞 |
| **`get_report_header_info`** | `:184` | ❌ **完全没有** |

它做的不是轻量读：`_bind_app()`（一次 dispatch）+ `ActivePartProgram` + `PartName` / `SerialNumber` /
`GetVariableValue` 多次往返。调用面：CLI 主线程（`cli.py:68`）+ GUI 工作线程（`gui/main_window.py:972,1156`）。

**改法** — 照 `get_active_part_name()` 的写法用 `acquire(blocking=False)`，拿不到返回空 header；
因为它是「要结果」的调用，也可以直接进阻塞锁。

**语义边界**
1. 返回空 header 时调用方要有兜底 —— `gui/main_window.py:970-975` 已有 `try/except`。
2. 非阻塞路径**不得抛异常**。
3. 不要顺手改 `_bind_app()` 的 dispatch 策略。

**验证** — 源码级断言，但**不要只守这一个方法**：断言 `pcdmis_connector.py` / `com_detector.py` 中
**每一个** `with com_apartment()` 都位于 `com_call_lock` 之内（用 `test_com_compat.py` 的 `_code_source()` 手法，先剔除 docstring）。
只守单点的话，下一个新增的 COM 方法会以完全相同的方式漂移 —— 这正是本条缺陷的成因（约定存在、无人机械校验）。

**实施记录（2026-09-22）**

| 文件 | 改动 |
|------|------|
| `connector/pcdmis_connector.py:178` | `get_report_header_info()` 的 COM 段包进 `with com_call_lock:`（缩进整体 +4），补 docstring 说明为何用**阻塞**锁 |
| `modules/pc_to_excel/tests/test_com_compat.py` | +4 条测试 |

**选阻塞锁、而不是 `get_active_part_name` 那种非阻塞回退的理由：**

1. 本方法是「要结果」的调用 —— 拿不到锁就返回空表头，会让导出文件名退化成
   `report_<时间戳>`、出货表件号变空，属于**静默降级**。
2. 已 grep 确认全部 3 个调用方：`cli.py:68`（CLI 主线程）、`gui/main_window.py:972`
   与 `:1156`（都在 `work()` 工作线程内）—— **没有 GUI 主线程调用** ⇒ 不存在卡界面的风险。
3. `ensure_session()` 刻意留在锁**外**：它内部的 `session_alive()` 用非阻塞抢锁，
   外层持锁会让那次探测退化（与 `extract_features` 的写法一致）。

**验证（含「守卫是否有牙」的证明）**

- 新增 4 条测试：2 条**行为**断言（锁在执行时确实被拿到 / 未连接时锁外早退不进锁）
  + 2 条**源码级**断言（两个模块各一条，参数化）。
- 守卫用 **AST** 判定而非文本匹配 —— docstring 里提到的名字天然不计入，不需要
  `_code_source()` 那套剔除；粒度取**函数级**是刻意的：两种加锁写法
  （`with com_call_lock:` 与 `com_call_lock.acquire(blocking=False)`）都要认。
- **证明守卫有效**：把 `git HEAD`（修复前）的源码取出跑同一个检查函数 →
  `offenders = ['get_report_header_info']`；修复后 → `[]`。
  即这条守卫在修复前**会失败**，不是事后补的空测试。
- 全量 `244 passed`（240 + 新增 4）。

---

## Phase 3 — 健壮性 / 可诊断性

### P3-1 splash 吞初始化异常

**现象** — PaddleOCR 预加载失败被静默吞掉，失败推迟到第一次识别才暴露。

**根因** — `splash._run_init()`（`:93-95`）把 `BaseException` 存进 `self._init_exc`，
但**全仓只有这一处赋值、没有任何地方读它**；`show_and_wait()` 返回 `self._init_result`（失败时为 `None`）
⇒ `main.py:200-204` 的 `except → logger.exception → raise` 是**死代码**。

**改法** — `show_and_wait()` 末尾（`:74` 之前）`if self._init_exc: raise self._init_exc`。

**语义边界** — `_init_exc` 是 `BaseException`，含 `KeyboardInterrupt` / `SystemExit`，必须**原样重抛**；
`min_display_ms` 的等待逻辑不受影响。

**验证** — monkeypatch `init_fn` 抛异常，断言 `show_and_wait()` 抛出。

---

### P3-2 IPC 命令被静默丢弃

**现象** — 冷启动期间点工具栏 → 第二进程 `sys.exit(0)`，实际什么都没发生，**无任何日志**。

**根因** — `consume_command()`（`utils/ipc.py:65-66`）超过 `COMMAND_TTL_SEC = 20` 直接删文件返回 `None` 且不记日志；
而第一个实例要等 Splash（`_BOOT_STEPS` 固定 sleep 合计 4.83s + PaddleOCR 预加载，冷启动常远超 20s）结束、
`Shell.__init__` 末尾才开始轮询（`toolbox/shell.py:463-478`）。

**改法** — 丢弃时 `logger.warning`；TTL 20s → 120s；Shell 首次轮询时主动 consume 一次。

**语义边界**
1. **不要**改成无限 TTL（会出现「几分钟后突然导出」）。
2. `clear_ipc_commands()` 在抢到实例锁时清理陈旧文件的逻辑不受影响。

**验证** — 单测 `consume_command(now=ts+25)` 断言返回 `None` 且产生 WARNING 日志。

---

### P3-3 依赖缺失被当成「入口不存在」

**现象** — 某个依赖缺失时，模块从导航里消失且**零日志**。

**根因** — `modules/__init__.py:31-34` 的 `except ModuleNotFoundError: continue` 分不清
「该入口不存在」与「入口内部依赖缺失」。`cmm_filler/gui.py` 在模块级 import `customtkinter` / `tkinterdnd2`，
一旦缺失则 `register_module` 永不执行；而 `except Exception` 里的 `logger.error` 对 `ModuleNotFoundError` **不可达**。

**改法** — 按「是否是本次探测的模块路径」分流，其余记 ERROR 后继续。

**语义边界** — `e.name` 可能是 `modules.cmm_filler.gui`，也可能是缺失的第三方包名 `tkinterdnd2`，
不能只比一个字符串；仍要 `continue`，不能 `raise`（保持启动不中断）。

**验证** — monkeypatch `importlib.import_module` 抛 `ModuleNotFoundError(name='tkinterdnd2')`，断言有 ERROR 日志且不崩。

---

### P3-4 不捕 `UnicodeDecodeError`

**现象** — 非 UTF-8 的 toolbox `settings.json` ⇒ 设置对话框打不开。

**根因** — `utils/settings.py:380` 只捕 `(json.JSONDecodeError, OSError)`，而 `UnicodeDecodeError` 是 `ValueError` 子类；
`toolbox/settings_dialog.py:86` 在 `__init__` 里**无 try 保护**。`load_json()`（`:210`）同样缺。

**改法** — 把 `UnicodeDecodeError` 加进两处 `except` 元组（已有先例：`modules/pc_to_excel/utils/local_settings.py:51`，保持一致）。

**语义边界**
1. `load_json` 的 `except` 里会写 `.corrupt-*.bak`，`UnicodeDecodeError` 走这条路是合理的。
2. `load_toolbox_settings` 只是回落默认值。
3. 启动路径已有 `main.py:110-115` 兜底，本次改动只为对话框那条路。

**验证** — 写一个 GBK 字节的 settings.json，断言不抛异常且回落默认值。

---

### P3-5 导出文件名秒级时间戳无去重

**现象** — 同一零件同一秒内两次导出静默覆盖，两次都报「已导出 N 条」。

**根因** — `build_export_filename()`（`utils/local_settings.py:113`）用 `%Y%m%d_%H%M%S`（秒级），
`export/pcdmis_style_report.py:378` 的 `wb.save(path)` 直接覆盖；`filename_pattern` 不含 `{time}` 时必然冲突。

**改法** — 改**保存侧**做唯一化（`while path.exists(): path = ..._i`）。

**语义边界**
1. `build_export_filename()` 是纯函数且有格式断言测试（`test_local_settings.py:128-159`）⇒ **不要改它**，这就是改保存侧的原因。
2. 唯一化要设上限（如 99）避免死循环。
3. 写法照 `export/inspection_form_fill.py:585` 已有的同类保护，保持一致。

**验证** — 单测同秒两次导出 → 两个不同文件。

---

### P3-6 COM 对象逃出 apartment（埋雷 API）

**现象** — 今天**不可利用**（所有调用方都丢弃返回值），但函数签名在鼓励别人保存它。

**根因** — `com_detector.py:427-432`：

```python
with com_call_lock:
    with com_apartment():
        for prog_id in candidates:
            try:
                app = win32com.client.GetActiveObject(prog_id)
                return True, prog_id, _read_version(app), "", app   # ← 带着接口指针退出公寓
```

`return` 会先执行 `__exit__` → `CoUninitialize()`，把 `app` 留在公寓之外。
现在没炸有两个原因：pywin32 在 `import pythoncom` 时已隐式 `CoInitialize` 过一次（引用计数不为 0，公寓没被真正拆掉）；
且 `connect()`（`pcdmis_connector.py:85`）与 `run_detection()` 都把 `_app` 丢掉了。

**改法** — 让 `try_connect_with_app()` / `quick_connect()` **只返回 ProgID/版本**；
需要对象就在公寓内用完（对照 `try_connect()`（`:407`）已经是只返回 4 元组的形态）。

**语义边界**
1. `connect()` 与 `run_detection()` 都丢弃 `_app` ⇒ 改签名影响面小。
2. `dispatch_pcdmis()` 的契约不变：它返回对象，由调用方自己包 `com_apartment()` —— 这个模式是对的，别一起改。

**验证** — 改后跑 `test_com_compat.py` 全量。

---

### P3-7 `tests/` 目录默认不被 pytest 收集

**现象** — `pytest tests` 收集到 **0 个**测试；`tests/phase8_smoke.py` 里的 42 个测试
只有在**显式指名文件**时才运行。

**根因** — 文件名 `phase8_smoke.py` 不匹配 pytest 默认的 `python_files = test_*.py / *_test.py`，
而仓库里没有任何 pytest 配置文件（无 `pytest.ini` / `pyproject.toml` / `setup.cfg` / `tox.ini`）
覆盖这个模式。`CLAUDE.md` 给的命令恰好是显式指名的（`pytest tests\phase8_smoke.py -q`），所以平时没暴露。

**影响** — 默认跑 `pytest` 会给出**虚假的覆盖感**：42 个测试（配置迁移、原子写、文件锁、降级导出、
crash 日志、toolbox 全局设置、日志级别切换）静默不跑。本次审查的基线数字也因此一度报错
（把 197 当成全部，实际是 **233**）。

**改法（二选一）**
1. 加 `pytest.ini`：`python_files = test_*.py *_test.py phase8_smoke.py` —— 最小改动，保留文件名。
2. 把文件 `git mv` 成 `test_phase8_smoke.py` —— 更符合惯例，但要同步改引用。

**语义边界**
1. 选 1 时可顺带加 `testpaths = tests modules`，让裸跑 `pytest` 覆盖全部；不加也能用显式路径。
2. 选 2 时先 grep 全仓 `phase8_smoke` 的引用（`CLAUDE.md`、`docs/`），别只改文件名。
3. 无论选哪个，`CLAUDE.md` 的 Phase 状态表与 `docs/PERF_UI_LATENCY.md` 里
   「130 tests passed」这类历史数字都需标注为过期。

**验证** — 裸跑 `python -m pytest -q` 收集数 ≥ 233；`--collect-only` 里能看到 `tests/phase8_smoke.py` 的用例。

**实施记录（2026-09-22）** —— 采用**改法 1**（加配置，不改文件名）

| 文件 | 改动 |
|------|------|
| `pytest.ini` | **新建**：`python_files = test_*.py *_test.py phase8_smoke.py` + `testpaths = tests modules` |
| `CLAUDE.md` | 「已验证命令」把 `pytest tests\phase8_smoke.py -q` 换成裸跑 `pytest -q`；Phase 8 的「130 tests passed」标注为已过期 |
| `README.md` | 烟测命令改为裸跑 `pytest -q`，并加一句「只跑 phase8_smoke.py 会漏掉 modules/*/tests 下 200+ 个用例」 |
| `docs/PERF_UI_LATENCY.md` | 补注：`TestCrashLog::test_exception_written` 现已通过；当时 `tests/` 不被收集，故该文的测试数字只覆盖 `modules/*/tests` |

**两个实施细节**

1. **`python_files` 是整体替换**，必须把默认的 `test_*.py` / `*_test.py` 一起写回来，
   否则会把所有 `test_*.py` 一并关掉 —— 这比原缺陷更糟。
2. **顺带加了 `testpaths = tests modules`**。原缺陷调查中实测：不加这一行，裸跑 `pytest`
   会从当前目录递归扫描，而本仓库的 `dist/` 与 `build/` 就在工作区里 —— 打包进来的
   第三方 `test_*.py` 将来可能被误收集。当前 `dist/` 里没有这类文件（已核实），
   但这是个真实隐患。

**验证结果**

| 命令 | 修复前 | 修复后 |
|------|:---:|:---:|
| `pytest --collect-only -q`（裸跑） | 206（漏 `tests/` 全部） | **248** |
| `pytest -q`（裸跑） | — | **248 passed** |
| `pytest tests\phase8_smoke.py -q`（显式路径） | 42 passed | 42 passed（不受影响） |

其中「裸跑收集到 `tests/phase8_smoke.py` 的用例数」= **42**，即全部找回。
显式路径的用法不受 `testpaths` 影响（该选项只在无参数时生效）。

---

## 开放决策（需要现场/产品信息才能定）

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | P2-4：报告里的逗号是千分位还是小数逗号？ | ✅ **已定（2026-09-22）**：小数分隔符是 `.`（用户确认 + 实测 1107:0）。逗号**不做**千分位解释，按 P2-4「改法」第 2 条处理 |
| 2 | P2-2：现场是否真存在「各轴公差不同」的多轴合并记录？ | ✅ **已定（2026-09-22）：存在**（用户确认「有时候真的会有」）⇒ 必须修，且判定侧与导出侧要同步改 |
| 3 | P1-2(a)：迁移改为保留未知键会让配置长期留存历史字段，是否接受？ | ✅ **已定（2026-09-22）**：接受 —— 用户选定「做 A + 顺手修 B-1」。理由：A 让「忘记同步」这个失效模式变得无害；B-1 把降级导出改回白名单以抵消 A 的副作用 |

---

## 已排除的候选（**不要重复排查**）

| 候选 | 排除理由 |
|------|---------|
| `_tolerance.py:360-362` FCF 每个 LINE 只取一个索引 | `_pick_fcf_line_index()` docstring 明确「跳过 - LS 与 FCF 名称」，是**刻意**选单一代表索引，非缺陷 |
| `report_filter.py:36-47` 全零 `尺寸位置` 行被当占位丢弃 | 逻辑成立，但要求该行所有轴实测值均 < 1e-12，真实测量不可达 |
| `inject/toolbar_launcher.py:201` 启动器 UTF-8 无 BOM 由 WSH/cmd 按 ANSI 读 | 只在非 ASCII 安装路径暴露；本机路径为 ASCII，**未能复现** |
| `core/feature.py:15-25` `_get_point()` 忽略 COM 返回值 | 结构可疑（by-ref VARIANT 预置 0.0，失败不抛异常时返回 `(0,0,0)` 而非 `(None,None,None)`，`scope="all"` 下会导出「实测 0.000」的假数据）。但需**真机确认** `FeatureCommand.GetPoint` 失败时是抛异常还是返回 `False` —— 触发条件未确认前不动 |

---

## 真机验证清单（单测覆盖不到）

- [ ] P1-1：一份 >50 项的 PDF 导出，核对序号 51+
- [ ] P1-2：启动两次，确认只弹一次迁移提示且 3 个字段仍在
- [ ] P1-3：汇总导出选两个不同目录的同名 PDF，核对第二个 Sheet
- [ ] P1-4：**先重新点一次「部署 BAS 脚本」**（编码修复不会自动生效），
      再在 PC-DMIS 内执行 `PC2XL_EXPORT`，确认 `pcdmis_partial_export.csv` 生成。
      注意重新部署会把配置第 1 行从旧项目路径
      `D:\AI\work\a1\pcdmis_toolbox\data\reports\...` 改成
      `D:\AI\work\cm2xl\data\reports\pcdmis_partial_export.csv`，按新路径找文件
- [ ] P2-1：构造下公差读不到的行，确认不丢行、无假超差。
      **2026-09-22 实测：`马丁测试-2026-08-28-B版.PRG` 全程序 42 条记录里
      `minus_tol is None` = 0 条、COM 抛异常 0 处 ⇒ 这份程序复现不了，需另找/另造。**
      先跑 `python -m modules.pc_to_excel.cli dump-tols --filter <前缀> -o dump.txt`
      拿清单，再决定用哪份程序。多段记录的轴字母也顺带看一眼（`SegmentAxis(j)` 单参已确认合法）
- [ ] P2-2：找一个多轴项核对报告。**已有现成样本：本程序的 `CC_15`/`CC_16`**
      （头行 + X/Y/直径位置 配对行，各轴公差不同），见 P2-2「现场实测补充」
- [ ] P2-3：多件连续测 + 子编号冲突弹窗
- [ ] P3-2：冷启动期间点工具栏一键导出
- [ ] 全量回归：`python -m pytest -q`（当前 278 passed）
- [ ] **发布前写 CHANGELOG**：OCR 缓存图片命名变更 → 历史缓存图片全部失效
      （由 `_cleanup_cache()` 的 30 天 mtime 自动清理，无需人工干预）。见 P1-3 边界 1
- [ ] **发布前写 CHANGELOG**：`export_config.txt` 写入编码改为 UTF-16 →
      **已部署过的机器必须重新点一次「部署 BAS 脚本」**，否则 `PC2XL_EXPORT` 仍会弹
      「写入文件失败」。见 P1-4 边界 3

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-09-22 | 初版：全量只读审查产出 15 项（P1×4 / P2×5 / P3×6），全部 ⬜ 未开始；登记 3 个开放决策与 4 个已排除候选 |
| 2026-09-22 | 兄弟项目反馈确认 P2-5 属 cm2xl 本地缺陷（**锁约定漂移**，非 COM 层设计缺陷）；P2-5 验证手段由「守单点」加强为「守全约定」 |
| 2026-09-22 | 用户答复开放决策 1、2：P2-4 小数分隔符为 `.`（附真实 OCR 缓存实测 1107:0 证据，**严重度由「丢数据」下调为「逻辑矛盾、实测未触发」**）；P2-2 确认现场存在 ⇒ 判定侧与导出侧必须同步修。决策 3（P1-2a）待定 |
| 2026-09-22 | 决策 3 定案（做 A + 修 B-1）⇒ **P1-2 实施完成**：`stamp_settings()` + 迁移保留未知键 + 降级导出改白名单；+7 条回归测试，`240 passed`。真机待验 |
| 2026-09-22 | **发现并登记 P3-7**：`tests/` 目录默认不被 pytest 收集（`phase8_smoke.py` 文件名不匹配 `test_*.py`），42 个测试静默不跑。**同时修正本文件与前期结论的基线数字：197 → 233** |
| 2026-09-22 | **P2-5 实施完成**：`get_report_header_info()` 的 COM 段包进 `com_call_lock`（阻塞式，附 3 条理由）；+4 条测试，其中源码守卫用 AST 判定并已证明「修复前会失败」。全量 `244 passed` |
| 2026-09-22 | 已提交一轮到分支 `fix/core-defects`：`0331696` P1-2 / `56e3770` P2-5 / `d607e11` docs |
| 2026-09-22 | **P1-1 实施完成**：`_get_max_data_row()` 锚点改为「序号列 ∪ 规格列」并覆盖全部 Sheet；新增 `_looks_like_serial()`。模板2 的 max_data_row 59 → 159，索引键 54 → 104（末键 `'100'`）。+4 条测试，已用 `git stash` 退回旧实现证明「修复前会失败」。全量 `248 passed`。**同时修正本节 P1-1 现象里的序号区间描述（1..100，非 109 个序号）** |
| 2026-09-22 | 已提交 `fcbc19c`（P1-1 + CLAUDE.md 计数修正） |
| 2026-09-22 | **P3-7 实施完成**：新建 `pytest.ini`（`python_files` 补上 `phase8_smoke.py` + `testpaths = tests modules`）。裸跑 `pytest` 收集数 206 → **248**，42 个用例全部找回；显式路径用法不受影响。同步 `CLAUDE.md` / `README.md` / `docs/PERF_UI_LATENCY.md` 里的历史测试数字与命令。**本文件的基线命令也随之简化为裸跑** |
| 2026-09-22 | **P1-3 实施完成**：缓存图片名改为 `{stem}_{路径哈希}{_pN}{_roi_比例}.png`。新增 `_path_cache_suffix()`；顺带接上**原本零引用的** `roi_cache_suffix()`（旧实现只加布尔 `_roi`，改 ROI 后仍命中旧 OCR）。+3 条测试，已用 `git stash` 证明「修复前 2 failed」。全量 `251 passed`。`dpi` 按原边界明确不做并已在 docstring 说明 |
| 2026-09-22 | **P2-1 实施完成**：两处下公差改走 `_normalize_minus_tol(_safe_float(...))` + `None` 时补 debug 日志。全文件 27 处 `tol_cmd.` 调用已逐条清点，**无第三处漏网**。+14 条测试（矩阵含 `show_negative` 维度 —— 实施时才发现 `show_negative=False` 才是「丢行」那条路径，现场默认即走它），已用 `git stash` 证明「修复前 10 failed / 7 passed」。全量 `265 passed`。登记一条待真机确认的遗留观察（`SegmentAxis(j)` 单参调用）。本文件基线数字 248 → 265 |
| 2026-09-22 | **P2-1 续 + 真机诊断落地**：补「COM **抛异常**」路径（新增 `_safe_com_float()`）；新增 `dump-tols` 只读诊断子命令（三态 `ok`/`COM_FAILED`/`RAISED`，汇总「下公差不可用」的行）。+12 条测试，全量 `277 passed`。两条「有牙」证明：回退到 HEAD → 6 failed（全是抛异常用例）；回退到 `6f77f72`（P2-1 前）→ 16 failed（三种失效路径全覆盖）。**`SegmentAxis(j)` 遗留观察结案**（2024.1 上单参合法）。本文件基线 265 → 277 |
| 2026-09-22 | **真机实测（PC-DMIS 2024.1 / `马丁测试-2026-08-28-B版.PRG`，242 命令）**：P2-1 条件**复现不了**（42 条记录 `minus_tol is None` = 0、抛异常 0）⇒ 真机清单该条需换程序。`CC_1`–`CC_4` 是被改动直接覆盖的区段区分支、下公差为真值 `0.0`，实测仍判**合格**（健康路径未被改坏）。`CC_15`/`CC_16` 成为 **P2-2 现成样本**，并暴露两个新边界：标量 plus/minus 与 `deviation.d` **不同源**、`outtol` 同样「首个写入者优先」导致超差短路失效（详见 P2-2「现场实测补充」） |
| 2026-09-22 | 顺带确认实现前提：本机 `cmds.Item(i)` 对每个索引都抛 **TypeError**，必须靠 `_get_command_at()` 的回退链取命令（诊断子命令复用之，未另写一套） |
| 2026-09-22 | **P1-4 实施完成**：`export_config.txt` 改按 UTF-16（带 BOM）写，对齐 BAS 读侧 `OpenTextFile(..., -1)`。本机复核根因：已部署文件 74 字节、前 4 字节 `44 3A 5C 41`、无 BOM；全仓仅一个写入方。+1 条测试，并**修正**原有那条按 utf-8 读回的测试（它过去通过正是 bug 被漏过的原因）。已用 `git stash` 证明「修复前 2 failed」（`assert b'C:' == b'\xff\xfe'`）。全量 `278 passed`。登记两条真机前置事实：编码修复不自动生效（需重新部署）；重新部署会同时把 CSV 落盘位置从旧项目路径换成 `cm2xl\data\reports`。本文件基线 277 → 278 |
