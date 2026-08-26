"""形位公差提取逻辑单元测试（无需 PCDMIS）。"""

from __future__ import annotations

from types import SimpleNamespace

from ..core.data_extractor import (  # noqa: E402
    _extract_tolerance_commands,
    _gdt_axis_letter,
    _iter_tolerance_feature_indices,
    _pick_tolerance_feature_index,
)


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


if __name__ == "__main__":
    test_iter_skips_constructed_and_keeps_all_real_features()
    test_extract_multi_feature_segments()
    test_gdt_axis_letter_position_vs_flatness()
    print("ok")
