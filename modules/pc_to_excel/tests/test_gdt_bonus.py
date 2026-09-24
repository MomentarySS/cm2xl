"""形位公差 BONUS 字段读取 helper 的单元测试（P3-11.1 修复）。

PC-DMIS 2024.1 真机 dump（2026-09-24）确认：
- `tol.segmentDimBonus(k, j)` 对所有 13 种形位符号都返 0.0 [ok]
- `cmd.GetFieldValue(LINE2_BONUS, j)` 在 2024.1 上返 False
  （被 _safe_float 归 None ⇒ 修复前 cm2xl 输出 BONUS 列空）

修复策略 = 双路径读取：方法路径优先，字段 ID 路径作回退。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ..core._tolerance import _read_gdt_bonus


class _TolCmdZero:
    """PC-DMIS 2024.1 实测形态：segmentDimBonus 返 0.0（位置度允差补偿=0）。"""
    def segmentDimBonus(self, k, j):
        return 0.0


class _TolCmdRealValue:
    def segmentDimBonus(self, k, j):
        return 0.5


class _TolCmdNone:
    def segmentDimBonus(self, k, j):
        return None


class _TolCmdRaises:
    def segmentDimBonus(self, k, j):
        raise AttributeError("模拟 COM 抛异常")


class _CmdWithTol:
    """cmd.ToleranceCommand 正常返回。"""
    def __init__(self, tol, field_value=None):
        self._tol = tol
        self._field_value = field_value

    @property
    def ToleranceCommand(self):
        return self._tol

    def GetFieldValue(self, const, idx):
        if self._field_value is None:
            return False  # PC-DMIS 2024.1 真实行为：LINE2_BONUS 返 False
        if isinstance(self._field_value, Exception):
            raise self._field_value
        return self._field_value


class _CmdNoTol:
    """没有 ToleranceCommand 属性（PC-DMIS 2017-2020 R2）。"""
    def GetFieldValue(self, const, idx):
        return False


class _CmdTolRaises:
    """ToleranceCommand 属性访问抛异常（COM 失败）。"""
    @property
    def ToleranceCommand(self):
        raise OSError("模拟 COM 失败")

    def GetFieldValue(self, const, idx):
        return False


# ---------------------------------------------------------------------------

def test_method_path_zero_is_transmitted_as_zero():
    """方法路径返 0.0 → 返回 0.0（**不是** None）—— 真实位置度允差补偿=0。"""
    cmd = _CmdWithTol(_TolCmdZero())
    assert _read_gdt_bonus(cmd, k=2, j=1) == 0.0
    assert _read_gdt_bonus(cmd, k=2, j=1) is not None


def test_method_path_real_value_is_transmitted():
    """方法路径返非 0 真实值（如 0.5）→ 直接透传。"""
    cmd = _CmdWithTol(_TolCmdRealValue())
    assert _read_gdt_bonus(cmd, k=2, j=1) == 0.5


def test_method_path_none_falls_back_to_field_id():
    """方法路径返 None → 回退字段 ID 路径（防御式兼容未来 PC-DMIS 版本）。"""
    cmd = _CmdWithTol(_TolCmdNone(), field_value=0.7)
    assert _read_gdt_bonus(cmd, k=2, j=1) == 0.7


def test_method_path_false_falls_back_to_field_id():
    """方法路径返 False（PC-DMIS COM 失败）→ 回退字段 ID 路径。"""
    class _TolReturnsFalse:
        def segmentDimBonus(self, k, j):
            return False

    cmd = _CmdWithTol(_TolReturnsFalse(), field_value=0.3)
    assert _read_gdt_bonus(cmd, k=2, j=1) == 0.3


def test_method_path_raises_falls_back_to_field_id():
    """方法路径抛异常 → _safe_com_float 兜住 → 回退字段 ID 路径。"""
    cmd = _CmdWithTol(_TolCmdRaises(), field_value=0.6)
    assert _read_gdt_bonus(cmd, k=2, j=1) == 0.6


def test_no_tolerance_command_property_falls_back():
    """cmd 没有 ToleranceCommand 属性（PC-DMIS 2017-2020 R2）→ 回退字段 ID 路径。"""
    cmd = _CmdNoTol()
    # _CmdNoTol 的 GetFieldValue 返 False → 字段 ID 路径也返 None
    assert _read_gdt_bonus(cmd, k=2, j=1) is None


def test_tolerance_command_property_raises_does_not_propagate():
    """cmd.ToleranceCommand 访问抛异常 → 不外抛，兜住 + 回退字段 ID 路径。"""
    cmd = _CmdTolRaises()
    # 不抛 + 字段 ID 路径返 False → 返回 None
    result = _read_gdt_bonus(cmd, k=2, j=1)
    assert result is None


def test_both_paths_fail_returns_none():
    """两条路径都失败 → 返回 None（cm2xl 输出空 cell）。"""
    cmd = _CmdWithTol(_TolCmdNone(), field_value=False)
    assert _read_gdt_bonus(cmd, k=2, j=1) is None


def test_method_path_zero_takes_precedence_over_field_zero():
    """方法路径优先：即使字段 ID 也返 0.0，方法路径是首选（语义与生产代码一致）。"""
    cmd = _CmdWithTol(_TolCmdZero(), field_value=0.5)
    # 方法路径返 0.0 → 直接返回 0.0（不回退）
    assert _read_gdt_bonus(cmd, k=2, j=1) == 0.0


def test_method_path_does_not_swallow_real_value_as_failed():
    """真实 0.0 不被当成 COM 失败 —— 这是 PC-DMIS COM 约定（_com_failed 用 is False 而非 == 0）。"""
    # _safe_com_float 内部调 _safe_float，_safe_float 调 _com_failed，
    # _com_failed 用 is False（不 == 0）⇒ 0.0 不算失败。
    cmd = _CmdWithTol(_TolCmdZero())
    assert _read_gdt_bonus(cmd, k=2, j=1) == 0.0


# ── 真实集成路径：_extract_tolerance_commands 把 bonus 透传到 FeatureRecord ──

def test_extract_fcf_commands_propagates_bonus_to_records():
    """集成测试：_extract_fcf_commands 走完 helper 后，records 的 bonus 字段非空。

    CC_38 等形位公差行走的是 _extract_fcf_commands（不是 _extract_tolerance_commands）——
    PC-DMIS 2024.1 上 IsFcfCommand=True 走老 FCF 路径。模拟 _CmdWithTol 让
    segmentDimBonus 返 0.0（PC-DMIS 2024.1 真实形态）。
    """
    from ..core._tolerance import _extract_fcf_commands

    class _Tol:
        ID = "CC_38"
        GDT_SYMBOL = "位置度"
        FeatureCount = 1
        SegmentCount = 1
        SizeCount = 0

        def FeatureID(self, j):
            return "圆柱3"

        def SegmentAxis(self, j):
            return "D"

        def SegmentDimNominal(self, k, j):
            return 0.0

        def SegmentDimMeasured(self, k, j):
            return 0.005

        def SegmentDimDeviation(self, k, j):
            return 0.005

        def SegmentDimPlusTol(self, k, j):
            return 0.3

        def segmentDimMinusTol(self, k, j):
            return 0.0

        def SegmentDimOutTol(self, k, j):
            return 0.0

        def segmentDimBonus(self, k, j):
            return 0.0  # PC-DMIS 2024.1 实测：返 0.0

    class _Cmd:
        ID = "CC_38"
        IsFcfCommand = True
        GDT_SYMBOL = "位置度"
        ToleranceCommand = _Tol()
        # GetFieldValue 模拟 PC-DMIS 2024.1 返 False（字段 ID 路径不可用）
        def GetFieldValue(self, const, idx):
            return False
        def GetDataTypeCount(self, field_const):
            # 647=LINE1_MEAS, 688=LINE2_MEAS, 771=LINE3_MEAS
            if field_const == 647: return 0  # FCF_SIZE 不走
            if field_const == 688: return 1  # FCF_GDT 走
            if field_const == 771: return 0  # LINE3 不走
            return 0

    records = _extract_fcf_commands([(82, _Cmd())], show_negative=False)
    assert len(records) == 1, f"应有 1 条记录（位置度形位公差），实际 {len(records)}"
    assert records[0].bonus == 0.0, (
        f"修复前 cm2xl 在 BONUS 列输出 None — 应为 0.0（位置度允差补偿场景）；"
        f"实际={records[0].bonus!r}"
    )


# ── helper 路径导入 ──

# helper 从顶层 `from ..core._tolerance import _read_gdt_bonus` 导入