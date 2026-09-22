"""用户设置持久化。"""


from __future__ import annotations


import json
import logging

from dataclasses import asdict, dataclass, field
from pathlib import Path


from ..app_meta import DEFAULT_TOLERANCE
from utils.paths import paths
from utils.settings import save_settings_json_atomic
from ..export.inspection_form_fill import FormFillConfig


logger = logging.getLogger(__name__)


@dataclass
class AppSettings:

    export_dir: str = ""
    filename_pattern: str = "{part}_{time}"
    tolerance: dict = field(default_factory=lambda: dict(DEFAULT_TOLERANCE))
    export_scope: str = "report"
    require_marked: bool = True
    form_fill: FormFillConfig = field(default_factory=FormFillConfig)

    def resolved_export_dir(self) -> Path:
        if self.export_dir.strip():
            return Path(self.export_dir)
        return paths.pc_excel_reports


def load_settings() -> AppSettings:
    settings_file = paths.config_dir / 'pc_to_excel' / 'settings.json'

    if not settings_file.is_file():
        return AppSettings()

    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        # 文件不存在/损坏时回退默认配置，并记录错误详情
        logger.warning("加载配置文件失败（%s），使用默认配置: %s", settings_file, exc)
        return AppSettings()
    except UnicodeDecodeError as exc:
        # 编码错误说明文件已损坏，记录详情后回退默认
        logger.error("配置文件编码错误（%s），使用默认配置: %s", settings_file, exc)
        return AppSettings()
    except Exception as exc:
        # 其他未知异常也记录，但仍然返回默认配置避免崩溃
        logger.exception("加载配置文件时发生未知异常（%s），使用默认配置: %s", settings_file, exc)
        return AppSettings()

    settings = AppSettings()

    try:
        settings.export_dir = str(data.get("export_dir", "") or "")
    except Exception as exc:
        logger.debug("解析 export_dir 失败，使用默认值: %s", exc)

    try:
        settings.filename_pattern = str(
            data.get("filename_pattern", "{part}_{time}") or "{part}_{time}"
        )
    except Exception as exc:
        logger.debug("解析 filename_pattern 失败，使用默认值: %s", exc)

    try:
        settings.tolerance = dict(data.get("tolerance") or DEFAULT_TOLERANCE)
    except Exception as exc:
        logger.debug("解析 tolerance 失败，使用默认值: %s", exc)
        settings.tolerance = dict(DEFAULT_TOLERANCE)

    try:
        settings.export_scope = str(data.get("export_scope", "report") or "report")
    except Exception as exc:
        logger.debug("解析 export_scope 失败，使用默认值: %s", exc)

    try:
        settings.require_marked = bool(data.get("require_marked", True))
    except Exception as exc:
        logger.debug("解析 require_marked 失败，使用默认值: %s", exc)

    try:
        settings.form_fill = FormFillConfig.from_dict(data.get("form_fill"))
    except Exception as exc:
        logger.debug("解析 form_fill 失败，使用默认值: %s", exc)
        settings.form_fill = FormFillConfig()

    return settings


def save_settings(settings: AppSettings) -> None:
    settings_file = paths.config_dir / 'pc_to_excel' / 'settings.json'
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    # FormFillConfig 用显式 to_dict，避免嵌套 dataclass 序列化差异
    payload["form_fill"] = settings.form_fill.to_dict()
    save_settings_json_atomic(settings_file, payload)


def build_export_filename(part_name: str, pattern: str | None = None) -> str:
    from datetime import datetime

    safe_part = "".join(c if c.isalnum() or c in "-_." else "_" for c in part_name) or "report"
    pat = pattern or "{part}_{time}"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = pat.replace("{part}", safe_part).replace("{time}", stamp)
    if not name.lower().endswith(".xlsx"):
        name += ".xlsx"
    return name


def ensure_default_dirs() -> None:
    paths.pc_excel_reports.mkdir(parents=True, exist_ok=True)
    (paths.config_dir / 'pc_to_excel').mkdir(parents=True, exist_ok=True)
