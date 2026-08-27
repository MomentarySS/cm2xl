"""拆分自 data_extractor.py — 特征（FeatureCommand）数据提取与几何参数读取。"""

from __future__ import annotations

from typing import Any

import pythoncom
import win32com.client

from ..connector.pcdlrn_constants import get_const
from ._common import _command_name, _deviation, _field_value, _safe_float
from .models import AxisValues, FeatureRecord


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
