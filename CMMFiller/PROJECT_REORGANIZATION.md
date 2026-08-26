# CMMFiller 项目整理说明

> **⚠️ 历史文档**：本文档记录 2026-07-10 的一次性整理操作，目录结构此后又有
> 变化（构建文件已回到根目录、新增 samples/outputs 拆分等），当前结构以
> `README.md` 为准。

整理日期：2026-07-10

## 整理前的问题

- 构建文件（build.bat / launch.bat / fix_dist.py / CMMFiller.spec / hooks/）散落在根目录
- templates/ 下 50 个 PDF 测试样本和 2 个 Excel 模板混在一起
- test_outputs/ 有大量 _bak_ 备份文件和 mb1/mb2 重复副本
- 没有 .gitignore

## 整理后的目录结构

```
D:\AI\Cursor\20060709-R\
├── build.bat                 # PyInstaller 打包脚本
├── launch.bat                # 启动 GUI 快捷方式
├── fix_dist.py               # 打包后修复脚本
├── CMMFiller.spec            # PyInstaller 打包配置
│
├── hooks/                    # PyInstaller hooks
│   ├── hook-customtkinter.py
│   ├── hook-paddleocr.py
│   ├── hook-paddleocr_pre.py
│   ├── paddleocr_fix.py
│   └── rth_paddleocr_fix.py
│
├── templates/                # Excel 模板文件（纯模板）
│   ├── 模板1.xlsx
│   └── 模板2.xlsx
│
├── samples/                  # CMM 测试 PDF 样本（50 个）
│   ├── 0624-001.PDF ~ 0709-002.PDF
│
├── outputs/                  # 程序输出目录（含 _bak_ 备份）
│   ├── 2026-06-24_项目汇总.xlsx
│   ├── 2026-06-24_项目汇总_bak_153115.xlsx
│   ├── ...（30 个文件）
│   ├── mb1/                  # 批量测试输出 1
│   └── mb2/                  # 批量测试输出 2
│
├── cache/                    # OCR 图片缓存
│   ├── *.png（50 个缓存图片）
│   └── ocr_cache.json
│
├── CLAUDE.md                 # 项目说明文档
├── README.md                 # 使用说明
├── .gitignore                # Git 忽略规则
├── cmm_filler_v10.py         # 核心逻辑（PDF→OCR→Excel填充）
├── cmm_filler_gui.py         # GUI 界面
├── template_wizard.py        # 模板配置向导
├── ocr_engine.py             # OCR 引擎封装
├── requirements.txt          # Python 依赖
└── template_config.json      # 当前生效配置
```

## 移动记录

| 原始位置 | 新位置 | 操作 |
|---------|--------|------|
| templates/*.PDF | samples/*.PDF | 移动（50 个 PDF） |
| test_outputs/* | outputs/* | 移动（30 个文件 + mb1/mb2） |
| hooks/ | hooks/（根目录） | 不动（PyInstaller 需要） |
| build.bat 等 | 根目录 | 不动（PyInstaller 在根目录运行） |

## 代码路径变更

### cmm_filler_v10.py

```python
# 变更前
PDF_FOLDER = str(BASE_DIR)
OUTPUT_FOLDER = str(BASE_DIR)

# 变更后
PDF_FOLDER = str(BASE_DIR / 'samples')
OUTPUT_FOLDER = str(BASE_DIR / 'outputs')
```

## .gitignore 规则

- 排除 `cache/`、`outputs/`、`__pycache__/`
- 排除 `*.xlsx`（模板除外）
- 排除 `dist/`、`build/`（PyInstaller 产物）
- 排除 IDE 配置和临时文件

## 注意事项

1. `build.bat` 会在打包前自动删除旧 `build/` 和 `dist/` 目录（PyInstaller 产物）
2. `hooks/` 在项目根目录，PyInstaller 通过相对路径 `hookspath=['hooks']` 引用
3. `CMMFiller.spec` 的 `hookspath` 和 `runtime_hooks` 指向 `hooks/`
4. `samples/` 和 `outputs/` 的路径变更对 GUI 模式同样生效（通过 `BASE_DIR` 自动解析）
