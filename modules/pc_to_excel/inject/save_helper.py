"""PRG 保存前检查与 COM Save 封装。"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any


def part_program_path(part: Any) -> Path | None:
    for attr in ("FullName", "Path", "Name"):
        try:
            raw = str(getattr(part, attr, "") or "").strip()
        except Exception:
            continue
        if not raw:
            continue
        if attr == "Name" and not raw.lower().endswith(".prg"):
            try:
                base = str(getattr(part, "Path", "") or "").strip()
                if base:
                    candidate = Path(base) / raw
                    if candidate.suffix.lower() == ".prg":
                        return candidate
            except Exception:
                pass
            continue
        path = Path(raw)
        if path.suffix.lower() == ".prg" or path.exists():
            return path
    return None


def check_save_preflight(part: Any) -> tuple[bool, str]:
    """返回 (可尝试保存, 失败原因说明)。"""
    path = part_program_path(part)
    if path is None:
        return False, (
            "程序还没有正式保存路径。\n"
            "请先在 PCDMIS 中：文件 → 另存为，保存为 .PRG 后再植入。"
        )

    if not path.exists():
        return False, f"PRG 文件在磁盘上不存在：\n{path}"

    if path.is_dir():
        return False, f"路径指向目录而非 .PRG 文件：\n{path}"

    try:
        mode = path.stat().st_mode
        if not (mode & stat.S_IWRITE):
            return False, (
                f"PRG 在 Windows 上被标记为只读：\n{path}\n\n"
                "右键文件 → 属性 → 取消「只读」，或在 PCDMIS 中另存到可写目录。"
            )
    except OSError as exc:
        return False, f"无法读取 PRG 文件属性：{path}\n{exc}"

    if not os.access(path, os.W_OK):
        return False, (
            f"当前 Windows 用户对 PRG 无写入权限：\n{path}\n\n"
            "常见原因：公司共享盘只读、被其他程序占用、需管理员权限。"
        )

    parent = path.parent
    if not parent.exists():
        return False, f"PRG 所在目录不存在：\n{parent}"
    if not os.access(parent, os.W_OK):
        return False, (
            f"PRG 所在目录不可写：\n{parent}\n\n"
            "建议将程序放到本地磁盘（如 D:\\Programs）再植入。"
        )

    return True, ""


def wait_app_ready(app: Any, timeout: float = 10.0) -> None:
    try:
        app.WaitUntilReady(timeout)
    except Exception:
        pass


def try_save_part_program(part: Any, app: Any | None = None) -> tuple[bool, str]:
    """尝试 COM Save；成功返回 (True, 保存路径)，失败返回 (False, 原因)。"""
    ok, reason = check_save_preflight(part)
    if not ok:
        return False, reason

    if app is not None:
        wait_app_ready(app)

    path = part_program_path(part)
    try:
        part.Save()
        return True, str(path or "")
    except Exception as exc:
        text = str(exc).strip() or repr(exc)
        hints = [
            f"COM Save() 失败：{text}",
            f"目标文件：{path}",
            "",
            "常见原因：",
            "1. PCDMIS 正在执行测量程序（请先停止执行再植入）",
            "2. PRG 只读或无写入权限（见上）",
            "3. 程序在网络盘/受控文件夹，策略禁止外部程序保存",
            "4. PCDMIS 弹出「另存为」对话框（COM 无法点确定）",
            "",
            "命令已写入内存，可在 PCDMIS 中按 Ctrl+S 手动保存。",
        ]
        return False, "\n".join(hints)
