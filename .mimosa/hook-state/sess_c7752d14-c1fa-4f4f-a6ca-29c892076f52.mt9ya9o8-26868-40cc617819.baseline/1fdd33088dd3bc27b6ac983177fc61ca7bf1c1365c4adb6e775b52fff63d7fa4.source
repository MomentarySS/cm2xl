"""向 PCDMIS 测量程序植入导出命令块。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from config import (
    BAS_FILENAME,
    BAS_TEMPLATE_FILENAME,
    DEPLOY_DIR,
    EXPORT_CMD_ID,
    OBTYPE_BASIC_SCRIPT,
    REPORTS_DIR,
    ROOT_DIR,
    SCRIPTS_DIR,
    _BUNDLE_DIR,
)
from connector.com_detector import com_apartment, get_command_at, get_active_part_program
from connector.pcdlrn_constants import get_const
from inject.save_helper import check_save_preflight, try_save_part_program


@dataclass
class InjectResult:
    success: bool
    message: str
    command_id: str = EXPORT_CMD_ID
    bas_path: str = ""
    already_exists: bool = False


def _bundled_bas_source() -> Path:
    search_roots = (_BUNDLE_DIR, ROOT_DIR)
    for root in search_roots:
        for name in (BAS_TEMPLATE_FILENAME, BAS_FILENAME):
            bundled = root / "scripts" / name
            if not bundled.is_file():
                continue
            if name == BAS_TEMPLATE_FILENAME or "@@CONFIG_PATH@@" in bundled.read_text(
                encoding="utf-8", errors="ignore"
            ):
                return bundled
    raise FileNotFoundError(f"缺少脚本模板: scripts/{BAS_TEMPLATE_FILENAME}")


def _format_script_path(path: Path) -> str:
    """PCDMIS SCRIPT 路径 — 含空格时用引号包裹。"""
    text = str(path.resolve())
    if " " in text and not (text.startswith('"') and text.endswith('"')):
        return f'"{text}"'
    return text


def _verify_bas_deployed(bas_path: Path) -> None:
    if not bas_path.is_file():
        raise FileNotFoundError(
            f"脚本文件不存在:\n{bas_path}\n\n请先点击「部署 BAS 脚本」。"
        )


def deploy_bas_script(target_dir: Path | None = None) -> Path:
    """将 export_current.bas 部署到 scripts 目录并写入 export_config.txt。"""
    dest_dir = target_dir or SCRIPTS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / BAS_FILENAME

    csv_path = REPORTS_DIR / "pcdmis_partial_export.csv"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config_path = dest_dir / "export_config.txt"
    config_path.write_text(
        f"{csv_path.resolve()}\nYES\n",
        encoding="utf-8",
    )

    source_text = _bundled_bas_source().read_text(encoding="utf-8")
    if "@@CONFIG_PATH@@" not in source_text:
        raise RuntimeError("BAS 模板缺少 @@CONFIG_PATH@@ 占位符")
    source_text = source_text.replace(
        "@@CONFIG_PATH@@",
        str(config_path.resolve()).replace("\\", "\\\\"),
    )
    dest.write_text(source_text, encoding="utf-8")
    _verify_bas_deployed(dest)
    return dest


def generate_command_text(bas_path: Path) -> str:
    path_str = _format_script_path(bas_path)
    return (
        f"{EXPORT_CMD_ID}=SCRIPT/FILENAME={path_str}\n"
        f"            FUNCTION/Main,SHOW=NO,,\n"
        f"            STARTSCRIPT/\n"
        f"            ENDSCRIPT/"
    )


def _find_export_command(cmds) -> tuple[int, object] | None:
    count = int(cmds.Count)
    for idx in range(1, count + 1):
        try:
            cmd = get_command_at(cmds, idx)
        except Exception:
            continue
        try:
            if str(cmd.ID or "").strip().upper() == EXPORT_CMD_ID.upper():
                return idx, cmd
        except Exception:
            continue
        try:
            if int(cmd.Type) == OBTYPE_BASIC_SCRIPT:
                name = str(cmd.GetText(get_const("FILE_NAME", 1), 0) or "")
                if BAS_FILENAME.lower() in name.lower():
                    return idx, cmd
        except Exception:
            continue
    return None


def _configure_script_command(cmd, bas_path: Path) -> None:
    file_name = get_const("FILE_NAME", 1)
    sub_name = get_const("SUB_NAME", 4)
    show_details = get_const("SHOW_DETAILS", 5)
    cmd_id = get_const("ID", 2)

    cmd.PutText(EXPORT_CMD_ID, cmd_id, 0)
    cmd.PutText(_format_script_path(bas_path), file_name, 0)
    cmd.PutText("Main", sub_name, 0)
    try:
        cmd.SetToggleString(1, show_details, 0)
    except Exception:
        pass
    try:
        cmd.Marked = True
    except Exception:
        pass


def inject_export_command(app, bas_path: Path | None = None) -> InjectResult:
    """通过 COM 在 PRG 末尾插入或更新 BASIC SCRIPT 导出命令。"""
    try:
        bas = bas_path or deploy_bas_script()
        _verify_bas_deployed(bas)
    except FileNotFoundError as exc:
        return InjectResult(False, str(exc))

    with com_apartment():
        part = get_active_part_program(app)
        if part is None:
            return InjectResult(False, "未找到活动测量程序，请先在 PCDMIS 中打开 .PRG")

        can_save, preflight_msg = check_save_preflight(part)
        save_note = ""
        if not can_save:
            save_note = f"\n\n【保存提示】{preflight_msg}"

        cmds = part.Commands
        existing = _find_export_command(cmds)

        if existing:
            _idx, cmd = existing
            _configure_script_command(cmd, bas)
            part.RefreshPart()
            saved, save_msg = try_save_part_program(part, app)
            if saved:
                msg = f"已更新导出命令「{EXPORT_CMD_ID}」\n已保存: {save_msg}\n脚本: {bas}"
            elif can_save:
                msg = (
                    f"已更新导出命令「{EXPORT_CMD_ID}」\n"
                    f"但自动保存失败:\n{save_msg}\n\n脚本: {bas}"
                )
            else:
                msg = (
                    f"已更新导出命令「{EXPORT_CMD_ID}」\n"
                    f"脚本: {bas}{save_note}\n\n"
                    "请在 PCDMIS 中手动 Ctrl+S 保存。"
                )
            return InjectResult(True, msg, bas_path=str(bas), already_exists=True)

        try:
            last = cmds.LastCommand
            cmds.InsertionPointAfter(last)
        except Exception as exc:
            return InjectResult(False, f"无法定位程序末尾: {exc}")

        try:
            script_cmd = cmds.Add(OBTYPE_BASIC_SCRIPT, True)
        except Exception as exc:
            return InjectResult(False, f"无法添加 BASIC SCRIPT 命令: {exc}")

        _configure_script_command(script_cmd, bas)
        try:
            script_cmd.ReDraw()
        except Exception:
            pass

        part.RefreshPart()
        saved, save_msg = try_save_part_program(part, app)
        if saved:
            msg = (
                f"已在程序末尾植入「{EXPORT_CMD_ID}」\n"
                f"已保存: {save_msg}\n脚本: {bas}\n\n"
                "用法: 光标移到该命令 → 文件 → 部分执行 → 从光标执行"
            )
        elif can_save:
            msg = (
                f"已在程序末尾植入「{EXPORT_CMD_ID}」\n"
                f"但自动保存失败:\n{save_msg}\n\n脚本: {bas}"
            )
        else:
            msg = (
                f"已在程序末尾植入「{EXPORT_CMD_ID}」\n"
                f"脚本: {bas}{save_note}\n\n"
                "命令已在 PCDMIS 内存中生效，请手动 Ctrl+S 保存 PRG。\n"
                "用法: 光标移到该命令 → 文件 → 部分执行 → 从光标执行"
            )

        return InjectResult(True, msg, bas_path=str(bas))


def check_export_command(app) -> InjectResult:
    with com_apartment():
        part = get_active_part_program(app)
        if part is None:
            return InjectResult(False, "未打开测量程序")
        existing = _find_export_command(part.Commands)
        if not existing:
            return InjectResult(False, "尚未植入导出命令")
        _idx, cmd = existing
        try:
            path = str(cmd.GetText(get_const("FILE_NAME", 1), 0) or "")
        except Exception:
            path = ""
        disk_path = Path(path.strip().strip('"'))
        if path and not disk_path.is_file():
            return InjectResult(
                False,
                f"PRG 中的脚本路径无效（PC-DMIS 会报「未找到脚本文件」）:\n{path}\n\n"
                f"请依次点击：\n1. 部署 BAS 脚本\n2. 植入/更新导出命令\n3. Ctrl+S 保存 PRG\n\n"
                f"脚本应部署到:\n{DEPLOY_DIR / 'scripts' / BAS_FILENAME}",
            )
        return InjectResult(True, f"已存在导出命令（索引 {_idx}）\n脚本: {path}", bas_path=path, already_exists=True)
