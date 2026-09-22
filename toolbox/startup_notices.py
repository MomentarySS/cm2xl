"""启动后待展示的迁移通知（main 写入，Shell 读取）。"""

from __future__ import annotations

from utils.startup_migrations import MigrationNotice

_pending: list[MigrationNotice] = []


def set_migration_notices(notices: list[MigrationNotice]) -> None:
    global _pending
    _pending = list(notices)


def pop_migration_notices() -> list[MigrationNotice]:
    global _pending
    items = list(_pending)
    _pending = []
    return items
