"""PC-DMIS 2017 R2–2026.1 连接兼容：ProgID 排序、附着运行实例、tlb 字段号。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ..app_meta import PROG_ID_CANDIDATES, PROG_ID_GENERIC
from ..connector import com_detector as cd
from ..connector.com_detector import (
    _prog_id_sort_key,
    get_connect_candidates,
    match_running_prog_id,
)
from ..connector.pcdlrn_constants import (
    _FallbackConstants,
    _constants_from_tlb_file,
)


TLB_2017 = Path(r"C:\Program Files\Hexagon\PC-DMIS 2017 R2 64-bit\Pcdlrn.tlb")
TLB_2019 = Path(r"C:\Program Files\Hexagon\PC-DMIS 2019 R2 64-bit\Pcdlrn.tlb")
TLB_2020 = Path(r"C:\Program Files\Hexagon\PC-DMIS 2020 R2 64-bit\Pcdlrn.tlb")
TLB_2024 = Path(r"C:\Program Files\Hexagon\PC-DMIS 2024.1 64-bit\Pcdlrn.tlb")


def test_prog_id_candidates_cover_2017_to_2026():
    assert "PCDLRN.Application.12.2" in PROG_ID_CANDIDATES
    assert "PCDLRN.Application.14.2" in PROG_ID_CANDIDATES
    assert "PCDLRN.Application.15.2" in PROG_ID_CANDIDATES
    assert "PCDLRN.Application.19.1" in PROG_ID_CANDIDATES
    assert "PCDLRN.Application.21.1" in PROG_ID_CANDIDATES
    assert PROG_ID_CANDIDATES[-1] == PROG_ID_GENERIC


def test_prog_id_sort_newest_first():
    ids = [
        "PCDLRN.Application.12.2",
        "PCDLRN.Application",
        "PCDLRN.Application.19.1",
        "PCDLRN.Application.15.2",
        "PCDLRN.Application.14.2",
    ]
    ordered = sorted(ids, key=_prog_id_sort_key)
    assert ordered[0] == "PCDLRN.Application.19.1"
    assert ordered[-1] == "PCDLRN.Application"
    assert ordered[1:-1] == [
        "PCDLRN.Application.15.2",
        "PCDLRN.Application.14.2",
        "PCDLRN.Application.12.2",
    ]


def test_get_connect_candidates_prefers_running_exe(monkeypatch):
    registered = [
        "PCDLRN.Application.19.1",
        "PCDLRN.Application.15.2",
        "PCDLRN.Application.14.2",
        "PCDLRN.Application.12.2",
        "PCDLRN.Application",
    ]
    exe_map = {
        "PCDLRN.Application.12.2": r"C:\Program Files\Hexagon\PC-DMIS 2017 R2 64-bit\PCDLRN.exe",
        "PCDLRN.Application.14.2": r"C:\Program Files\Hexagon\PC-DMIS 2019 R2 64-bit\PCDLRN.exe",
        "PCDLRN.Application.15.2": r"C:\Program Files\Hexagon\PC-DMIS 2020 R2 64-bit\PCDLRN.exe",
        "PCDLRN.Application.19.1": r"C:\Program Files\Hexagon\PC-DMIS 2024.1 64-bit\PCDLRN.exe",
        "PCDLRN.Application": r"C:\Program Files\Hexagon\PC-DMIS 2017 R2 64-bit\PCDLRN.exe",
    }
    monkeypatch.setattr(cd, "_registered_prog_ids", lambda: list(registered))
    monkeypatch.setattr(
        cd,
        "get_pcdmis_exe_path",
        lambda: exe_map["PCDLRN.Application.12.2"],
    )
    monkeypatch.setattr(cd, "_exe_from_prog_id", lambda pid: exe_map.get(pid))
    candidates = get_connect_candidates()
    assert candidates[0] == "PCDLRN.Application.12.2"
    assert match_running_prog_id(registered) == "PCDLRN.Application.12.2"


def test_fallback_unit_type_matches_tlb():
    assert _FallbackConstants.UNIT_TYPE == 172
    assert _FallbackConstants.DIM_MEASURED == 328
    assert _FallbackConstants.LINE1_MEAS == 647


@pytest.mark.parametrize("tlb_path", [TLB_2017, TLB_2019, TLB_2020, TLB_2024])
def test_local_tlb_field_ids_stable(tlb_path: Path):
    if not tlb_path.is_file():
        pytest.skip(f"本机无 {tlb_path}")
    snap = _constants_from_tlb_file(str(tlb_path))
    assert snap is not None
    assert snap.AXIS == 132
    assert snap.NOMINAL == 166
    assert snap.UNIT_TYPE == 172
    assert snap.DIM_MEASURED == 328
    assert snap.LINE1_MEAS == 647
    assert snap.LINE2_MEAS == 688
    assert snap.GDT_SYMBOL == 708
    assert snap.BASIC_SCRIPT == 12346
