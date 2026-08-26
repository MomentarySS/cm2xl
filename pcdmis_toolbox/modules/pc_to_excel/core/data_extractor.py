"""PC-DMIS COM 数据提取 — 遍历 Commands 按类型解析为 FeatureRecord。

实现参考:
- https://blog.iyatt.com/?p=18363  (特征 / 评价尺寸)
- https://blog.iyatt.com/?p=18719  (ToleranceCommand 形位公差, 2023.2+)
- https://docs.hexagonmi.com/pcdmis/2024.1/en/helpcenter/mergedProjects/automationobjects/webframe.html
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

import win32com.client
import pythoncom

from ..connector.pcdlrn_constants import get_const
from .models import AxisValues, FeatureRecord, PassStatus


ProgressCallback = Callable[[int, int, str], None]

ExportScope = str  # "report" | "all"


def extract_from_application(
    app: Any,
    progress_cb: ProgressCallback | None = None,
    scope: ExportScope = "report",
    require_marked: bool = True,
) -> list[FeatureRecord]:
    """从已连接的 PCDLRN.Application 提取数据。

    scope:
      - report: 仅报告窗口相关（已评价尺寸/形位公差/大小尺寸，默认）
      - all: 全部可识别数据（含特征、基准、计算尺寸等）
    """
    part = app.ActivePartProgram
    if part is None:
        raise RuntimeError("未找到活动测量程序，请先在 PCDMIS 中打开测量程序 (.PRG)")

    cmds = part.Commands
    show_negative = _minus_tol_show_negative(part)
    cache, by_idx = _build_command_cache(cmds, progress_cb)
    records: list[FeatureRecord] = []

    records.extend(_extract_features(cache))
    records.extend(_extract_dimensions(cache, by_idx, show_negative))
    tol_records, tol_indices = _extract_tolerance_commands(cache, show_negative)
    records.extend(tol_records)
    tol_names = {r.name for r in tol_records}
    records.extend(
        _extract_fcf_commands(
            cache,
            show_negative,
            skip_names=tol_names,
            skip_indices=tol_indices,
        )
    )
    records.extend(_extract_datum_markers(cache))
    records.extend(_extract_assign_commands(cache))

    if scope == "report":
        from .report_filter import filter_report_window_records

        records = filter_report_window_records(
            records,
            by_idx,
            require_marked=require_marked,
        )

    # 按 PRG 命令序号排序，保证形位公差与尺寸交错顺序与报告窗口一致
    records.sort(
        key=lambda r: (
            r.cmd_index or r.write_cmd_index or 10**9,
            r.write_cmd_index or 0,
            r.name or "",
        )
    )

    if progress_cb:
        progress_cb(len(cache), len(cache), f"完成，共 {len(records)} 条")
    return records


def extract_from_part_program(
    part: Any,
    progress_cb: ProgressCallback | None = None,
    scope: ExportScope = "report",
    require_marked: bool = True,
) -> list[FeatureRecord]:
    """从 PartProgram 对象提取（供 COM 打开 .PRG 后使用）。"""
    class _AppShim:
        ActivePartProgram = part

    return extract_from_application(
        _AppShim(),
        progress_cb=progress_cb,
        scope=scope,
        require_marked=require_marked,
    )


def _build_command_cache(
    cmds: Any,
    progress_cb: ProgressCallback | None = None,
) -> tuple[list[tuple[int, Any]], dict[int, Any]]:
    """单次 COM 遍历缓存全部 Commands（大程序性能优化）。"""
    count = int(cmds.Count)
    cache: list[tuple[int, Any]] = []
    for idx in range(1, count + 1):
        try:
            cmd = cmds.Item(idx)
        except Exception:
            try:
                cmd = cmds(idx)
            except Exception:
                continue
        cache.append((idx, cmd))
        if progress_cb and (idx == count or idx % 25 == 0):
            progress_cb(idx, count, f"读取命令 {idx}/{count}…")
    return cache, {idx: cmd for idx, cmd in cache}


def _minus_tol_show_negative(part: Any) -> bool:
    try:
        return bool(part.PartProgramSettings.MinusTolerancesShowNegative)
    except Exception:
        return False


def _com_failed(value: Any) -> bool:
    """GetFieldValue 失败时 COM 返回 False。"""
    return value is False or value is None


def _field_value(cmd: Any, field: str, index: int = 0) -> Any:
    """GetFieldValue 包装 — 失败返回 False/None。"""
    try:
        return cmd.GetFieldValue(get_const(field), index)
    except Exception:
        return False


def _get_data_type_count(cmd: Any, field: str) -> int:
    try:
        return int(cmd.GetDataTypeCount(get_const(field)))
    except Exception:
        return 0


def _dim_attr(dim: Any, *names: str) -> Any:
    """DimensionCommand 属性 — 兼容 NOMINAL / Nominal 等大小写。"""
    for name in names:
        try:
            val = getattr(dim, name, None)
            if val is not None and val is not False:
                return val
        except Exception:
            continue
    return None


def _text_value(cmd: Any, field: str, index: int = 0) -> str:
    """GetText 包装 — 用于尺寸 ID 等文本字段。"""
    try:
        val = str(cmd.GetText(get_const(field), index) or "").strip()
        if val and val not in ("0", "None", "False"):
            return val
    except Exception:
        pass
    raw = _field_value(cmd, field, index)
    if not _com_failed(raw):
        return str(raw).strip()
    return ""


def _read_dim_field(cmd: Any, dim: Any | None, const_name: str, *dim_attrs: str) -> float | None:
    """评价尺寸字段 — 优先 Command.GetFieldValue（2024.1 无 DimensionCommand 时）。"""
    val = _safe_float(_field_value(cmd, const_name, 0))
    if val is not None:
        return val
    if dim is None:
        return None
    if not dim_attrs:
        dim_attrs = (const_name.title(), const_name)
    for attr in dim_attrs:
        val = _safe_float(_dim_attr(dim, attr, attr.upper(), attr.lower()))
        if val is not None:
            return val
    return None


def _clean_feat_name(val: Any) -> str:
    text = str(val or "").strip()
    if text in ("", "0", "None", "False", "FALSE", "TRUE", "True"):
        return ""
    # 过滤编辑窗口/距离选项垃圾串（如「（中心到中心）」）
    if text.startswith(("（", "(")) or "中心到中心" in text:
        return ""
    if "自动" in text and "点" in text:
        return ""
    return text


def _is_axis_ref_label(name: str) -> bool:
    n = (name or "").replace(" ", "")
    return n in ("X轴", "Y轴", "Z轴") or n.endswith("轴") and len(n) <= 3


def _finalize_feat_triple(
    feats: list[str], *, keep_axis_refs: bool
) -> tuple[str, str, str]:
    """去重并按报告习惯截断（距离类去掉轴向参考）。"""
    ordered: list[str] = []
    seen: set[str] = set()
    for feat in feats:
        if not feat or feat in seen:
            continue
        if not keep_axis_refs and _is_axis_ref_label(feat):
            continue
        seen.add(feat)
        ordered.append(feat)
    while len(ordered) < 3:
        ordered.append("")
    return ordered[0], ordered[1], ordered[2]


def _read_dimension_feats(cmd: Any, dim: Any | None) -> tuple[str, str, str]:
    """评价尺寸关联特征 — DimensionCommand.Feat* / GetReferencedFeature / REF_ID。"""
    feats = ["", "", ""]
    cmd_id = _command_name(cmd)
    type_desc = _dimension_type_name(cmd)
    keep_axis_refs = "角度" in type_desc

    if dim is not None:
        for i in (1, 2, 3):
            feats[i - 1] = _clean_feat_name(_dim_attr(dim, f"Feat{i}", f"FEAT{i}"))
        for i in (1, 2, 3):
            if feats[i - 1]:
                continue
            try:
                ref = dim.GetReferencedFeature(i)
            except Exception:
                ref = None
            if ref is None:
                continue
            feats[i - 1] = _clean_feat_name(
                getattr(ref, "ID", None) or getattr(ref, "DisplayID", None)
            )

    # 补全空位：3D 角度第二项常在 REF_ID[2]（如「X 轴」）
    for i in (1, 2, 3):
        if feats[i - 1]:
            continue
        for field in ("REF_ID", "DISPLAY_ID"):
            val = _clean_feat_name(_text_value(cmd, field, i))
            if not val or val == cmd_id or val in feats:
                continue
            feats[i - 1] = val
            break
    if not feats[0]:
        val = _clean_feat_name(_text_value(cmd, "REF_ID", 0))
        if val and val != cmd_id:
            feats[0] = val

    return _finalize_feat_triple(feats, keep_axis_refs=keep_axis_refs)


def _dimension_nominal_is_placeholder(
    cmd: Any, dim: Any | None, value: float | None
) -> bool:
    """尺寸位置头行名义值常为 0，真实名义值在配对行。"""
    if value is None:
        return True
    if abs(value) > 1e-12:
        return False
    return _dimension_type_name(cmd) in ("尺寸位置",)


def _read_dimension_bonus_outtol(cmd: Any) -> tuple[float | None, float | None]:
    bonus = _safe_float(_field_value(cmd, "DIM_BONUS", 0))
    outtol = _safe_float(_field_value(cmd, "DIM_OUTTOL", 0))
    return bonus, outtol


def _apply_dimension_report_meta(
    rec: FeatureRecord,
    header_cmd: Any,
    header_dim: Any | None,
    field_cmd: Any,
    plus_tol: float | None,
    minus_tol: float | None,
) -> None:
    """填充 PC-DMIS 报告行元数据（特征名 / 公差 / Bonus）。"""
    if not rec.feat1:
        f1, f2, f3 = _read_dimension_feats(header_cmd, header_dim)
        if not f1:
            f1, f2, f3 = _read_dimension_feats(field_cmd, None)
        rec.feat1, rec.feat2, rec.feat3 = f1, f2, f3
    if rec.plus_tol is None:
        rec.plus_tol = plus_tol
    if rec.minus_tol is None:
        rec.minus_tol = minus_tol
    bonus, outtol = _read_dimension_bonus_outtol(field_cmd)
    if rec.bonus is None:
        rec.bonus = bonus
    if rec.outtol is None:
        rec.outtol = outtol


def _gdt_axis_letter(symbol: str, axis: str) -> str:
    sym = (symbol or "").strip()
    axis = (axis or "").strip().upper()
    if sym in ("位置度", "POSITION") or "位置" in sym:
        return "TP"
    if axis and axis not in ("D", "0", "FALSE", "NONE"):
        return axis
    return "D"


def _gdt_segment_label(seg_index: int, seg_count: int) -> str:
    if seg_count > 1 or seg_index > 1:
        return f"SEG={seg_index}"
    return ""


def _dimension_feat_suffix(cmd: Any, dim: Any | None) -> str:
    """报告窗口副标题 — 如 CC_5.1-圆3 中的「圆3」。"""
    for source in (dim, cmd):
        if source is None:
            continue
        try:
            feat = str(_dim_attr(source, "Feat1", "FEAT1") or "").strip()
            if feat:
                return feat
        except Exception:
            continue
    return ""


def _dimension_name(cmd: Any, dim: Any | None, fallback_idx: int) -> str:
    """评价尺寸名称 — 优先命令 ID（FAI_2-1）；勿把 DISPLAY_ID 特征名当尺寸 ID。"""
    base = ""
    for source in (cmd, dim):
        if source is not None:
            base = _command_name(source)
            if base:
                break
    if not base:
        for field in ("ID", "DIM_ID"):
            # ID 常用 index 0；DISPLAY_ID 在本机常存放特征名，不能当尺寸 ID
            base = _text_value(cmd, field, 0) or _text_value(cmd, field, 1)
            if base:
                break

    # 报告尺寸列用命令 ID（FAI_10 / FAI_2-1）；特征名放描述括号，不拼进 ID
    if base:
        return base
    feat = _dimension_feat_suffix(cmd, dim)
    if not feat:
        f1, _, _ = _read_dimension_feats(cmd, dim)
        feat = f1
    if feat:
        return feat

    desc = _dimension_type_name(cmd).replace(" ", "")
    if desc and desc not in ("DIMENSION",):
        return f"{desc}_{fallback_idx}"
    return f"DIM_{fallback_idx}"


def _try_get_dimension_command(cmd: Any) -> Any | None:
    """DimensionCommand — win32com 常把属性标成 callable，调用会报「找不到成员」。"""
    for name in ("DimensionCommand", "DimensionCmd"):
        try:
            raw = getattr(cmd, name)
        except Exception:
            continue
        if raw is None:
            continue
        # CDispatch 属性勿直接调用；仅对真正的无参工厂函数尝试
        type_name = type(raw).__name__
        if type_name in ("CDispatch", "DispatchBaseClass"):
            return raw
        if callable(raw):
            try:
                called = raw()
                if called is not None:
                    return called
            except Exception:
                return raw
            continue
        return raw
    return None


def locate_dimension_measured_field(cmd: Any) -> tuple[str, int]:
    """定位评价尺寸实测值所在的 COM 字段（读写应使用同一字段/索引）。"""
    for const in ("DIM_MEASURED", "DIM_LENGTH", "DIM_LENGTH2", "DIM_HALF_ANGLE"):
        for idx in range(0, 8):
            val = _safe_float(_field_value(cmd, const, idx))
            if val is not None:
                return const, idx
    return "", 0


def _read_dimension_measured(cmd: Any, dim: Any | None) -> float | None:
    """评价尺寸实测 — 仅通过 Command 字段读取（不依赖 DimensionCommand）。"""
    const, idx = locate_dimension_measured_field(cmd)
    if const:
        return _safe_float(_field_value(cmd, const, idx))
    if dim is not None:
        for attr in ("Measured", "MEASURED", "Length", "LENGTH"):
            val = _safe_float(_dim_attr(dim, attr))
            if val is not None:
                return val
    return None


def _read_dimension_axis(cmd: Any, dim: Any | None, axis_field: Any) -> str:
    if dim is not None:
        axis = str(_dim_attr(dim, "AxisLetter", "AXIS") or "").strip()
        if axis:
            return axis
    if not _com_failed(axis_field):
        return str(axis_field).strip()
    axis = _text_value(cmd, "AXIS", 0)
    return axis


_DIMENSION_COMPANION_TYPES = frozenset(
    {"半径位置", "半角位置", "直径位置", "长度位置", "锥角位置"}
)
_DIMENSION_PAIR_COMPANIONS = _DIMENSION_COMPANION_TYPES | frozenset(
    {"尺寸位置", "圆锥角度"}
)


def _normalize_dim_desc(desc: str) -> str:
    return (desc or "").replace(" ", "")


def _is_axis_position_companion(desc: str) -> bool:
    norm = _normalize_dim_desc(desc)
    if norm in ("X轴位置", "Y轴位置", "Z轴位置"):
        return True
    if norm in _DIMENSION_COMPANION_TYPES:
        return False
    return "轴位置" in norm and norm not in {
        "尺寸位置",
        "长度位置",
        "直径位置",
        "半径位置",
        "半角位置",
        "锥角位置",
        "圆锥角度",
    }


def _should_skip_dimension_desc(desc: str) -> bool:
    return desc in ("终止尺寸", "基准定义", "尺寸格式") or "逼近距离" in desc or "回退距离" in desc


def _is_dimension_companion_desc(desc: str) -> bool:
    """尺寸位置头行的实测附属行（半径/半角/直径/长度/XYZ 轴等）。"""
    norm = _normalize_dim_desc(desc)
    if norm in _DIMENSION_COMPANION_TYPES:
        return True
    if _is_axis_position_companion(desc):
        return True
    return "逼近矢量" in desc or "方向偏差" in desc or "矢量方向" in desc


def _is_dimension_companion_row(first_cmd: Any, next_cmd: Any, axis_field: Any) -> bool:
    """有 ID 头行 + 无 ID 实测附属行。"""
    if not _command_name(first_cmd):
        return False
    if _command_name(next_cmd):
        return False
    try:
        if not next_cmd.IsDimension:
            return False
    except Exception:
        return False

    first_desc = _dimension_type_name(first_cmd)
    next_desc = _dimension_type_name(next_cmd)
    if not (
        next_desc in _DIMENSION_PAIR_COMPANIONS
        or _is_dimension_companion_desc(next_desc)
    ):
        return False
    if next_desc in _DIMENSION_COMPANION_TYPES or _is_axis_position_companion(next_desc):
        return True
    if _is_dimension_companion_desc(next_desc):
        return True
    if first_desc == "尺寸位置" and next_desc == "尺寸位置":
        return _com_failed(axis_field) or _dimension_measured_is_placeholder(
            first_cmd, _read_dimension_measured(first_cmd, None)
        )
    return False


def _collect_dimension_companions(
    by_idx: dict[int, Any],
    header_idx: int,
    count: int,
    header_cmd: Any,
    axis_field: Any,
) -> list[tuple[int, Any]]:
    """连续附属行 — 如 尺寸位置 + 长度位置，或 基准 + X/Y/Z 轴位置。"""
    companions: list[tuple[int, Any]] = []
    idx = header_idx + 1
    while idx <= count:
        next_cmd = by_idx.get(idx)
        if next_cmd is None:
            idx += 1
            continue
        if not _is_dimension_companion_row(header_cmd, next_cmd, axis_field):
            break
        companions.append((idx, next_cmd))
        idx += 1
    return companions


def _has_recent_dimension_header(by_idx: dict[int, Any], idx: int, lookback: int = 6) -> bool:
    """当前行是否为应已合并到头行的 orphan 附属行。"""
    for back in range(idx - 1, max(0, idx - lookback), -1):
        cmd = by_idx.get(back)
        if cmd is None:
            continue
        if not _command_name(cmd):
            continue
        try:
            if not cmd.IsDimension:
                continue
        except Exception:
            continue
        desc = _dimension_type_name(cmd)
        if _should_skip_dimension_desc(desc):
            continue
        return True
    return False


def _dimension_measured_is_placeholder(cmd: Any, value: float | None) -> bool:
    """尺寸位置头行实测常为 0，真实值在配对行。"""
    if value is None:
        return True
    if abs(value) > 1e-12:
        return False
    return _dimension_type_name(cmd) == "尺寸位置"


def _should_pair_dimension_commands(first_cmd: Any, next_cmd: Any, axis_field: Any) -> bool:
    """兼容旧调用 — 仅判断首条附属行。"""
    return _is_dimension_companion_row(first_cmd, next_cmd, axis_field)


def _resolve_dimension_record_type(first_cmd: Any, work_cmd: Any) -> str:
    """逻辑尺寸类型 — 配对时保留头行类型（原生 Excel：尺寸位置+锥角→尺寸位置）。"""
    first_desc = _dimension_type_name(first_cmd)
    if work_cmd is first_cmd or work_cmd is None:
        return first_desc
    work_desc = _dimension_type_name(work_cmd)
    # 半径/半角位置头行本身常无实测，报告描述用附属行类型
    if work_desc in ("半径位置", "半角位置") and first_desc in ("尺寸位置", "DIMENSION"):
        return work_desc
    return first_desc


def _pick_dimension_field_cmd(
    first_cmd: Any, first_dim: Any | None, work_cmd: Any, work_dim: Any | None
) -> tuple[Any, Any | None]:
    """字段读取来源 — 配对时优先实测行，头行 0 值视为占位。"""
    paired = work_cmd is not first_cmd
    first_meas = _read_dimension_measured(first_cmd, first_dim)
    work_meas = _read_dimension_measured(work_cmd, work_dim) if paired else None

    if paired:
        work_desc = _dimension_type_name(work_cmd)
        if work_desc in _DIMENSION_COMPANION_TYPES or _is_dimension_companion_desc(work_desc):
            return work_cmd, work_dim
        if work_meas is not None and _dimension_measured_is_placeholder(first_cmd, first_meas):
            return work_cmd, work_dim
        if work_meas is not None and first_meas is None:
            return work_cmd, work_dim

    if first_meas is not None and not (
        paired and _dimension_measured_is_placeholder(first_cmd, first_meas)
    ):
        return first_cmd, first_dim
    if work_meas is not None:
        return work_cmd, work_dim
    return first_cmd, first_dim


def _resolve_dimension_values(
    first_cmd: Any,
    first_dim: Any | None,
    work_cmd: Any,
    work_dim: Any | None,
    axis_field: Any,
    show_negative: bool,
) -> tuple[str, float | None, float | None, float | None, float | None, float | None]:
    """名义值优先头行，实测/偏差优先实测行。"""
    paired = work_cmd is not first_cmd
    meas_cmd, meas_dim = _pick_dimension_field_cmd(
        first_cmd, first_dim, work_cmd, work_dim
    )
    nom_cmd = first_cmd if paired else meas_cmd
    nom_dim = first_dim if paired else meas_dim

    axis = _read_dimension_axis(meas_cmd, meas_dim, axis_field)
    measured_val = _read_dimension_measured(meas_cmd, meas_dim)
    nominal_val = _read_dim_field(nom_cmd, nom_dim, "NOMINAL", "NOMINAL", "Nominal")
    if nominal_val is None and paired:
        nominal_val = _read_dim_field(meas_cmd, meas_dim, "NOMINAL", "NOMINAL", "Nominal")
    if paired and _dimension_nominal_is_placeholder(nom_cmd, nom_dim, nominal_val):
        comp_nom = _read_dim_field(meas_cmd, meas_dim, "NOMINAL", "NOMINAL", "Nominal")
        if comp_nom is not None and not _dimension_nominal_is_placeholder(
            meas_cmd, meas_dim, comp_nom
        ):
            nominal_val = comp_nom

    deviation_val = _read_dim_field(
        meas_cmd, meas_dim, "DIM_DEVIATION", "Deviation", "DEVIATION"
    )
    if deviation_val is None and paired:
        deviation_val = _read_dim_field(
            nom_cmd, nom_dim, "DIM_DEVIATION", "Deviation", "DEVIATION"
        )
    if measured_val is None and nominal_val is not None and deviation_val is not None:
        measured_val = nominal_val + deviation_val
    if deviation_val is None and measured_val is not None and nominal_val is not None:
        deviation_val = measured_val - nominal_val

    plus_tol = _read_dim_field(meas_cmd, meas_dim, "F_PLUS_TOL", "Plus", "PLUS")
    if plus_tol is None and paired:
        plus_tol = _read_dim_field(nom_cmd, nom_dim, "F_PLUS_TOL", "Plus", "PLUS")
    minus_raw = _read_dim_field(meas_cmd, meas_dim, "F_MINUS_TOL", "Minus", "MINUS")
    if minus_raw is None and paired:
        minus_raw = _read_dim_field(nom_cmd, nom_dim, "F_MINUS_TOL", "Minus", "MINUS")
    minus_tol = _normalize_minus_tol(minus_raw, show_negative)
    return axis, nominal_val, measured_val, deviation_val, plus_tol, minus_tol


def _dimension_passes_gate(cmd: Any, dim: Any | None) -> bool:
    """DIM_MEASURED 可读，或有其它实测/名义+偏差字段。"""
    gv = _field_value(cmd, "DIM_MEASURED", 0)
    if not _com_failed(gv):
        return True
    if _read_dimension_measured(cmd, dim) is not None:
        return True
    nominal = _read_dim_field(cmd, dim, "NOMINAL", "NOMINAL", "Nominal")
    deviation = _read_dim_field(cmd, dim, "DIM_DEVIATION", "Deviation", "DEVIATION")
    return nominal is not None and deviation is not None


def _is_datum_id(name: str) -> bool:
    """基准命令 ID 通常为单字母或短字母组合（A、B、A-B）。"""
    n = (name or "").strip()
    if not n or len(n) > 3:
        return False
    return n.replace("-", "").isalpha()


def _safe_float(value: Any) -> float | None:
    if _com_failed(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_minus_tol(minus: float | None, show_negative: bool) -> float | None:
    """PC-DMIS 内部下公差符号与显示设置相关，取实际意义值。"""
    if minus is None:
        return None
    if show_negative:
        return minus
    return -minus


def _get_command_at(cmds: Any, index: int) -> Any:
    """读取 Commands 集合中的单条命令（兼容 Item / 调用式索引）。"""
    for getter in (
        lambda: cmds.Item(index),
        lambda: cmds(index),
        lambda: cmds[index],
    ):
        try:
            result = getter()
            if result is not None:
                return result
        except Exception:
            continue
    raise RuntimeError(f"无法读取 Commands 索引 {index}")


def _iter_commands(cmds: Any):
    """遍历 Commands 集合（COM 通常为 1-based）。"""
    count = int(cmds.Count)
    for idx in range(1, count + 1):
        try:
            yield idx, cmds.Item(idx)
        except Exception:
            yield idx, cmds(idx)


def _command_name(*sources: Any) -> str:
    """按优先级读取命令 ID（与 PCDMIS 标识符一致）。"""
    for source in sources:
        if source is None:
            continue
        try:
            val = str(getattr(source, "ID", "") or "").strip()
            if val:
                return val
        except Exception:
            continue
    return ""


def _gdt_command_id(cmd: Any, tol_cmd: Any | None, idx: int, prefix: str = "GDT") -> str:
    """形位公差命令 ID — 优先 cmd.ID（如 FCF圆柱度1）。"""
    for source in (cmd, tol_cmd):
        name = _command_name(source)
        if name:
            return name
    for source in (cmd, tol_cmd):
        if source is None:
            continue
        for field in ("DISPLAY_ID", "ID", "DIM_ID", "REF_ID"):
            try:
                name = _text_value(source, field, 0)
            except Exception:
                name = ""
            if name:
                return name
        for prop in ("ReportLabel", "Name", "Label"):
            try:
                val = str(getattr(source, prop, "") or "").strip()
                if val:
                    return val
            except Exception:
                continue
    return f"{prefix}_{idx}"


def _is_fcf_style_id(name: str) -> bool:
    n = (name or "").strip()
    return bool(n) and n.upper().startswith("FCF")


def _is_constructed_feature_alias(name: str) -> bool:
    n = (name or "").upper()
    return " - LS" in n or " - LOCAL" in n or " - CONSTRUCT" in n


def _resolve_gdt_command_name(cmd: Any, tol_cmd: Any, idx: int) -> str:
    """ToleranceCommand 显示名 — 优先 FCF 命令 ID，不从被测特征名回退。"""
    name = _gdt_command_id(cmd, tol_cmd, idx, "TOL")
    if name and not name.startswith("TOL_"):
        return name
    for prop in ("ReportLabel", "Name", "Label"):
        for source in (cmd, tol_cmd):
            if source is None:
                continue
            try:
                val = str(getattr(source, prop, "") or "").strip()
                if _is_fcf_style_id(val):
                    return val
            except Exception:
                continue
    try:
        feat_count = int(tol_cmd.FeatureCount)
    except Exception:
        feat_count = 0
    for j in range(1, feat_count + 1):
        try:
            fid = str(tol_cmd.FeatureID(j) or "").strip()
        except Exception:
            continue
        if _is_fcf_style_id(fid):
            return fid
    return name


def _pick_tolerance_feature_index(tol_cmd: Any, feat_count: int) -> int:
    """形位公差实测行 — 跳过构造特征（- LS）与 FCF 名称行（取首个可用）。"""
    indices = _iter_tolerance_feature_indices(tol_cmd, feat_count)
    return indices[0] if indices else 1


def _iter_tolerance_feature_indices(tol_cmd: Any, feat_count: int) -> list[int]:
    """遍历全部可用被测特征索引（跳过 -LS / FCF 名称行）。"""
    if feat_count < 1:
        return []
    if feat_count == 1:
        return [1]
    indices: list[int] = []
    for j in range(1, feat_count + 1):
        try:
            fid = str(tol_cmd.FeatureID(j) or "").strip()
        except Exception:
            continue
        if _is_fcf_style_id(fid) or _is_constructed_feature_alias(fid):
            continue
        indices.append(j)
    return indices or [1]


def _pick_fcf_line_index(cmd: Any, line_count: int, line_prefix: str) -> int:
    """Legacy FCF 实测行 — 跳过 - LS 与 FCF 名称。"""
    if line_count <= 1:
        return 1
    for j in range(1, line_count + 1):
        feat = str(_field_value(cmd, f"{line_prefix}_FEATNAME", j) or "").strip()
        if _is_fcf_style_id(feat) or _is_constructed_feature_alias(feat):
            continue
        return j
    return 1


def _gdt_record_name(
    command_id: str,
    feat_id: str,
    *,
    seg_index: int = 1,
    feat_index: int = 1,
    seg_count: int = 1,
    feat_count: int = 1,
    allow_feat_suffix: bool = False,
) -> str:
    """形位公差记录名 — 默认仅命令 ID（FCF圆柱度1），不用圆柱2/圆3。"""
    if command_id and not command_id.startswith("TOL_"):
        if allow_feat_suffix and feat_count > 1 and seg_count > 1:
            suffix = feat_id or str(feat_index)
            return f"{command_id}_S{seg_index}_{suffix}"
        if allow_feat_suffix and feat_count > 1:
            return f"{command_id}_{feat_id or feat_index}"
        if seg_count > 1:
            return f"{command_id}_S{seg_index}"
        return command_id
    if _is_fcf_style_id(feat_id):
        return feat_id
    if command_id:
        return command_id
    if not feat_id:
        return f"GDT_{feat_index}"
    return f"GDT_{feat_index}"


def _merge_axis_into_record(
    rec: FeatureRecord,
    axis: str,
    nominal_val: float | None,
    measured_val: float | None,
    deviation_val: float | None,
    plus_tol: float | None,
    minus_tol: float | None,
) -> None:
    """同一尺寸 ID 多轴数据合并到一条记录（如位置度 X/Y）。"""
    letter = (axis or "D").strip().upper()
    nom_part, meas_part, dev_part = _axis_values_for_letter(
        letter, nominal_val, measured_val, deviation_val
    )
    merge_keys = ("x", "y", "z", "d", "length", "width", "height", "angle", "minor_d")
    for key in merge_keys:
        for src, dst in ((nom_part, rec.nominal), (meas_part, rec.measured), (dev_part, rec.deviation)):
            val = getattr(src, key, None)
            if val is not None:
                setattr(dst, key, val)

    tol_part = _tolerance_from_limits(plus_tol, minus_tol, axis)
    if tol_part is None:
        return
    if rec.tolerance is None:
        rec.tolerance = AxisValues()
    for key in merge_keys:
        val = getattr(tol_part, key, None)
        if val is not None:
            setattr(rec.tolerance, key, val)


def _axis_values_for_letter(
    axis: str,
    nominal: float | None,
    measured: float | None,
    deviation: float | None,
) -> tuple[AxisValues, AxisValues, AxisValues]:
    nom, meas, dev = AxisValues(), AxisValues(), AxisValues()
    letter = (axis or "").strip().upper()
    field_map = {
        "X": "x",
        "Y": "y",
        "Z": "z",
        "D": "d",
        "M": "d",
        "DF": "d",
        "DIST": "d",
        "距离": "d",
        "DIAM": "d",
        "直径": "d",
        "R": "d",
        "半径": "d",
        "L": "length",
        "长度": "length",
        "A": "angle",
        "ANGLE": "angle",
        "角度": "angle",
        "PA": "angle",
    }
    key = field_map.get(letter, "d")
    setattr(nom, key, nominal)
    setattr(meas, key, measured)
    setattr(dev, key, deviation)
    return nom, meas, dev


def _get_point(feat_cmd: Any, data_kind: int) -> tuple[float | None, float | None, float | None]:
    """FeatureCommand.GetPoint — 读取质心坐标。"""
    x = y = z = 0.0
    x_ref = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, x)
    y_ref = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, y)
    z_ref = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, z)
    try:
        feat_cmd.GetPoint(get_const("FPOINT_CENTROID"), data_kind, x_ref, y_ref, z_ref)
        return x_ref.value, y_ref.value, z_ref.value
    except Exception:
        return None, None, None


def _feature_type_name(cmd: Any, feat_cmd: Any) -> str:
    for getter in (
        lambda: str(feat_cmd.FeatType),
        lambda: str(cmd.TypeDescription),
        lambda: str(cmd.Type),
    ):
        try:
            val = getter()
            if val and val not in ("0", "None"):
                return val
        except Exception:
            continue
    return "FEATURE"


# (属性名, 理论字段名列表, 实测字段名列表)
_GEO_FIELD_SPECS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("d", ("THEO_DIAM",), ("MEAS_D", "MEAS_DIAM")),
    ("length", ("THEO_LENGTH",), ("MEAS_LENGTH",)),
    ("width", ("THEO_WIDTH",), ("MEAS_WIDTH",)),
    ("height", ("THEO_HEIGHT",), ("MEAS_HEIGHT",)),
    ("angle", ("THEO_ANGLE",), ("MEAS_ANGLE",)),
    ("minor_d", ("THEO_MINOR_DIAMETER",), ("MEAS_MINOR_DIAMETER",)),
    ("i", ("THEO_I",), ("MEAS_I",)),
    ("j", ("THEO_J",), ("MEAS_J",)),
    ("k", ("THEO_K",), ("MEAS_K",)),
)

# 用户关心的 11 类元素 — 顺序从具体到一般（避免「圆柱」被「圆」抢先匹配）
_FEATURE_ELEMENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("圆柱", ("圆柱", "CYLINDER")),
    ("圆锥", ("圆锥", "CONE")),
    ("圆槽", ("圆槽", "ROUND SLOT", "ROUND_SLOT")),
    ("方槽", ("方槽", "SQUARE SLOT", "SQUARE_SLOT")),
    ("凹口槽", ("凹口", "开槽", "OPEN SLOT", "NOTCH")),
    ("椭圆", ("椭圆", "ELLIPSE")),
    ("多边形", ("多边形", "POLYGON")),
    ("球", ("球", "SPHERE")),
    ("直线", ("直线", "LINE")),
    ("平面", ("平面", "PLANE")),
    ("圆", ("圆", "CIRCLE")),
)


def normalize_feature_element(type_name: str) -> str | None:
    """将 PCDMIS FeatType 归一化为 11 类元素名，无法识别时返回 None。"""
    upper = (type_name or "").upper()
    for label, keywords in _FEATURE_ELEMENT_KEYWORDS:
        for kw in keywords:
            if kw.upper() in upper or kw in type_name:
                return label
    return None


def _read_field_candidates(cmd: Any, names: tuple[str, ...]) -> float | None:
    for name in names:
        val = _safe_float(_field_value(cmd, name, 0))
        if val is not None:
            return val
    return None


def _read_diameter_from_feat(feat_cmd: Any) -> tuple[float | None, float | None]:
    theo = meas = None
    try:
        theo_raw = getattr(feat_cmd, "TheoDiam", None)
        if theo_raw is None:
            theo_raw = getattr(feat_cmd, "Diam", None)
        theo = _safe_float(theo_raw)

        meas_raw = getattr(feat_cmd, "MeasDiam", None)
        if meas_raw is None:
            meas_raw = getattr(feat_cmd, "Diam", None)
        meas = _safe_float(meas_raw)
    except Exception:
        pass
    return theo, meas


def _read_diameter(cmd: Any, feat_cmd: Any | None = None) -> tuple[float | None, float | None]:
    """读取特征直径理论/实测（圆、圆柱、球等）。"""
    theo = _read_field_candidates(cmd, ("THEO_DIAM",))
    meas = _read_field_candidates(cmd, ("MEAS_D", "MEAS_DIAM"))
    if theo is None and meas is None and feat_cmd is not None:
        theo, meas = _read_diameter_from_feat(feat_cmd)
    return theo, meas


def _build_geometry_values(
    cmd: Any,
    feat_cmd: Any,
    theo_x: float | None,
    theo_y: float | None,
    theo_z: float | None,
    meas_x: float | None,
    meas_y: float | None,
    meas_z: float | None,
) -> tuple[AxisValues, AxisValues, AxisValues]:
    """读取特征几何参数 — 按 COM 字段逐项尝试，适配 11 类元素。"""
    nominal = AxisValues(x=theo_x, y=theo_y, z=theo_z)
    measured = AxisValues(x=meas_x, y=meas_y, z=meas_z)

    for attr, theo_fields, meas_fields in _GEO_FIELD_SPECS:
        theo_val = _read_field_candidates(cmd, theo_fields)
        meas_val = _read_field_candidates(cmd, meas_fields)
        if attr == "d" and theo_val is None and meas_val is None:
            theo_val, meas_val = _read_diameter_from_feat(feat_cmd)
        setattr(nominal, attr, theo_val)
        setattr(measured, attr, meas_val)

    theo_d, meas_d = _read_diameter(cmd, feat_cmd)
    if nominal.d is None:
        nominal.d = theo_d
    if measured.d is None:
        measured.d = meas_d

    deviation = AxisValues(
        x=_deviation(meas_x, theo_x),
        y=_deviation(meas_y, theo_y),
        z=_deviation(meas_z, theo_z),
    )
    for attr, _theo_fields, _meas_fields in _GEO_FIELD_SPECS:
        setattr(
            deviation,
            attr,
            _deviation(getattr(measured, attr), getattr(nominal, attr)),
        )
    return nominal, measured, deviation


def _extract_features(cache: list[tuple[int, Any]]) -> list[FeatureRecord]:
    records: list[FeatureRecord] = []
    for idx, cmd in cache:
        try:
            if not cmd.IsFeature:
                continue
        except Exception:
            continue

        try:
            feat_cmd = cmd.FeatureCommand
            name = _command_name(cmd, feat_cmd)
            if not name:
                continue

            theo_x, theo_y, theo_z = _get_point(feat_cmd, get_const("FDATA_THEO"))
            meas_x, meas_y, meas_z = _get_point(feat_cmd, get_const("FDATA_MEAS"))
            type_name = _feature_type_name(cmd, feat_cmd)
            nominal, measured, deviation = _build_geometry_values(
                cmd, feat_cmd, theo_x, theo_y, theo_z, meas_x, meas_y, meas_z
            )

            records.append(
                FeatureRecord(
                    name=name,
                    feature_type=type_name,
                    nominal=nominal,
                    measured=measured,
                    deviation=deviation,
                    cmd_index=idx,
                    source_kind="feature",
                )
            )
        except Exception:
            continue
    return records


def _deviation(measured: float | None, nominal: float | None) -> float | None:
    if measured is None or nominal is None:
        return None
    return measured - nominal


def _dimension_type_name(cmd: Any) -> str:
    try:
        desc = str(cmd.TypeDescription or "").strip()
        if desc and desc not in ("0", "None"):
            return desc
    except Exception:
        pass
    return "DIMENSION"


def _upsert_dimension_record(
    records: list[FeatureRecord],
    index_by_name: dict[str, int],
    *,
    dim_id: str,
    record_desc: str,
    cmd_index: int,
    write_idx: int,
    axis: str,
    nominal_val: float | None,
    measured_val: float | None,
    deviation_val: float | None,
    plus_tol: float | None,
    minus_tol: float | None,
    meas_field: str,
    meas_field_idx: int,
    first_cmd: Any,
    first_dim: Any | None,
    field_cmd: Any,
    field_dim: Any | None,
    work_dim: Any | None,
) -> None:
    if dim_id in index_by_name:
        rec = records[index_by_name[dim_id]]
        _merge_axis_into_record(
            rec,
            axis,
            nominal_val,
            measured_val,
            deviation_val,
            plus_tol,
            minus_tol,
        )
        if write_idx > 0:
            rec.write_cmd_index = write_idx
        if axis:
            rec.write_axis = axis
        if meas_field:
            rec.write_field = meas_field
            rec.write_field_index = meas_field_idx
        _apply_dimension_report_meta(
            rec, first_cmd, first_dim, field_cmd, plus_tol, minus_tol
        )
        return

    nom, meas, dev = _axis_values_for_letter(
        axis, nominal_val, measured_val, deviation_val
    )
    tol = _tolerance_from_limits(plus_tol, minus_tol, axis)
    bonus, outtol = _read_dimension_bonus_outtol(field_cmd)
    f1, f2, f3 = _read_dimension_feats(first_cmd, first_dim)
    if not f1:
        f1, f2, f3 = _read_dimension_feats(field_cmd, work_dim)
    records.append(
        FeatureRecord(
            name=dim_id,
            feature_type=record_desc,
            nominal=nom,
            measured=meas,
            deviation=dev,
            tolerance=tol,
            cmd_index=cmd_index,
            write_cmd_index=write_idx,
            source_kind="dimension",
            write_axis=axis,
            write_field=meas_field,
            write_field_index=meas_field_idx,
            feat1=f1,
            feat2=f2,
            feat3=f3,
            plus_tol=plus_tol,
            minus_tol=minus_tol,
            bonus=bonus,
            outtol=outtol,
        )
    )
    index_by_name[dim_id] = len(records) - 1


def _extract_dimensions(
    cache: list[tuple[int, Any]],
    by_idx: dict[int, Any],
    show_negative: bool,
) -> list[FeatureRecord]:
    """评价尺寸 — Legacy Dimension（2D 距离 / 位置 / 半径位置等）。"""
    records: list[FeatureRecord] = []
    index_by_name: dict[str, int] = {}
    # 用原始命令序号上界遍历；不能用 len(cache)，否则中间读失败会漏掉后面的命令
    count = max((idx for idx, _ in cache), default=0)
    idx = 1

    while idx <= count:
        first_cmd = by_idx.get(idx)
        if first_cmd is None:
            idx += 1
            continue

        try:
            if not first_cmd.IsDimension:
                idx += 1
                continue
        except Exception:
            idx += 1
            continue

        first_desc = _dimension_type_name(first_cmd)
        if _should_skip_dimension_desc(first_desc):
            idx += 1
            continue

        if not _command_name(first_cmd) and (
            _normalize_dim_desc(first_desc) in _DIMENSION_COMPANION_TYPES
            or _is_axis_position_companion(first_desc)
        ):
            if _has_recent_dimension_header(by_idx, idx):
                idx += 1
                continue

        try:
            first_dim = _try_get_dimension_command(first_cmd)
        except Exception:
            first_dim = None

        axis_field = _field_value(first_cmd, "AXIS", 0)
        companions = _collect_dimension_companions(
            by_idx, idx, count, first_cmd, axis_field
        )

        if companions and _command_name(first_cmd):
            dim_id = _dimension_name(first_cmd, first_dim, idx)
            record_desc = _resolve_dimension_record_type(
                first_cmd, companions[0][1]
            )
            any_values = False

            for comp_idx, comp_cmd in companions:
                comp_dim = _try_get_dimension_command(comp_cmd)
                if not (
                    _dimension_passes_gate(first_cmd, first_dim)
                    or _dimension_passes_gate(comp_cmd, comp_dim)
                ):
                    continue

                comp_axis_field = _field_value(comp_cmd, "AXIS", 0)
                field_cmd, field_dim = _pick_dimension_field_cmd(
                    first_cmd, first_dim, comp_cmd, comp_dim
                )
                if _read_dimension_measured(field_cmd, field_dim) is None:
                    continue

                any_values = True
                meas_field, meas_field_idx = locate_dimension_measured_field(field_cmd)
                axis, nominal_val, measured_val, deviation_val, plus_tol, minus_tol = (
                    _resolve_dimension_values(
                        first_cmd,
                        first_dim,
                        comp_cmd,
                        comp_dim,
                        comp_axis_field,
                        show_negative,
                    )
                )
                _upsert_dimension_record(
                    records,
                    index_by_name,
                    dim_id=dim_id,
                    record_desc=record_desc,
                    cmd_index=idx,
                    write_idx=comp_idx,
                    axis=axis,
                    nominal_val=nominal_val,
                    measured_val=measured_val,
                    deviation_val=deviation_val,
                    plus_tol=plus_tol,
                    minus_tol=minus_tol,
                    meas_field=meas_field,
                    meas_field_idx=meas_field_idx,
                    first_cmd=first_cmd,
                    first_dim=first_dim,
                    field_cmd=field_cmd,
                    field_dim=field_dim,
                    work_dim=comp_dim,
                )

            if not any_values and _is_datum_id(dim_id):
                idx += len(companions) + 1
                continue

            idx += len(companions) + 1
            continue

        work_cmd = first_cmd
        work_dim = first_dim

        if idx < count:
            next_cmd = by_idx.get(idx + 1)
            if next_cmd is not None and _should_pair_dimension_commands(
                first_cmd, next_cmd, axis_field
            ):
                work_cmd = next_cmd
                work_dim = _try_get_dimension_command(next_cmd)

        if not (
            _dimension_passes_gate(first_cmd, first_dim)
            or _dimension_passes_gate(work_cmd, work_dim)
        ):
            idx += 1
            continue

        field_cmd, field_dim = _pick_dimension_field_cmd(
            first_cmd, first_dim, work_cmd, work_dim
        )
        write_idx = idx + 1 if field_cmd is work_cmd and work_cmd is not first_cmd else idx
        meas_field, meas_field_idx = locate_dimension_measured_field(field_cmd)

        dim_id = _dimension_name(first_cmd, first_dim, idx)
        if _is_datum_id(dim_id) and _read_dimension_measured(field_cmd, field_dim) is None:
            idx += 1
            continue

        axis, nominal_val, measured_val, deviation_val, plus_tol, minus_tol = (
            _resolve_dimension_values(
                first_cmd, first_dim, work_cmd, work_dim, axis_field, show_negative
            )
        )
        record_desc = _resolve_dimension_record_type(first_cmd, work_cmd)

        _upsert_dimension_record(
            records,
            index_by_name,
            dim_id=dim_id,
            record_desc=record_desc,
            cmd_index=idx,
            write_idx=write_idx,
            axis=axis,
            nominal_val=nominal_val,
            measured_val=measured_val,
            deviation_val=deviation_val,
            plus_tol=plus_tol,
            minus_tol=minus_tol,
            meas_field=meas_field,
            meas_field_idx=meas_field_idx,
            first_cmd=first_cmd,
            first_dim=first_dim,
            field_cmd=field_cmd,
            field_dim=field_dim,
            work_dim=work_dim,
        )

        if work_cmd is not first_cmd:
            idx += 1
        idx += 1

    return records


def _tolerance_from_limits(
    plus: float | None, minus: float | None, axis: str
) -> AxisValues | None:
    if plus is None and minus is None:
        return None
    letter = (axis or "D").strip().upper()
    field_map = {
        "X": "x",
        "Y": "y",
        "Z": "z",
        "D": "d",
        "M": "d",
        "DF": "d",
        "L": "length",
        "A": "angle",
        "ANGLE": "angle",
        "PA": "angle",
    }
    key = field_map.get(letter, "d")
    tol = AxisValues()
    if plus is not None:
        setattr(tol, key, plus)
    if minus is not None:
        # tolerance 模型用上下限；minus 已是实际意义负值
        current = getattr(tol, key)
        if current is None:
            setattr(tol, key, abs(minus))
    return tol


def _extract_tolerance_commands(
    cache: list[tuple[int, Any]],
    show_negative: bool,
) -> tuple[list[FeatureRecord], set[int]]:
    """形位公差 — 2022.2+ ToleranceCommand（2024.1 推荐路径）。"""
    records: list[FeatureRecord] = []
    indices: set[int] = set()
    for idx, cmd in cache:
        try:
            is_tol = cmd.IsToleranceCommand
        except Exception:
            is_tol = False
        if not is_tol:
            continue

        try:
            tol_cmd = cmd.ToleranceCommand
            display_name = _resolve_gdt_command_name(cmd, tol_cmd, idx)
            indices.add(idx)
            gdt_symbol = ""
            try:
                gdt_symbol = str(tol_cmd.gdtSymbol or "")
            except Exception:
                pass
            if not gdt_symbol:
                gdt_symbol = str(_field_value(cmd, "GDT_SYMBOL", 0) or "").strip()

            # 尺寸区（大小尺寸 / 组合尺寸行）
            try:
                size_count = int(tol_cmd.sizeCountCombined)
            except Exception:
                size_count = 0

            for j in range(1, size_count + 1):
                try:
                    minus_raw = tol_cmd.sizeMinusTol(j)
                    minus_tol = minus_raw if show_negative else -minus_raw
                    feat_text = str(tol_cmd.sizeText(j) or "").strip()
                    name = display_name if size_count == 1 else f"{display_name}_{j}"
                    if size_count > 1 and feat_text and feat_text != display_name:
                        name = display_name

                    axis = str(tol_cmd.SizeAxis(j) or "D")
                    nom, meas, dev = _axis_values_for_letter(
                        axis,
                        _safe_float(tol_cmd.sizeNominal(j)),
                        _safe_float(tol_cmd.sizeMeasured(j)),
                        _safe_float(tol_cmd.sizeDeviation(j)),
                    )
                    tol = _tolerance_from_limits(
                        _safe_float(tol_cmd.sizePlusTol(j)),
                        minus_tol,
                        axis,
                    )
                    plus = _safe_float(tol_cmd.sizePlusTol(j))
                    outtol = None
                    for getter in (
                        lambda: tol_cmd.sizeOutOfTol(j),
                        lambda: tol_cmd.SizeOutOfTol(j),
                    ):
                        try:
                            outtol = _safe_float(getter())
                            if outtol is not None:
                                break
                        except Exception:
                            continue
                    records.append(
                        FeatureRecord(
                            name=name,
                            feature_type=f"TOLERANCE_{gdt_symbol or 'SIZE'}",
                            nominal=nom,
                            measured=meas,
                            deviation=dev,
                            tolerance=tol,
                            cmd_index=idx,
                            source_kind="tolerance",
                            write_axis=axis,
                            feat1=feat_text,
                            plus_tol=plus,
                            minus_tol=minus_tol,
                            outtol=outtol,
                        )
                    )
                except Exception:
                    continue

            # 区段 × 特征（与官方示例一致：双重循环）
            try:
                seg_count = int(tol_cmd.SegmentCount)
            except Exception:
                seg_count = 0

            try:
                feat_count = int(tol_cmd.FeatureCount)
            except Exception:
                feat_count = 0

            feat_indices = _iter_tolerance_feature_indices(tol_cmd, feat_count)
            segment_indices = (
                list(range(1, seg_count + 1))
                if seg_count > 0
                else ([1] if feat_indices else [])
            )

            for k in segment_indices:
                for j in feat_indices:
                    try:
                        feat_id = str(tol_cmd.FeatureID(j) or "").strip()
                        name = _gdt_record_name(
                            display_name,
                            feat_id,
                            seg_index=k,
                            feat_index=j,
                            seg_count=max(seg_count, 1),
                            feat_count=len(feat_indices),
                        )
                        axis = str(tol_cmd.SegmentAxis(j) or "D")
                        minus_raw = tol_cmd.segmentDimMinusTol(k, j)
                        minus_tol = minus_raw if show_negative else -minus_raw

                        nom, meas, dev = _axis_values_for_letter(
                            axis,
                            _safe_float(tol_cmd.SegmentDimNominal(k, j)),
                            _safe_float(tol_cmd.SegmentDimMeasured(k, j)),
                            _safe_float(tol_cmd.SegmentDimDeviation(k, j)),
                        )
                        tol = _tolerance_from_limits(
                            _safe_float(tol_cmd.SegmentDimPlusTol(k, j)),
                            minus_tol,
                            axis,
                        )
                        plus = _safe_float(tol_cmd.SegmentDimPlusTol(k, j))
                        axis_letter = _gdt_axis_letter(gdt_symbol, axis)
                        segment = _gdt_segment_label(k, max(seg_count, 1))
                        outtol = None
                        for getter in (
                            lambda: tol_cmd.SegmentDimOutTol(k, j),
                            lambda: tol_cmd.segmentDimOutTol(k, j),
                        ):
                            try:
                                outtol = _safe_float(getter())
                                if outtol is not None:
                                    break
                            except Exception:
                                continue
                        records.append(
                            FeatureRecord(
                                name=name,
                                feature_type=f"TOLERANCE_{gdt_symbol or 'SEG'}",
                                nominal=nom,
                                measured=meas,
                                deviation=dev,
                                tolerance=tol,
                                cmd_index=idx,
                                source_kind="tolerance",
                                write_axis=axis_letter,
                                feat1=feat_id,
                                segment=segment,
                                plus_tol=plus,
                                minus_tol=minus_tol,
                                outtol=outtol,
                            )
                        )
                    except Exception:
                        continue
        except Exception:
            continue

    return records, indices


def _extract_fcf_commands(
    cache: list[tuple[int, Any]],
    show_negative: bool,
    skip_names: set[str] | None = None,
    skip_indices: set[int] | None = None,
) -> list[FeatureRecord]:
    """Legacy 形位公差 — IsFcfCommand（2019–2023 及兼容程序）。"""
    skip = skip_names or set()
    skip_idx = skip_indices or set()
    records: list[FeatureRecord] = []

    for idx, cmd in cache:
        if idx in skip_idx:
            continue
        try:
            if not cmd.IsFcfCommand:
                continue
        except Exception:
            continue

        cmd_id = _gdt_command_id(cmd, None, idx, "FCF")
        gdt_symbol = str(_field_value(cmd, "GDT_SYMBOL", 0) or "").strip()

        line1_count = _get_data_type_count(cmd, "LINE1_MEAS")
        if line1_count >= 1:
            j = _pick_fcf_line_index(cmd, line1_count, "LINE1")
            name = cmd_id
            if name not in skip:
                plus_tol = _safe_float(_field_value(cmd, "LINE1_PLUSTOL", j))
                minus_tol = _normalize_minus_tol(
                    _safe_float(_field_value(cmd, "LINE1_MINUSTOL", j)), show_negative
                )
                feat = str(_field_value(cmd, "LINE1_FEATNAME", j) or "").strip()
                records.append(
                    FeatureRecord(
                        name=name,
                        feature_type="FCF_SIZE",
                        nominal=AxisValues(d=_safe_float(_field_value(cmd, "LINE1_NOMINAL", j))),
                        measured=AxisValues(d=_safe_float(_field_value(cmd, "LINE1_MEAS", j))),
                        deviation=AxisValues(d=_safe_float(_field_value(cmd, "LINE1_DEV", j))),
                        tolerance=_tolerance_from_limits(plus_tol, minus_tol, "D"),
                        cmd_index=idx,
                        source_kind="fcf",
                        write_axis="D",
                        feat1=feat,
                        plus_tol=plus_tol,
                        minus_tol=minus_tol,
                        bonus=_safe_float(_field_value(cmd, "LINE1_BONUS", j)),
                        outtol=_safe_float(_field_value(cmd, "LINE1_OUTTOL", j)),
                    )
                )

        line2_count = _get_data_type_count(cmd, "LINE2_MEAS")
        if line2_count >= 1:
            j = _pick_fcf_line_index(cmd, line2_count, "LINE2")
            name = cmd_id
            if name not in skip:
                axis = str(_field_value(cmd, "LINE2_AXIS", j) or "D").strip()
                plus_tol = _safe_float(_field_value(cmd, "LINE2_PLUSTOL", j))
                minus_tol = _normalize_minus_tol(
                    _safe_float(_field_value(cmd, "LINE2_MINUSTOL", j)), show_negative
                )
                feat = str(_field_value(cmd, "LINE2_FEATNAME", j) or "").strip()
                axis_letter = _gdt_axis_letter(gdt_symbol, axis)
                nom, meas, dev = _axis_values_for_letter(
                    axis,
                    _safe_float(_field_value(cmd, "LINE2_NOMINAL", j)),
                    _safe_float(_field_value(cmd, "LINE2_MEAS", j)),
                    _safe_float(_field_value(cmd, "LINE2_DEV", j)),
                )
                records.append(
                    FeatureRecord(
                        name=name,
                        feature_type=f"FCF_{gdt_symbol or 'GDT'}",
                        nominal=nom,
                        measured=meas,
                        deviation=dev,
                        tolerance=_tolerance_from_limits(plus_tol, minus_tol, axis),
                        cmd_index=idx,
                        source_kind="fcf",
                        write_axis=axis_letter,
                        feat1=feat,
                        segment="SEG=1",
                        plus_tol=plus_tol,
                        minus_tol=minus_tol,
                        bonus=_safe_float(_field_value(cmd, "LINE2_BONUS", j)),
                        outtol=_safe_float(_field_value(cmd, "LINE2_OUTTOL", j)),
                    )
                )

        line3_tol = str(_field_value(cmd, "LINE3_TOL", 0) or "").strip()
        line3_count = _get_data_type_count(cmd, "LINE3_MEAS")
        if line3_count >= 1:
            j = _pick_fcf_line_index(cmd, line3_count, "LINE3")
            name = cmd_id
            if name not in skip:
                plus_tol = _safe_float(_field_value(cmd, "LINE3_PLUSTOL", j))
                minus_raw = _safe_float(_field_value(cmd, "LINE3_MINUSTOL", j))
                minus_tol = _normalize_minus_tol(minus_raw, show_negative)
                suffix = line3_tol or gdt_symbol or "SEC"
                records.append(
                    FeatureRecord(
                        name=name,
                        feature_type=f"FCF_{suffix}",
                        nominal=AxisValues(d=_safe_float(_field_value(cmd, "LINE3_NOMINAL", j))),
                        measured=AxisValues(d=_safe_float(_field_value(cmd, "LINE3_MEAS", j))),
                        deviation=AxisValues(d=_safe_float(_field_value(cmd, "LINE3_DEV", j))),
                        tolerance=_tolerance_from_limits(plus_tol, minus_tol, "D"),
                        cmd_index=idx,
                        source_kind="fcf",
                        write_axis="D",
                    )
                )

    return records


def _extract_datum_markers(cache: list[tuple[int, Any]]) -> list[FeatureRecord]:
    """基准定义 — IsDimension 无实测或 DATDEF 类命令。"""
    records: list[FeatureRecord] = []
    seen: set[str] = set()

    for idx, cmd in cache:
        try:
            if not cmd.IsDimension:
                continue
        except Exception:
            continue

        if not _com_failed(_field_value(cmd, "DIM_MEASURED", 0)):
            continue

        try:
            dim = cmd.DimensionCommand
            dim_id = _command_name(dim, cmd)
        except Exception:
            dim_id = _command_name(cmd)

        if not dim_id or not _is_datum_id(dim_id) or dim_id in seen:
            continue
        seen.add(dim_id)
        nom = _safe_float(_field_value(cmd, "NOMINAL", 0))
        records.append(
            FeatureRecord(
                name=dim_id,
                feature_type="DATUM",
                nominal=AxisValues(d=nom) if nom is not None else AxisValues(),
                cmd_index=idx,
                source_kind="datum",
            )
        )

    return records


def _is_assign_command(cmd: Any) -> bool:
    try:
        if hasattr(cmd, "IsAssign") and bool(cmd.IsAssign):
            return True
    except Exception:
        pass
    try:
        desc = str(cmd.TypeDescription or "").strip().upper()
        if any(k in desc for k in ("ASSIGN", "赋值", "计算", "CALC")):
            return True
    except Exception:
        pass
    try:
        typ = str(getattr(cmd, "Type", "") or "").strip().upper()
        if typ in ("ASSIGN", "CALC", "CALCULATED"):
            return True
    except Exception:
        pass
    return False


def _extract_assign_commands(cache: list[tuple[int, Any]]) -> list[FeatureRecord]:
    """计算/赋值尺寸 — ASSIGN 或 TypeDescription 含「赋值/计算」。"""
    records: list[FeatureRecord] = []
    seen: set[str] = set()

    for idx, cmd in cache:
        if not _is_assign_command(cmd):
            continue
        name = _command_name(cmd)
        if not name:
            name = f"ASSIGN_{idx}"
        if name in seen:
            continue
        seen.add(name)

        axis = str(_field_value(cmd, "AXIS", 0) or "D").strip().upper()
        nominal = _safe_float(_field_value(cmd, "NOMINAL", 0))
        measured = _read_dimension_measured(cmd, _try_get_dimension_command(cmd))
        if measured is None:
            measured = _safe_float(_field_value(cmd, "MEAS_D", 0))
        nom, meas, dev = _axis_values_for_letter(axis, nominal, measured, _deviation(measured, nominal))
        desc = _dimension_type_name(cmd)
        if desc in ("0", "None", "DIMENSION"):
            desc = "计算尺寸"

        records.append(
            FeatureRecord(
                name=name,
                feature_type=desc,
                nominal=nom,
                measured=meas,
                deviation=dev,
                cmd_index=idx,
                source_kind="assign",
                write_axis=axis,
            )
        )
    return records


def summarize_extraction(records: list[FeatureRecord]) -> dict[str, int]:
    """按 feature_type 统计提取结果。"""
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec.feature_type] = counts.get(rec.feature_type, 0) + 1
    return counts


def summarize_dimension_records(records: list[FeatureRecord]) -> dict[str, int]:
    """统计评价尺寸（含 2D 距离 / 位置 / 半径位置等）。"""
    counts: dict[str, int] = {}
    for rec in records:
        if not is_dimension_record(rec):
            continue
        counts[rec.feature_type] = counts.get(rec.feature_type, 0) + 1
    return counts


def is_dimension_record(rec: FeatureRecord) -> bool:
    """判断是否为 Legacy 评价尺寸（非特征、非 ToleranceCommand）。"""
    ftype = rec.feature_type or ""
    if rec.source_kind in ("assign", "datum", "prg_offline"):
        return False
    if ftype.startswith("TOLERANCE_") or ftype == "DATUM" or ftype.startswith("FCF_"):
        return False
    if ftype in ("终止尺寸", "基准定义", "尺寸格式"):
        return False
    keywords = (
        "尺寸",
        "距离",
        "位置",
        "半径",
        "半角",
        "直径",
        "角度",  # 尺寸3D 角度 / 圆锥角度
        "DIMENSION",
    )
    return any(k in ftype for k in keywords)


class RecordCategory(str, Enum):
    """GUI / 导出用业务分类。"""

    FEATURE = "特征"
    EVALUATED_DIM = "已评价尺寸"
    GDT = "形位公差"
    SIZE_DIM = "大小尺寸"
    DATUM = "基准"
    CALCULATED = "计算尺寸"


RECORD_CATEGORY_ORDER: tuple[str, ...] = (
    "全部",
    RecordCategory.FEATURE.value,
    RecordCategory.EVALUATED_DIM.value,
    RecordCategory.GDT.value,
    RecordCategory.SIZE_DIM.value,
    RecordCategory.DATUM.value,
    RecordCategory.CALCULATED.value,
)


def classify_record(rec: FeatureRecord) -> RecordCategory:
    """将单条记录归入业务分类。"""
    ftype = rec.feature_type or ""
    if rec.source_kind == "datum" or ftype == "DATUM":
        return RecordCategory.DATUM
    if rec.source_kind == "assign" or "计算" in ftype or "ASSIGN" in ftype.upper():
        return RecordCategory.CALCULATED
    if ftype in ("FCF_SIZE", "TOLERANCE_SIZE"):
        return RecordCategory.SIZE_DIM
    if ftype.startswith("TOLERANCE_") or (
        ftype.startswith("FCF_") and ftype not in ("FCF_SIZE", "FCF_OFFLINE")
    ):
        return RecordCategory.GDT
    if is_dimension_record(rec):
        return RecordCategory.EVALUATED_DIM
    return RecordCategory.FEATURE


def summarize_by_category(records: list[FeatureRecord]) -> dict[str, int]:
    """按业务分类统计条数。"""
    counts: dict[str, int] = {}
    for rec in records:
        key = classify_record(rec).value
        counts[key] = counts.get(key, 0) + 1
    return counts


def parse_category_filter(label: str) -> str:
    """从「已评价尺寸 (11)」解析出分类名。"""
    text = (label or "全部").strip()
    if text == "全部":
        return "全部"
    for name in RECORD_CATEGORY_ORDER[1:]:
        if text == name or text.startswith(f"{name} ("):
            return name
    return "全部"


def category_filter_options(records: list[FeatureRecord]) -> list[str]:
    """生成分类下拉选项（含条数）。"""
    counts = summarize_by_category(records)
    total = len(records)
    options = [f"全部 ({total})" if total else "全部"]
    for name in RECORD_CATEGORY_ORDER[1:]:
        n = counts.get(name, 0)
        options.append(f"{name} ({n})" if n else name)
    return options


def matches_evaluated_dim_group(feature_type: str, group: str) -> bool:
    """已评价尺寸子类：距离 / 位置 / 半径 / 夹角。"""
    ftype = feature_type or ""
    if group == "距离":
        return "距离" in ftype
    if group == "位置":
        return ftype == "尺寸位置"
    if group == "半径":
        return "半径" in ftype
    if group == "夹角":
        return "半角" in ftype or "夹角" in ftype
    return ftype == group


def summarize_feature_elements(records: list[FeatureRecord]) -> dict[str, int]:
    """统计 11 类基础元素覆盖（仅 IsFeature 类记录）。"""
    counts: dict[str, int] = {}
    for rec in records:
        element = normalize_feature_element(rec.feature_type)
        if element is None:
            continue
        counts[element] = counts.get(element, 0) + 1
    return counts
