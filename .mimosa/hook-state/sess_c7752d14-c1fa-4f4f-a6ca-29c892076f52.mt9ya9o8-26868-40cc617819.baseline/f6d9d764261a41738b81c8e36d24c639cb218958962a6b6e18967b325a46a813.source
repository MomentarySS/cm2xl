"""全局配置 — PCDMIS 按需 Excel 测量报告工具。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resolve_deploy_dir() -> Path:
    """BAS/配置固定部署到 LocalAppData，避免 exe 路径含空格导致 PCDMIS 找不到脚本。"""
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "PCDMIS_ExcelExporter"


ROOT_DIR = _resolve_root()
DEPLOY_DIR = _resolve_deploy_dir()
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
SCRIPTS_DIR = DEPLOY_DIR / "scripts"
_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))

APP_TITLE = "PCDMIS 按需 Excel 测量报告"
APP_VERSION = "1.4.5"
GUI_THEME = "litera"
GUI_SIZE = (960, 720)

EXPORT_CMD_ID = "PC2XL_EXPORT"
BAS_FILENAME = "export_current.bas"
BAS_TEMPLATE_FILENAME = "export_current.bas.template"

# 连接候选：运行时仍优先扫注册表；下列为 2022.1–2026.1 离线兜底（未注册会跳过）
# 营销版本 ↔ ProgID 约：2022→17 / 2023→18 / 2024→19 / 2025→20 / 2026→21（本机 2024.1=19.1 已核实）
PROG_ID_CANDIDATES = [
    "PCDLRN.Application.21.1",  # 2026.1
    "PCDLRN.Application.20.2",  # 2025.2
    "PCDLRN.Application.20.1",  # 2025.1
    "PCDLRN.Application.19.2",  # 2024.2
    "PCDLRN.Application.19.1",  # 2024.1
    "PCDLRN.Application.18.2",  # 2023.2
    "PCDLRN.Application.18.1",  # 2023.1
    "PCDLRN.Application.17.2",  # 2022.2
    "PCDLRN.Application.17.1",  # 2022.1
    "PCDLRN.Application",
]

DEFAULT_TOLERANCE = {
    "x_lower": -0.02,
    "x_upper": 0.02,
    "y_lower": -0.02,
    "y_upper": 0.02,
    "z_lower": -0.02,
    "z_upper": 0.02,
    "d_lower": -0.05,
    "d_upper": 0.05,
}

# PCDLRN OBTYPE — BASIC_SCRIPT
OBTYPE_BASIC_SCRIPT = 12346

SETTINGS_FILE = DATA_DIR / "settings.json"
