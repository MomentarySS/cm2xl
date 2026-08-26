"""
PCDMIS Toolbox 2.0 — 统一主题常量
测房友好青绿主色，所有模块必须从这里引用颜色，禁止硬编码。
"""

import json
from pathlib import Path

TOOLBOX_THEME = {
    # 基础色
    "accent": "#0F766E",
    "accent_hover": "#14B8A6",
    "primary": "#115E59",
    "primary_hover": "#0F766E",
    # 状态色
    "ok": "#15803D",
    "warn": "#C2410C",
    "bad": "#B91C1C",
    # 界面色
    "muted": "#64748B",
    "card_bg": "#FFFFFF",
    "card_border": "#E2E8F0",
    "page_bg": "#F1F5F9",
    # 文字
    "text": "#1E293B",
    "text_muted": "#64748B",
}

TOOLBOX_THEME_JSON_PATH = Path(__file__).parent / "theme.json"


def _build_theme_json(dest: Path | None = None) -> None:
    """
    生成 CustomTkinter 自定义主题 JSON，写入 dest 或默认 theme.json。
    使用青绿主色，避免默认紫/蓝/绿切换时的颜色跳变。
    """
    theme = {
        "CTk": {
            "fg_color": [TOOLBOX_THEME["page_bg"], "#0F172A"],
        },
        "CTkFrame": {
            "corner_radius": 8,
            "border_color": [TOOLBOX_THEME["card_border"], "#334155"],
            "fg_color": [TOOLBOX_THEME["card_bg"], "#1E293B"],
        },
        "CTkButton": {
            "corner_radius": 6,
            "border_color": [TOOLBOX_THEME["accent"], "#14B8A6"],
            "hover_color": [TOOLBOX_THEME["accent_hover"], "#0D9488"],
            "pressed_color": [TOOLBOX_THEME["primary"], "#115E59"],
            "fg_color": [TOOLBOX_THEME["accent"], "#0F766E"],
            "text_color": ["#FFFFFF", "#F1F5F9"],
            "border_width": 0,
        },
        "CTkLabel": {
            "corner_radius": 0,
            "fg_color": [TOOLBOX_THEME["page_bg"], "#0F172A"],
            "text_color": [TOOLBOX_THEME["text"], "#F1F5F9"],
        },
        "CTkEntry": {
            "corner_radius": 6,
            "border_color": [TOOLBOX_THEME["card_border"], "#334155"],
            "fg_color": [TOOLBOX_THEME["page_bg"], "#1E293B"],
            "text_color": [TOOLBOX_THEME["text"], "#F1F5F9"],
        },
        "CTkOptionMenu": {
            "corner_radius": 6,
            "fg_color": [TOOLBOX_THEME["accent"], "#0F766E"],
            "button_color": [TOOLBOX_THEME["primary"], "#115E59"],
            "hover_color": [TOOLBOX_THEME["accent_hover"], "#14B8A6"],
            "text_color": ["#FFFFFF", "#F1F5F9"],
        },
        "CTkProgressBar": {
            "corner_radius": 6,
            "fg_color": [TOOLBOX_THEME["page_bg"], "#1E293B"],
            "progress_color": [TOOLBOX_THEME["accent"], "#0F766E"],
        },
        "CTkSwitch": {
            "corner_radius": 12,
            "fg_color": [TOOLBOX_THEME["muted"], "#475569"],
            "progress_color": [TOOLBOX_THEME["accent"], "#0F766E"],
            "button_color": ["#FFFFFF", "#E2E8F0"],
            "button_hover_color": ["#F1F5F9", "#CBD5E1"],
        },
    }

    dest = dest or TOOLBOX_THEME_JSON_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(theme, indent=2), encoding="utf-8")


def apply_theme() -> None:
    """
    在 main.py 启动最早处调用一次，设置 CustomTkinter 全局主题。
    此后各模块不得再调用 set_default_color_theme。
    """
    import customtkinter as ctk

    # 生成自定义主题 JSON（如果不存在或过旧）
    if not TOOLBOX_THEME_JSON_PATH.exists():
        _build_theme_json()

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme(str(TOOLBOX_THEME_JSON_PATH))
