"""
启动时配置迁移（路径 + schema 版本），并收集需向用户展示的说明。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from utils.paths import paths
from utils.settings import (
    CONFIG_SCHEMA_VERSION,
    _LEGACY_DEFAULT_VERSION,
    load_and_migrate_settings,
    load_json,
    migrate_settings_if_needed,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationNotice:
    module: str
    title: str
    detail: str


def _legacy_path_pairs() -> list[tuple[str, Path, Path, str]]:
    """(module_name, old_path, new_path, label) — 按优先级排列。"""
    pairs: list[tuple[str, Path, Path, str]] = []

    cmm_cfg = paths.config_dir / "cmm_filler"
    for name in ("settings.json", "template_config.json"):
        pairs.append((
            "cmm_filler",
            paths.data_dir / "cmm_filler" / name,
            cmm_cfg / name,
            name,
        ))
        pairs.append((
            "cmm_filler",
            Path(os.environ.get("LOCALAPPDATA", "")) / "CMMFiller" / name,
            cmm_cfg / name,
            name,
        ))
        pairs.append((
            "cmm_filler",
            Path(os.environ.get("APPDATA", "")) / "CMMFiller" / name,
            cmm_cfg / name,
            name,
        ))

    pc_new = paths.config_dir / "pc_to_excel" / "settings.json"
    for old in (
        paths.data_dir / "settings.json",
        paths.root / "data" / "settings.json",
        Path(os.environ.get("LOCALAPPDATA", "")) / "PCDMIS_ExcelExporter" / "settings.json",
        Path(os.environ.get("APPDATA", "")) / "PCDMIS_ExcelExporter" / "settings.json",
    ):
        pairs.append(("pc_to_excel", old, pc_new, "settings.json"))

    return pairs


def run_startup_migrations() -> list[MigrationNotice]:
    """执行全部启动迁移，返回需弹窗告知用户的事件列表。"""
    notices: list[MigrationNotice] = []
    migrated_targets: set[str] = set()

    for module, old_path, new_path, label in _legacy_path_pairs():
        target_key = str(new_path)
        if target_key in migrated_targets:
            continue
        if not old_path.is_file() or new_path.is_file():
            continue
        try:
            migrate_settings_if_needed(module, old_path, new_path)
            migrated_targets.add(target_key)
            bak = old_path.with_suffix(".bak")
            notices.append(MigrationNotice(
                module=module,
                title="配置文件已迁移",
                detail=(
                    f"模块：{module}\n"
                    f"文件：{label}\n\n"
                    f"已从旧位置复制到新位置：\n"
                    f"  旧：{old_path}\n"
                    f"  新：{new_path}\n\n"
                    f"旧文件已备份为：\n  {bak}"
                ),
            ))
            logger.info("[startup] 路径迁移: %s → %s", old_path, new_path)
        except Exception as exc:
            logger.warning("[startup] 路径迁移跳过 %s: %s", old_path, exc)

    version_targets = (
        ("cmm_filler", paths.config_dir / "cmm_filler" / "settings.json"),
        ("pc_to_excel", paths.config_dir / "pc_to_excel" / "settings.json"),
    )
    for module_name, config_path in version_targets:
        if not config_path.is_file():
            continue
        data = load_json(config_path)
        file_version = data.get("_version", "0.0.0")
        if file_version == "0.0.0":
            file_version = _LEGACY_DEFAULT_VERSION.get(module_name, "0.0.0")
        if file_version == CONFIG_SCHEMA_VERSION:
            continue
        try:
            load_and_migrate_settings(module_name, config_path)
            backup = config_path.with_suffix(f".v{file_version}.bak")
            notices.append(MigrationNotice(
                module=module_name,
                title="配置版本已升级",
                detail=(
                    f"模块：{module_name}\n\n"
                    f"配置 schema 已从 v{file_version} 升级到 v{CONFIG_SCHEMA_VERSION}。\n"
                    f"升级前备份：\n  {backup}"
                ),
            ))
            logger.info("[startup] schema 升级: %s v%s → v%s", module_name, file_version, CONFIG_SCHEMA_VERSION)
        except Exception as exc:
            logger.warning("[startup] schema 升级跳过 %s: %s", module_name, exc)

    return notices
