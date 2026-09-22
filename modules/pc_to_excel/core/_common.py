"""拆分自 data_extractor.py — 跨模块共享的底层工具与 COM 字段访问。

仅依赖 models 与 connector.pcdlrn_constants（叶子模块），供 _dimension /
_tolerance / feature / _datum 等子模块复用，避免循环导入。
"""

from __future__ import annotations

import math
from typing import Any, Callable

from ..connector.pcdlrn_constants import get_const
from .models import AxisValues


ProgressCallback = Callable[[int, int, str], None]

ExportScope = str  # "report" | "all"


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


def _safe_float(value: Any) -> float | None:
    """COM float 安全转换 — COM 失败值（False/None）或 NaN 均返回 None。"""
    if _com_failed(value):
        return None
    try:
        f = float(value)
        # NaN 在 PCDMIS COM 中也表示无效值，应作 None 处理
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _normalize_minus_tol(minus: float | None, show_negative: bool) -> float | None:
    """PC-DMIS 内部下公差符号与显示设置相关，取实际意义值。"""
    if minus is None:
        return None
    if show_negative:
        return minus
    return -minus


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


def _dimension_type_name(cmd: Any) -> str:
    try:
        desc = str(cmd.TypeDescription or "").strip()
        if desc and desc not in ("0", "None"):
            return desc
    except Exception:
        pass
    return "DIMENSION"


def _deviation(measured: float | None, nominal: float | None) -> float | None:
    if measured is None or nominal is None:
        return None
    return measured - nominal


def _is_datum_id(name: str) -> bool:
    """基准命令 ID 通常为单字母或短字母组合（A、B、A-B）。"""
    n = (name or "").strip()
    if not n or len(n) > 3:
        return False
    return n.replace("-", "").isalpha()


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
