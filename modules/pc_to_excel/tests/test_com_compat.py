"""PC-DMIS 2017 R2–2026.1 连接兼容：ProgID 排序、附着运行实例、tlb 字段号。"""

from __future__ import annotations

import ast
import inspect
import textwrap
import threading
from pathlib import Path

import pytest


def _code_source(func) -> str:
    """返回 func 的源码，剔除 docstring。

    源码级断言（"不允许出现 X 调用"）必须只查真实代码：docstring 里为了说明
    背景往往会提到被禁用的 API 名字，直接用 getsource() 会误报。
    """
    src = inspect.getsource(func)
    src = textwrap.dedent(src)  # 方法源码带类缩进，ast.parse 需要顶格
    tree = ast.parse(src)
    node = tree.body[0]
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        doc_node = node.body[0]
        doc = ast.get_source_segment(src, doc_node)
        if doc:
            src = src.replace(doc, "", 1)
    return src

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


def test_dispatch_prefers_get_active_object(monkeypatch):
    """已运行实例优先 GetActiveObject，且全程禁止 EnsureDispatch。

    顺序是固定的，不再靠 is_pcdmis_running() 探测（那会 spawn tasklist.exe，
    实测 ~190ms/次）。本测试同时断言 dispatch_pcdmis 不再调用该探测。
    """
    calls: list[str] = []
    guard: list[bool] = []

    class _Win32:
        @staticmethod
        def GetActiveObject(prog_id):
            calls.append("GetActiveObject")
            return object()

        @staticmethod
        def Dispatch(prog_id):
            calls.append("Dispatch")
            raise AssertionError("GetActiveObject 成功时不应回退到 Dispatch")

    def _spy_is_pcdmis_running() -> bool:
        guard.append(True)
        return True

    monkeypatch.setattr(cd, "is_pcdmis_running", _spy_is_pcdmis_running)
    monkeypatch.setattr("win32com.client.GetActiveObject", _Win32.GetActiveObject)
    monkeypatch.setattr("win32com.client.Dispatch", _Win32.Dispatch)
    result = cd.dispatch_pcdmis("PCDLRN.Application.19.1")
    assert result is not None
    assert calls == ["GetActiveObject"]
    assert guard == [], "dispatch_pcdmis() 不应调用 is_pcdmis_running()（每次 spawn tasklist）"
    # 项目铁律：禁止 EnsureDispatch（会重建 gencache，二次导出假死）。
    # 源码层面断言一次，防止将来有人把它加回来（剔除 docstring，避免误报）。
    assert "EnsureDispatch" not in _code_source(cd.dispatch_pcdmis)


def test_dispatch_falls_back_to_dispatch(monkeypatch):
    """GetActiveObject 失败（未运行实例）时回退 Dispatch。"""
    calls: list[str] = []

    class _Win32:
        @staticmethod
        def GetActiveObject(prog_id):
            calls.append("GetActiveObject")
            raise RuntimeError("RPC server is unavailable")

        @staticmethod
        def Dispatch(prog_id):
            calls.append("Dispatch")
            return "dispatched-app"

    monkeypatch.setattr("win32com.client.GetActiveObject", _Win32.GetActiveObject)
    monkeypatch.setattr("win32com.client.Dispatch", _Win32.Dispatch)
    result = cd.dispatch_pcdmis("PCDLRN.Application.19.1")
    assert result == "dispatched-app"
    assert calls == ["GetActiveObject", "Dispatch"], "必须先试 GetActiveObject，失败后转 Dispatch"


def test_dispatch_raises_when_both_fail(monkeypatch):
    """两条路都失败时报 ToolboxError，且错误信息包含两个工厂的失败原因。"""
    from utils.error_codes import ErrorCode, ToolboxError

    class _Win32:
        @staticmethod
        def GetActiveObject(prog_id):
            raise RuntimeError("not running")

        @staticmethod
        def Dispatch(prog_id):
            raise RuntimeError("bad clsid")

    monkeypatch.setattr("win32com.client.GetActiveObject", _Win32.GetActiveObject)
    monkeypatch.setattr("win32com.client.Dispatch", _Win32.Dispatch)
    with pytest.raises(ToolboxError) as exc_info:
        cd.dispatch_pcdmis("PCDLRN.Application.19.1")
    assert exc_info.value.code == ErrorCode.PCDMIS_CONNECT_FAIL
    msg = str(exc_info.value)
    assert "GetActiveObject" in msg and "not running" in msg
    assert "Dispatch" in msg and "bad clsid" in msg


# ── Fix 4-B：get_active_part_name() 不得再走 ensure_session() ──────────────


class _FakePart:
    def __init__(self, name: str) -> None:
        self.Name = name


class _FakeApp:
    def __init__(self, part) -> None:
        self.ActivePartProgram = part


def _make_connector(monkeypatch, *, connected: bool, part, bind_raises=False):
    """构造一个最小 PcdmisConnector，只注入 get_active_part_name 依赖的字段。"""
    from ..connector.pcdmis_connector import PcdmisConnector

    conn = PcdmisConnector()
    conn._connected = connected
    conn._active_prog_id = "PCDLRN.Application.19.1" if connected else ""
    conn._last_part_name = "CACHED"

    def _bind_app():
        if bind_raises:
            raise RuntimeError("COM session dead")
        return _FakeApp(part)

    monkeypatch.setattr(conn, "_bind_app", _bind_app)

    # 任何路径调 ensure_session() 都算回归：那会多付一次 dispatch 探测
    def _boom():
        raise AssertionError("get_active_part_name() 不应调用 ensure_session()")

    monkeypatch.setattr(conn, "ensure_session", _boom)
    return conn


def test_get_active_part_name_skips_ensure_session(monkeypatch):
    """已连接时只做轻量读取，不再 ensure_session() 自愈。"""
    conn = _make_connector(monkeypatch, connected=True, part=_FakePart("PART-42"))
    assert conn.get_active_part_name() == "PART-42"
    assert conn._last_part_name == "PART-42"


def test_get_active_part_name_not_connected_returns_cache(monkeypatch):
    """未连接直接返回缓存，不碰 COM。"""
    conn = _make_connector(monkeypatch, connected=False, part=None)
    assert conn.get_active_part_name() == "CACHED"


def test_get_active_part_name_failure_falls_back_to_cache(monkeypatch):
    """读失败（COM 会话失效）时兜底返回上次缓存，不抛异常。"""
    conn = _make_connector(monkeypatch, connected=True, part=None, bind_raises=True)
    assert conn.get_active_part_name() == "CACHED"


def test_get_active_part_name_none_part_returns_cache(monkeypatch):
    """没有打开的程序时返回缓存。"""
    conn = _make_connector(monkeypatch, connected=True, part=None)
    assert conn.get_active_part_name() == "CACHED"


def test_get_active_part_name_no_com_lock_returns_cache(monkeypatch):
    """抽数中抢不到 com_call_lock 时返回缓存，绝不阻塞。

    注意 com_call_lock 是 threading.RLock()：同线程可重入，必须由**另一个
    线程**持有才能真正制造 acquire(blocking=False) 失败的场景。
    """
    conn = _make_connector(monkeypatch, connected=True, part=_FakePart("PART-99"))
    from ..connector import com_detector as cd

    held = threading.Event()
    release = threading.Event()

    def _hold():
        with cd.com_call_lock:
            held.set()
            release.wait(5)

    worker = threading.Thread(target=_hold, daemon=True)
    worker.start()
    try:
        assert held.wait(5), "worker 未能持有 com_call_lock"
        assert conn.get_active_part_name() == "CACHED"
    finally:
        release.set()
        worker.join(5)


def test_get_active_part_name_source_has_no_ensure_session():
    """源码层面断言：该方法不再包含 ensure_session 调用（剔除 docstring）。"""
    from ..connector.pcdmis_connector import PcdmisConnector

    src = _code_source(PcdmisConnector.get_active_part_name)
    assert "ensure_session" not in src, (
        "get_active_part_name() 不应再调用 ensure_session()（多付一次 dispatch 探测）"
    )


def test_ensure_session_still_used_by_export_path():
    """导出前的会话自愈路径未被破坏：_ensure_connected() 仍走 ensure_session()。"""
    from ..connector.pcdmis_connector import PcdmisConnector

    assert hasattr(PcdmisConnector, "ensure_session"), "ensure_session() 必须保留"
    assert hasattr(PcdmisConnector, "session_alive"), "session_alive() 必须保留"


def test_com_session_error_detects_rpc_not_tk():
    from ..connector.pcdmis_connector import _is_com_session_error
    from utils.error_codes import ErrorCode, ToolboxError

    assert _is_com_session_error(RuntimeError("RPC server is unavailable"))
    assert _is_com_session_error(RuntimeError("main thread is not in main loop")) is False
    assert _is_com_session_error(ToolboxError(ErrorCode.PCDMIS_NO_DATA, "empty")) is False
