"""报告窗口过滤单元测试。"""

from __future__ import annotations

from ..core.models import AxisValues, FeatureRecord, PassStatus
from ..core.report_filter import (
    REPORT_CATEGORIES,
    _has_measured_values,
    _is_cmd_marked,
    _is_orphan_companion_dimension,
    _is_zero_only_position_header,
    _record_marked,
    filter_report_window_records,
    is_report_window_record,
    summarize_report_filter,
)


# ---------------------------------------------------------------------------
# Helper: mock PCDMIS command with configurable .Marked attribute
# ---------------------------------------------------------------------------


class _MockCmd:
    def __init__(self, marked: bool = True):
        self.Marked = marked


class _MockCmdNoMarked:
    """COM object that raises AttributeError when accessing .Marked."""

    def __getattr__(self, name: str):
        if name == "Marked":
            raise AttributeError("COM object does not have 'Marked' attribute")
        raise AttributeError(name)


# ---------------------------------------------------------------------------
# FeatureRecord factory helpers
# ---------------------------------------------------------------------------


def _rec(
    name: str = "FAI_1",
    feature_type: str = "尺寸位置",
    *,
    measured: AxisValues | None = None,
    deviation: AxisValues | None = None,
    source_kind: str = "dimension",
    cmd_index: int = 1,
    write_cmd_index: int = 0,
) -> FeatureRecord:
    return FeatureRecord(
        name=name,
        feature_type=feature_type,
        measured=measured or AxisValues(d=14.0),
        deviation=deviation or AxisValues(),
        source_kind=source_kind,
        cmd_index=cmd_index,
        write_cmd_index=write_cmd_index,
    )


# ---------------------------------------------------------------------------
# _is_orphan_companion_dimension
# ---------------------------------------------------------------------------


def test_orphan_companion_length():
    rec = _rec(name="长度位置_1")
    assert _is_orphan_companion_dimension(rec) is True


def test_orphan_companion_diam():
    rec = _rec(name="直径位置_3")
    assert _is_orphan_companion_dimension(rec) is True


def test_orphan_companion_x_axis():
    rec = _rec(name="X轴位置_5")
    assert _is_orphan_companion_dimension(rec) is True


def test_orphan_companion_radius():
    rec = _rec(name="半径位置_2")
    assert _is_orphan_companion_dimension(rec) is True


def test_orphan_companion_angle():
    rec = _rec(name="锥角位置_1")
    assert _is_orphan_companion_dimension(rec) is True


def test_orphan_diam_with_diam_feature_type():
    """feature_type=直径位置 + name matching _ORPHAN_DIAM_POSITION → True."""
    rec = FeatureRecord(name="直径位置_7", feature_type="直径位置", measured=AxisValues())
    assert _is_orphan_companion_dimension(rec) is True


def test_not_orphan_regular_name():
    rec = _rec(name="FAI_1")
    assert _is_orphan_companion_dimension(rec) is False


def test_not_orphan_autocylinder():
    """圆特征不会被误识别为orphan（ORPHAN_COMPANION_NAME不匹配）。"""
    rec = _rec(name="AUTOCYLINDER")
    assert _is_orphan_companion_dimension(rec) is False


def test_not_orphan_matched_position_header():
    """匹配的尺寸位置头行（有真实实测值）不是orphan。"""
    rec = _rec(name="尺寸位置_1", measured=AxisValues(d=14.0))
    assert _is_orphan_companion_dimension(rec) is False


# ---------------------------------------------------------------------------
# _is_zero_only_position_header
# ---------------------------------------------------------------------------


def test_zero_only_true():
    """所有实测值为0 → 头行占位符。"""
    rec = _rec(
        name="尺寸位置_1",
        feature_type="尺寸位置",
        source_kind="dimension",
        measured=AxisValues(x=0.0, y=0.0, z=0.0),
    )
    assert _is_zero_only_position_header(rec) is True


def test_zero_only_with_near_zero():
    """|value| < 1e-12 视为0。"""
    rec = _rec(
        name="尺寸位置_1",
        feature_type="尺寸位置",
        source_kind="dimension",
        measured=AxisValues(d=1e-14),
    )
    assert _is_zero_only_position_header(rec) is True


def test_zero_only_false_has_nonzero():
    """有任意非零实测值 → 不是占位符。"""
    rec = _rec(
        name="尺寸位置_1",
        feature_type="尺寸位置",
        source_kind="dimension",
        measured=AxisValues(d=0.0, x=0.001),
    )
    assert _is_zero_only_position_header(rec) is False


def test_zero_only_false_wrong_feature_type():
    """feature_type不是尺寸位置 → 不是占位符。"""
    rec = _rec(
        name="尺寸位置_1",
        feature_type="圆形",
        source_kind="dimension",
        measured=AxisValues(x=0.0, y=0.0, z=0.0),
    )
    assert _is_zero_only_position_header(rec) is False


def test_zero_only_false_wrong_source_kind():
    """source_kind不是dimension → 不是占位符。"""
    rec = _rec(
        name="尺寸位置_1",
        feature_type="尺寸位置",
        source_kind="datum",
        measured=AxisValues(x=0.0, y=0.0, z=0.0),
    )
    assert _is_zero_only_position_header(rec) is False


# ---------------------------------------------------------------------------
# _is_cmd_marked
# ---------------------------------------------------------------------------


def test_cmd_marked_true():
    assert _is_cmd_marked(_MockCmd(marked=True)) is True


def test_cmd_marked_false():
    assert _is_cmd_marked(_MockCmd(marked=False)) is False


def test_cmd_marked_missing_attribute():
    """COM对象缺少Marked属性时返回False（保守默认，不误过滤）。"""
    assert _is_cmd_marked(_MockCmdNoMarked()) is False


# ---------------------------------------------------------------------------
# _record_marked
# ---------------------------------------------------------------------------


def test_record_marked_single_index_marked():
    cmd_by_index = {1: _MockCmd(marked=True)}
    rec = _rec(cmd_index=1, write_cmd_index=0)
    assert _record_marked(rec, cmd_by_index) is True


def test_record_marked_write_index_marked():
    cmd_by_index = {5: _MockCmd(marked=True)}
    rec = _rec(cmd_index=0, write_cmd_index=5)
    assert _record_marked(rec, cmd_by_index) is True


def test_record_marked_both_indices():
    cmd_by_index = {1: _MockCmd(marked=False), 5: _MockCmd(marked=True)}
    rec = _rec(cmd_index=1, write_cmd_index=5)
    assert _record_marked(rec, cmd_by_index) is True


def test_record_marked_neither_marked():
    cmd_by_index = {1: _MockCmd(marked=False), 5: _MockCmd(marked=False)}
    rec = _rec(cmd_index=1, write_cmd_index=5)
    assert _record_marked(rec, cmd_by_index) is False


def test_record_marked_no_indices():
    """cmd_index和write_cmd_index均为0 → 默认返回True（不过滤）。"""
    rec = _rec(cmd_index=0, write_cmd_index=0)
    assert _record_marked(rec, {}) is True


def test_record_marked_index_not_in_map():
    """cmd_index对应命令不在cmd_by_index中 → False。"""
    rec = _rec(cmd_index=99, write_cmd_index=0)
    assert _record_marked(rec, {1: _MockCmd(marked=True)}) is False


# ---------------------------------------------------------------------------
# _has_measured_values
# ---------------------------------------------------------------------------


def test_has_measured_values_measured_d():
    rec = _rec(measured=AxisValues(d=14.0))
    assert _has_measured_values(rec) is True


def test_has_measured_values_deviation():
    rec = _rec(measured=AxisValues(), deviation=AxisValues(d=0.05))
    assert _has_measured_values(rec) is True


def test_has_measured_values_both_none():
    rec = _rec(measured=AxisValues(), deviation=AxisValues())
    assert _has_measured_values(rec) is False


def test_has_measured_values_x_axis():
    rec = _rec(measured=AxisValues(x=1.0))
    assert _has_measured_values(rec) is True


# ---------------------------------------------------------------------------
# is_report_window_record
# ---------------------------------------------------------------------------


def test_is_report_window_discards_feature():
    """FEATURE分类不是报告窗口数据。"""
    rec = _rec(feature_type="圆")
    # classify_record(圆) → FEATURE，不在 REPORT_CATEGORIES 中
    assert is_report_window_record(rec) is False


def test_is_report_window_discards_datum():
    """DATUM分类不是报告窗口数据。"""
    rec = _rec(feature_type="DATUM", source_kind="datum")
    assert is_report_window_record(rec) is False


def test_is_report_window_discards_orphan():
    """orphan companion dimension 会被排除。"""
    rec = _rec(name="长度位置_1", feature_type="尺寸位置")
    # classify_record → EVALUATED_DIM（是REPORT_CATEGORIES），但 orphan
    assert is_report_window_record(rec) is False


def test_is_report_window_discards_zero_header():
    """零占位符头行会被排除。"""
    rec = _rec(
        name="尺寸位置_1",
        feature_type="尺寸位置",
        source_kind="dimension",
        measured=AxisValues(x=0.0, y=0.0, z=0.0),
    )
    assert is_report_window_record(rec) is False


def test_is_report_window_discards_no_measured():
    """无实测值的已评价尺寸会被排除。"""
    rec = _rec(feature_type="已评价尺寸", measured=AxisValues(), deviation=AxisValues())
    assert is_report_window_record(rec) is False


def test_is_report_window_passes_valid_evaluated_dim():
    """EVALUATED_DIM + 有实测值 + 无orphan标记 → 通过。"""
    rec = _rec(
        name="FAI_1",
        feature_type="尺寸位置",
        measured=AxisValues(d=14.0),
        source_kind="dimension",
    )
    assert is_report_window_record(rec) is True


def test_is_report_window_respects_require_marked_true():
    """require_marked=True 且命令未标记 → False。"""
    rec = _rec(cmd_index=1, write_cmd_index=0)
    cmd_by_index = {1: _MockCmd(marked=False)}
    assert (
        is_report_window_record(rec, cmd_by_index, require_marked=True) is False
    )


def test_is_report_window_respects_require_marked_false():
    """require_marked=False 时跳过Marked检查。"""
    rec = _rec(cmd_index=1, write_cmd_index=0)
    cmd_by_index = {1: _MockCmd(marked=False)}
    assert (
        is_report_window_record(rec, cmd_by_index, require_marked=False) is True
    )


def test_is_report_window_no_cmd_by_index_with_require_marked():
    """cmd_by_index=None 时跳过Marked检查，直接返回True（如果其他条件通过）。"""
    rec = _rec(feature_type="已评价尺寸", measured=AxisValues(d=1.0))
    assert is_report_window_record(rec, None, require_marked=True) is True


def test_is_report_window_gdt_feature():
    """GDT分类（形位公差）在REPORT_CATEGORIES中 → 通过。

    注意：GDT记录的实测值必须在TOLERANCE_VALUE_KEYS（x/y/z/d/length/width/height/angle/minor_d）
    中才被is_report_window_record保留；i/j/k虽然也是AxisValues字段，
    但不属于TOLERANCE_VALUE_KEYS，不会触发_has_measured_values为True。
    """
    rec = _rec(
        name="位置度_1",
        feature_type="TOLERANCE_位置度",
        measured=AxisValues(d=0.05),  # d 在 TOLERANCE_VALUE_KEYS 中
    )
    assert is_report_window_record(rec) is True


def test_is_report_window_size_dim():
    """SIZE_DIM分类在REPORT_CATEGORIES中 → 通过。"""
    rec = _rec(
        name="FCF_SIZE_1",
        feature_type="FCF_SIZE",
        measured=AxisValues(d=10.0),
    )
    assert is_report_window_record(rec) is True


# ---------------------------------------------------------------------------
# filter_report_window_records
# ---------------------------------------------------------------------------


def test_filter_report_window_records_mixed():
    valid = _rec(name="有效_1", feature_type="尺寸位置", measured=AxisValues(d=1.0))
    orphan = _rec(name="长度位置_1", feature_type="尺寸位置")
    no_data = _rec(
        name="无数据", feature_type="已评价尺寸", measured=AxisValues(), deviation=AxisValues()
    )
    # i 不在 TOLERANCE_VALUE_KEYS 中，故 _has_measured_values 返回 False，会被过滤
    gdt = _rec(
        name="形位_1", feature_type="TOLERANCE_位置度", measured=AxisValues(i=0.1)
    )
    records = [orphan, valid, no_data, gdt]
    result = filter_report_window_records(records)
    # GDT(i=0.1) 被 _has_measured_values 过滤（i∉TOLERANCE_VALUE_KEYS）
    # 仅 valid（尺寸位置+有实测值）通过
    assert len(result) == 1
    assert result[0] is valid


def test_filter_report_window_records_require_marked():
    marked_cmd = {1: _MockCmd(marked=True)}
    unmarked_rec = _rec(name="未标记", feature_type="尺寸位置", measured=AxisValues(d=1.0))
    marked_rec = _rec(
        name="已标记", feature_type="尺寸位置", measured=AxisValues(d=1.0), cmd_index=2
    )
    records = [unmarked_rec, marked_rec]
    cmd_by_index = {1: _MockCmd(marked=False), 2: _MockCmd(marked=True)}
    result = filter_report_window_records(records, cmd_by_index, require_marked=True)
    assert len(result) == 1
    assert result[0].name == "已标记"


# ---------------------------------------------------------------------------
# summarize_report_filter
# ---------------------------------------------------------------------------


def test_summarize_report_filter():
    before = [_rec(name=f"r{i}") for i in range(10)]
    after = before[:3]
    summary = summarize_report_filter(before, after)
    assert summary == "报告窗口筛选: 10 → 3 条"
