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
        # 形态 C：setter 抛异常（模拟「Property ... can not be set」）
        self._save_setter_raises: BaseException | None = None
        # SaveAs 降级路径（形态 C 用）：callable 实例 / None（不存在）
        self.saveas_callable: Any = None
        self.saveas_call_count = 0

        # IsModified 行为：True / False / 一个抛异常的 sentinel
        self._is_modified_value = is_modified_after

    @property
    def Save(self):
        """按构造时给的形态暴露 Save —— 既支持方法也支持属性 getter。"""
        return self._save_attr

    @Save.setter
    def Save(self, value: Any) -> None:
        # 测试钩子：setter 被调多少次、是否真做落盘
        if self._save_setter_raises is not None:
            raise self._save_setter_raises
        if self._save_setter_hook is not None:
            self._save_setter_hook(value)
        self._save_attr = value

    def SaveAs(self, path_str: str) -> None:
        """SaveAs 降级路径 —— 形态 C（read-only Save）时调用。

        `saveas_callable` 为 None ⇒ 模拟「SaveAs 也不存在」，抛 AttributeError
        上层（事实上这是不可能的形态，但留着降级链的最后一档可测性）。
        """
        self.saveas_call_count += 1
        if self.saveas_callable is None:
            raise AttributeError(
                f"'FakePart' has no SaveAs (saveas_callable=None)"
            )
        self.saveas_callable(path_str)

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


def test_failure_hint_mentions_read_only_form():
    """2026-09-23 真机发现第三种形态：Save 属性 setter 不存在 ⇒ 抛 'Property can not be set'。

    P1-6 没覆盖 —— 本次按用户选择「仅改提示，不改逻辑」，所以提示里**必须**
    明确提到 read-only 这种形态与「cm2xl 无降级路径 ⇒ 走 Ctrl+S」。若有人再把
    这种形态的报错漏在 hint 外，下一个排查者会再次走错路。

    关键字选择说明：不能直接断言 "can not be set"（旧 hint 也会从异常原文
    echo 进去）—— 必须断言新文案才有的字符串（"setter 不存在"）。
    """
    from ..inject.save_helper import _save_failure_hint

    hint = _save_failure_hint(
        RuntimeError("Property '<unknown>.Save' can not be set."),
        Path("/tmp/demo.PRG"),
    )
    # 正向：read-only 形态必须在提示里有专门的解释（不是只 echo 异常）
    assert "setter 不存在" in hint, (
        f"提示必须解释 read-only 形态的根因（属性 setter 不存在） —— "
        f"不能只 echo 原异常 'Property can not be set'。"
        f"实际：{hint!r}"
    )
    # 正向：必须明说 cm2xl 对 read-only 无降级路径 ⇒ 走 Ctrl+S
    assert "无降级路径" in hint, (
        f"read-only 形态下 cm2xl 没有降级路径 —— 提示必须明说『走 Ctrl+S』。"
        f"实际：{hint!r}"
    )


# ---------------------------------------------------------------------------
# P1-7（2026-09-23 真机新增）：形态 C —— Save read-only 属性 + SaveAs 降级
# ---------------------------------------------------------------------------


def test_save_read_only_falls_back_to_saveas(writable_prg: Path):
    """形态 C：Save 是 read-only 属性（setter 抛 Property can not be set）+
    SaveAs 是 callable method ⇒ cm2xl 自动降级到 `part.SaveAs(part.FullName)`，
    IsModified 应转 False。

    对应用户真机（PCDLRN.Application.19.1 / 2024.1，part.Save 求值 True / callable=False；
    part.SaveAs 求值 <bound method SaveAs> / callable=True）。
    """

    saveas_calls: list[str] = []

    def _saveas_impl(path_str: str) -> None:
        saveas_calls.append(path_str)

    part = _FakePart(
        prg_path=writable_prg,
        save_attr=True,            # Save 求值是真值 ⇒ 属性形态
        is_modified_after=False,   # 落盘后 IsModified 转 False
    )
    part._save_setter_raises = RuntimeError("Property '<unknown>.Save' can not be set.")
    part.saveas_callable = _saveas_impl

    saved, msg = try_save_part_program(part)

    # 核心：SaveAs 降级成功
    assert saved is True, (
        f"SaveAs 降级路径必须工作（SaveAs 可调 ⇒ 视为保存成功）。"
        f"实际：saved = {saved}, msg = {msg!r}"
    )
    assert str(writable_prg) in msg
    # SaveAs 必须被调用过一次（这是关键反证：证明走了降级路径，不是恰好别的原因返回 True）
    assert part.saveas_call_count == 1, (
        f"SaveAs 应被调用过一次 —— 没调说明没走降级。"
        f"saveas_call_count = {part.saveas_call_count}"
    )
    # SaveAs 必须接到 FullName（或 Path）
    assert saveas_calls, "SaveAs 必须被调用并接到路径"
    assert saveas_calls[0] == str(writable_prg), (
        f"SaveAs 应接 FullName，传错路径等于没存。"
        f"实际传给 SaveAs: {saveas_calls[0]!r}"
    )


def test_save_read_only_no_saveas_reports_failure(writable_prg: Path):
    """形态 C 极端：Save read-only + SaveAs 也不存在 ⇒ 必须报失败（不静默吞）。

    这是「P1-7 终极降级链断了」的兜底 —— 既无 Save 也无 SaveAs，cm2xl 没招，
    必须走 hint 提示「走 Ctrl+S」（提示里已经有「无降级路径」说明）。
    """

    part = _FakePart(
        prg_path=writable_prg,
        save_attr=True,
        is_modified_after=True,     # 任意：IsModified 在降级失败后不会被读到
    )
    part._save_setter_raises = RuntimeError("Property '<unknown>.Save' can not be set.")
    # saveas_callable 留 None ⇒ SaveAs 调用抛 AttributeError

    saved, msg = try_save_part_program(part)

    assert saved is False, (
        "Save read-only + SaveAs 不存在 ⇒ 必须报失败（不静默吞）。"
        f"实际：saved = {saved}, msg = {msg!r}"
    )
    assert "无降级路径" in msg, (
        f"失败提示里必须含『无降级路径』字样（让用户/排查者立刻看清根因）。"
        f"实际：{msg!r}"
    )