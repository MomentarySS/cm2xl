"""
日志目录维护：启动时按总量裁剪 + 用户手动清理。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ARCHITECTURE 3.6：启动时 log_dir 超过此值则删最旧文件
LOG_DIR_SIZE_LIMIT_BYTES = 100 * 1024 * 1024


def iter_log_files(log_dir: Path) -> list[Path]:
    """枚举日志目录下可清理的日志文件（含轮转备份与 crash.log）。"""
    if not log_dir.is_dir():
        return []
    files: list[Path] = []
    for pattern in ("*.log", "*.log.*", "crash.log"):
        files.extend(log_dir.glob(pattern))
    # 去重（crash.log 同时匹配 *.log）
    unique: dict[str, Path] = {}
    for f in files:
        if f.is_file():
            unique[str(f.resolve())] = f
    return list(unique.values())


def directory_size_bytes(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def cleanup_logs(
    log_dir: Path,
    *,
    max_total_bytes: int | None = LOG_DIR_SIZE_LIMIT_BYTES,
    dry_run: bool = False,
) -> dict:
    """
    按修改时间从旧到新删除日志文件，直到目录总量低于 max_total_bytes。

    max_total_bytes=None 表示尽量清空（手动「清理日志」）。
    返回 {deleted_files, freed_bytes, remaining_bytes}。
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    files = iter_log_files(log_dir)
    total = directory_size_bytes(files)
    limit = max_total_bytes if max_total_bytes is not None else 0

    if max_total_bytes is not None and total <= limit:
        return {"deleted_files": 0, "freed_bytes": 0, "remaining_bytes": total}

    deleted = 0
    freed = 0
    # 最旧优先删除；同 mtime 时按路径名稳定排序
    for f in sorted(files, key=lambda p: (p.stat().st_mtime, str(p))):
        if max_total_bytes is not None and total <= limit:
            break
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if not dry_run:
            try:
                f.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("删除日志失败 %s: %s", f, exc)
                continue
        deleted += 1
        freed += size
        total -= size

    logger.info(
        "日志清理完成: deleted=%s freed=%.1fMB remaining=%.1fMB dir=%s",
        deleted, freed / (1024 * 1024), max(total, 0) / (1024 * 1024), log_dir,
    )
    return {"deleted_files": deleted, "freed_bytes": freed, "remaining_bytes": max(total, 0)}


def prune_logs_on_startup(log_dir: Path, *, limit_bytes: int = LOG_DIR_SIZE_LIMIT_BYTES) -> dict | None:
    """启动时若日志目录超过 limit_bytes 则自动裁剪；否则无操作。"""
    files = iter_log_files(log_dir)
    total = directory_size_bytes(files)
    if total <= limit_bytes:
        return None
    return cleanup_logs(log_dir, max_total_bytes=limit_bytes)
