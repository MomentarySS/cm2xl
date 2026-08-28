"""
cm2xl — 统一主题常量
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
    # 界面色（暖灰纸感：降低纯白刺激，拉大层级对比）
    "muted": "#5B6775",
    "card_bg": "#F0EEE6",
    "card_border": "#B8BFC8",
    "page_bg": "#E4E2DA",
    "entry_bg": "#FAFAF8",
    "entry_border": "#9CA8B6",
    "hint_bg": "#D9EDE8",
    # 文字
    "text": "#1A2332",
    "text_muted": "#4B5563",
}

TOOLBOX_THEME_JSON_PATH = Path(__file__).parent / "theme.json"


def _build_theme_json(dest: Path | None = None) -> None:
    """
    生成 CustomTkinter 自定义主题 JSON，写入 dest 或默认 theme.json。
    使用青绿主色，基于 green 主题完整字段表，避免默认紫/蓝/绿切换时的颜色跳变。
    完整字段参考：customtkinter/assets/themes/green.json

    配色策略：
    - 浅色：暖灰纸背景 + 浅米卡片 + 清晰边框（降低眩光、提高控件可辨度）
    - 深色：用低饱和深石板，避免纯黑冷感
    - CTkLabel fg_color 设为 transparent，避免文字后出现灰色色块
    """
    accent = TOOLBOX_THEME["accent"]
    accent_h = TOOLBOX_THEME["accent_hover"]
    primary = TOOLBOX_THEME["primary"]
    page_bg_l = TOOLBOX_THEME["page_bg"]
    page_bg_d = "#1A1F2B"           # 深石板（非纯黑）
    card_bg_l = TOOLBOX_THEME["card_bg"]
    card_bg_d = "#252B3A"           # 深石板卡片
    card_bd = TOOLBOX_THEME["card_border"]
    card_bd_d = "#374151"
    entry_bg_l = TOOLBOX_THEME["entry_bg"]
    entry_bd_l = TOOLBOX_THEME["entry_border"]
    text_l = TOOLBOX_THEME["text"]
    text_d = "#E8E6E1"              # 暖白文字（非冷蓝白）
    muted = TOOLBOX_THEME["text_muted"]
    checkbox_bd_l = "#7B8794"

    theme = {
        "CTk": {"fg_color": [page_bg_l, page_bg_d]},
        "CTkToplevel": {"fg_color": [card_bg_l, card_bg_d]},
        "CTkFrame": {
            "corner_radius": 8,
            "border_width": 0,
            "border_color": [card_bd, card_bd_d],
            "fg_color": [card_bg_l, card_bg_d],
            "top_fg_color": [page_bg_l, page_bg_d],
        },
        "CTkButton": {
            "corner_radius": 6,
            "border_width": 0,
            "border_color": [accent, accent_h],
            "fg_color": [accent, accent],
            "hover_color": [accent_h, "#0D9488"],
            "pressed_color": [primary, primary],
            "text_color": ["#FFFFFF", "#F1F5F9"],
            "text_color_disabled": [muted, "#64748B"],
        },
        "CTkLabel": {
            "corner_radius": 0,
            "border_width": 0,
            # 默认透明 —— 否则 CustomTkinter 会画一个 page_bg 色矩形在文字后面，
            # 浅色模式下会出现一块灰色色块。
            "fg_color": "transparent",
            "border_color": [card_bd, card_bd_d],
            "text_color": [text_l, text_d],
        },
        "CTkEntry": {
            "corner_radius": 6,
            "border_width": 1,
            "border_color": [entry_bd_l, card_bd_d],
            "fg_color": [entry_bg_l, page_bg_d],
            "text_color": [text_l, text_d],
            "placeholder_text_color": [muted, "#64748B"],
        },
        "CTkOptionMenu": {
            "corner_radius": 6,
            "fg_color": [accent, accent],
            "button_color": [primary, primary],
            "button_hover_color": [accent_h, "#0D9488"],
            "text_color": ["#FFFFFF", "#F1F5F9"],
            "text_color_disabled": [muted, "#64748B"],
        },
        "CTkProgressBar": {
            "corner_radius": 6,
            "border_width": 0,
            "border_color": [card_bd, card_bd_d],
            "fg_color": [page_bg_l, page_bg_d],
            "progress_color": [accent, accent],
        },
        "CTkSwitch": {
            "corner_radius": 12,
            "border_width": 0,
            "button_length": 0,
            "fg_color": [TOOLBOX_THEME["muted"], "#475569"],
            "progress_color": [accent, accent],
            "button_color": ["#FFFFFF", "#E2E8F0"],
            "button_hover_color": ["#F1F5F9", "#CBD5E1"],
            "text_color": [text_l, text_d],
            "text_color_disabled": [muted, "#64748B"],
        },
        "CTkSlider": {
            "corner_radius": 6,
            "button_corner_radius": 6,
            "border_width": 0,
            "button_length": 0,
            "fg_color": [page_bg_l, page_bg_d],
            "progress_color": [accent, accent],
            "button_color": [accent, accent],
            "button_hover_color": [accent_h, "#0D9488"],
        },
        "CTkComboBox": {
            "corner_radius": 6,
            "border_width": 1,
            "border_color": [card_bd, card_bd_d],
            "fg_color": [page_bg_l, page_bg_d],
            "button_color": [primary, primary],
            "button_hover_color": [accent_h, "#0D9488"],
            "text_color": [text_l, text_d],
            "text_color_disabled": [muted, "#64748B"],
        },
        "CTkCheckBox": {
            "corner_radius": 6,
            "border_width": 1,
            # fg_color = 勾选后方框填充色（须与白色勾形成对比，不能用浅底）
            "border_color": [checkbox_bd_l, card_bd_d],
            "fg_color": [accent, accent],
            "hover_color": [accent_h, "#0D9488"],
            "checkmark_color": ["#FFFFFF", "#F1F5F9"],
            "text_color": [text_l, text_d],
            "text_color_disabled": [muted, "#64748B"],
        },
        "CTkRadioButton": {
            "corner_radius": 6,
            "border_width_checked": 3,
            "border_width_unchecked": 3,
            "fg_color": [page_bg_l, page_bg_d],
            "border_color": [accent, accent],
            "hover_color": [accent_h, "#0D9488"],
            "text_color": [text_l, text_d],
            "text_color_disabled": [muted, "#64748B"],
        },
        "CTkSegmentedButton": {
            "corner_radius": 6,
            "border_width": 0,
            "fg_color": [page_bg_l, page_bg_d],
            "selected_color": [accent, accent],
            "selected_hover_color": [accent_h, "#0D9488"],
            "unselected_color": [card_bg_l, card_bg_d],
            "unselected_hover_color": [TOOLBOX_THEME["card_border"], "#475569"],
            "text_color": [text_l, text_d],
            "text_color_disabled": [muted, "#64748B"],
        },
        "CTkTextbox": {
            "corner_radius": 6,
            "border_width": 0,
            "border_color": [card_bd, card_bd_d],
            "fg_color": [card_bg_l, card_bg_d],
            "text_color": [text_l, text_d],
            "scrollbar_button_color": [primary, primary],
            "scrollbar_button_hover_color": [accent_h, "#0D9488"],
        },
        "CTkScrollableFrame": {
            "label_fg_color": [accent, accent],
        },
        "CTkScrollbar": {
            "corner_radius": 6,
            "border_spacing": 6,
            "fg_color": [page_bg_l, page_bg_d],
            "button_color": [card_bd, card_bd_d],
            "button_hover_color": [accent_h, "#0D9488"],
        },
        "DropdownMenu": {
            "fg_color": [card_bg_l, card_bg_d],
            "hover_color": [accent_h, "#0D9488"],
            "text_color": [text_l, text_d],
        },
        "CTkFont": {
            "macOS": {"family": "SF Pro", "size": 13, "weight": "normal"},
            "Windows": {"family": "Segoe UI", "size": 13, "weight": "normal"},
            "Linux": {"family": "Ubuntu", "size": 13, "weight": "normal"},
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
