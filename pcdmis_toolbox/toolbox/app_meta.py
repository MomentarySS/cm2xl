"""
PCDMIS Toolbox 2.0 — 统一版本与元数据
所有模块必须从这里导入版本常量，禁止硬编码。
"""

APP_TITLE = "PCDMIS Toolbox"
APP_VERSION = "2.0.0"
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

# 测房友好青绿主色调（与 utils/theme.py 保持一致）
TOOLBOX_THEME = {
    "accent": "#0F766E",
    "accent_hover": "#14B8A6",
    "primary": "#115E59",
    "primary_hover": "#0F766E",
    "ok": "#15803D",
    "warn": "#C2410C",
    "bad": "#B91C1C",
    "muted": "#64748B",
    "card_bg": "#FFFFFF",
    "card_border": "#E2E8F0",
    "page_bg": "#F1F5F9",
    "text": "#1E293B",
    "text_muted": "#64748B",
}
