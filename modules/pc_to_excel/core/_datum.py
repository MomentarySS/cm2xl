"""拆分自 data_extractor.py — 基准定义与计算/赋值尺寸。"""

from __future__ import annotations

from typing import Any

from ._common import (
    _axis_values_for_letter,
    _com_failed,
    _command_name,
    _deviation,
    _dimension_type_name,
    _field_value,
    _is_datum_id,
    _safe_float,
)
from ._dimension import _read_dimension_measured, _try_get_dimension_command
from .models import AxisValues, FeatureRecord


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
