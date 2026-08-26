"""公差判定单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.models import AxisValues, FeatureRecord, PassStatus, ToleranceConfig
from core.tolerance import apply_tolerance


def test_asymmetric_tolerance_fail_on_minus_side():
    """+0.10/-0.02，偏差 -0.05 应判超差（旧逻辑会按 ±0.10 误判合格）。"""
    rec = FeatureRecord(
        name="FAI_1",
        feature_type="尺寸位置",
        deviation=AxisValues(d=-0.05),
        plus_tol=0.10,
        minus_tol=-0.02,
        write_axis="D",
    )
    apply_tolerance([rec], ToleranceConfig())
    assert rec.status == PassStatus.FAIL
    assert "D" in rec.failed_axes


def test_asymmetric_tolerance_pass_inside():
    rec = FeatureRecord(
        name="FAI_1",
        feature_type="尺寸位置",
        deviation=AxisValues(d=-0.01),
        plus_tol=0.10,
        minus_tol=-0.02,
        write_axis="D",
    )
    apply_tolerance([rec], ToleranceConfig())
    assert rec.status == PassStatus.PASS


def test_outtol_forces_fail():
    rec = FeatureRecord(
        name="FAI_1",
        feature_type="尺寸位置",
        deviation=AxisValues(d=0.0),
        plus_tol=0.1,
        minus_tol=-0.1,
        outtol=0.02,
        write_axis="D",
    )
    apply_tolerance([rec], ToleranceConfig())
    assert rec.status == PassStatus.FAIL


def test_angle_without_tol_not_fail_by_length_default():
    rec = FeatureRecord(
        name="FAI_A",
        feature_type="尺寸3D 角度",
        deviation=AxisValues(angle=0.2),
        write_axis="A",
    )
    apply_tolerance([rec], ToleranceConfig())
    assert rec.status == PassStatus.NA
