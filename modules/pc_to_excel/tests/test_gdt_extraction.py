"""形位公差提取逻辑单元测试（无需 PCDMIS）。"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from ..core.data_extractor import (  # noqa: E402
    _extract_tolerance_commands,
    _gdt_axis_letter,
    _iter_tolerance_feature_indices,
    _pick_tolerance_feature_index,
)
from ..core.models import ToleranceConfig, PassStatus  # noqa: E402
from ..core.tolerance import apply_tolerance  # noqa: E402


class _TolCmd:
    def __init__(self):
        self.ID = "FAI_POS"
        self.gdtSymbol = "位置度"
        self.sizeCountCombined = 0
        self.SegmentCount = 1
        self.FeatureCount = 3
        self._feats = {
            1: "圆1 - LS",
            2: "圆5",
            3: "圆8",
        }
        self._meas = {2: 0.004, 3: 0.006}

    def FeatureID(self, j):
        return self._feats[j]

    def SegmentAxis(self, j):
        return "M"

    def SegmentDimNominal(self, k, j):
        return 0.0

    def SegmentDimMeasured(self, k, j):
        return self._meas.get(j, 0.0)

    def SegmentDimDeviation(self, k, j):
        return self._meas.get(j, 0.0)

    def SegmentDimPlusTol(self, k, j):
        return 0.04

    def segmentDimMinusTol(self, k, j):
        return 0.0

    def SegmentDimOutTol(self, k, j):
        return 0.0


class _TolCmdWrapper:
    def __init__(self, tol: _TolCmd):
        self.ID = tol.ID
        self.IsToleranceCommand = True
        self.ToleranceCommand = tol


def test_iter_skips_constructed_and_keeps_all_real_features():
    tol = _TolCmd()
    indices = _iter_tolerance_feature_indices(tol, 3)
    assert indices == [2, 3]
    assert _pick_tolerance_feature_index(tol, 3) == 2


def test_extract_multi_feature_segments():
    tol = _TolCmd()
    cache = [(10, _TolCmdWrapper(tol))]
    records, indices = _extract_tolerance_commands(cache, show_negative=True)
    assert indices == {10}
    assert len(records) == 2
    assert {r.feat1 for r in records} == {"圆5", "圆8"}
    assert all(r.name == "FAI_POS" for r in records)
    assert all(r.write_axis == "TP" for r in records)  # 位置度 → TP


def test_gdt_axis_letter_position_vs_flatness():
    assert _gdt_axis_letter("位置度", "M") == "TP"
    assert _gdt_axis_letter("平面度", "M") == "M"
    assert _gdt_axis_letter("同心度", "M") == "M"


# ---------------------------------------------------------------------------
# P2-1 下公差未做 COM 失败防护
#
# 修复前：`minus_raw = tol_cmd.sizeMinusTol(j)` 直接取负，没有 _safe_float：
#   - 返回 None  → `-None` 抛 TypeError，被 `except Exception: continue` 吞掉，
#                  而 indices.add(idx) 已认领该命令 ⇒ 该行**静默消失**；
#   - 返回 False（本包约定的 COM 失败值）→ `-False == 0` → 下公差被当成真实下限
#                  ⇒ 偏差在负侧的行被判**假超差**。
# 期望值从被测对象自身推导：记录条数、minus_tol、以及 apply_tolerance 的判定结果。
# ---------------------------------------------------------------------------


class _SizeTolCmd:
    """尺寸区 ToleranceCommand —— sizeMinusTol 可注入 COM 失败值。"""

    def __init__(self, minus_value):
        self.ID = "FAI_D1"
        self.gdtSymbol = ""
        self.sizeCountCombined = 1
        self.SegmentCount = 0
        self.FeatureCount = 0
        self._minus = minus_value

    def sizeMinusTol(self, j):
        return self._minus

    def sizePlusTol(self, j):
        return 0.05

    def sizeNominal(self, j):
        return 10.0

    def sizeMeasured(self, j):
        return 9.96

    def sizeDeviation(self, j):
        return -0.04

    def sizeText(self, j):
        return "10.0"

    def SizeAxis(self, j):
        return "D"

    def sizeOutOfTol(self, j):
        return 0.0


class _SegMinusOverride(_TolCmd):
    """区段区 ToleranceCommand —— 只覆盖 segmentDimMinusTol 的返回值。"""

    def __init__(self, minus_value):
        super().__init__()
        self._minus = minus_value

    def segmentDimMinusTol(self, k, j):
        return self._minus


def _extract_size_record(minus_value, show_negative=True):
    tol = _SizeTolCmd(minus_value)
    return _extract_tolerance_commands([(7, _TolCmdWrapper(tol))], show_negative=show_negative)


def _extract_segment_records(minus_value, show_negative=True):
    tol = _SegMinusOverride(minus_value)
    return _extract_tolerance_commands(
        [(10, _TolCmdWrapper(tol))], show_negative=show_negative
    )


# show_negative=False 是「丢行」那条路径：`-None` 才抛 TypeError。
# 现场默认就是 False（`_minus_tol_show_negative()` 异常时回落 False），所以两个取值都要覆盖。
_SHOW_NEGATIVE_CASES = [True, False]


@pytest.mark.parametrize("show_negative", _SHOW_NEGATIVE_CASES)
@pytest.mark.parametrize("minus_value", [None, False])
def test_size_minus_tol_com_failure_keeps_row(minus_value, show_negative):
    """sizeMinusTol 返回 None/False ⇒ 记录不丢，minus_tol 为 None。"""
    records, indices = _extract_size_record(minus_value, show_negative=show_negative)
    assert indices == {7}
    assert len(records) == 1, "下公差读不到时该行被丢弃了"
    rec = records[0]
    assert rec.minus_tol is None
    # plus 有值时 tolerance 仍须按单边构造（边界 1）
    assert rec.plus_tol == 0.05
    assert rec.tolerance is not None
    assert rec.tolerance.d == 0.05


@pytest.mark.parametrize("show_negative", _SHOW_NEGATIVE_CASES)
def test_size_minus_tol_false_does_not_cause_false_ng(show_negative):
    """COM 返回 False 时不得把下公差当 0 ⇒ 偏差 -0.04 在 +0.05 单边内应判合格。"""
    records, _ = _extract_size_record(False, show_negative=show_negative)
    rec = records[0]
    apply_tolerance(records, ToleranceConfig())
    assert rec.failed_axes == []
    assert rec.status == PassStatus.PASS


@pytest.mark.parametrize("show_negative", _SHOW_NEGATIVE_CASES)
@pytest.mark.parametrize("minus_value", [None, False])
def test_segment_minus_tol_com_failure_keeps_rows(minus_value, show_negative):
    """segmentDimMinusTol 返回 None/False ⇒ 两条区段记录都不丢。"""
    records, indices = _extract_segment_records(minus_value, show_negative=show_negative)
    assert indices == {10}
    assert len(records) == 2, "下公差读不到时区段行被丢弃了"
    assert all(r.minus_tol is None for r in records)
    assert all(r.plus_tol == 0.04 for r in records)


@pytest.mark.parametrize("show_negative", _SHOW_NEGATIVE_CASES)
def test_minus_tol_sign_convention_unchanged(show_negative):
    """show_negative 的符号约定必须与改动前一致（不能顺手取反）。"""
    rec = _extract_size_record(0.03, show_negative=show_negative)[0][0]
    assert rec.minus_tol == (0.03 if show_negative else -0.03)


@pytest.mark.parametrize("show_negative", _SHOW_NEGATIVE_CASES)
def test_minus_tol_unavailable_logs_debug(caplog, show_negative):
    """读不到下公差时补一条 debug 日志，便于真机追溯。"""
    with caplog.at_level(logging.DEBUG, logger="pc_to_excel"):
        _extract_size_record(False, show_negative=show_negative)
    assert any("下公差不可用" in r.getMessage() for r in caplog.records)


if __name__ == "__main__":
    test_iter_skips_constructed_and_keeps_all_real_features()
    test_extract_multi_feature_segments()
    test_gdt_axis_letter_position_vs_flatness()
    print("ok")
