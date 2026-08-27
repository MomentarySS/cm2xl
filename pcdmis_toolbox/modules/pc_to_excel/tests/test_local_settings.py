"""用户设置持久化单元测试。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest

from ..export.inspection_form_fill import FormFillConfig
from ..utils.local_settings import (
    AppSettings,
    build_export_filename,
    ensure_default_dirs,
    load_settings,
    save_settings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePaths:
    """Fake PathManager that routes config to a temp directory."""

    def __init__(self, root: Path):
        self._root = root

    @property
    def config_dir(self) -> Path:
        return self._root / "config"

    @property
    def pc_excel_reports(self) -> Path:
        return self._root / "reports"


def _patch_paths(module_paths: str, fake: _FakePaths) -> None:
    """Patch 'paths' in the __globals__ of load_settings / save_settings.

    The import 'from utils.paths import paths' in local_settings.py binds the
    name 'paths' in the module's namespace.  We need to patch the __globals__
    dict of each function (not just the module attribute) because Python
    resolves names in function bodies from the function's own globals dict,
    not from module __setattr__.
    """
    for func in (load_settings, save_settings, ensure_default_dirs):
        func.__globals__[module_paths] = fake


def _write_settings_json(cfg_dir: Path, data: dict) -> Path:
    """Write a settings.json file into cfg_dir and return its path."""
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "settings.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_settings() -> AppSettings:
    return AppSettings()


@pytest.fixture
def populated_settings() -> AppSettings:
    return AppSettings(
        export_dir="/custom/export",
        filename_pattern="{part}_report",
        tolerance={"x_lower": -0.01, "x_upper": 0.01},
        export_scope="all",
        require_marked=False,
        form_fill=FormFillConfig(
            form_path="C:/forms/ship.xlsx",
            cmm_codes=["A", "B"],
            write_piece_id=False,
            piece_id="TEST-001",
        ),
    )


# ---------------------------------------------------------------------------
# AppSettings defaults
# ---------------------------------------------------------------------------


def test_app_settings_defaults(empty_settings):
    assert empty_settings.export_dir == ""
    assert empty_settings.filename_pattern == "{part}_{time}"
    assert empty_settings.tolerance == {
        "x_lower": -0.02, "x_upper": 0.02,
        "y_lower": -0.02, "y_upper": 0.02,
        "z_lower": -0.02, "z_upper": 0.02,
        "d_lower": -0.05, "d_upper": 0.05,
    }
    assert empty_settings.export_scope == "report"
    assert empty_settings.require_marked is True
    assert isinstance(empty_settings.form_fill, FormFillConfig)


def test_app_settings_resolved_export_dir_empty():
    """export_dir 为空时，resolved_export_dir 返回 paths.pc_excel_reports。"""
    settings = AppSettings()
    resolved = settings.resolved_export_dir()
    assert isinstance(resolved, Path)
    assert resolved.name == "reports"


def test_app_settings_resolved_export_dir_custom():
    """export_dir 非空时，resolved_export_dir 返回该路径。"""
    settings = AppSettings(export_dir="/my/custom/dir")
    assert settings.resolved_export_dir() == Path("/my/custom/dir")


# ---------------------------------------------------------------------------
# build_export_filename
# ---------------------------------------------------------------------------


def test_build_export_filename_simple():
    result = build_export_filename("PART123")
    assert result.endswith(".xlsx")
    assert "PART123" in result


def test_build_export_filename_has_time():
    result = build_export_filename("PART123")
    assert re.search(r"\d{8}_\d{6}", result) is not None


def test_build_export_filename_custom_pattern():
    result = build_export_filename("PART123", pattern="{part}_REPORT")
    assert result.startswith("PART123_REPORT")
    assert result.endswith(".xlsx")


def test_build_export_filename_unsafe_chars():
    """非字母数字字符（除 - _ .）应被替换为下划线。"""
    result = build_export_filename("PART/123:C*")
    assert all(c.isalnum() or c in "-_." for c in result.replace(".xlsx", ""))


def test_build_export_filename_empty_part():
    """零件名为空时使用默认值 'report'。"""
    result = build_export_filename("")
    assert "report" in result.lower()


def test_build_export_filename_already_xlsx():
    """pattern 结尾已有 .xlsx 时不重复追加。"""
    assert build_export_filename("PART", pattern="{part}.xlsx") == "PART.xlsx"


# ---------------------------------------------------------------------------
# save_settings + load_settings round-trip
# ---------------------------------------------------------------------------


def test_save_settings_creates_file(tmp_path: Path, populated_settings):
    """save_settings 应创建 settings.json 到配置的 config_dir。"""
    fake = _FakePaths(tmp_path)
    _patch_paths("paths", fake)

    save_settings(populated_settings)
    written = tmp_path / "config" / "pc_to_excel" / "settings.json"
    assert written.exists()
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["export_dir"] == "/custom/export"
    assert data["filename_pattern"] == "{part}_report"


def test_load_settings_full_roundtrip(tmp_path: Path):
    """保存后再加载，所有字段一致。"""
    cfg_dir = tmp_path / "config" / "pc_to_excel"
    _write_settings_json(
        cfg_dir,
        {
            "export_dir": "/custom/export",
            "filename_pattern": "{part}_report",
            "export_scope": "all",
            "require_marked": False,
            "form_fill": {
                "enabled": True,
                "form_path": "C:/forms/ship.xlsx",
                "cmm_codes": ["A", "B"],
                "write_piece_id": False,
                "piece_id": "TEST-001",
                "id_prefixes": ["FAI", "CC"],
                "serial_col": "A",
                "instrument_col": "G",
                "spec_col": "B",
                "data_start_col": "H",
                "target_col": "auto",
                "hyphen_to_dot": True,
                "manual_map": {},
                "manual_map_text": "",
                "header_scan_row": 5,
                "data_start_row": 6,
                "chain_from_last": True,
                "last_fill_output": "",
                "nominal_check": True,
                "nominal_tol": 0.05,
            },
            "tolerance": {"x_lower": -0.01, "x_upper": 0.01},
        },
    )
    fake = _FakePaths(tmp_path)
    _patch_paths("paths", fake)

    loaded = load_settings()
    assert loaded.export_dir == "/custom/export"
    assert loaded.filename_pattern == "{part}_report"
    assert loaded.export_scope == "all"
    assert loaded.require_marked is False
    assert loaded.form_fill.cmm_codes == ["A", "B"]
    assert loaded.form_fill.piece_id == "TEST-001"


# ---------------------------------------------------------------------------
# load_settings error handling
# ---------------------------------------------------------------------------


def test_load_settings_no_file_returns_defaults(tmp_path: Path):
    """settings.json 不存在时返回默认配置。"""
    cfg_dir = tmp_path / "config" / "pc_to_excel"
    cfg_dir.mkdir(parents=True)  # 目录存在但文件不存在
    fake = _FakePaths(tmp_path)
    _patch_paths("paths", fake)

    settings = load_settings()
    assert settings.export_dir == ""
    assert settings.require_marked is True
    assert settings.filename_pattern == "{part}_{time}"


def test_load_settings_invalid_json_returns_defaults(tmp_path: Path, caplog):
    """JSON 格式损坏时返回默认配置，并记录 warning 日志。"""
    cfg_dir = tmp_path / "config" / "pc_to_excel"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "settings.json").write_text("{ invalid json }", encoding="utf-8")
    fake = _FakePaths(tmp_path)
    _patch_paths("paths", fake)

    with caplog.at_level(logging.WARNING):
        settings = load_settings()
    assert settings.export_dir == ""
    assert settings.require_marked is True
    assert any("加载配置文件失败" in r.message for r in caplog.records)


def test_load_settings_partial_json(tmp_path: Path):
    """JSON 中只有部分字段时，缺失字段使用默认值。"""
    cfg_dir = tmp_path / "config" / "pc_to_excel"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "settings.json").write_text(
        json.dumps({"export_dir": "/partial", "require_marked": False}),
        encoding="utf-8",
    )
    fake = _FakePaths(tmp_path)
    _patch_paths("paths", fake)

    settings = load_settings()
    assert settings.export_dir == "/partial"
    assert settings.require_marked is False
    assert settings.filename_pattern == "{part}_{time}"


# ---------------------------------------------------------------------------
# ensure_default_dirs
# ---------------------------------------------------------------------------


def test_ensure_default_dirs_creates_dirs(tmp_path: Path):
    """ensure_default_dirs 应创建 pc_excel_reports 和 config 子目录。"""
    fake = _FakePaths(tmp_path)
    _patch_paths("paths", fake)

    ensure_default_dirs()
    assert (tmp_path / "reports").exists()
    assert (tmp_path / "config" / "pc_to_excel").exists()
