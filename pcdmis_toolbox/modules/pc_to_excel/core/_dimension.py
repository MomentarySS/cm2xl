"""拆分自 data_extractor.py — Legacy 评价尺寸读取与配对合并。"""

from __future__ import annotations

from typing import Any

from ._common import (
    _axis_values_for_letter,
    _com_failed,
    _command_name,
    _dimension_type_name,
    _field_value,
    _is_datum_id,
    _normalize_minus_tol,
    _safe_float,
    _text_value,
    _tolerance_from_limits,
)
from .models import AxisValues, FeatureRecord


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
