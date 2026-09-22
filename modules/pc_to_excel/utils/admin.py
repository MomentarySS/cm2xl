"""Windows 管理员权限检测。"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from utils.paths import paths


def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_process_elevated(pid: int) -> bool | None:
    if sys.platform != "win32":
        return None

    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None

    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(handle, 0x0008, ctypes.byref(token)):
            return None
        elevation = ctypes.c_ulong()
        size = ctypes.c_ulong()
        if not advapi32.GetTokenInformation(
            token,
            20,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(size),
        ):
            return None
        return bool(elevation.value)
    finally:
        if token.value:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(handle)


def admin_status_text() -> str:
    return "管理员 ✓" if is_admin() else "普通用户 ✓"


def normal_launch_hint() -> str:
    return (
        "PC-DMIS 当前以普通用户运行，本工具也必须是普通用户，否则 COM 无法连接。\n\n"
        f"请关闭本窗口，然后在普通终端执行：\n  cd {paths.root}\n  python main.py"
    )


def admin_required_hint() -> str:
    return (
        "PC-DMIS 以管理员运行时，本工具也必须是管理员，否则 COM 无法连接。\n\n"
        f"请右键 {paths.root / 'run_as_admin.bat'} → 以管理员身份运行"
    )
