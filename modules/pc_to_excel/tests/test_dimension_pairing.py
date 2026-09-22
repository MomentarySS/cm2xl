"""尺寸位置配对逻辑单元测试（无需 PCDMIS）。"""

from __future__ import annotations

from types import SimpleNamespace

from ..core.data_extractor import (  # noqa: E402
    _collect_dimension_companions,
    _dimension_name,
    _dimension_type_name,
    _is_dimension_companion_row,
    _resolve_dimension_record_type,
    _should_pair_dimension_commands,
)
from ..core.report_filter import _is_orphan_companion_dimension  # noqa: E402
from ..core.models import FeatureRecord  # noqa: E402


class _Cmd:
    def __init__(
        self,
        *,
        cmd_id: str = "",
        type_desc: str = "尺寸位置",
        is_dimension: bool = True,
        measured: float | None = None,
        axis: str = "D",
    ):
        self.ID = cmd_id
        self.TypeDescription = type_desc
        self.IsDimension = is_dimension
        self._measured = measured
        self._axis = axis

    def GetFieldValue(self, field, index=0):
        if field in (184, "DISPLAY_ID"):
            return False
        if field in ("DIM_MEASURED", 328):
            return self._measured if self._measured is not None else False
        if field in ("AXIS", 132):
            return self._axis
        return False

    def GetText(self, field, index=0):
        return ""


def test_pair_size_position_with_diameter_position():
    header = _Cmd(cmd_id="CC_5.1", type_desc="尺寸位置", measured=0.0)
    companion = _Cmd(cmd_id="", type_desc="直径位置", measured=1.7)
    assert _should_pair_dimension_commands(header, companion, False)


def test_pair_size_position_with_length_position():
    header = _Cmd(cmd_id="FAI_17A", type_desc="尺寸位置", measured=0.0)
    companion = _Cmd(cmd_id="", type_desc="长度位置", measured=3.995, axis="L")
    assert _is_dimension_companion_row(header, companion, False)


def test_collect_xyz_axis_companions():
    header = _Cmd(cmd_id="基准", type_desc="尺寸位置", measured=0.0)
    by_idx = {
        1: header,
        2: _Cmd(cmd_id="", type_desc="X轴位置", measured=-0.011, axis="X"),
        3: _Cmd(cmd_id="", type_desc="Y轴位置", measured=0.005, axis="Y"),
        4: _Cmd(cmd_id="", type_desc="Z轴位置", measured=0.002, axis="Z"),
        5: _Cmd(cmd_id="FAI_1", type_desc="尺寸 2D 距离", measured=1.4, axis="M"),
    }
    companions = _collect_dimension_companions(by_idx, 1, 5, header, False)
    assert len(companions) == 3
    assert _dimension_type_name(companions[0][1]) == "X轴位置"


def test_dimension_name_uses_command_id_only():
    header = _Cmd(cmd_id="CC_5.1", type_desc="尺寸位置")
    dim = SimpleNamespace(Feat1="圆3")
    # 尺寸列用命令 ID；特征名走描述括号，不再拼进 ID
    assert _dimension_name(header, dim, 120) == "CC_5.1"


def test_fai_17a_name_preserved():
    header = _Cmd(cmd_id="FAI_17A", type_desc="尺寸位置")
    dim = SimpleNamespace(Feat1="圆槽1")
    assert _dimension_name(header, dim, 211) == "FAI_17A"


def test_pair_cone_angle_with_cone_angle_position():
    header = _Cmd(cmd_id="FAI_2-1", type_desc="尺寸位置", measured=0.0)
    companion = _Cmd(cmd_id="", type_desc="锥角位置", measured=120.0, axis="A")
    assert _is_dimension_companion_row(header, companion, False)
    # 与 PCDMIS 原生 Excel 一致：评价类型保留头行「尺寸位置」
    assert _resolve_dimension_record_type(header, companion) == "尺寸位置"


def test_collect_cone_angle_companion():
    header = _Cmd(cmd_id="FAI_2-1", type_desc="圆锥角度", measured=0.0)
    by_idx = {
        1: header,
        2: _Cmd(cmd_id="", type_desc="锥角位置", measured=120.0, axis="A"),
        3: _Cmd(cmd_id="FAI_1", type_desc="尺寸 2D 距离", measured=14.0, axis="M"),
    }
    companions = _collect_dimension_companions(by_idx, 1, 3, header, False)
    assert len(companions) == 1
    assert _dimension_type_name(companions[0][1]) == "锥角位置"


def test_orphan_cone_angle_filtered():
    rec = FeatureRecord(name="锥角位置_251", feature_type="锥角位置")
    assert _is_orphan_companion_dimension(rec)


if __name__ == "__main__":
    test_pair_size_position_with_diameter_position()
    test_pair_size_position_with_length_position()
    test_collect_xyz_axis_companions()
    test_dimension_name_uses_command_id_only()
    test_fai_17a_name_preserved()
    test_pair_cone_angle_with_cone_angle_position()
    test_collect_cone_angle_companion()
    test_orphan_cone_angle_filtered()
    print("ok")
