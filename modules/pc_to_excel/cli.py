"""命令行 — 批量导出与命令植入。"""



from __future__ import annotations



import argparse

import sys

from pathlib import Path

from typing import Any



from .connector.pcdmis_connector import PcdmisConnector

from .core.models import ToleranceConfig

from .core.tolerance import apply_tolerance

from .export.inspection_form_fill import default_fill_output_path, fill_inspection_form

from .export.template_report import export_report

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





# P1-4 ~ P1-8（脚本输出功能）已于 2026-09-23 取消：
#   cmd_inject / p_inject subparser 移除，对应的 BAS 部署与导出命令
#   植入代码（modules/pc_to_excel/inject/）整目录删除。CLI 不再支持
#   \inject\ 子命令；如需 PCDMIS → CSV 导出，请走 PC-DMIS 工具栏或
#   手动操作。





_DUMP_DIM_FIELDS = (
    "DIM_MEASURED",
    "DIM_DEVIATION",
    "DIM_OUTTOL",
    "DIM_BONUS",
    "F_PLUS_TOL",
    "F_MINUS_TOL",
)

_DUMP_SIZE_METHODS = (
    "sizeText",
    "SizeAxis",
    "sizeNominal",
    "sizeMeasured",
    "sizeDeviation",
    "sizePlusTol",
    "sizeMinusTol",
    "sizeOutOfTol",
    # P3-11.1 诊断：BONUS 列漏填根因定位 —— cm2xl 输出位置度/垂直度/平行度/倾斜度
    # 的 BONUS 列空，但 PC-DMIS 原生写 0。需抓 PC-DMIS COM 返回值（0 / False / 抛异常）
    "sizeBonus",
)

_DUMP_SEG_METHODS = (
    "SegmentAxis",
    "SegmentDimNominal",
    "SegmentDimMeasured",
    "SegmentDimDeviation",
    "SegmentDimPlusTol",
    "segmentDimMinusTol",
    # P3-11.1 诊断：同上
    "segmentDimBonus",
)


def _dump_probe(getter) -> tuple[Any, str]:
    """调用一次 COM getter —— 返回 (原值, 状态)。

    状态刻意区分三种：`ok` / `COM_FAILED`（返回 False/None）/ `RAISED:<异常名>`。
    诊断工具必须分开报，否则「COM 抛异常」会被误当成「返回值不可用」——
    两者在 `_tolerance.py` 里是**不同**的失效路径（前者旧代码直接丢行）。
    """
    from .core._common import _com_failed

    try:
        raw = getter()
    except Exception as exc:
        return None, f"RAISED:{type(exc).__name__}"
    return raw, "COM_FAILED" if _com_failed(raw) else "ok"


def _dump_minus(raw: Any, state: str, show_negative: bool) -> Any:
    """把探针结果折算成生产代码会得到的 minus_tol（先 `_safe_float` 再归一化符号）。

    注意：COM 读回的常是**字符串**（如 `'  -0.010'`），必须过 `_safe_float`；
    直接喂 `_normalize_minus_tol` 会把字符串原样返回，报出误导性的结果。
    """
    from .core._common import _normalize_minus_tol, _safe_float

    if state != "ok":
        return None
    return _normalize_minus_tol(_safe_float(raw), show_negative)


def cmd_dump_tols(args: argparse.Namespace) -> int:
    """只读诊断：转储各命令上/下公差的 COM 读取结果，定位「读不到」的行。

    存在的理由：P2-1（下公差未做 COM 失败防护）的真机验证要求「构造下公差
    读不到的行」，但那没法从 UI 手工制造 COM 故障。这个子命令把当前程序里
    每个 ToleranceCommand / 评价尺寸的公差读取结果原样列出来，
    并在末尾汇总「哪些行的下公差不可用」，让验证从「碰运气找」变成「跑一次拿清单」。
    """
    from .connector.com_detector import com_apartment, com_call_lock
    from .connector.pcdlrn_constants import get_const
    from .core._command_cache import _get_command_at
    from .core.data_extractor import _minus_tol_show_negative

    lines: list[str] = []

    def w(line: str = "") -> None:
        lines.append(line)

    connector = PcdmisConnector()
    info = connector.connect()
    if not info.connected:
        print(info.message, file=sys.stderr)
        return 1

    wanted = (args.filter or "").strip().upper()
    unavailable: list[str] = []
    raised: list[str] = []
    hit = 0

    with com_call_lock:
        with com_apartment():
            app = connector._bind_app()
            part = app.ActivePartProgram
            if part is None:
                print("未找到活动测量程序，请先在 PCDMIS 中打开 .PRG", file=sys.stderr)
                return 1
            show_negative = _minus_tol_show_negative(part)

            w("PCDMIS 下公差诊断（只读）")
            try:
                w(f"程序  : {part.Name}")
            except Exception:
                pass
            w(f"版本  : {info.version}")
            w(f"show_negative = {show_negative}  (PartProgramSettings.MinusTolerancesShowNegative)")

            cmds = part.Commands
            total = int(cmds.Count)
            w(f"命令数: {total}" + (f"   过滤前缀: {wanted}" if wanted else ""))
            w()

            for i in range(1, total + 1):
                try:
                    cmd = _get_command_at(cmds, i)
                except Exception as exc:
                    raised.append(f"idx={i} 命令本身读取失败 RAISED:{type(exc).__name__}")
                    continue
                try:
                    cid = str(cmd.ID or "")
                except Exception:
                    cid = ""
                if wanted and not cid.upper().startswith(wanted):
                    continue
                hit += 1

                try:
                    is_tol = bool(cmd.IsToleranceCommand)
                except Exception:
                    is_tol = False
                try:
                    desc = str(cmd.TypeDescription or "")
                except Exception:
                    desc = ""

                w("=" * 78)
                w(f"[{i}] {cid or '(无 ID)'}   类型={desc}   ToleranceCommand={is_tol}")

                if is_tol:
                    try:
                        tol = cmd.ToleranceCommand
                    except Exception as exc:
                        raised.append(f"idx={i} {cid} ToleranceCommand RAISED:{type(exc).__name__}")
                        w(f"    ToleranceCommand RAISED:{type(exc).__name__}")
                        continue

                    def _int_attr(name: str) -> int:
                        raw, state = _dump_probe(lambda: getattr(tol, name))
                        w(f"    tol.{name:<20} = {raw!r} [{state}]")
                        try:
                            return int(raw)
                        except Exception:
                            return 0

                    w(f"    tol.gdtSymbol            = {_dump_probe(lambda: tol.gdtSymbol)[0]!r}")
                    size_count = _int_attr("sizeCountCombined")
                    seg_count = _int_attr("SegmentCount")
                    feat_count = _int_attr("FeatureCount")

                    for j in range(1, size_count + 1):
                        w(f"    -- 尺寸行 j={j}")
                        for meth in _DUMP_SIZE_METHODS:
                            raw, state = _dump_probe(lambda m=meth, jj=j: getattr(tol, m)(jj))
                            w(f"       {meth:<20}({j}) = {raw!r} [{state}]")
                            if meth == "sizeMinusTol":
                                minus = _dump_minus(raw, state, show_negative)
                                w(f"       → minus_tol = {minus!r}")
                                if minus is None:
                                    unavailable.append(
                                        f"[{i}] {cid} 尺寸行 j={j} （{state}）"
                                    )
                                if state.startswith("RAISED"):
                                    raised.append(
                                        f"[{i}] {cid} sizeMinusTol({j}) {state}"
                                    )

                    for k in range(1, seg_count + 1):
                        for j in range(1, max(feat_count, 1) + 1):
                            w(f"    -- 区段行 k={k} j={j}")
                            for meth in _DUMP_SEG_METHODS:
                                if meth == "SegmentAxis":
                                    getter = lambda m=meth, jj=j: getattr(tol, m)(jj)  # noqa: E731
                                    shown = f"({j})"
                                else:
                                    getter = lambda m=meth, kk=k, jj=j: getattr(tol, m)(kk, jj)  # noqa: E731
                                    shown = f"({k}, {j})"
                                raw, state = _dump_probe(getter)
                                w(f"       {meth:<20}{shown} = {raw!r} [{state}]")
                                if meth == "segmentDimMinusTol":
                                    minus = _dump_minus(raw, state, show_negative)
                                    w(f"       → minus_tol = {minus!r}")
                                    if minus is None:
                                        unavailable.append(
                                            f"[{i}] {cid} 区段行 k={k} j={j} （{state}）"
                                        )
                                    if state.startswith("RAISED"):
                                        raised.append(
                                            f"[{i}] {cid} segmentDimMinusTol({k},{j}) {state}"
                                        )
                else:
                    for field in _DUMP_DIM_FIELDS:
                        try:
                            cval = get_const(field)
                        except Exception as exc:
                            w(f"    {field:<14} 常量不可用 <{type(exc).__name__}>")
                            continue
                        raw, state = _dump_probe(lambda c=cval: cmd.GetFieldValue(c, 0))
                        w(f"    {field:<14}(const={cval!r}) = {raw!r} [{state}]")
                        if field == "F_MINUS_TOL":
                            minus = _dump_minus(raw, state, show_negative)
                            w(f"    → minus_tol = {minus!r}")
                            if minus is None:
                                unavailable.append(f"[{i}] {cid} F_MINUS_TOL （{state}）")
                            if state.startswith("RAISED"):
                                raised.append(f"[{i}] {cid} F_MINUS_TOL {state}")

    w()
    w("=" * 78)
    w(f"汇总：命中命令 {hit} 条")
    w(f"  下公差不可用（minus_tol is None）: {len(unavailable)} 条")
    for item in unavailable:
        w(f"    - {item}")
    w(f"  COM 抛异常: {len(raised)} 处")
    for item in raised:
        w(f"    - {item}")
    if not unavailable:
        w("  → 本程序无法复现 P2-1 的「下公差读不到」条件（需另找或另造数据）")

    text = "\n".join(lines)
    print(text)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"\n已写入 {out_path}")
    return 0


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




    p_dump = sub.add_parser(
        "dump-tols",
        help="只读诊断：转储各命令上/下公差的 COM 读取结果（定位「下公差读不到」的行）",
    )

    p_dump.add_argument(
        "--filter",
        default="",
        help="只转储 ID 以此前缀开头的命令，如 CC_（默认全部）",
    )

    p_dump.add_argument("-o", "--out", help="同时把结果写入该 UTF-8 文本文件")

    p_dump.set_defaults(func=cmd_dump_tols)



    args = parser.parse_args()

    if not args.command:

        parser.print_help()

        raise SystemExit(0)

    raise SystemExit(args.func(args))





if __name__ == "__main__":

    main()


