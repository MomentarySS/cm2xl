"""命令行 — 批量导出与命令植入。"""



from __future__ import annotations



import argparse

import sys

from pathlib import Path



from .connector.pcdmis_connector import PcdmisConnector

from .core.models import ToleranceConfig

from .core.tolerance import apply_tolerance

from .export.inspection_form_fill import default_fill_output_path, fill_inspection_form

from .export.template_report import export_report

from .inject.command_injector import deploy_bas_script, inject_export_command

from .utils.local_settings import build_export_filename, ensure_default_dirs, load_settings






def cmd_export(args: argparse.Namespace) -> int:

    ensure_default_dirs()

    settings = load_settings()

    connector = PcdmisConnector()

    info = connector.connect()

    if not info.connected:

        print(info.message, file=sys.stderr)

        return 1



    records = connector.extract_features(

        scope=settings.export_scope if not args.all else "all",

        require_marked=settings.require_marked if not args.all else False,

    )

    tol = ToleranceConfig.from_dict(settings.tolerance)

    apply_tolerance(records, tol)



    header = connector.get_report_header_info()

    out_dir = Path(args.output).parent if args.output else settings.resolved_export_dir()

    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = Path(args.output) if args.output else out_dir / build_export_filename(

        header.part_name or header.program_name or "report"

    )



    export_report(

        records,

        out_path,

        part_name=header.part_name,

        program_path=header.program_name,

        header=header,

    )

    print(f"已导出 {len(records)} 条 → {out_path}")

    return 0





def cmd_fill_form(args: argparse.Namespace) -> int:

    ensure_default_dirs()

    settings = load_settings()

    cfg = settings.form_fill



    if args.prefixes:

        cfg.id_prefixes = [p.strip() for p in args.prefixes.split(",") if p.strip()]

    if args.cmm_codes:

        cfg.cmm_codes = [c.strip().upper() for c in args.cmm_codes.split(",") if c.strip()]

    if args.target_col:

        cfg.target_col = args.target_col.strip().lower()

    if args.form:

        cfg.form_path = args.form

        if getattr(args, "reset_chain", False):

            cfg.last_fill_output = ""


    if getattr(args, "no_chain", False):

        cfg.chain_from_last = False



    form_path, chained = cfg.resolve_input_form()

    if form_path is None:

        print("请指定出货检测表：--form 路径.xlsx", file=sys.stderr)

        return 1



    connector = PcdmisConnector()

    info = connector.connect()

    if not info.connected:

        print(info.message, file=sys.stderr)

        return 1



    records = connector.extract_features(

        scope=settings.export_scope if not args.all else "all",

        require_marked=settings.require_marked if not args.all else False,

    )

    tol = ToleranceConfig.from_dict(settings.tolerance)

    apply_tolerance(records, tol)



    name_base = Path(cfg.form_path) if cfg.form_path else form_path

    out_path = Path(args.output) if args.output else default_fill_output_path(

        name_base, settings.resolved_export_dir()

    )

    if out_path.resolve() == form_path.resolve():

        print("输出路径不能与出货表底稿相同，请另存副本。", file=sys.stderr)

        return 1



    result = fill_inspection_form(records, form_path, out_path, config=cfg)

    result.chained = chained

    cfg.last_fill_output = str(result.output_path)

    settings.form_fill = cfg

    from .utils.local_settings import save_settings



    save_settings(settings)



    mode = "续填" if chained else "新开"

    print(

        f"[{mode}] 底稿 {form_path.name} → 列 {result.target_col} "

        f"填入 {result.filled} 格 → {result.output_path}"

    )

    if result.unmatched_form:

        print(f"表中未匹配: {', '.join(result.unmatched_form[:20])}")

    if result.unmatched_pcdmis:

        print(f"测量多余序号: {', '.join(result.unmatched_pcdmis[:20])}")

    return 0





def cmd_inject(args: argparse.Namespace) -> int:

    bas = deploy_bas_script()

    connector = PcdmisConnector()

    info = connector.connect()

    if not info.connected:

        print(info.message, file=sys.stderr)

        return 1



    from .connector.com_detector import com_apartment, dispatch_pcdmis



    with com_apartment():

        app = dispatch_pcdmis(connector.prog_id)

        result = inject_export_command(app, bas_path=bas)

    print(result.message)

    return 0 if result.success else 1





def main() -> None:

    parser = argparse.ArgumentParser(description="PCDMIS 按需 Excel 测量报告 CLI")

    sub = parser.add_subparsers(dest="command")



    p_export = sub.add_parser("export", help="从 PCDMIS COM 提取并导出 Excel")

    p_export.add_argument("-o", "--output", help="输出 xlsx 路径")

    p_export.add_argument(

        "--all",

        action="store_true",

        help="导出全部数据（含特征/基准），默认仅报告窗口已评价数据",

    )

    p_export.set_defaults(func=cmd_export)



    p_fill = sub.add_parser("fill-form", help="按序号填入出货检测表（仅 CMM 行）")

    p_fill.add_argument("--form", help="出货检测表 xlsx")

    p_fill.add_argument("-o", "--output", help="输出 xlsx（默认另存副本）")

    p_fill.add_argument("--prefixes", help="尺寸前缀，逗号分隔，如 FAI_,CC_,尺寸_")

    p_fill.add_argument("--cmm-codes", help="CMM 检具代号，逗号分隔，如 A 或 A,CMM")

    p_fill.add_argument("--target-col", help="写入列：auto / H / I …")

    p_fill.add_argument("--all", action="store_true", help="提取全部数据")

    p_fill.add_argument("--no-chain", action="store_true", help="不接着上次结果，强制用 --form")

    p_fill.add_argument("--reset-chain", action="store_true", help="清除续填记录并以 --form 新开")

    p_fill.set_defaults(func=cmd_fill_form)



    p_inject = sub.add_parser("inject", help="向当前 PRG 植入导出命令")

    p_inject.set_defaults(func=cmd_inject)



    args = parser.parse_args()

    if not args.command:

        parser.print_help()

        raise SystemExit(0)

    raise SystemExit(args.func(args))





if __name__ == "__main__":

    main()


