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
    # 内含中文字符串（MsgBox 文案）—— 与真模板对齐，
    # 让 P1-8 的 GBK 编码测试有真东西可断（不是空壳断言）。
    template.write_text(
        'SCRIPT/FILENAME="@@CONFIG_PATH@@"\n'
        "FUNCTION/Main,SHOW=NO,,\n"
        'MsgBox "无法连接 PC-DMIS 活动程序。", 16, "导出失败"\n'
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
    # P1-8：部署出的 BAS 按 GBK 编码（PC-DMIS Basic Scripting Engine 按 ANSI 读）。
    # 模板源是 UTF-8（CRLF），仅部署写出时换成 GBK。这里读回也要走 GBK。
    content = result.read_text(encoding="gbk")
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
# P1-8（2026-09-23 真机新增）：BAS 文件部署出必须按 GBK 编码
# ---------------------------------------------------------------------------


def test_deploy_bas_script_writes_gbk_encoding(tmp_path: Path, monkeypatch):
    """P1-8：PC-DMIS Basic Scripting Engine 按系统 ANSI（中文 Windows = GBK/CP936）
    解码 BAS 文件，不认 UTF-8 中文。deploy_bas_script 必须按 GBK 写出。

    测试策略：
    1. 模板里有 `MsgBox "无法连接 PC-DMIS 活动程序。"`（UTF-8 字节 = `E6 97 A0 ...`）
    2. 部署后**绝不能**保留 UTF-8 字节（GBK 编码里同样字符是 2 字节，码点不同）
    3. 部署后按 GBK 能干净 decode，且 round-trip 内容与源匹配
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
    raw = (deploy_dir / BAS_FILENAME).read_bytes()

    # 1) 不能是 UTF-8 BOM（GBK 不带 BOM；UTF-8 BOM 会让引擎误判）
    assert raw[:3] != b"\xef\xbb\xbf", (
        "deploy_bas_script 不应写 UTF-8 BOM —— "
        "PC-DMIS 引擎按 GBK 解码 UTF-8 中文会乱码。"
    )
    # 2) 不能是 UTF-16 BOM（那是 export_config.txt 的，P1-4 修过；BAS 不该用）
    assert raw[:2] != b"\xff\xfe" and raw[:2] != b"\xfe\xff", (
        "BAS 文件不应是 UTF-16 —— BAS 引擎按 ANSI 读。"
    )

    # 3) 模板里的中文「无法连接」UTF-8 字节 = E6 97 A0 E6 B3 95 E8 BF 9E E6 8E A5
    #    这些字节**绝不能**原样出现在部署结果里 —— 否则说明仍按 UTF-8 写。
    utf8_3bytes = "无法连接".encode("utf-8")
    assert utf8_3bytes not in raw, (
        f"deploy_bas_script 仍按 UTF-8 部署（发现模板里中文的 UTF-8 字节 "
        f"{utf8_3bytes.hex()} 原样存在）。应改按 GBK 写出。"
    )

    # 4) 按 GBK 必须能干净 decode
    text = raw.decode("gbk")
    assert "无法连接" in text, (
        f"按 GBK decode 后应能找到模板里的中文「无法连接」。"
    )

    # 5) 反向守卫：证明「按 GBK decode」不是空壳 —— 用 GBK 解 UTF-8 内容会乱码
    utf8_bytes_with_chinese = b"' foo\nMsgBox \"\xe6\x97\xa0\xe6\xb3\x95\xe8\xbf\x9e\xe6\x8e\xa5\"\n"
    assert "无法连接" not in utf8_bytes_with_chinese.decode("gbk"), (
        "反向守卫：UTF-8 中文按 GBK 解码**不**还原原文 —— "
        "证明 'DeploymentBS 写 GBK = utf-8 内容含中文 → 回原' 这条测试不是空壳。"
    )


def test_deploy_bas_script_gbk_roundtrip_preserves_chinese(tmp_path: Path, monkeypatch):
    r"""Round-trip 守卫：按 GBK 写出的内容**字节**必须是真 GBK，不能是 Python repr。

    防「unicode escape」或「str repr」之类的退化改法 —— GBK 是字节编码，
    不是 Python repr。

    检测法：
    1. 正向：raw 字节里必须包含「无法连接」的 GBK 字节序列（CE DE C7 EB）
       —— 这只在「真按 GBK 写」时成立
    2. 反向：raw 字节里**不**应包含 Python repr 的字面 `\u65e0\u6cd5`（这条
       在「按 repr 写」时才成立）
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
    raw = (deploy_dir / BAS_FILENAME).read_bytes()
    text = raw.decode("gbk")

    # 占位符必须被替换
    assert "@@CONFIG_PATH@@" not in text
    # 中文必须原样
    assert "无法连接" in text
    assert "导出失败" in text

    # 正向：raw 字节必须含「无法连接」的 GBK 字节序列
    gbk_bytes = "无法连接".encode("gbk")
    assert gbk_bytes in raw, (
        f"raw 字节应包含「无法连接」的 GBK 编码（{gbk_bytes.hex()}），"
        f"实测 raw 头 80 字节：{raw[:80].hex()}"
    )

    # 反向：raw 字节**不**应含 Python repr 的字面 \u65e0\u6cd5（防退化改法）
    repr_bytes = b"\\u65e0\\u6cd5"
    assert repr_bytes not in raw, (
        f"raw 字节不应含 Python repr 的字面 \\u65e0\\u6cd5 —— "
        f"说明被人改成了 unicode_escape / repr 而非真 GBK。"
    )


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
