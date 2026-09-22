"""拆分自 data_extractor.py — COM 命令遍历与单次缓存。"""

from __future__ import annotations

from typing import Any

from ._common import ProgressCallback


def _build_command_cache(
    cmds: Any,
    progress_cb: ProgressCallback | None = None,
) -> tuple[list[tuple[int, Any]], dict[int, Any]]:
    """单次 COM 遍历缓存全部 Commands（大程序性能优化）。"""
    count = int(cmds.Count)
    cache: list[tuple[int, Any]] = []
    for idx in range(1, count + 1):
        try:
            cmd = cmds.Item(idx)
        except Exception:
            try:
                cmd = cmds(idx)
            except Exception:
                continue
        cache.append((idx, cmd))
        if progress_cb and (idx == count or idx % 25 == 0):
            progress_cb(idx, count, f"读取命令 {idx}/{count}…")
    return cache, {idx: cmd for idx, cmd in cache}


def _get_command_at(cmds: Any, index: int) -> Any:
    """读取 Commands 集合中的单条命令（兼容 Item / 调用式索引）。"""
    for getter in (
        lambda: cmds.Item(index),
        lambda: cmds(index),
        lambda: cmds[index],
    ):
        try:
            result = getter()
            if result is not None:
                return result
        except Exception:
            continue
    raise RuntimeError(f"无法读取 Commands 索引 {index}")


def _iter_commands(cmds: Any):
    """遍历 Commands 集合（COM 通常为 1-based）。"""
    count = int(cmds.Count)
    for idx in range(1, count + 1):
        try:
            yield idx, cmds.Item(idx)
        except Exception:
            yield idx, cmds(idx)
