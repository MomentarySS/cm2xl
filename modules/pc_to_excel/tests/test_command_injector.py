"""BAS 脚本注入单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ..inject.command_injector import (
    BAS_FILENAME,
    EXPORT_CMD_ID,
    InjectResult,
    _format_script_path,
    _verify_bas_deployed,
    deploy_bas_script,
    generate_command_text,
)
from .conftest import FakePathManager


# ---------------------------------------------------------------------------
# _format_script_path
# ---------------------------------------------------------------------------


def test_format_script_path_no_spaces(tmp_path: Path):
    """无空格路径直接返回 resolve() 结果。"""
    target = tmp_path / "scripts" / "export.bas"
    target.parent.mkdir()
    target.touch()
    result = _format_script_path(target)
    assert result == str(target.resolve())
    assert " " not in result


def test_format_script_path_with_spaces(tmp_path: Path):
    """含空格路径应被双引号包裹。"""
    target = tmp_path / "Program Files" / "PCDMIS" / "scripts" / "export.bas"
    target.parent.mkdir(parents=True)
    target.touch()
    result = _format_script_path(target)
    assert result.startswith('"')
    assert result.endswith('"')
    assert "Program Files" in result


def test_format_script_path_already_quoted(tmp_path: Path):
    """含非法引号的路径按普通路径处理（引号字符被 resolve() 展开为普通路径）。"""
    target = tmp_path / "already quoted" / "bas.bas"
    target.parent.mkdir(parents=True)
    target.touch()
    result = _format_script_path(target)
    assert result.startswith('"')
    assert result.endswith('"')
    assert "already quoted" in result


def test_format_script_path_unix_style():
    """Unix 风格路径在 Windows 上 resolve() 后变成 Windows 路径。"""
    # Linux 风格路径在 Windows 上 resolve() 会变成以项目目录为基准的相对路径，
    # 或保持 Unix 格式（取决于 Path 实现）。这里只测返回值非空且包含原文件名。
    result = _format_script_path(Path("/home/user/scripts/export.bas"))
    assert "export.bas" in result
    assert result  # 非空


# ---------------------------------------------------------------------------
# _verify_bas_deployed
# ---------------------------------------------------------------------------


def test_verify_bas_deployed_ok(tmp_path: Path):
    (tmp_path / BAS_FILENAME).touch()
    # 不抛异常即通过
    _verify_bas_deployed(tmp_path / BAS_FILENAME)


def test_verify_bas_deployed_missing():
    with pytest.raises(FileNotFoundError) as exc_info:
        _verify_bas_deployed(Path("/nonexistent/export_current.bas"))
    assert "脚本文件不存在" in str(exc_info.value)


# ---------------------------------------------------------------------------
# generate_command_text
# ---------------------------------------------------------------------------


def test_generate_command_text(tmp_path: Path):
    bas = tmp_path / "scripts" / BAS_FILENAME
    bas.parent.mkdir()
    bas.touch()
    result = generate_command_text(bas)
    assert EXPORT_CMD_ID in result
    assert BAS_FILENAME in result
    assert "FUNCTION/Main,SHOW=NO" in result
    assert "STARTSCRIPT" in result
    assert "ENDSCRIPT" in result


def test_generate_command_text_with_spaces_in_dir(tmp_path: Path):
    bas = tmp_path / "Program Files" / "PCDMIS scripts" / BAS_FILENAME
    bas.parent.mkdir(parents=True)
    bas.touch()
    result = generate_command_text(bas)
    assert EXPORT_CMD_ID in result
    # 含空格目录的路径应被引号包裹
    assert '"' in result


# ---------------------------------------------------------------------------
# deploy_bas_script
# ---------------------------------------------------------------------------


def _write_bas_template(root: Path, name: str = "export_current.bas.template") -> Path:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    template = scripts / name
    template.write_text(
        'SCRIPT/FILENAME="@@CONFIG_PATH@@"\n'
        "FUNCTION/Main,SHOW=NO,,\n"
        "STARTSCRIPT/\n"
        "ENDSCRIPT/",
        encoding="utf-8",
    )
    return template


class _FullFakePaths:
    """Fake PathManager covering all paths needed by deploy_bas_script."""

    def __init__(self, root: Path, deploy_dir: Path | None = None):
        self._root = root
        self._deploy = deploy_dir or (root / "scripts")

    @property
    def root(self) -> Path:
        return self._root

    @property
    def bas_deploy_dir(self) -> Path:
        return self._deploy

    @property
    def pc_excel_reports(self) -> Path:
        return self._root / "reports"


def test_deploy_bas_script_copies_and_substitutes(tmp_path: Path, monkeypatch):
    """deploy_bas_script 应复制模板内容并替换 @@CONFIG_PATH@@。"""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_bas_template(project_root)
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()

    fake_paths = _FullFakePaths(project_root, deploy_dir)

    monkeypatch.setattr(
        "modules.pc_to_excel.inject.command_injector.paths",
        fake_paths,
    )
    monkeypatch.setattr(
        "modules.pc_to_excel.inject.command_injector._BUNDLE_DIR",
        project_root,
    )

    result = deploy_bas_script(deploy_dir)

    assert result.name == BAS_FILENAME
    assert result.exists()
    content = result.read_text(encoding="utf-8")
    # 占位符被替换
    assert "@@CONFIG_PATH@@" not in content
    assert "export_config.txt" in content


def test_deploy_bas_script_creates_export_config(tmp_path: Path, monkeypatch):
    """deploy_bas_script 应创建 export_config.txt（UTF-16，见下方 BOM 用例）。

    注意：本用例原先按 `encoding="utf-8"` 读回 —— 那正是 P1-4 的缺陷本身
    （写 UTF-8、读 UTF-16）。读法已改为与 BAS 读侧一致的 utf-16。
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_bas_template(project_root)
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()

    fake_paths = _FullFakePaths(project_root, deploy_dir)

    monkeypatch.setattr(
        "modules.pc_to_excel.inject.command_injector.paths",
        fake_paths,
    )
    monkeypatch.setattr(
        "modules.pc_to_excel.inject.command_injector._BUNDLE_DIR",
        project_root,
    )

    deploy_bas_script(deploy_dir)

    config = deploy_dir / "export_config.txt"
    assert config.exists()
    text = config.read_text(encoding="utf-16")
    lines = text.strip().split("\n")
    assert len(lines) == 2
    assert lines[1].strip() == "YES"


def test_export_config_is_utf16_with_bom(tmp_path: Path, monkeypatch):
    """P1-4：export_config.txt 必须是**带 BOM 的 UTF-16**，否则 BAS 侧断不开行。

    读侧 `fso.OpenTextFile(CONFIG_PATH, 1, False, -1)` 的第 4 参 -1 = TristateTrue，
    所以这里用 `bytes.decode("utf-16")`（同样依 BOM 判定）来等价复现。
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_bas_template(project_root)
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()

    monkeypatch.setattr(
        "modules.pc_to_excel.inject.command_injector.paths",
        _FullFakePaths(project_root, deploy_dir),
    )
    monkeypatch.setattr(
        "modules.pc_to_excel.inject.command_injector._BUNDLE_DIR",
        project_root,
    )

    deploy_bas_script(deploy_dir)
    raw = (deploy_dir / "export_config.txt").read_bytes()

    # 1) 必须带 BOM（utf-16-le 不带，FSO 的 TristateTrue 在无 BOM 时行为不确定）
    assert raw[:2] == b"\xff\xfe", "export_config.txt 缺少 UTF-16 BOM"

    # 2) 按 FSO 的读法必须能干净地断成两行
    lines = raw.decode("utf-16").splitlines()
    assert len(lines) == 2
    assert lines[0].strip().endswith("pcdmis_partial_export.csv")
    assert lines[1].strip() == "YES"

    # 3) 反向守卫：证明上面第 2 条不是空壳 —— 旧的「UTF-8 无 BOM」写法
    #    按 FSO 的读法**不满足**「干净两行 + 第二行 YES」这个契约。
    #    实测本机那份 74 字节配置解出来连行都断不开（只有 1 行），
    #    正是 readExportConfig 把乱码路径当成有效值返回 True 的原因。
    #    这里只断言契约不成立，不锁死具体失效形态（它取决于字节内容）。
    legacy = (
        f"{_FullFakePaths(project_root, deploy_dir).pc_excel_reports}"
        "/pcdmis_partial_export.csv\nYES\n"
    ).encode("utf-8")
    assert legacy[:2] != b"\xff\xfe"
    legacy_lines = legacy.decode("utf-16", errors="replace").splitlines()
    assert not (len(legacy_lines) == 2 and legacy_lines[1].strip() == "YES")


# ---------------------------------------------------------------------------
# InjectResult dataclass
# ---------------------------------------------------------------------------


def test_inject_result_dataclass():
    r = InjectResult(success=True, message="OK", already_exists=True)
    assert r.success is True
    assert r.message == "OK"
    assert r.already_exists is True
    assert r.bas_path == ""
    assert r.command_id == EXPORT_CMD_ID  # "PC2XL_EXPORT"


def test_inject_result_defaults():
    r = InjectResult(success=False, message="failed")
    assert r.success is False
    assert r.bas_path == ""
    assert r.already_exists is False
    assert r.command_id == EXPORT_CMD_ID


def test_inject_result_str_message():
    r = InjectResult(success=True, message="done")
    assert "done" in str(r.message)
