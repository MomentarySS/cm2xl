"""
生成 CMMFiller 安装与使用说明 PDF
运行: python docs/generate_user_guide.py
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fpdf import FPDF

DOCS_DIR = Path(__file__).resolve().parent
OUTPUT_PDF = DOCS_DIR / 'CMMFiller_安装与使用说明.pdf'
FONT_PATH = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'msyh.ttc'
from version import __version__ as VERSION
TODAY = date.today().strftime('%Y-%m-%d')


class GuidePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font('YaHei', '', str(FONT_PATH))
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('YaHei', size=9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, 'CMMFiller 安装与使用说明', align='R', new_x='LMARGIN', new_y='NEXT')
        self.ln(1)

    def footer(self):
        self.set_y(-14)
        self.set_font('YaHei', size=9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f'第 {self.page_no()} 页', align='C')

    def cover(self):
        self.add_page()
        self.ln(50)
        self.set_font('YaHei', size=28)
        self.set_text_color(0, 51, 102)
        self.cell(0, 16, 'CMMFiller', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)
        self.set_font('YaHei', size=20)
        self.cell(0, 12, '三坐标测量报告自动填充工具', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(8)
        self.set_font('YaHei', size=14)
        self.set_text_color(80, 80, 80)
        self.cell(0, 10, '安装与使用说明', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(30)
        self.set_font('YaHei', size=11)
        self.cell(0, 8, f'版本：{VERSION}', align='C', new_x='LMARGIN', new_y='NEXT')
        self.cell(0, 8, f'日期：{TODAY}', align='C', new_x='LMARGIN', new_y='NEXT')

    def chapter(self, title: str):
        self.ln(4)
        self.set_font('YaHei', size=16)
        self.set_text_color(0, 51, 102)
        self.cell(0, 12, title, new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(0, 102, 204)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def section(self, title: str):
        self.ln(2)
        self.set_font('YaHei', size=13)
        self.set_text_color(0, 80, 160)
        self.cell(0, 10, title, new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def paragraph(self, text: str):
        self.set_font('YaHei', size=11)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 7, text)
        self.ln(2)

    def bullet(self, text: str):
        self.set_font('YaHei', size=11)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 7, f'  - {text}')
        self.ln(1)

    def numbered(self, num: int, text: str):
        self.set_font('YaHei', size=11)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 7, f'  {num}. {text}')
        self.ln(1)

    def code_block(self, text: str):
        self.set_fill_color(245, 245, 245)
        self.set_font('YaHei', size=10)
        self.set_text_color(50, 50, 50)
        for line in text.strip().splitlines():
            self.cell(0, 6, '  ' + line, fill=True, new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

    def table(self, headers: list[str], rows: list[list[str]], col_widths: list[int] | None = None):
        if col_widths is None:
            width = 190 / len(headers)
            col_widths = [width] * len(headers)
        self.set_font('YaHei', size=10)
        self.set_fill_color(230, 240, 250)
        self.set_text_color(0, 51, 102)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border=1, fill=True)
        self.ln()
        self.set_text_color(30, 30, 30)
        for row in rows:
            self.set_font('YaHei', size=10)
            max_h = 8
            for i, cell in enumerate(row):
                x, y = self.get_x(), self.get_y()
                self.multi_cell(col_widths[i], 7, cell, border=1)
                max_h = max(max_h, self.get_y() - y)
                self.set_xy(x + col_widths[i], y)
            self.ln(max_h)
        self.ln(3)


def build_pdf() -> Path:
    pdf = GuidePDF()
    pdf.cover()

    # 1. 简介
    pdf.add_page()
    pdf.chapter('1. 软件简介')
    pdf.paragraph(
        'CMMFiller 是一款面向制造业质量检验场景的桌面工具，用于从 CMM（三坐标测量机）'
        'PDF 报告中自动识别测量数据，并填充到 Excel 检验记录模板中。'
    )
    pdf.paragraph('主要功能：')
    pdf.bullet('批量 OCR 识别 CMM PDF 报告中的零件名、日期、测量尺寸')
    pdf.bullet('按日期自动分组，将 1#–5# 样品写入 Sheet A，6# 及以上写入 Sheet B')
    pdf.bullet('自动匹配规格、上下公差，填入对应 Excel 列')
    pdf.bullet('支持导出标准模板（仅规格/公差，不含实测值）')
    pdf.bullet('提供模板配置向导，适配不同 Excel 模板结构')

    # 2. 系统要求
    pdf.chapter('2. 系统要求')
    pdf.table(
        ['项目', '要求'],
        [
            ['操作系统', 'Windows 10 / 11（64 位）'],
            ['内存', '建议 8 GB 及以上'],
            ['磁盘空间', '安装包约 500 MB；首次运行需额外下载 OCR 模型约 30 MB'],
            ['网络', '首次运行 OCR 需联网下载模型；之后可离线使用'],
            ['其他', '处理前请关闭正在编辑的输出 Excel 文件'],
        ],
        [40, 150],
    )

    # 3. 安装
    pdf.chapter('3. 安装方式')
    pdf.section('3.1 打包版（推荐给最终用户）')
    pdf.numbered(1, '获取软件文件夹 dist\\CMMFiller\\（或安装包解压/安装后的目录）。')
    pdf.numbered(2, '双击 launch.bat，或直接运行 CMMFiller.exe --gui 启动图形界面。')
    pdf.numbered(3, '首次启动若提示 Windows 安全警告，选择「仍要运行」或添加信任。')
    pdf.paragraph('打包版默认路径：')
    pdf.bullet('内置模板：程序目录\\_internal\\templates\\模板2.xlsx')
    pdf.bullet('配置文件：%LOCALAPPDATA%\\CMMFiller\\template_config.json')
    pdf.bullet('OCR 缓存：%LOCALAPPDATA%\\CMMFiller\\cache\\')
    pdf.bullet('默认输出：%LOCALAPPDATA%\\CMMFiller\\outputs\\')
    pdf.bullet('运行日志：%LOCALAPPDATA%\\CMMFiller\\run.log')

    pdf.section('3.2 开发版（程序员/调试）')
    pdf.code_block(
        'pip install -r requirements.txt\n'
        'set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python\n'
        'python cmm_filler_v10.py --gui'
    )
    pdf.paragraph('开发版默认 PDF 样本目录为 samples\\，输出目录为 outputs\\。')

    # 4. 快速开始
    pdf.chapter('4. 快速开始（5 步上手）')
    pdf.numbered(1, '启动软件，进入图形界面。')
    pdf.numbered(2, '选择 Excel 模板（默认使用模板2.xlsx，可点击「浏览」更换）。')
    pdf.numbered(3, '选择包含 CMM PDF 报告的文件夹（文件名格式如 0709-001.PDF）。')
    pdf.numbered(4, '选择输出文件夹（打包版默认为 AppData 下的 outputs 目录）。')
    pdf.numbered(5, '点击「开始处理」，等待日志显示「处理完成」。')
    pdf.paragraph('处理完成后，点击「打开输出」查看生成的 Excel 文件。')

    # 5. 界面说明
    pdf.add_page()
    pdf.chapter('5. 界面功能说明')
    pdf.table(
        ['区域/按钮', '说明'],
        [
            ['Excel 模板', '选择要填充的目标 Excel 文件'],
            ['PDF 文件夹', '存放 CMM 测量报告 PDF 的目录'],
            ['输出文件夹', '生成的汇总 Excel 保存位置'],
            ['开始处理', '批量 OCR 并按日期分组填充 Excel'],
            ['导出标准模板', '从 PDF 提取规格/公差，生成标准模板（不含实测值）'],
            ['模板配置', '打开模板配置向导，设置列映射和字段位置'],
            ['打开输出', '在资源管理器中打开输出文件夹'],
            ['处理日志', '实时显示 OCR 进度、识别结果和错误信息'],
        ],
        [45, 145],
    )

    # 6. 输出文件
    pdf.chapter('6. 输出文件说明')
    pdf.section('6.1 项目汇总文件')
    pdf.paragraph('文件名格式：{日期}_项目汇总.xlsx，例如 2026-07-09_项目汇总.xlsx')
    pdf.bullet('Sheet A：存放样品 1#–5# 的实测数据')
    pdf.bullet('Sheet B：存放样品 6# 及以上的溢出数据')
    pdf.bullet('自动写入零件名、检验日期等头部信息')

    pdf.section('6.2 标准模板文件')
    pdf.paragraph('文件名格式：标准模板_{日期}_已填描述.xlsx')
    pdf.paragraph('包含从 PDF 提取的规格、上公差、下公差，不含实测测量值，可用于检验规程参考。')

    pdf.section('6.3 自动备份')
    pdf.paragraph(
        '若输出文件已存在且被占用，程序会自动等待并重试保存。'
        '覆盖已有文件前，会自动生成 _bak_时间戳.xlsx 备份。'
    )

    # 7. 模板配置
    pdf.chapter('7. 模板配置向导')
    pdf.paragraph('当更换 Excel 模板或列位置发生变化时，使用「模板配置」向导：')
    pdf.numbered(1, '选择 Excel 模板文件和工作表（Sheet）。')
    pdf.numbered(2, '指定数据起始行、样品序号行。')
    pdf.numbered(3, '映射列：序号、规格、上公差、下公差。')
    pdf.numbered(4, '映射样品列：1#、2#、3# … 对应 Excel 列。')
    pdf.numbered(5, '设置零件名、日期的写入单元格位置。')
    pdf.numbered(6, '保存配置到 %LOCALAPPDATA%\\CMMFiller\\template_config.json。')
    pdf.paragraph('配置保存后，主程序会自动读取，无需重启。')

    # 8. 命令行
    pdf.add_page()
    pdf.chapter('8. 命令行用法（高级）')
    pdf.paragraph('打包版可在 cmd 中运行 CMMFiller.exe，支持以下参数：')
    pdf.code_block(
        'CMMFiller.exe --gui                    启动图形界面\n'
        'CMMFiller.exe --wizard                 启动模板配置向导\n'
        'CMMFiller.exe -f D:\\PDFs -o D:\\out     指定 PDF 目录和输出目录\n'
        'CMMFiller.exe -t 模板.xlsx -f D:\\PDFs  指定模板和 PDF 目录\n'
        'CMMFiller.exe --export-template -f D:\\PDFs  导出标准模板'
    )

    # 9. PDF 命名规则
    pdf.chapter('9. PDF 文件命名规则')
    pdf.paragraph('程序根据 PDF 文件名解析样品序号和日期组：')
    pdf.bullet('标准格式：MMDD-NNN.PDF，例如 0709-001.PDF 表示 7 月 9 日第 1 个样品')
    pdf.bullet('同日期 PDF 自动归为一组，生成一份汇总 Excel')
    pdf.bullet('误操作文件（如 003-1.PDF）会被自动忽略')
    pdf.paragraph('请确保 PDF 为 CMM 设备导出的标准测量报告，扫描件需清晰可读。')

    # 10. 常见问题
    pdf.chapter('10. 常见问题与排查')
    faq = [
        ('首次运行很慢？', '若已打包内置 OCR 模型则无需下载；开发版首次运行需联网下载约 17-30 MB 模型到 models/paddleocr/。'),
        ('提示 Excel 保存失败？', '请关闭正在打开的输出 Excel 文件，程序会自动重试最多 5 次。'),
        ('OCR 识别不准确？', '检查 PDF 清晰度；删除 cache 目录下对应缓存后重新处理；适当提高 DPI（默认 300）。'),
        ('切换模板后报错？', '运行模板配置向导，确认 Sheet 名、列映射和数据起始行正确。'),
        ('打包版找不到模板？', '使用「浏览」手动选择模板，或通过向导重新配置 template_path。'),
        ('protobuf 冲突报错？', '开发版运行时设置环境变量：PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python'),
        ('如何查看详细日志？', '打开 %LOCALAPPDATA%\\CMMFiller\\run.log'),
    ]
    for q, a in faq:
        pdf.section(q)
        pdf.paragraph(a)

    # 11. 目录结构
    pdf.add_page()
    pdf.chapter('11. 附录：关键路径速查')
    pdf.table(
        ['路径', '用途'],
        [
            ['dist\\CMMFiller\\CMMFiller.exe', '打包版主程序'],
            ['launch.bat', '快捷启动 GUI'],
            ['templates\\模板2.xlsx', '默认 Excel 模板（开发版）'],
            ['samples\\', '测试 PDF 样本（开发版）'],
            ['outputs\\', '输出目录（开发版）'],
            ['%LOCALAPPDATA%\\CMMFiller\\', '配置、缓存、日志（打包版）'],
        ],
        [70, 120],
    )

    pdf.chapter('12. 技术支持')
    pdf.paragraph('遇到问题时，请收集以下信息以便排查：')
    pdf.bullet('软件版本（当前 v' + VERSION + '）')
    pdf.bullet('问题 PDF 样例（可脱敏）')
    pdf.bullet('%LOCALAPPDATA%\\CMMFiller\\run.log 日志文件')
    pdf.bullet('使用的 Excel 模板文件')
    pdf.paragraph('- 文档结束 -')

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT_PDF))
    return OUTPUT_PDF


if __name__ == '__main__':
    path = build_pdf()
    print(f'已生成: {path}')
