"""PCDMIS COM 探测 — 注册表扫描与连接尝试。"""

from __future__ import annotations

import os
import re
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager

from config import PROG_ID_CANDIDATES

SEARCH_TERMS = ["PCDLRN", "PC-DMIS", "PCDMIS", "Hexagon"]
REGISTRY_PATHS = [
    r"HKLM\SOFTWARE\Classes",
    r"HKLM\SOFTWARE\WOW6432Node\Classes",
]
INSTALL_PATHS = [
    r"C:\Program Files\Hexagon\PC-DMIS",
    r"C:\Program Files (x86)\Hexagon\PC-DMIS",
    r"D:\Program Files\Hexagon\PC-DMIS",
    r"D:\Hexagon\PC-DMIS",
    r"D:\PF\PCDMIS-2024.1",
]


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

    def sort_key(pid: str) -> tuple[int, int, str]:
        upper = pid.upper()
        is_generic = upper in ("PCDLRN.APPLICATION", "PCDLRN.APPLICATION.1")
        return (1 if is_generic else 0, -len(pid), pid)

    found.sort(key=sort_key)
    return found


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
    for prog_id in discover_prog_ids_fast()[:3]:
        exe = _exe_from_prog_id(prog_id)
        if exe:
            dirs.append(str(Path(exe).parent))
    return list(dict.fromkeys(dirs))


def _prog_id_registered(prog_id: str) -> bool:
    return "REG_SZ" in _run_reg(["query", rf"HKCR\{prog_id}\CLSID", "/ve"])


def get_connect_candidates() -> list[str]:
    discovered = discover_prog_ids_fast()
    seen: set[str] = set()
    merged: list[str] = []
    for pid in discovered + PROG_ID_CANDIDATES:
        if pid in seen or not _prog_id_registered(pid):
            continue
        seen.add(pid)
        merged.append(pid)
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


def is_pcdmis_running() -> bool:
    return get_pcdmis_pid() is not None


def is_pcdmis_elevated() -> bool | None:
    pid = get_pcdmis_pid()
    if pid is None:
        return None
    try:
        from utils.admin import is_process_elevated

        return is_process_elevated(pid)
    except Exception:
        return None


def check_elevation_match() -> tuple[bool, str]:
    """检查本工具与 PCDMIS 权限是否一致。"""
    pcd_elev = is_pcdmis_elevated()
    tool_elev = False
    try:
        from utils.admin import admin_required_hint, is_admin, normal_launch_hint

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
    return struct.calcsize("P") * 8


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
    """绑定 PCDMIS Application；优先 EnsureDispatch 以获取完整类型库接口。"""
    import win32com.client  # type: ignore[import-untyped]
    import win32com.client.gencache as gencache  # type: ignore[import-untyped]

    errors: list[str] = []
    for label, factory in (
        ("EnsureDispatch", lambda: gencache.EnsureDispatch(prog_id)),
        ("Dispatch", lambda: win32com.client.Dispatch(prog_id)),
        ("GetActiveObject", lambda: win32com.client.GetActiveObject(prog_id)),
    ):
        try:
            return factory()
        except Exception as exc:
            errors.append(f"{label}: {exc}")
    raise RuntimeError(f"无法绑定 {prog_id}\n" + "\n".join(errors))


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
        hints.append("PCDMIS 未运行 — 请先启动 PC-DMIS（2022.1–2026.1）并打开测量程序。")
    elif "-2147221005" in last_error and ok:
        hints.append(
            "ProgID 在注册表中存在但 COM 激活失败。"
            "请确认 PC-DMIS 已完整安装，并以管理员运行过一次完成 COM 注册；且 Python/exe 为 64 位。"
        )
    if "-2146959355" in last_error or "-2147221021" in last_error:
        if ok:
            hints.append(
                "COM 无法附着到已运行的 PCDMIS — 将尝试 Dispatch 启动/连接，"
                "请稍候约 10 秒。"
            )
    if python_bitness() != 64:
        hints.append(
            f"当前 Python 为 {python_bitness()} 位，PC-DMIS 2022+（64-bit）需 64 位 Python。"
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

    with com_apartment():
        last_error = ""
        for prog_id in candidates:
            app = None
            # Dispatch 最可靠；GetActiveObject 仅在 ROT 已注册时可用
            for factory in (
                lambda pid=prog_id: win32com.client.Dispatch(pid),
                lambda pid=prog_id: win32com.client.GetActiveObject(pid),
            ):
                try:
                    app = factory()
                    break
                except Exception as exc:
                    last_error = str(exc)
            if app is None:
                continue
            try:
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

    ok, prog_id, version, error = try_connect(result.all_prog_ids)
    result.connected = ok
    result.active_prog_id = prog_id
    result.version = version
    result.message = f"已连接 ({prog_id})" if ok else error
    return result
