"""部署 PC-DMIS 工具栏用的一键导出启动器（.vbs / .bat）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from utils.file_io import atomic_write_text
from utils.paths import paths

LAUNCHER_BAT = "cm2xl_toolbar_export.bat"
LAUNCHER_VBS = "cm2xl_toolbar_export.vbs"
LAUNCHER_README = "工具栏安装.txt"

TOOLBAR_FLAGS = ("--module", "pc_to_excel", "--auto-export")
# installer/cm2xl.iss AppId；Inno 卸载键为 {GUID}_is1
_INNO_UNINSTALL_KEYS = (
    r"{A1B2C3D4-E5F6-7890-ABCD-EF1234567891}_is1",
    r"{A1B2C3D4-E5F6-7890-ABCD-EF1234567891}",
)

INSTALL_STEPS = (
    "PC-DMIS 工具栏挂载（做一次即可）：\n"
    "1. 视图 → 工具栏 → 自定义 → 菜单选项卡 → 创建项目\n"
    "2. 文件类型选「所有文件」，打开本目录下的 cm2xl_toolbar_export.vbs\n"
    "   （若自定义对话框不认 vbs，改用同目录 .bat）\n"
    "3. 在「用户自定义命令」里把新项拖到 PC-DMIS 工具栏\n"
    "4. 关闭自定义对话框\n\n"
    "之后在 PC-DMIS 点该按钮：启动 cm2xl → 跳到「PCDMIS导出」→ 按当前设置"
    "（默认仅 Mark）自动导出 Excel。\n"
    "cm2xl 已在运行时，会唤醒现有窗口再导一次，不另开实例。"
)


def _cm2xl_exe_in(dir_path: Path | str | None) -> Path | None:
    if not dir_path:
        return None
    exe = Path(str(dir_path).strip().strip('"'))
    if exe.is_file() and exe.name.lower() == "cm2xl.exe":
        return exe.resolve()
    if exe.suffix.lower() in {".ico", ".exe"}:
        exe = exe.parent / "cm2xl.exe"
    else:
        exe = exe / "cm2xl.exe"
    if exe.is_file():
        return exe.resolve()
    return None


def _registry_install_dirs() -> list[Path]:
    try:
        import winreg
    except ImportError:
        return []
    hives = (
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    found: list[Path] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        exe = _cm2xl_exe_in(str(raw or ""))
        if exe is None:
            return
        key = str(exe).lower()
        if key not in seen:
            seen.add(key)
            found.append(exe)

    for hive, prefix in hives:
        for sub in _INNO_UNINSTALL_KEYS:
            try:
                with winreg.OpenKey(hive, prefix + "\\" + sub) as key:
                    for value_name in ("InstallLocation", "DisplayIcon", "DisplayName"):
                        try:
                            raw, _ = winreg.QueryValueEx(key, value_name)
                        except OSError:
                            continue
                        if value_name != "DisplayName":
                            _add(raw)
            except OSError:
                continue
        try:
            with winreg.OpenKey(hive, prefix) as root:
                n = winreg.QueryInfoKey(root)[0]
                for i in range(n):
                    name = winreg.EnumKey(root, i)
                    try:
                        with winreg.OpenKey(root, name) as key:
                            try:
                                display, _ = winreg.QueryValueEx(key, "DisplayName")
                            except OSError:
                                continue
                            if not str(display).lower().startswith("cm2xl"):
                                continue
                            for value_name in ("InstallLocation", "DisplayIcon"):
                                try:
                                    raw, _ = winreg.QueryValueEx(key, value_name)
                                except OSError:
                                    continue
                                _add(raw)
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def find_installed_cm2xl() -> Path | None:
    """定位 Inno 安装的 cm2xl.exe（不含开发目录 dist/）。"""
    for exe in _registry_install_dirs():
        return exe
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    local_app = os.environ.get("LOCALAPPDATA", "")
    for candidate in (
        Path(program_files) / "cm2xl" / "cm2xl.exe",
        Path(local_app) / "Programs" / "cm2xl" / "cm2xl.exe",
    ):
        if candidate.is_file():
            return candidate.resolve()
    return None


def _dev_python_argv(root: Path) -> list[str]:
    python = Path(sys.executable).resolve()
    if python.name.lower() == "python.exe":
        pythonw = python.with_name("pythonw.exe")
        if pythonw.is_file():
            python = pythonw
    main_py = root.joinpath("main.py").resolve()
    return [str(python), str(main_py), *TOOLBAR_FLAGS]


def resolve_toolbar_argv(
    root: Path | None = None,
    *,
    prefer_installed: bool = True,
) -> list[str]:
    """返回可直接 CreateProcess 的 argv。优先安装版 cm2xl.exe。"""
    flags = list(TOOLBAR_FLAGS)
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), *flags]
    if prefer_installed:
        installed = find_installed_cm2xl()
        if installed is not None:
            return [str(installed), *flags]
    return _dev_python_argv((root or paths.root).resolve())


def toolbar_workdir(argv: list[str], root: Path | None = None) -> Path:
    if argv and argv[0].lower().endswith(".exe"):
        return Path(argv[0]).resolve().parent
    return (root or paths.root).resolve()


def _bat_quote(arg: str) -> str:
    return '"' + arg.replace('"', "") + '"'


def _vbs_quote_arg(arg: str) -> str:
    return '""' + arg.replace('"', "") + '""'


def format_bat_script(argv: list[str], workdir: Path) -> str:
    quoted = " ".join(_bat_quote(a) for a in argv)
    wd = _bat_quote(str(workdir.resolve()))
    return (
        "@echo off\r\n"
        "REM cm2xl — PC-DMIS toolbar one-click Excel export\r\n"
        f"cd /d {wd}\r\n"
        f"start \"\" {quoted}\r\n"
    )


def format_vbs_script(argv: list[str], workdir: Path) -> str:
    run_cmd = " ".join(_vbs_quote_arg(a) for a in argv)
    wd = str(workdir.resolve()).replace('"', "")
    return (
        "Option Explicit\r\n"
        "Dim sh\r\n"
        "Set sh = CreateObject(\"WScript.Shell\")\r\n"
        f"sh.CurrentDirectory = \"{wd}\"\r\n"
        f"sh.Run \"{run_cmd}\", 1, False\r\n"
    )


def deploy_toolbar_launcher(target_dir: Path | None = None) -> Path:
    """写入 vbs/bat/说明到 BAS 同目录，返回推荐给 PC-DMIS 的 .vbs 路径。"""
    dest_dir = target_dir or paths.bas_deploy_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    root = paths.root.resolve()
    argv = resolve_toolbar_argv(root)
    workdir = toolbar_workdir(argv, root)

    bat = dest_dir / LAUNCHER_BAT
    vbs = dest_dir / LAUNCHER_VBS
    readme = dest_dir / LAUNCHER_README
    atomic_write_text(bat, format_bat_script(argv, workdir))
    atomic_write_text(vbs, format_vbs_script(argv, workdir))
    launch_hint = argv[0]
    atomic_write_text(
        readme,
        INSTALL_STEPS + f"\n\n启动目标：\n{launch_hint}\n\n启动器：\n{vbs}\n{bat}\n",
    )
    return vbs
