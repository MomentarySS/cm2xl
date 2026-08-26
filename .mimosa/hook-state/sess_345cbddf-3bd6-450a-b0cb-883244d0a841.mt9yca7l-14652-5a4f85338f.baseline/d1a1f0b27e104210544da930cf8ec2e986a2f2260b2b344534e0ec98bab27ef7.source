# CMMFiller — 三坐标测量报告自动填充工具

## 项目简介
从 CMM 三坐标测量 PDF 报告中自动 OCR 识别数据，填充到 Excel 模板中。
- 零件名：R590-微调套筒（示例）
- OCR 引擎：PaddleOCR（中文，模型内置完全离线）
- Excel 模板：`templates/模板2.xlsx`，Sheet 名 `FAI`

## 目录结构
```
templates/           Excel 模板（模板1.xlsx、模板2.xlsx）
samples/             测试 PDF 样本（0624-001 ~ 0709-002，50 个）
outputs/             处理输出（开发模式默认）
models/paddleocr/    内置 OCR 模型（约 18MB，.gitignore 忽略）
hooks/               PyInstaller hooks
installer/           Inno Setup 脚本（CMMFiller.iss，未编译）
docs/                安装与使用说明 PDF + 生成脚本
cmm_filler_v10.py    核心逻辑（OCR→解析→Excel 填充）
cmm_filler_gui.py    CustomTkinter GUI（拖拽/预览/NG 统计）
template_wizard.py   tkinter 模板配置向导（GUI 内以模态对话框运行）
ocr_engine.py        PaddleOCR 封装（强校验内置模型，禁止联网下载）
version.py           版本信息（v1.0.0）
```

## 当前配置（%LOCALAPPDATA%\CMMFiller\template_config.json 优先）
- sheet_name: FAI
- data_start_row: 10, sample_row: 9
- 列映射：serial=A, spec=C, upper_tol=D, lower_tol=E
- 样品列：1#=H ~ 5#=L；max_data_row 可选（缺省时自动扫模板规格列末行+5 缓冲）
- 零件名写入 D5，日期写入 P4

## 核心接口（2026-08-22 起）
- `analyze_pdfs(pdf_folder)` — 只 OCR+解析不写 Excel，返回结构化结果（供 GUI 预览）
- `batch_process_by_date(..., excluded_measures=None)` — excluded_measures 为
  `{pdf_stem: {测量项编号}}`，被剔除项不写入实测值
- `export_summary_workbook(pdf_paths, output_folder)` — 汇总导出：挑选的多份 PDF
  写入单 Excel，每 PDF 一个 Sheet（CMM Dimensions Report 汇总样式：行1 合并大标题、
  行2 零件名/日期/序列号、行3 表头 10 列[坐标系/补偿留空]、行4+ 数据，
  NG 行实际值/误差/趋势红字、趋势=超差量、数字格式 0.0000）；输出 `数据汇总_YYYYMMDD_HHMM.xlsx`
- 测量项自带 `ng` 字段（实测超差判定，`_is_ng()`），summary 含 `ng_count`
- CLI 行为不变，新参数全部可选
- GUI 第三个 Tab「汇总导出」：多选/拖拽 PDF 文件列表（去重保序）→ 生成汇总 Excel；
  与「处理」页共用输出文件夹设置

## 最近完成的工作（2026-08-21 ~ 08-22）

### Bug 修复
1. **OCR「写到 API」问题**：PaddleOCR 找不到内置模型时会静默联网下载
   （paddleocr.bj.bcebos.com），工厂内网不通即失败。触发条件 = 打包版
   `_internal/models/paddleocr` 缺失（用户只拷 exe / 杀软删文件）。
   修复：ocr_engine.py 初始化前强校验模型，缺失时弹中文提示；GUI 补写 run.log
2. 死代码清理：删除 initialize_template/fill_by_desc_match（约 100 行）和向导
   _refresh_preview 残码
3. 行上限 34 硬编码改为 `_get_max_data_row()`（配置项 > 模板扫描 > 回退默认），
   超限项打 warning 不再静默丢弃

### 新功能（UI 升级）
1. **拖拽**：模板/PDF/输出三个输入框支持拖文件夹或文件（tkinterdnd2）
2. **处理前预览**：识别结果表格展示，可勾选剔除误识别项再落 Excel（默认开启，可关）
3. **NG 超差统计**：预览和结果页红色高亮 + 汇总徽章
4. **Tabview 双页布局**（处理/结果）、日志按级别着色、统计徽章卡
5. **向导模态化**：TemplateWizard(parent) 共用主窗口 Tk 实例，
   彻底消灭「两个 tk.Tk() 冲突」和子进程依赖
6. **首次运行引导**：settings.json 为空 → 模态引导窗（三路径实时 ✓/✗
   校验、支持拖拽；完成或跳过均保存，下次不再打扰）

### 样品列拓展（2026-08-22）
1. **修复溢出覆盖 bug**：同日期 >6 份时 7#/8# 全写 H 列互相覆盖
   （历史样本最多 6 份从未暴露）。现溢出样品按顺序占用样品位
   （第 1 个溢出 → 1# 位，第 2 个 → 2# 位…），每组上限 = 2×主样品数，
   超出截断并记 skipped + 告警
2. **主样品数可配**：配置项 `main_sample_count`（默认 5，范围 1-20），
   模板有几个样品位就填几个，超出才溢出；向导「其他设置」下拉可选 1-10
3. **非连续样品列**：清空/写入按样品位列表遍历（如 1#=H,2#=K,3#=N 不再清错）
4. **向导下拉扩到 A-Z**（原只到 L 列，模板列在 M 之后无法配置）

### 汇总导出 + 解析修复（2026-08-22）
1. **新功能「汇总导出」**：挑多个 PDF → 单 Excel 每 PDF 一个 Sheet，
   Calypso Dimensions Report 风格（见核心接口）。回归：test_summary_export.py
   （8 PDF 逐列核对 / NG 红字 / sheet 名净化 / GUI 冒烟）
2. **修复既有解析 bug**：测量项行头后紧跟的行号伪影（纯整数如 '1'）会把
   理论值/公差/实测 4 数窗口错位（FAI_12 首当其冲，16/52 份样本受影响）。
   现跳过「当前项尚未收集到数字时出现的无小数点整数」；
   已对 52 份缓存样本全量 diff 验证只修不错，批处理 50 份回归 0 失败

### 打包瘦身（984MB → 627MB，-36%）
- spec excludes：llvmlite/numba/matplotlib/pandas/skimage/networkx/imageio/
  fontTools/cryptography/docx（paddlex 连带的训练侧依赖，推理链不用）
- scipy 按需收集（只留 ndimage/special/io 三个子包）
- cv2 的 ffmpeg 视频 DLL 打包后删除（build.bat 步骤 3.5 自动做）
- 进一步方案：换 onnxruntime 推理可到 ~400MB（需转模型重测，未做）

## 运行方式
```bash
# CLI 模式
python cmm_filler_v10.py

# GUI 模式
python cmm_filler_v10.py --gui

# 模板配置向导（独立窗口）
python template_wizard.py

# 导出标准模板
python cmm_filler_v10.py --export-template -f samples/

# 汇总导出回归测试（含 GUI 冒烟）
python test_summary_export.py
```

## 打包
```bash
build.bat    # 模型检查 → PyInstaller → fix_dist → 删 ffmpeg DLL → 校验
```
产物在 `dist/CMMFiller/`（约 627MB），双击 exe 直接开 GUI，离线可用。

## 注意事项
- 配置优先级：%LOCALAPPDATA%\CMMFiller\ > 项目目录 template_config.json
- 日志输出到 stdout 和 %LOCALAPPDATA%\CMMFiller\run.log（GUI 模式也写）
- OCR 缓存 %LOCALAPPDATA%\CMMFiller\cache\，避免重复识别
- 日期组按日期自动分组，1#-5# 放主 Sheet，6#+ 复制成 Sheet B
- **开发注意**：本机 Mimosa 安全 hook 禁止用 Bash 写 .py（含 cp 备份），
  必须走 Edit/Write；subprocess/os.startfile 一律被拦，GUI 中如需打开文件
  用剪贴板复制路径方案
- **改核心代码后必须跑小批量 OCR 回归**（10+ 份 PDF，检查输出 Excel 每列
  实测值）——曾有缩进错误导致实测值只写最后一列，靠逐列检查才发现
