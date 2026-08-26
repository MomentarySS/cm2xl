"""报告窗口数据过滤 — 仅保留已评价/输出到报告的尺寸。"""

from __future__ import annotations

import re
from typing import Any

from core.data_extractor import RecordCategory, classify_record
from core.models import FeatureRecord, TOLERANCE_VALUE_KEYS


REPORT_CATEGORIES: frozenset[RecordCategory] = frozenset(
    {
        RecordCategory.EVALUATED_DIM,
        RecordCategory.GDT,
        RecordCategory.SIZE_DIM,
    }
)

_ORPHAN_DIAM_POSITION = re.compile(r"^直径位置_\d+$")
_ORPHAN_COMPANION_NAME = re.compile(
    r"^(长度位置|直径位置|半径位置|半角位置|锥角位置|X轴位置|Y轴位置|Z轴位置)_\d+$"
)


def _is_orphan_companion_dimension(rec: FeatureRecord) -> bool:
    """未与尺寸位置头行合并的系统命名附属行 — 报告窗口不会出现。"""
    name = (rec.name or "").replace(" ", "")
    if _ORPHAN_COMPANION_NAME.match(name):
        return True
    if (rec.feature_type or "").replace(" ", "") == "直径位置":
        return bool(_ORPHAN_DIAM_POSITION.match(rec.name or ""))
    return False


def _is_zero_only_position_header(rec: FeatureRecord) -> bool:
    """尺寸位置头行占位（实测全 0，真实值在配对行）。"""
    if (rec.feature_type or "") != "尺寸位置" or rec.source_kind != "dimension":
        return False
    values = [
        getattr(rec.measured, key)
        for key in TOLERANCE_VALUE_KEYS
        if getattr(rec.measured, key) is not None
    ]
    if not values:
        return False
    return all(abs(float(v)) < 1e-12 for v in values)


def _is_cmd_marked(cmd: Any) -> bool:
    try:
        return bool(cmd.Marked)
    except Exception:
        return True


def _record_marked(rec: FeatureRecord, cmd_by_index: dict[int, Any]) -> bool:
    indices = {rec.cmd_index, rec.write_cmd_index}
    indices.discard(0)
    if not indices:
        return True
    return any(_is_cmd_marked(cmd_by_index[idx]) for idx in indices if idx in cmd_by_index)


def _has_measured_values(rec: FeatureRecord) -> bool:
    for bundle in (rec.measured, rec.deviation):
        for key in TOLERANCE_VALUE_KEYS:
            if getattr(bundle, key, None) is not None:
                return True
    return False


def is_report_window_record(
    rec: FeatureRecord,
    cmd_by_index: dict[int, Any] | None = None,
    *,
    require_marked: bool = True,
) -> bool:
    """是否为报告窗口会出现的已评价数据（非原始特征/基准/计算行）。"""
    if classify_record(rec) not in REPORT_CATEGORIES:
        return False
    if _is_orphan_companion_dimension(rec) or _is_zero_only_position_header(rec):
        return False
    if not _has_measured_values(rec):
        return False
    if require_marked and cmd_by_index is not None:
        return _record_marked(rec, cmd_by_index)
    return True


def filter_report_window_records(
    records: list[FeatureRecord],
    cmd_by_index: dict[int, Any] | None = None,
    *,
    require_marked: bool = True,
) -> list[FeatureRecord]:
    return [
        rec
        for rec in records
        if is_report_window_record(rec, cmd_by_index, require_marked=require_marked)
    ]


def summarize_report_filter(
    before: list[FeatureRecord],
    after: list[FeatureRecord],
) -> str:
    return f"报告窗口筛选: {len(before)} → {len(after)} 条"
