"""PC-DMIS COM 数据提取 — 遍历 Commands 按类型解析为 FeatureRecord。

实现参考:
- https://blog.iyatt.com/?p=18363  (特征 / 评价尺寸)
- https://blog.iyatt.com/?p=18719  (ToleranceCommand 形位公差, 2023.2+)
- https://docs.hexagonmi.com/pcdmis/2024.1/en/helpcenter/mergedProjects/automationobjects/webframe.html

本文件仅为入口：组合并统一导出各子模块，不承担具体实现。具体实现已拆分到
_common / _command_cache / _dimension / _tolerance / feature / _datum /
classification 等子模块（保持原函数名与 `_` 前缀不变）。
"""

from __future__ import annotations

from typing import Any

from ._command_cache import _build_command_cache, _get_command_at, _iter_commands
from ._common import ExportScope, ProgressCallback, _dimension_type_name
from ._datum import _extract_assign_commands, _extract_datum_markers
from ._dimension import (
    _collect_dimension_companions,
    _dimension_name,
    _extract_dimensions,
    _is_dimension_companion_row,
    _resolve_dimension_record_type,
    _should_pair_dimension_commands,
    locate_dimension_measured_field,
)
from ._tolerance import (
    _extract_fcf_commands,
    _extract_tolerance_commands,
    _gdt_axis_letter,
    _iter_tolerance_feature_indices,
    _pick_tolerance_feature_index,
)
from .classification import (
    RECORD_CATEGORY_ORDER,
    RecordCategory,
    category_filter_options,
    classify_record,
    is_dimension_record,
    matches_evaluated_dim_group,
    normalize_feature_element,
    parse_category_filter,
    summarize_by_category,
    summarize_dimension_records,
    summarize_extraction,
    summarize_feature_elements,
)
from .feature import _extract_features
from .models import FeatureRecord


def _minus_tol_show_negative(part: Any) -> bool:
    try:
        return bool(part.PartProgramSettings.MinusTolerancesShowNegative)
    except Exception:
        return False


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
    try:
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
    finally:
        cache.clear()
        by_idx.clear()


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


__all__ = [
    "ExportScope",
    "ProgressCallback",
    "RecordCategory",
    "RECORD_CATEGORY_ORDER",
    "category_filter_options",
    "classify_record",
    "extract_from_application",
    "extract_from_part_program",
    "is_dimension_record",
    "locate_dimension_measured_field",
    "matches_evaluated_dim_group",
    "normalize_feature_element",
    "parse_category_filter",
    "summarize_by_category",
    "summarize_dimension_records",
    "summarize_extraction",
    "summarize_feature_elements",
]
