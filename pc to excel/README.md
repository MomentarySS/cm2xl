# PCDMIS 按需 Excel 测量报告

轻量工具：从 PCDMIS 当前已测数据导出 **PC-DMIS 原生格式 Excel**，按序号填入厂内出货表，或向 PRG 植入导出命令块。

**v1.4.5**：兼容 PC-DMIS 2022.1–2026.1（ProgID 自动发现 + 兜底列表）；界面见 v1.4.3；BONUS 待样例。

## 快速开始

```bat
pip install -r requirements.txt
python main.py
```

打包：`build.bat` → `dist\PCDMIS按需Excel报告.exe`

## 文档

- [用户手册.md](用户手册.md)

## 命令行

```bat
python cli.py export -o reports\out.xlsx
python cli.py fill-form --form "出货.xlsx"
python cli.py inject
```
