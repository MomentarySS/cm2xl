# CMM 报告填充（cmm_filler）

从 CMM 三坐标 **PDF 报告** OCR 识别测量数据，按 Excel 模板自动填充；支持多页 PDF、文字层快通道、NG 统计导出。

## 典型流程

1. 准备 **Excel 模板**（内置「模板1/模板2」，或用「模板配置」向导自定义列映射）。
2. 选择 **PDF 文件夹**（可拖放文件夹到输入框）。
3. 选择 **输出文件夹**。
4. 可选：开启「处理前预览识别结果」，修正低置信度项。
5. 点击 **▶ 开始处理**。

## 主要功能页

| 页签 | 说明 |
|------|------|
| 处理 | 批量 PDF → 按日期/件号分组写入 Excel |
| 汇总 | 多 PDF 汇总到一个 Excel（每 PDF 一 Sheet） |
| NG 分析 | 文件夹内 NG 项排行，导出统计 Excel |
| 结果 | 成功/失败统计与输出文件列表 |

## 报告版式（Profile）

- 设置 → OCR / 报告版式：可选 FAI 默认、PC-DMIS 等 Profile。
- 支持自定义前缀（FAI、CC、DIM 等）与子编号冲突处理（预览页紫色高亮）。

## 维护

- **查看日志路径**：顶栏「关于」→ 复制或打开日志文件夹
- **查看日志**：处理页「📃 查看日志」（打开 `CMMFiller.log` 内容）
- **清理 OCR 缓存**：「设置」→ OCR 模型区，或处理页「🧹 清理 OCR 缓存」
- 启动时若日志总量超过约 100MB，会自动删除最旧日志文件

## CLI（可选）

```bash
python -m modules.cmm_filler.cli fill --pdf-folder ... --template ... --output ...
python -m modules.cmm_filler.cli ng-stats --pdf-folder ... --output ...
```

## 常见问题

- **首次 OCR 较慢**：PaddleOCR 模型加载约 10–30 秒，属正常现象。
- **识别列错位**：在设置中调整 ROI 或切换报告 Profile；扫描件依赖 OCR 表格对齐。
- **路径含中文**：建议安装路径与 BAS 部署路径避免空格；PDF/模板路径一般可用中文。

## 配置位置

`%LOCALAPPDATA%\cm2xl\config\cmm_filler\settings.json`
