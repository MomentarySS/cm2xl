"""用户设置持久化。"""



from __future__ import annotations



import json

from dataclasses import asdict, dataclass, field

from pathlib import Path



from config import DEFAULT_TOLERANCE, REPORTS_DIR, SETTINGS_FILE

from export.inspection_form_fill import FormFillConfig





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

        return REPORTS_DIR





def load_settings() -> AppSettings:

    if not SETTINGS_FILE.is_file():

        return AppSettings()

    try:

        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))

    except Exception:

        return AppSettings()



    settings = AppSettings()

    try:

        settings.export_dir = str(data.get("export_dir", "") or "")

    except Exception:

        pass

    try:

        settings.filename_pattern = str(

            data.get("filename_pattern", "{part}_{time}") or "{part}_{time}"

        )

    except Exception:

        pass

    try:

        settings.tolerance = dict(data.get("tolerance") or DEFAULT_TOLERANCE)

    except Exception:

        settings.tolerance = dict(DEFAULT_TOLERANCE)

    try:

        settings.export_scope = str(data.get("export_scope", "report") or "report")

    except Exception:

        pass

    try:

        settings.require_marked = bool(data.get("require_marked", True))

    except Exception:

        pass

    try:

        settings.form_fill = FormFillConfig.from_dict(data.get("form_fill"))

    except Exception:

        settings.form_fill = FormFillConfig()

    return settings





def save_settings(settings: AppSettings) -> None:

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    payload = asdict(settings)

    # FormFillConfig 用显式 to_dict，避免嵌套 dataclass 序列化差异

    payload["form_fill"] = settings.form_fill.to_dict()

    SETTINGS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")





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

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)


