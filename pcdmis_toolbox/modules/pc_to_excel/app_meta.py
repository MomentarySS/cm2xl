"""PC to Excel 版本信息"""
from toolbox.app_meta import APP_VERSION

APP_TITLE = "PCDMIS 按需 Excel 测量报告"
__version__ = APP_VERSION

EXPORT_CMD_ID = "PC2XL_EXPORT"
OBTYPE_BASIC_SCRIPT = 12346

# 产品名 → COM 内部版本（日历年 − 2005）。2017 R2 起均为 64 位。
PCDMIS_RELEASES: tuple[tuple[str, int, int], ...] = (
    ("2026.1", 21, 1),
    ("2025.2", 20, 2),
    ("2025.1", 20, 1),
    ("2024.2", 19, 2),
    ("2024.1", 19, 1),
    ("2023.2", 18, 2),
    ("2023.1", 18, 1),
    ("2022.2", 17, 2),
    ("2022.1", 17, 1),
    ("2021.2", 16, 2),
    ("2021.1", 16, 1),
    ("2020 R2", 15, 2),
    ("2020 R1", 15, 1),
    ("2019 R2", 14, 2),
    ("2019 R1", 14, 1),
    ("2018 R2", 13, 2),
    ("2018 R1", 13, 1),
    ("2017 R2", 12, 2),
    ("2017 R1", 12, 1),
)

PROG_ID_GENERIC = "PCDLRN.Application"
PROG_ID_CANDIDATES = [
    f"PCDLRN.Application.{major}.{minor}" for _, major, minor in PCDMIS_RELEASES
] + [PROG_ID_GENERIC]

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
