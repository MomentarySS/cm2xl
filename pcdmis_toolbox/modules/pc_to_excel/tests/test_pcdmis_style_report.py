"""PC-DMIS 样式报告行展开测试。"""

from __future__ import annotations

from ..core.models import AxisValues, FeatureRecord, ReportHeaderInfo  # noqa: E402
from ..export.pcdmis_style_report import (  # noqa: E402
    _HEADER,
    _META_ROWS,
    flatten_to_pcdmis_rows,
)


def test_2d_distance_row():
    rec = FeatureRecord(
        name="CC_1",
        feature_type="尺寸 2D 距离",
        nominal=AxisValues(d=1.4),
        measured=AxisValues(d=1.4),
        deviation=AxisValues(d=0.0),
        feat1="圆5",
        feat2="圆柱1",
        plus_tol=0.02,
        minus_tol=-0.02,
        write_axis="M",
    )
    rows = flatten_to_pcdmis_rows(rec)
    assert len(rows) == 1
    row = rows[0]
    assert row.dim_id == "CC_1"
    assert row.description == "尺寸 2D 距离 (圆5,圆柱1)"
    assert row.axis == "M"
    assert "特征" not in _HEADER
    assert "段" not in _HEADER


def test_position_row():
    rec = FeatureRecord(
        name="CC_5.1-圆3",
        feature_type="尺寸位置",
        nominal=AxisValues(d=1.7),
        measured=AxisValues(d=1.7),
        deviation=AxisValues(d=0.0),
        feat1="圆3",
        plus_tol=0.02,
        minus_tol=-0.02,
        write_axis="D",
    )
    rows = flatten_to_pcdmis_rows(rec)
    row = rows[0]
    assert row.dim_id == "CC_5.1"
    assert row.description == "尺寸位置 (圆3)"
    assert row.axis == "D"


def test_gdt_row():
    rec = FeatureRecord(
        name="CC_18.1",
        feature_type="TOLERANCE_位置度",
        nominal=AxisValues(d=0.0),
        measured=AxisValues(d=0.004),
        deviation=AxisValues(d=0.004),
        feat1="点12",
        plus_tol=0.05,
        minus_tol=0.0,
        write_axis="TP",
        segment="SEG=1",
        source_kind="tolerance",
    )
    rows = flatten_to_pcdmis_rows(rec)
    row = rows[0]
    assert row.description == "ISO 几何公差命令 (点12)"
    assert row.axis == "TP"


def test_meta_rows():
    assert len(_META_ROWS) == 5
    labels = [label for label, _ in _META_ROWS]
    assert "PC-DMIS测量程序" in labels
    assert "序列号" in labels


def test_fai_hyphen_id_preserved():
    rec = FeatureRecord(
        name="FAI_2-1",
        feature_type="尺寸位置",
        nominal=AxisValues(angle=120.0),
        measured=AxisValues(angle=120.0),
        deviation=AxisValues(angle=0.0),
        feat1="圆锥3",
        write_axis="A",
    )
    rows = flatten_to_pcdmis_rows(rec)
    assert rows[0].dim_id == "FAI_2-1"
    assert rows[0].description == "尺寸位置 (圆锥3)"
    assert rows[0].axis == "A"


if __name__ == "__main__":
    test_2d_distance_row()
    test_position_row()
    test_gdt_row()
    test_meta_rows()
    test_fai_hyphen_id_preserved()
    print("ok")
