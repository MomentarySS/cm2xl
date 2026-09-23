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


# ---------------------------------------------------------------------------
# P1-6 拆分：part.Save 的形态分派与效果验证
# ---------------------------------------------------------------------------


def _part_is_modified(part: Any) -> bool | None:
    """读 `part.IsModified`（2024.1 实测存在且可读）。

    返回值：
      True  —— 已被修改（未落盘）
      False —— 未修改（已落盘）
      None  —— 读不到（属性不存在 / 抛异常 / 类型不是 bool）—— 视为未知

    注：早期版本的 part 未必有 IsModified 字段；本函数容错返回 None，
    调用方需自行降级。
    """
    try:
        val = getattr(part, "IsModified")
    except Exception:
        return None
    return val if isinstance(val, bool) else None


def _trigger_part_save(part: Any) -> None:
    """触发保存当前程序。

    2024.1 实测：`part.Save` 是**属性**（读出来是 bool、`callable=False`），
    `PCDLRN.Application` 上没有任何 Save* 成员；老版本 `Save` 是**方法**。
    按运行时形态分派 —— 写死 `part.Save()` 在 2024.1 会恒抛
    `TypeError: 'bool' object is not callable`。

    注：本函数只负责**触发**，不验证落盘。落盘与否由调用方用
    `_part_is_modified()` 验证（防「假成功」）。

    P1-7（2026-09-23 真机新增）：同一 PCDLRN.Application.19.1 / 2024.1 在不同
    PC-DMIS 实例上 `Save` 的 setter 存在性不一致：
        - A. 老版本 / 部分 2024.1 实例：Save 是方法 ⇒ `save()` 工作
        - B. 部分 2024.1 实例：Save 是 bool 属性、setter 存在 ⇒ `part.Save = True` 工作
        - C. 部分 2024.1 实例：Save 是属性、**setter 不存在** ⇒ `part.Save = True`
          抛 `Property '<unknown>.Save' can not be set`
    本函数对形态 C 自动降级到 `part.SaveAs(part.FullName)`（SaveAs 是 callable
    method；用户机器 2026-09-23 实测确认）。SaveAs 仍失败时再 raise —— 由上层
    `_save_failure_hint` 处理（提示「无降级路径 ⇒ 走 Ctrl+S」）。
    """
    save = getattr(part, "Save", None)
    if callable(save):
        save()                 # 形态 A：方法
        return
    try:
        # 形态 B：属性赋值触发。赋 True / False 都能触发落盘（PCDMIS 内部按 setter
        # 实现判定），赋哪个值与落盘无关；按属性本意赋 True。
        part.Save = True
    except Exception:
        # 形态 C：read-only 属性，降级到 SaveAs(part.FullName)
        saveas = getattr(part, "SaveAs", None)
        if not callable(saveas):
            raise  # 既无 Save 也无 SaveAs，让上层 hint 提示走 Ctrl+S
        path_str = (
            getattr(part, "FullName", None)
            or getattr(part, "Path", None)
            or ""
        )
        saveas(path_str)


def _save_failure_hint(exc: BaseException, path: Path | None) -> str:
    """把保存失败原因格式化成对用户有用的多行提示。

    P1-6 改法要点：
      - 原「常见原因 4 条」（执行中 / 只读 / 网络盘 / 另存为对话框）是**猜测性**的，
        实际根因是 API 形态不符。删除那些条目，避免误导下一个排查的人。
      - 保留「Ctrl+S 手动保存」这条 —— 命令已写入内存，对用户仍有效。

    2026-09-23 真机又发现 P1-6 没覆盖的第三种形态（同一 PCDLRN 版本，不同实例
    表现不同 —— 字段常量在 PC-DMIS 内部按 apartment 分配，Save 属性 setter 存在性
    跟着变）：
      - 形态 A：老版本 → Save 是方法 ⇒ `part.Save()` 工作
      - 形态 B：2024.1 部分实例 → Save 是 bool 属性、setter 存在 ⇒ `part.Save = True` 工作
      - **形态 C**：2024.1 部分实例 → Save 是属性、**setter 不存在** ⇒ `part.Save = True`
        抛 `Property '<unknown>.Save' can not be set`（用户真机 2026-09-23 复现）
    P1-7 登记该形态的完整修法（SaveAs 降级 / 走 Ctrl+S 终极路径）。本次仅**更新
    提示文案**，不动运行时逻辑。
    """
    text = str(exc).strip() or repr(exc)
    return "\n".join([
        f"COM 保存失败：{text}",
        f"目标文件：{path}",
        "",
        "实测根因（PC-DMIS 2024.1）：",
        "  `part.Save` 在不同实例上形态不一致（同一 PCDLRN.Application.19.1，",
        "  不同 PRG / COM 上下文会暴露不同表现）：",
        "    · 老版本 / 部分 2024.1 实例：Save 是方法",
        "    · 部分 2024.1 实例：Save 是 bool 属性、setter 存在",
        "    · 部分 2024.1 实例：Save 是属性、**setter 不存在** ⇒ 抛 'Property can not be set'",
        "  cm2xl 已按运行时形态分派；但 read-only 这种 cm2xl 无降级路径。",
        "",
        "命令已写入内存，可在 PCDMIS 中按 Ctrl+S 手动保存。",
    ])


def try_save_part_program(part: Any, app: Any | None = None) -> tuple[bool, str]:
    """尝试 COM Save；成功返回 (True, 保存路径)，失败返回 (False, 原因)。

    P1-6 关键变更：
      - `part.Save` 按运行时形态分派（方法 / 属性），不写死一种。
      - 触发后**必须**用 `IsModified` 验证效果：若仍为 True，说明「没抛异常也
        没落盘」（属性 setter 是空操作），必须照实报失败 ——「假成功」比假失败
        更难排查。
      - 读不到 `IsModified` 时退回「未抛异常即视为成功」，但返回值里标注
        「未经验证」，方便调用方按需降级。

    调用契约保持不变：`(bool, str)` —— `(True, path)` 或 `(False, reason)`，
    或 `(True, "path（保存结果未经验证）")` 用于读不到 IsModified 的回退分支。
    """
    ok, reason = check_save_preflight(part)
    if not ok:
        return False, reason

    if app is not None:
        wait_app_ready(app)

    path = part_program_path(part)

    try:
        _trigger_part_save(part)
    except Exception as exc:
        return False, _save_failure_hint(exc, path)

    # 验证效果：仅看「没抛异常」会被「空 setter」骗过（属性 setter 若是空操作，
    # 异常不抛、IsModified 也不动），所以必须落盘后读 IsModified。
    after = _part_is_modified(part)
    if after is True:
        # setter 被调用、未抛异常，但 IsModified 仍 True ⇒ 未落盘 ⇒ 报失败
        return False, _save_failure_hint(
            RuntimeError("Save 已触发且未抛异常，但 IsModified 仍为 True（未落盘）"),
            path,
        )
    if after is None:
        return True, f"{path}（未能读取 IsModified，保存结果未经验证）"
    return True, str(path or "")
