"""`dump-tols` 诊断子命令的单元测试（不连 PCDMIS）。"""

from __future__ import annotations

import pytest

from ..cli import _dump_minus, _dump_probe, cmd_dump_tols


class _FakeArgs:
    def __init__(self, **kw):
        self.filter = ""
        self.out = None
        for key, val in kw.items():
            setattr(self, key, val)


def test_dump_probe_distinguishes_raise_from_com_failure():
    """诊断必须把「COM 抛异常」与「返回失败值」分开报 —— 两者是不同的失效路径。"""

    def _boom():
        raise ValueError("x")

    assert _dump_probe(lambda: 0.01) == (0.01, "ok")
    assert _dump_probe(lambda: 0.0) == (0.0, "ok")  # 真实 0 公差不算失败
    assert _dump_probe(lambda: False) == (False, "COM_FAILED")
    assert _dump_probe(lambda: None) == (None, "COM_FAILED")
    assert _dump_probe(_boom) == (None, "RAISED:ValueError")


def test_dump_minus_converts_com_string_to_float():
    """COM 读回的是字符串，必须过 `_safe_float` 再归一化（否则会报出字符串）。"""
    assert _dump_minus("  -0.010", "ok", True) == -0.01
    assert _dump_minus("   0.000", "ok", True) == 0.0
    assert _dump_minus("  -0.010", "ok", False) == 0.01


def test_dump_minus_unavailable_states_are_none():
    assert _dump_minus(False, "COM_FAILED", True) is None
    assert _dump_minus(None, "RAISED:ValueError", True) is None


def test_dump_tols_is_wired_into_cli_parser(monkeypatch):
    """`dump-tols` 必须真的挂到 argparse 上，且连不上时以 1 退出（不是 argparse 的 2）。"""
    import sys

    from ..connector.base import ConnectionInfo

    monkeypatch.setattr(sys, "argv", ["pc_to_excel", "dump-tols", "--filter", "CC_"])
    monkeypatch.setattr(
        "modules.pc_to_excel.cli.PcdmisConnector.connect",
        lambda self: ConnectionInfo(connected=False, source="test", message="未连接"),
    )
    with pytest.raises(SystemExit) as exc:
        from ..cli import main

        main()
    assert exc.value.code == 1


def test_dump_tols_reports_not_connected(capsys, monkeypatch):
    from ..connector.base import ConnectionInfo

    monkeypatch.setattr(
        "modules.pc_to_excel.cli.PcdmisConnector.connect",
        lambda self: ConnectionInfo(connected=False, source="test", message="未连接"),
    )
    assert cmd_dump_tols(_FakeArgs()) == 1
    assert "未连接" in capsys.readouterr().err


# ─── P3-11.1 诊断：BONUS 必须在 dump 范围里 ───────────────────────────────

def test_dump_size_methods_includes_size_bonus():
    """P3-11.1 诊断：ToleranceCommand 尺寸行的 BONUS 必须在 dump 范围里。

    不加则 PC-DMIS 上 PC-DMIS 返回 False/抛异常 的真实原因被遮蔽，
    只能瞎猜根因。
    """
    from ..cli import _DUMP_SIZE_METHODS

    assert "sizeBonus" in _DUMP_SIZE_METHODS


def test_dump_seg_methods_includes_segment_dim_bonus():
    """P3-11.1 诊断：ToleranceCommand 区段行的 BONUS 必须在 dump 范围里。"""
    from ..cli import _DUMP_SEG_METHODS

    assert "segmentDimBonus" in _DUMP_SEG_METHODS
