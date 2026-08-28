"""
cm2xl — 统一版本与元数据
所有模块必须从这里导入版本常量，禁止硬编码。
"""

from utils.theme import TOOLBOX_THEME  # noqa: F401  # 唯一主题定义点，兼容旧引用

APP_TITLE = "cm2xl"
APP_VERSION = "1.0.6"
APP_BUILD = "1"

# PCDMIS BASIC SCRIPT 命令 ID（固定，由 PCDMIS 菜单项引用）
EXPORT_CMD_ID = "PC2XL_EXPORT"

# PCDMIS COM ProgID 版本映射（用于自动发现）
PCDLRN_PROGIDS = [
    "PCDLRN.Application.24.0",  # 2026
    "PCDLRN.Application.23.0",  # 2025
    "PCDLRN.Application.22.0",  # 2024
    "PCDLRN.Application.21.0",  # 2023
    "PCDLRN.Application.20.0",  # 2022.2
    "PCDLRN.Application.19.1",  # 2022.1
]
