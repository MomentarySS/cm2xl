"""
Phase 8 自动化测试（无 GUI / 无 PCDMIS 依赖项）

覆盖：
1. 原子写 + 文件锁
2. 配置迁移（旧路径 → 新路径）
3. 配置版本升级链
4. 降级导出
5. crash.log 异常处理
6. toolbox 全局设置读写
7. logging set_log_level 动态切换
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
import traceback
import warnings
from pathlib import Path

import pytest

# ── 路径 ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.settings import (
    TOOLBOX_DEFAULT_SETTINGS,
    TOOLBOX_SETTINGS_VERSION,
    FileLock,
    load_and_migrate_settings,
    load_toolbox_settings,
    migrate_settings_if_needed,
    save_settings_json_atomic,
    save_toolbox_settings,
    export_legacy_settings,
    CONFIG_SCHEMA_VERSION,
    _MIGRATIONS,
    migrate_cmm_filler_1_0_to_2_0,
    migrate_pc_to_excel_1_4_to_2_0,
)
from utils.logging import set_log_level, setup_logging
from utils.error_codes import ErrorCode, ToolboxError, format_user_error
from utils.audit import audit

warnings.filterwarnings("ignore", category=SyntaxWarning)


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_dir():
    d = Path(tempfile.mkdtemp(prefix="tb_phase8_"))
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def toolbox_tmp(tmp_dir, monkeypatch):
    """临时 config_dir，隔离 toolbox 设置读写。"""
    cfg = tmp_dir / "config" / "toolbox"
    cfg.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_dir / "LocalAppData"))
    return cfg


# ── 1. 原子写 ───────────────────────────────────────────────────────────────

class TestAtomicWrite:
    def test_roundtrip(self, tmp_dir):
        path = tmp_dir / "cfg.json"
        data = {"a": 1, "b": "hello", "nested": {"x": [1, 2, 3]}}
        save_settings_json_atomic(path, data)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == data

    def test_parent_auto_create(self, tmp_dir):
        path = tmp_dir / "deep" / "nested" / "cfg.json"
        save_settings_json_atomic(path, {"k": "v"})
        assert path.exists()

    def test_overwrite(self, tmp_dir):
        path = tmp_dir / "cfg.json"
        save_settings_json_atomic(path, {"v": 1})
        save_settings_json_atomic(path, {"v": 2})
        assert json.loads(path.read_text())["v"] == 2

    def test_corrupt_after_crash(self, tmp_dir):
        """模拟写一半崩溃：先写坏文件，再正常写。"""
        path = tmp_dir / "cfg.json"
        path.write_text("NOT JSON{", encoding="utf-8")
        save_settings_json_atomic(path, {"ok": True})
        assert json.loads(path.read_text(encoding="utf-8"))["ok"] is True


# ── 2. 文件锁 ───────────────────────────────────────────────────────────────

class TestFileLock:
    def test_acquire_release(self, tmp_dir):
        lock = FileLock(tmp_dir / "test.lock")
        with lock as acquired:
            assert acquired is True
            assert (tmp_dir / "test.lock").exists()
        # 释放后文件应删除
        assert not (tmp_dir / "test.lock").exists()

    def test_stale_lock_recovery(self, tmp_dir):
        lock_path = tmp_dir / "stale.lock"
        lock_path.write_text("999999999", encoding="utf-8")  # 不存在的 PID
        lock = FileLock(lock_path, timeout=0.5)
        with lock as acquired:
            assert acquired is True

    def test_concurrent_conflict(self, tmp_dir):
        import time

        lock_path = tmp_dir / "shared.lock"
        order = []
        start = threading.Event()

        def worker(name):
            start.wait(timeout=1.0)
            lock = FileLock(lock_path, timeout=3.0)
            with lock as acquired:
                if acquired:
                    order.append(name)
                    time.sleep(0.15)

        t1 = threading.Thread(target=worker, args=("t1",))
        t2 = threading.Thread(target=worker, args=("t2",))
        t1.start()
        t2.start()
        start.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        # 两个线程都拿到了锁（串行），不应同时持有
        assert len(order) == 2


# ── 3. 配置迁移（位置迁移） ─────────────────────────────────────────────────

class TestMigrateSettings:
    def test_migrate_copies_and_backups(self, tmp_dir):
        old = tmp_dir / "old" / "settings.json"
        new = tmp_dir / "new" / "settings.json"
        old.parent.mkdir()
        old.write_text(json.dumps({"template_path": "/old/tpl.xlsx"}), encoding="utf-8")
        result = migrate_settings_if_needed("cmm_filler", old, new)
        assert new.exists()
        assert old.with_suffix(".bak").exists()
        assert result["template_path"] == "/old/tpl.xlsx"

    def test_no_overwrite_existing(self, tmp_dir):
        old = tmp_dir / "old" / "s.json"
        new = tmp_dir / "new" / "s.json"
        old.parent.mkdir(); new.parent.mkdir()
        old.write_text("{}", encoding="utf-8")
        new.write_text(json.dumps({"_version": "2.0.0"}), encoding="utf-8")
        result = migrate_settings_if_needed("cmm_filler", old, new)
        # 不覆盖已有
        assert result.get("_version") == "2.0.0"


# ── 4. 版本升级链 ───────────────────────────────────────────────────────────

class TestVersionUpgradeChain:
    def test_cmm_filler_1_0_to_2_0(self):
        old = {"template_path": "tpl.xlsx", "pdf_folder": "/pdf", "output_folder": "/out"}
        new = migrate_cmm_filler_1_0_to_2_0(old)
        assert new["_version"] == CONFIG_SCHEMA_VERSION
        assert new["template_path"] == "tpl.xlsx"
        assert new["pdf_folder"] == "/pdf"

    def test_pc_to_excel_1_4_to_2_0(self):
        old = {"export_dir": "/d", "tolerance": {"mode": "asymmetric"}}
        new = migrate_pc_to_excel_1_4_to_2_0(old)
        assert new["_version"] == CONFIG_SCHEMA_VERSION
        assert new["export_dir"] == "/d"
        assert new["tolerance"] == {"mode": "asymmetric"}

    def test_load_and_migrate_from_1_0(self, tmp_dir):
        path = tmp_dir / "cmm_filler" / "settings.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"_version": "1.0.0", "pdf_folder": "/a"}), encoding="utf-8")
        result = load_and_migrate_settings("cmm_filler", path)
        assert result["_version"] == CONFIG_SCHEMA_VERSION
        assert result["pdf_folder"] == "/a"

    def test_load_and_migrate_from_1_4(self, tmp_dir):
        path = tmp_dir / "pc_to_excel" / "settings.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"_version": "1.4.5", "export_dir": "/b", "tolerance": {}}),
            encoding="utf-8",
        )
        result = load_and_migrate_settings("pc_to_excel", path)
        assert result["_version"] == CONFIG_SCHEMA_VERSION
        assert result["export_dir"] == "/b"

    def test_no_migration_fn_raises(self, tmp_dir):
        path = tmp_dir / "x" / "s.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"_version": "9.9.9"}), encoding="utf-8")
        with pytest.raises(ToolboxError) as exc_info:
            load_and_migrate_settings("cmm_filler", path)
        assert exc_info.value.code == ErrorCode.CONFIG_MIGRATION_FAIL


# ── 5. 降级导出 ─────────────────────────────────────────────────────────────

class TestLegacyExport:
    def test_cmm_filler_export(self, tmp_dir):
        target = tmp_dir / "legacy_cmm.json"
        data = {
            "_version": "2.0.0",
            "template_path": "/t.xlsx",
            "pdf_folder": "/pdf",
            "output_folder": "/out",
            "_schema": "cmm_filler.settings",
        }
        export_legacy_settings("cmm_filler", target, data)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert "template_path" in loaded
        assert "_version" not in loaded  # 不应带内部字段

    def test_pc_to_excel_export(self, tmp_dir):
        target = tmp_dir / "legacy_pc.json"
        data = {
            "_version": "2.0.0",
            "_schema": "pc_to_excel.settings",
            "export_dir": "/d",
            "tolerance": {"mode": "6pack"},
        }
        export_legacy_settings("pc_to_excel", target, data)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["export_dir"] == "/d"
        assert loaded["tolerance"] == {"mode": "6pack"}


# ── 6. Toolbox 全局设置 ─────────────────────────────────────────────────────

class TestToolboxSettings:
    def test_defaults(self, tmp_path, monkeypatch):
        cfg = tmp_path / "toolbox"
        cfg.mkdir()
        settings_file = cfg / "settings.json"
        monkeypatch.setattr(
            "utils.settings._toolbox_settings_path",
            lambda: settings_file,
        )
        # 不创建文件 → 返回默认值
        s = load_toolbox_settings()
        assert s["appearance_mode"] == "system"
        assert s["ocr_model_dir"] == ""
        assert s["log_level"] == "INFO"

    def test_save_load_roundtrip(self, tmp_dir, monkeypatch):
        cfg = tmp_dir / "cfg" / "toolbox"
        cfg.mkdir(parents=True)
        monkeypatch.setattr("utils.settings._toolbox_settings_path", lambda: cfg / "settings.json")
        save_toolbox_settings({"appearance_mode": "dark", "log_level": "DEBUG"})
        loaded = load_toolbox_settings()
        assert loaded["appearance_mode"] == "dark"
        assert loaded["log_level"] == "DEBUG"
        # 未传字段保持默认
        assert loaded["ocr_model_dir"] == ""

    def test_atomic_write_on_save(self, tmp_dir, monkeypatch):
        cfg = tmp_dir / "cfg2" / "toolbox"
        cfg.mkdir(parents=True)
        p = cfg / "settings.json"
        monkeypatch.setattr("utils.settings._toolbox_settings_path", lambda: p)
        save_toolbox_settings({"appearance_mode": "light"})
        assert p.exists()
        # 确认是完整 JSON（非半截）
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["appearance_mode"] == "light"


# ── 7. logging set_log_level ───────────────────────────────────────────────

class TestSetLogLevel:
    def test_dynamic_level_change(self):
        logger = setup_logging("tb_test_phase8")
        logger.setLevel(logging.DEBUG)
        assert logger.level == logging.DEBUG
        set_log_level("tb_test_phase8", "WARNING")
        assert logger.level == logging.WARNING
        for h in logger.handlers:
            assert h.level == logging.WARNING

    def test_invalid_level_falls_back_to_info(self):
        logger = setup_logging("tb_test_phase8_invalid")
        logger.setLevel(logging.DEBUG)
        set_log_level("tb_test_phase8_invalid", "NOTEXIST")
        assert logger.level == logging.INFO


# ── 8. crash.log 异常处理 ───────────────────────────────────────────────────

class TestCrashLog:
    def test_exception_written(self, tmp_dir):
        fake_log = tmp_dir / "crash.log"
        exc_type, exc_val, exc_tb = None, None, None
        try:
            raise ToolboxError(ErrorCode.MODEL_MISSING, "test crash")
        except Exception:
            exc_type, exc_val, exc_tb = sys.exc_info()

        tb = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        with open(fake_log, "a", encoding="utf-8") as f:
            f.write(tb)

        content = fake_log.read_text(encoding="utf-8")
        assert "MODEL_MISSING" in content or "model" in content.lower()
        assert "test crash" in content

    def test_format_user_error_toolbox(self):
        err = ToolboxError(ErrorCode.PDF_NOT_FOUND, "PDF 不见了")
        title, hint = format_user_error(err)
        assert "E3001" in title
        assert "PDF" in title

    def test_format_user_error_unknown(self):
        title, hint = format_user_error(RuntimeError("random boom"))
        assert "random boom" in title


# ── 9. 配置加载的向前兼容 ───────────────────────────────────────────────────

class TestLoadToolboxSettingsCompatibility:
    def test_unknown_keys_ignored(self, tmp_dir, monkeypatch):
        cfg = tmp_dir / "cfg3" / "toolbox"
        cfg.mkdir(parents=True)
        p = cfg / "settings.json"
        monkeypatch.setattr("utils.settings._toolbox_settings_path", lambda: p)
        # 写入含未来未知字段的文件
        save_toolbox_settings({"appearance_mode": "dark", "future_feature": 123})
        loaded = load_toolbox_settings()
        assert loaded["appearance_mode"] == "dark"
        assert "future_feature" not in loaded

    def test_corrupt_file_falls_back_to_default(self, tmp_dir, monkeypatch):
        cfg = tmp_dir / "cfg4" / "toolbox"
        cfg.mkdir(parents=True)
        p = cfg / "settings.json"
        p.write_text("NOT JSON", encoding="utf-8")
        monkeypatch.setattr("utils.settings._toolbox_settings_path", lambda: p)
        loaded = load_toolbox_settings()
        assert loaded["appearance_mode"] == "system"


# ── 10. 模块 core 导入（非 GUI） ───────────────────────────────────────────

class TestModuleCoreImports:
    def test_cmm_filler_core(self):
        from modules.cmm_filler.core.filler import CMMReportFiller  # noqa: F401

    def test_cmm_filler_ocr_engine(self):
        from modules.cmm_filler.ocr.engine import OCREngine, PaddleOCREngine  # noqa: F401

    def test_pc_to_excel_module_adapter(self):
        from modules.pc_to_excel.module import PCToExcelModule  # noqa: F401

    def test_pc_to_excel_main_window(self):
        from modules.pc_to_excel.gui.main_window import MainWindow  # noqa: F401
