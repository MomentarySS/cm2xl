"""
CMMFiller CLI 入口
提供命令行操作能力（与 GUI 并存）。

用法：
  python -m modules.cmm_filler.cli --help
"""

import argparse
import sys
import logging
from pathlib import Path

from ..app_meta import __version__
from .core.filler import CMMReportFiller

logger = logging.getLogger('CMMFiller')
logging.basicConfig(level=logging.INFO, format='%(message)s')


def cmd_process(args):
    """批量处理 PDF 文件夹"""
    filler = CMMReportFiller(args.template, dpi=args.dpi)
    summary = filler.batch_process_by_date(args.pdf_folder, args.output)
    print(f"处理完成：成功 {summary['processed_pdfs']}/{summary['total_pdfs']}，"
          f"失败 {len(summary['failed_pdfs'])}，"
          f"输出 {len(summary['output_files'])} 个文件")


def cmd_export_template(args):
    """导出标准模板（不含实测值）"""
    filler = CMMReportFiller(args.template, dpi=args.dpi)
    summary = filler.export_standard_template(args.pdf_folder, args.output)
    print(f"导出完成：成功 {summary['processed_pdfs']}/{summary['total_pdfs']}，"
          f"输出 {summary['output_file']}")


def cmd_summary(args):
    """汇总多 PDF 到单个 Excel"""
    filler = CMMReportFiller(args.template, dpi=args.dpi)
    summary = filler.export_summary_workbook(args.pdfs, args.output)
    print(f"汇总完成：{summary['sheet_count']} 个 Sheet，"
          f"NG {summary['ng_count']} 项，输出 {summary['output_file']}")


def main():
    parser = argparse.ArgumentParser(
        description=f'CMMFiller CLI (v{__version__})',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest='command')

    p = sub.add_parser('process', help='批量处理 PDF 文件夹')
    p.add_argument('-t', '--template', required=True, help='Excel 模板路径')
    p.add_argument('-f', '--pdf-folder', required=True, help='PDF 文件夹')
    p.add_argument('-o', '--output', required=True, help='输出文件夹')
    p.add_argument('--dpi', type=int, default=300, help='PDF 渲染 DPI（默认 300）')
    p.set_defaults(func=cmd_process)

    e = sub.add_parser('export-template', help='导出标准模板（规格+公差，不含实测值）')
    e.add_argument('-t', '--template', required=True, help='Excel 模板路径')
    e.add_argument('-f', '--pdf-folder', required=True, help='PDF 文件夹')
    e.add_argument('-o', '--output', required=True, help='输出文件夹')
    e.add_argument('--dpi', type=int, default=300, help='PDF 渲染 DPI（默认 300）')
    e.set_defaults(func=cmd_export_template)

    s = sub.add_parser('summary', help='汇总多个 PDF 到单个 Excel')
    s.add_argument('-t', '--template', required=True, help='Excel 模板路径')
    s.add_argument('-p', '--pdfs', nargs='+', required=True, help='PDF 文件列表')
    s.add_argument('-o', '--output', required=True, help='输出文件夹')
    s.add_argument('--dpi', type=int, default=300, help='PDF 渲染 DPI（默认 300）')
    s.set_defaults(func=cmd_summary)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()
