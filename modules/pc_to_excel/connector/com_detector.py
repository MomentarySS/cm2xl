"""PCDMIS COM 探测 — 注册表扫描与连接尝试。"""

from __future__ import annotations

import os
import re
import struct
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager

from ..app_meta import PROG_ID_CANDIDATES, PROG_ID_GENERIC
from utils.error_codes import ErrorCode, ToolboxError

SEARCH_TERMS = ["PCDLRN", "PC-DMIS", "PCDMIS", "Hexagon"]
REGISTRY_PATHS = [
    r"HKLM\SOFTWARE\Classes",
    r"HKLM\SOFTWARE\WOW6432Node\Classes",
]

# Python 解释器字长，在模块首次导入时确定一次（由解释器启动参数决定，不会动态改变）
_PYTHON_POINTER_BITS: int = struct.calcsize("P") * 8
INSTALL_PATHS = [
    r"C:\Program Files\Hexagon\PC-DMIS",
    r"C:\Program Files (x86)\Hexagon\PC-DMIS",
    r"D:\Program Files\Hexagon\PC-DMIS",
    r"D:\Hexagon\PC-DMIS",
    r"D:\PF\PCDMIS-2024.1",
]
HEXAGON_ROOTS = [
    r"C:\Program Files\Hexagon",
    r"C:\Program Files (x86)\Hexagon",
    r"D:\Program Files\Hexagon",
    r"D:\Hexagon",
]
_PROG_ID_VER_RE = re.compile(r"^PCDLRN\.Application(?:\.(\d+)\.(\d+))?$", re.I)

# 所有 PC-DMIS COM 调用串行化，避免主线程探测与后台抽数互相卡住。
com_call_lock = threading.RLock()


@dataclass
class DetectionResult:
    prog_ids: list[str] = field(default_factory=list)
    install_dirs: list[str] = field(default_factory=list)
    connected: bool = False
    active_prog_id: str = ""
    version: str = ""
    message: str = ""

    @property
    def all_prog_ids(self) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for pid in self.prog_ids + PROG_ID_CANDIDATES:
            if pid not in seen:
                seen.add(pid)
                merged.append(pid)
        merged.sort(key=_prog_id_sort_key)
        return merged


def _run_reg(args: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            ["reg", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.stdout or ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def discover_prog_ids_fast() -> list[str]:
    found: list[str] = []
    stdout = _run_reg(["query", "HKCR", "/f", "PCDLRN.Application", "/k"])
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("HKEY_CLASSES_ROOT\\"):
            continue
        key = line.split("\\", 1)[1]
        if key.upper().startswith("PCDLRN.APPLICATION"):
            found.append(key)

    found.sort(key=_prog_id_sort_key)
    return found


def _prog_id_sort_key(pid: str) -> tuple[int, int, int, str]:
    """版本 ProgID 新→旧；无版本号的 PCDLRN.Application 放最后。"""
    match = _PROG_ID_VER_RE.match(pid.strip())
    if not match or match.group(1) is None:
        return (1, 0, 0, pid)
    return (0, -int(match.group(1)), -int(match.group(2)), pid)


def _normalize_exe_path(raw: str) -> str:
    return os.path.normcase(os.path.normpath(raw.strip().strip('"')))


def _exe_from_prog_id(prog_id: str) -> str | None:
    clsid_out = _run_reg(["query", rf"HKCR\{prog_id}\CLSID", "/ve"])
    match = re.search(r"\{[0-9A-Fa-f-]{36}\}", clsid_out)
    if not match:
        return None
    clsid = match.group(0)
    server_out = _run_reg(["query", rf"HKCR\CLSID\{clsid}\LocalServer32", "/ve"])
    for line in server_out.splitlines():
        if "REG_SZ" not in line:
            continue
        raw = line.split("REG_SZ", 1)[1].strip().strip('"')
        if raw.lower().endswith("pcdlrn.exe"):
            return raw
    return None


def discover_install_dirs() -> list[str]:
    dirs: list[str] = [p for p in INSTALL_PATHS if os.path.isdir(p)]
    for root in HEXAGON_ROOTS:
        base = Path(root)
        if not base.is_dir():
            continue
        for item in base.glob("PC-DMIS *"):
            if (item / "PCDLRN.exe").is_file():
                dirs.append(str(item))
    for prog_id in discover_prog_ids_fast()[:8]:
        exe = _exe_from_prog_id(prog_id)
        if exe:
            dirs.append(str(Path(exe).parent))
    return list(dict.fromkeys(dirs))


def _prog_id_registered(prog_id: str) -> bool:
    return "REG_SZ" in _run_reg(["query", rf"HKCR\{prog_id}\CLSID", "/ve"])


def _registered_prog_ids() -> list[str]:
    discovered = discover_prog_ids_fast()
    seen: set[str] = set()
    merged: list[str] = []
    for pid in discovered + PROG_ID_CANDIDATES:
        if pid in seen or not _prog_id_registered(pid):
            continue
        seen.add(pid)
        merged.append(pid)
    merged.sort(key=_prog_id_sort_key)
    return merged


def match_running_prog_id(candidates: list[str] | None = None) -> str:
    """用正在运行的 PCDLRN.exe 路径匹配版本 ProgID，避免连到另一套已安装版本。"""
    exe = get_pcdmis_exe_path()
    if not exe:
        return ""
    want = _normalize_exe_path(exe)
    for pid in candidates or _registered_prog_ids():
        if pid.upper() == PROG_ID_GENERIC.upper():
            continue
        found = _exe_from_prog_id(pid)
        if found and _normalize_exe_path(found) == want:
            return pid
    generic_exe = _exe_from_prog_id(PROG_ID_GENERIC)
    if generic_exe and _normalize_exe_path(generic_exe) == want:
        return PROG_ID_GENERIC
    return ""


def get_connect_candidates() -> list[str]:
    merged = _registered_prog_ids()
    running = match_running_prog_id(merged)
    if running:
        return [running] + [p for p in merged if p != running]
    return merged


def scan_registry() -> list[str]:
    found: list[str] = list(discover_prog_ids_fast())
    for reg_path in REGISTRY_PATHS:
        for term in SEARCH_TERMS:
            try:
                result = subprocess.run(
                    ["reg", "query", reg_path, "/s", "/f", term],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            if not result.stdout:
                continue
            for line in result.stdout.splitlines():
                if "ProgID" not in line or "REG_SZ" not in line:
                    continue
                value = line.split("REG_SZ")[-1].strip()
                if value and "PCDLRN" in value.upper() and value not in found:
                    found.append(value)
    return found


def scan_install_paths() -> list[str]:
    return discover_install_dirs()


def get_pcdmis_pid() -> int | None:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq PCDLRN.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in (result.stdout or "").splitlines():
            parts = [p.strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == "pcdlrn.exe":
                return int(parts[1])
    except Exception:
        return None
    return None


def get_pcdmis_exe_path() -> str | None:
    """读取正在运行的 PCDLRN.exe 完整路径（限权查询，管理员进程也可读）。"""
    pid = get_pcdmis_pid()
    if pid is None:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(32768)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None
    return None


def is_pcdmis_running() -> bool:
    return get_pcdmis_pid() is not None


def is_pcdmis_elevated() -> bool | None:
    pid = get_pcdmis_pid()
    if pid is None:
        return None
    try:
        from ..utils.admin import is_process_elevated

        return is_process_elevated(pid)
    except Exception:
        return None


def check_elevation_match() -> tuple[bool, str]:
    """检查本工具与 PCDMIS 权限是否一致。"""
    pcd_elev = is_pcdmis_elevated()
    tool_elev = False
    try:
        from ..utils.admin import admin_required_hint, is_admin, normal_launch_hint

        tool_elev = is_admin()
        if pcd_elev is None:
            return True, ""
        if pcd_elev == tool_elev:
            return True, ""
        if pcd_elev and not tool_elev:
            return False, admin_required_hint()
        return False, normal_launch_hint()
    except Exception:
        return True, ""


def python_bitness() -> int:
    """返回 Python 解释器的字长（32 或 64），由解释器启动参数决定，不会动态改变。"""
    return _PYTHON_POINTER_BITS


@contextmanager
def com_apartment():
    """后台线程调用 COM 前必须初始化 apartment（否则 CO_E_NOTINITIALIZED）。"""
    import pythoncom  # type: ignore[import-untyped]

    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def dispatch_pcdmis(prog_id: str):
    """绑定 PCDMIS Application。

    PC-DMIS 已在运行时只用 GetActiveObject / Dispatch 附着，禁止 EnsureDispatch：
    后者会重建 gencache，第二次导出可卡住数十秒甚至假死。
    """
    import win32com.client  # type: ignore[import-untyped]

    errors: list[str] = []
    running = is_pcdmis_running()
    factories: list[tuple[str, object]] = []
    if running:
        factories.append(("GetActiveObject", lambda: win32com.client.GetActiveObject(prog_id)))
        factories.append(("Dispatch", lambda: win32com.client.Dispatch(prog_id)))
    else:
        factories.append(("Dispatch", lambda: win32com.client.Dispatch(prog_id)))
        factories.append(("GetActiveObject", lambda: win32com.client.GetActiveObject(prog_id)))
    for label, factory in factories:
        try:
            with com_call_lock:
                return factory()
        except Exception as exc:
            errors.append(f"{label}: {exc}")
    raise ToolboxError(
        ErrorCode.PCDMIS_CONNECT_FAIL,
        f"无法绑定 {prog_id}\n" + "\n".join(errors),
    )


def get_active_part_program(app) -> object | None:
    """读取当前活动测量程序；无打开程序时返回 None。"""
    try:
        part = app.ActivePartProgram
        return part if part is not None else None
    except AttributeError:
        return None
    except Exception:
        return None


def get_command_at(cmds, index: int):
    """读取 Commands 集合中的单条命令（兼容 Item / 调用式索引）。"""
    for getter in (
        lambda: cmds.Item(index),
        lambda: cmds(index),
        lambda: cmds[index],
    ):
        try:
            result = getter()
            if result is not None:
                return result
        except Exception:
            continue
    raise RuntimeError(f"无法读取 Commands 索引 {index}")


def _read_version(app) -> str:
    for attr in ("VersionString", "Version"):
        try:
            value = getattr(app, attr, None)
            if value:
                return str(value)
        except Exception:
            continue
    return "未知"


def _format_connect_error(last_error: str, candidates: list[str]) -> str:
    install_dirs = discover_install_dirs()
    prog_list = ", ".join(candidates[:5]) if candidates else "无"
    install_list = "\n  ".join(install_dirs) if install_dirs else "未找到"
    hints = [f"已尝试 ProgID: {prog_list}", f"安装目录:\n  {install_list}"]

    ok, elev_msg = check_elevation_match()
    if not ok and elev_msg:
        hints.insert(0, "【最可能原因】权限级别不一致\n" + elev_msg)

    if not is_pcdmis_running():
        hints.append("PCDMIS 未运行 — 请先启动 PC-DMIS（2017 R2–2026.1，64 位）并打开测量程序。")
    elif "-2147221005" in last_error and ok:
        hints.append(
            "ProgID 在注册表中存在但 COM 激活失败。"
            "请确认 PC-DMIS 已完整安装，并以管理员运行过一次完成 COM 注册；且 Python/exe 为 64 位。"
        )
    if "-2146959355" in last_error or "-2147221021" in last_error:
        if ok:
            hints.append(
                "COM 无法附着到已运行的 PCDMIS。"
                "多版本同机时请只开一套，并以与本工具相同的权限运行。"
            )
    if python_bitness() != 64:
        hints.append(
            f"当前 Python 为 {python_bitness()} 位，PC-DMIS 2017 R2+（64-bit）需 64 位 Python。"
        )

    return f"{last_error}\n\n" + "\n\n".join(hints)


def try_connect(prog_ids: list[str] | None = None) -> tuple[bool, str, str, str]:
    ok, prog_id, version, error, _app = try_connect_with_app(prog_ids)
    return ok, prog_id, version, error


def try_connect_with_app(
    prog_ids: list[str] | None = None,
) -> tuple[bool, str, str, str, object | None]:
    """连接 PCDMIS — 参考 blog.iyatt.com/?p=18363，优先附着已运行实例。"""
    candidates = prog_ids or get_connect_candidates()
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        return False, "", "", "未安装 pywin32，请运行: pip install pywin32", None

    ok_elev, elev_msg = check_elevation_match()
    if not ok_elev:
        return False, "", "", elev_msg, None

    last_error = ""
    with com_call_lock:
        with com_apartment():
            for prog_id in candidates:
                try:
                    app = win32com.client.GetActiveObject(prog_id)
                    return True, prog_id, _read_version(app), "", app
                except Exception as exc:
                    last_error = str(exc)

            dispatch_ids = list(candidates)
            if is_pcdmis_running():
                matched = match_running_prog_id(candidates)
                dispatch_ids = [matched] if matched else []
                if not dispatch_ids:
                    message = _format_connect_error(last_error, candidates)
                    return False, "", "", message, None

            for prog_id in dispatch_ids:
                try:
                    app = win32com.client.Dispatch(prog_id)
                    return True, prog_id, _read_version(app), "", app
                except Exception as exc:
                    last_error = str(exc)

    message = _format_connect_error(last_error, candidates)
    return False, "", "", message, None


def quick_connect(
    prog_ids: list[str] | None = None,
) -> tuple[bool, str, str, str, object | None]:
    return try_connect_with_app(prog_ids or get_connect_candidates())


def run_detection(attempt_connect: bool = True) -> DetectionResult:
    result = DetectionResult(
        prog_ids=discover_prog_ids_fast(),
        install_dirs=discover_install_dirs(),
    )
    if not attempt_connect:
        result.message = "仅扫描注册表，未尝试连接"
        return result

    ok, prog_id, version, error = try_connect()
    result.connected = ok
    result.active_prog_id = prog_id
    result.version = version
    result.message = f"已连接 ({prog_id})" if ok else error
    return result
