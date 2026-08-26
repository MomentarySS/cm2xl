"""PC to Excel 版本信息"""
from toolbox.app_meta import APP_VERSION

APP_TITLE = "PCDMIS 按需 Excel 测量报告"
__version__ = APP_VERSION

EXPORT_CMD_ID = "PC2XL_EXPORT"
OBTYPE_BASIC_SCRIPT = 12346

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
