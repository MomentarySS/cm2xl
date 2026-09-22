"""启动参数、IPC、PC-DMIS 工具栏启动器。"""

from __future__ import annotations

import time
from pathlib import Path

from toolbox.launch_args import parse_launch_args
from utils.ipc import (
    CMD_AUTO_EXPORT,
    clear_ipc_commands,
    consume_command,
    write_auto_export_command,
)
from ..inject.toolbar_launcher import (
    LAUNCHER_BAT,
    LAUNCHER_VBS,
    deploy_toolbar_launcher,
    format_bat_script,
    format_vbs_script,
    resolve_toolbar_argv,
)


def test_parse_auto_export_implies_module_and_skip_ocr():
    args = parse_launch_args(["--auto-export"])
    assert args.auto_export is True
    assert args.module == "pc_to_excel"
    assert args.skip_ocr is True


def test_parse_module_equals_form():
    args = parse_launch_args(["--module=pc_to_excel"])
    assert args.module == "pc_to_excel"
    assert args.auto_export is False
    assert args.skip_ocr is True


def test_auto_export_overrides_other_module():
    args = parse_launch_args(["--module", "cmm_filler", "--auto-export"])
    assert args.module == "pc_to_excel"
    assert args.auto_export is True
    assert args.skip_ocr is True


def test_parse_cmm_filler_keeps_ocr():
    args = parse_launch_args(["--module", "cmm_filler"])
    assert args.module == "cmm_filler"
    assert args.skip_ocr is False


def test_parse_unknown_module_ignored():
    args = parse_launch_args(["--module", "nope"])
    assert args.module is None
    assert args.auto_export is False


def test_parse_empty():
    args = parse_launch_args([])
    assert args.module is None
    assert args.auto_export is False
    assert args.skip_ocr is False


def test_ipc_write_consume_roundtrip(tmp_path: Path, monkeypatch):
    class _P:
        @property
        def data_dir(self) -> Path:
            return tmp_path

    monkeypatch.setattr("utils.ipc.paths", _P())
    write_auto_export_command()
    cmd = consume_command()
    assert cmd is not None
    assert cmd["cmd"] == CMD_AUTO_EXPORT
    assert consume_command() is None


def test_ipc_expired_dropped(tmp_path: Path, monkeypatch):
    class _P:
        @property
        def data_dir(self) -> Path:
            return tmp_path

    monkeypatch.setattr("utils.ipc.paths", _P())
    write_auto_export_command()
    cmd = consume_command(now=time.time() + 100)
    assert cmd is None


def test_ipc_clear(tmp_path: Path, monkeypatch):
    class _P:
        @property
        def data_dir(self) -> Path:
            return tmp_path

    monkeypatch.setattr("utils.ipc.paths", _P())
    write_auto_export_command()
    clear_ipc_commands()
    assert consume_command() is None


def test_ipc_corrupt_file(tmp_path: Path, monkeypatch):
    class _P:
        @property
        def data_dir(self) -> Path:
            return tmp_path

    monkeypatch.setattr("utils.ipc.paths", _P())
    (tmp_path / "ipc_command.json").write_text("not-json", encoding="utf-8")
    assert consume_command() is None
    assert not (tmp_path / "ipc_command.json").exists()


def test_toolbar_argv_dev_points_at_main_py():
    argv = resolve_toolbar_argv(
        Path(__file__).resolve().parents[3],
        prefer_installed=False,
    )
    assert "--auto-export" in argv
    assert argv[-1] == "--auto-export"
    assert any(p.endswith("main.py") for p in argv)


def test_toolbar_argv_prefers_installed(tmp_path: Path, monkeypatch):
    fake = tmp_path / "cm2xl.exe"
    fake.write_bytes(b"mz")
    monkeypatch.setattr(
        "modules.pc_to_excel.inject.toolbar_launcher.find_installed_cm2xl",
        lambda: fake,
    )
    argv = resolve_toolbar_argv(tmp_path, prefer_installed=True)
    assert argv[0] == str(fake)
    assert "--auto-export" in argv
    assert all(not p.endswith("main.py") for p in argv)


def test_format_bat_and_vbs_quote_spaces(tmp_path: Path):
    argv = [r"C:\Program Files\cm2xl\cm2xl.exe", "--module", "pc_to_excel", "--auto-export"]
    bat = format_bat_script(argv, tmp_path)
    vbs = format_vbs_script(argv, tmp_path)
    assert 'start ""' in bat
    assert '"C:\\Program Files\\cm2xl\\cm2xl.exe"' in bat
    assert "--auto-export" in bat
    assert "WScript.Shell" in vbs
    assert "pc_to_excel" in vbs
    assert "False" in vbs


def test_deploy_toolbar_launcher_writes_files(tmp_path: Path, monkeypatch):
    class _P:
        @property
        def root(self) -> Path:
            return tmp_path

        @property
        def bas_deploy_dir(self) -> Path:
            return tmp_path / "scripts"

    monkeypatch.setattr(
        "modules.pc_to_excel.inject.toolbar_launcher.paths",
        _P(),
    )
    monkeypatch.setattr(
        "modules.pc_to_excel.inject.toolbar_launcher.find_installed_cm2xl",
        lambda: None,
    )
    (tmp_path / "main.py").write_text("# stub\n", encoding="utf-8")
    vbs = deploy_toolbar_launcher()
    assert vbs.name == LAUNCHER_VBS
    assert vbs.is_file()
    bat = tmp_path / "scripts" / LAUNCHER_BAT
    assert bat.is_file()
    text = vbs.read_text(encoding="utf-8")
    assert "--auto-export" in text
    assert "main.py" in text
