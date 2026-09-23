"""try_save_part_program 的形态分派与 IsModified 验证（P1-6）。

P1-6 现象：植入后弹「COM Save() 失败：'bool' object is not callable」。
根因：`part.Save` 在 2024.1 是**属性**（bool）不是方法，老版本是方法；
原代码写死 `part.Save()` ⇒ 2024.1 上恒抛 TypeError ⇒ 自动保存恒失败，
用户每次都得手动 Ctrl+S。

改法：按运行时形态分派 + 用 `IsModified` 验证效果。
本测试**不需要 PC-DMIS**，用替身覆盖三种形态：

  | 替身形态                                                | 期望                |
  | `Save` 是 bool 属性、赋值后 `IsModified` 转 False       | `(True, path)`       |
  | `Save` 是方法（老版本）、`IsModified` 转 False          | `(True, path)`       |
  | `Save` 是属性但赋值空操作、`IsModified` 仍 True         | **`(False, ...)`**   ← 防假成功 |
  | `IsModified` 读不到（抛异常）                          | `(True, ...含「未经验证」...)` |
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import pytest

from ..inject.save_helper import try_save_part_program


# ---------------------------------------------------------------------------
# 替身：构造一个 preflight 能过、形态可配置的 part
# ---------------------------------------------------------------------------


class _FakePart:
    """替身 — 控制 part.Save / part.IsModified 的运行时形态。

    设计要点：
    - `Save` 是**真**的 class-level property（getter + setter），跟真机
      COM 行为对齐 —— 外部代码 `part.Save = True` 会走 fset。
    - `_save_setter_hook` 可选回调 —— 测试用它在 setter 触发时记数 / 模拟
      空操作，而不必改 IsModified。
    - `IsModified` 返回固定值或抛异常，由 `is_modified_after` 控制。
    """

    def __init__(
        self,
        *,
        prg_path: Path,
        save_attr: Any,
        is_modified_after: bool | Exception,
    ) -> None:
        # preflight 需要的属性
        self.FullName = str(prg_path)
        self.Path = str(prg_path)
        self.Name = prg_path.name

        self._save_attr = save_attr
        self._save_setter_hook: Any = None

        # IsModified 行为：True / False / 一个抛异常的 sentinel
        self._is_modified_value = is_modified_after

    @property
    def Save(self):
        """按构造时给的形态暴露 Save —— 既支持方法也支持属性 getter。"""
        return self._save_attr

    @Save.setter
    def Save(self, value: Any) -> None:
        # 测试钩子：setter 被调多少次、是否真做落盘
        if self._save_setter_hook is not None:
            self._save_setter_hook(value)
        self._save_attr = value

    @property
    def IsModified(self) -> bool:
        """根据测试场景返回 True / False / 抛异常。"""
        v = self._is_modified_value
        if isinstance(v, Exception):
            raise v
        return v


class _MethodLikeSave:
    """模拟老版本：Save 是方法、callable=True。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


# ---------------------------------------------------------------------------
# preflight 通过所需：tmp 路径下放一个可写 .prg
# ---------------------------------------------------------------------------


@pytest.fixture
def writable_prg(tmp_path: Path) -> Path:
    """preflight 通过所需的 .prg 文件：可写 / 父目录可写。"""
    prg = tmp_path / "demo.PRG"
    prg.write_text("", encoding="utf-8")
    # 确保可写（tmp_path 默认可写；但显式 chmod 排除偶然因素）
    prg.chmod(stat.S_IWRITE | stat.S_IREAD)
    return prg


# ---------------------------------------------------------------------------
# 形态 1 — `Save` 是属性、赋值后 IsModified 转 False
# ---------------------------------------------------------------------------


def test_save_attr_property_succeeds(writable_prg: Path):
    """2024.1 真机形态：`part.Save` 是属性（bool），赋 True 触发保存，
    IsModified 由 True 转 False ⇒ 应返回 (True, path)。

    替身状态：构造时 IsModified 已是落盘后值 False —— 等价于真机里
    赋值触发后磁盘写完的状态。
    """

    part = _FakePart(
        prg_path=writable_prg,
        save_attr=False,           # 旧值（任意 bool）—— 形式合法即可
        is_modified_after=False,   # 落盘后 IsModified 转 False
    )

    saved, msg = try_save_part_program(part)

    assert saved is True
    assert str(writable_prg) in msg


# ---------------------------------------------------------------------------
# 形态 2 — `Save` 是方法（老版本）、调用后 IsModified 转 False
# ---------------------------------------------------------------------------


def test_save_method_succeeds(writable_prg: Path):
    """老版本形态：part.Save 是 callable 方法，调用一次后 IsModified 转 False。"""

    method = _MethodLikeSave()
    part = _FakePart(
        prg_path=writable_prg,
        save_attr=method,           # 直接传 callable —— 触发 _trigger_part_save 的方法分支
        is_modified_after=False,
    )

    saved, msg = try_save_part_program(part)

    assert saved is True
    assert str(writable_prg) in msg
    # 反向守卫：方法分支真的被走过（不是错误走了属性 setter）
    assert method.calls == 1, (
        "形态 2 应走『方法分支』（callable save）：但 _trigger_part_save 没调到。"
    )


# ---------------------------------------------------------------------------
# 形态 3 — `Save` 是属性但 setter 空操作、IsModified 仍 True ← 防假成功
# ---------------------------------------------------------------------------


def test_save_property_no_op_reports_failure(writable_prg: Path):
    """防假成功：属性 setter 不抛异常、但 IsModified 仍为 True ⇒ 必须报失败。

    否则「没保存」会被错报成「已保存」—— 比 P1-6 的假失败更糟。
    """

    call_count = {"n": 0}

    def _no_op_hook(_value: Any) -> None:
        # 模拟 setter 是空操作 —— 不动 IsModified
        call_count["n"] += 1

    part = _FakePart(
        prg_path=writable_prg,
        save_attr=False,
        is_modified_after=True,     # 落盘后**仍**为 True
    )
    part._save_setter_hook = _no_op_hook

    saved, msg = try_save_part_program(part)

    # 核心断言：必须报失败
    assert saved is False, (
        "属性 setter 空操作 + IsModified 仍 True ⇒ 必须报失败。"
        f"实际：saved = {saved}, msg = {msg!r}"
    )
    assert call_count["n"] == 1, (
        "setter 应被调用过一次 —— 这次没调说明 _trigger_part_save 没走到"
        f"『属性形态』分支。call_count={call_count['n']}"
    )
    # 提示里要有 IsModified 仍 True 的提示（让用户 / 排查者能看清根因）
    assert "IsModified" in msg or "未落盘" in msg, (
        f"失败提示里应说明 IsModified 仍为 True / 未落盘（让排查者立刻定位）。"
        f"实际：{msg!r}"
    )


# ---------------------------------------------------------------------------
# 形态 4 — IsModified 读不到（抛异常） ⇒ 返回 True + 「未经验证」
# ---------------------------------------------------------------------------


def test_is_modified_unreadable_falls_back_to_unverified(writable_prg: Path):
    """IsModified 读不到时退回「未抛异常即视为成功」+ 标注「未经验证」。

    注：这是降级路径 —— 老版本 part 未必有 IsModified 字段；不能因此把所有
    落盘都判失败（否则会引入新的假失败）。
    """

    part = _FakePart(
        prg_path=writable_prg,
        save_attr=False,
        is_modified_after=RuntimeError("dispnotfnd"),   # IsModified 不存在
    )

    saved, msg = try_save_part_program(part)

    assert saved is True, "IsModified 读不到应判为『未经验证的成功』，不能判失败"
    assert "未经验证" in msg, (
        f"返回值里必须标注『未经验证』—— 让调用方知道这次落盘未被验证。"
        f"实际：{msg!r}"
    )


# ---------------------------------------------------------------------------
# 反向守卫 — 修 bug 的人若把 _save_failure_hint 的 Ctrl+S 提示删了，立刻报警
# ---------------------------------------------------------------------------


def test_failure_hint_keeps_ctrl_s_workaround():
    """保留 Ctrl+S 提示 —— 这是 P1-6 文档明确要求的（命令已写入内存，仍有效）。

    若有人嫌啰嗦删掉这条 —— 文档明确禁止。
    """
    from ..inject.save_helper import _save_failure_hint

    hint = _save_failure_hint(RuntimeError("boom"), Path("/tmp/demo.PRG"))
    assert "Ctrl+S" in hint, "Ctrl+S 手动保存提示必须保留"
    # 反向断言：原 4 条猜测性条目应已删除
    assert "另存为" not in hint, "原『PCDMIS 弹出另存为对话框』猜测应删除"
    assert "网络盘" not in hint, "原『网络盘/受控文件夹』猜测应删除"
    assert "PCDMIS 正在执行测量程序" not in hint, "原『执行中』猜测应删除"


def test_failure_hint_mentions_real_root_cause():
    """新提示必须包含真实根因（API 形态不符）。"""
    from ..inject.save_helper import _save_failure_hint

    hint = _save_failure_hint(
        TypeError("'bool' object is not callable"),
        Path("/tmp/demo.PRG"),
    )
    assert "属性" in hint and "bool" in hint, (
        f"提示必须解释真实根因（Save 是属性而非方法）。实际：{hint!r}"
    )