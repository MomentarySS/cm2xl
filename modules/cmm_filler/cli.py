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

from .app_meta import __version__
from .core.filler import CMMReportFiller

logger = logging.getLogger('CMMFiller')
logging.basicConfig(level=logging.INFO, format='%(message)s')


def _parse_roi_arg(roi_str: str | None) -> dict | None:
    """解析 ROI 参数，格式：top,left,bottom,right（百分比 0-100）。"""
    if not roi_str:
        return None
    parts = [p.strip() for p in roi_str.split(',')]
    if len(parts) != 4:
        raise ValueError('ROI 格式应为 top,left,bottom,right（百分比）')
    keys = ('top', 'left', 'bottom', 'right')
    return {k: float(parts[i]) / 100.0 for i, k in enumerate(keys)}


def _add_profile_args(p):
    p.add_argument('--profile', default='default', help='报告 Profile 名称（default / hexagon_pc_dmis）')
    p.add_argument('--roi', default=None, help='OCR 裁剪 ROI：top,left,bottom,right 百分比，如 18,0,2,0')
    p.add_argument('--extra-prefix', default=None, help='额外尺寸前缀，逗号分隔（叠加到 Profile）')


def _filler_from_args(args, template: str) -> CMMReportFiller:
    from .core.report_profile import parse_prefix_text
    extra = parse_prefix_text(args.extra_prefix) if args.extra_prefix else None
    return CMMReportFiller(
        template, dpi=args.dpi,
        report_profile=args.profile,
        ocr_roi=_parse_roi_arg(args.roi),
        custom_item_prefixes=extra,
    )


def cmd_process(args):
    """批量处理 PDF 文件夹"""
    filler = _filler_from_args(args, args.template)
    summary = filler.batch_process_by_date(args.pdf_folder, args.output)
    print(f"处理完成：成功 {summary['processed_pdfs']}/{summary['total_pdfs']}，"
          f"失败 {len(summary['failed_pdfs'])}，"
          f"输出 {len(summary['output_files'])} 个文件")


def cmd_export_template(args):
    """导出标准模板（不含实测值）"""
    filler = _filler_from_args(args, args.template)
    summary = filler.export_standard_template(args.pdf_folder, args.output)
    print(f"导出完成：成功 {summary['processed_pdfs']}/{summary['total_pdfs']}，"
          f"输出 {summary['output_file']}")


def cmd_summary(args):
    """汇总多 PDF 到单个 Excel"""
    filler = _filler_from_args(args, args.template)
    summary = filler.export_summary_workbook(args.pdfs, args.output)
    print(f"汇总完成：{summary['sheet_count']} 个 Sheet，"
          f"NG {summary['ng_count']} 项，输出 {summary['output_file']}")


def cmd_ng_stats(args):
    """导出 NG 统计分析"""
    filler = _filler_from_args(args, args.template)
    summary = filler.export_ng_analysis(args.pdf_folder, args.output)
    print(f"NG 分析完成：{summary['processed_pdfs']}/{summary['total_pdfs']} 份报告，"
          f"NG {summary['ng_count']} 次，输出 {summary['output_file']}")


def cmd_tables(args):
    """通用 PDF 表格提取（需 pdfplumber）"""
    from .core.pdf_table_import import batch_export_pdf_tables
    paths = list(args.pdfs or [])
    if args.pdf_folder:
        from utils.file_io import glob_pdfs
        paths.extend(str(p) for p in glob_pdfs(Path(args.pdf_folder)))
    summary = batch_export_pdf_tables(paths, args.output)
    print(f"表格提取：{summary['processed']}/{summary['total']}，失败 {len(summary['failed'])}")


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
    _add_profile_args(p)
    p.set_defaults(func=cmd_process)

    e = sub.add_parser('export-template', help='导出标准模板（规格+公差，不含实测值）')
    e.add_argument('-t', '--template', required=True, help='Excel 模板路径')
    e.add_argument('-f', '--pdf-folder', required=True, help='PDF 文件夹')
    e.add_argument('-o', '--output', required=True, help='输出文件夹')
    e.add_argument('--dpi', type=int, default=300, help='PDF 渲染 DPI（默认 300）')
    _add_profile_args(e)
    e.set_defaults(func=cmd_export_template)

    s = sub.add_parser('summary', help='汇总多个 PDF 到单个 Excel')
    s.add_argument('-t', '--template', required=True, help='Excel 模板路径')
    s.add_argument('-p', '--pdfs', nargs='+', required=True, help='PDF 文件列表')
    s.add_argument('-o', '--output', required=True, help='输出文件夹')
    s.add_argument('--dpi', type=int, default=300, help='PDF 渲染 DPI（默认 300）')
    _add_profile_args(s)
    s.set_defaults(func=cmd_summary)

    n = sub.add_parser('ng-stats', help='NG 统计分析导出')
    n.add_argument('-t', '--template', required=True, help='Excel 模板路径（用于加载配置）')
    n.add_argument('-f', '--pdf-folder', required=True, help='PDF 文件夹')
    n.add_argument('-o', '--output', required=True, help='输出文件夹')
    n.add_argument('--dpi', type=int, default=300, help='PDF 渲染 DPI（默认 300）')
    _add_profile_args(n)
    n.set_defaults(func=cmd_ng_stats)

    tbl = sub.add_parser('tables', help='通用 PDF 表格提取（需 pdfplumber）')
    tbl.add_argument('-o', '--output', required=True, help='输出文件夹')
    tbl.add_argument('-f', '--pdf-folder', default=None, help='PDF 文件夹')
    tbl.add_argument('-p', '--pdfs', nargs='*', default=None, help='PDF 文件列表')
    tbl.set_defaults(func=cmd_tables)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()
