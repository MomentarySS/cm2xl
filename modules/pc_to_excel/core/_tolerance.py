"""拆分自 data_extractor.py — 形位公差 / GD&T（ToleranceCommand + Legacy FCF）。"""

from __future__ import annotations

import logging
from typing import Any

from ._common import (
    _axis_values_for_letter,
    _command_name,
    _field_value,
    _get_data_type_count,
    _normalize_minus_tol,
    _safe_float,
    _text_value,
    _tolerance_from_limits,
)
from .models import AxisValues, FeatureRecord

logger = logging.getLogger("pc_to_excel")


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


def _extract_tolerance_commands(
    cache: list[tuple[int, Any]],
    show_negative: bool,
) -> tuple[list[FeatureRecord], set[int]]:
    """形位公差 — ToleranceCommand（COM 约 2022.1+；2017–2020 R2 走 IsFCFCommand）。"""
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
                    # COM 失败值（False/None）必须走 _safe_float —— 直接取负会得到 0，
                    # 下公差被当成真实下限 ⇒ 偏差在负侧的行全判超差（假 NG）。
                    minus_tol = _normalize_minus_tol(
                        _safe_float(tol_cmd.sizeMinusTol(j)), show_negative
                    )
                    if minus_tol is None:
                        # 有 plus 也是有效数据 ⇒ 保留该行（单边公差），只记日志便于追溯
                        logger.debug(
                            "尺寸行下公差不可用（COM 返回 False/None 或未设置），"
                            "按单边公差保留: cmd=%s size=%d/%d",
                            display_name,
                            j,
                            size_count,
                        )
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
                        minus_tol = _normalize_minus_tol(
                            _safe_float(tol_cmd.segmentDimMinusTol(k, j)), show_negative
                        )
                        if minus_tol is None:
                            logger.debug(
                                "区段行下公差不可用（COM 返回 False/None 或未设置），"
                                "按单边公差保留: cmd=%s seg=%d feat=%d",
                                display_name,
                                k,
                                j,
                            )

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
