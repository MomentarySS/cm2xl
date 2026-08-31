"""
cm2xl — 壳层共享 UI 组件与主题配对色。

对话框、顶栏、导航、启动画面等 toolbox 层复用，避免在各文件重复硬编码深色值。
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from utils.theme import TOOLBOX_THEME

UI_FONT = "Microsoft YaHei"
UI_FONT_MONO = "Consolas"


def theme_pair(light_key: str, dark_key: str) -> list[str]:
    """返回 CustomTkinter 可用的 [浅色, 深色] 配对色。"""
    return [TOOLBOX_THEME[light_key], TOOLBOX_THEME[dark_key]]


def text_color() -> list[str]:
    return theme_pair("text", "text_dark")


def muted_color() -> list[str]:
    return theme_pair("text_muted", "text_muted_dark")


def accent_color() -> list[str]:
    accent = TOOLBOX_THEME["accent"]
    return [accent, accent]


def accent_hover_color() -> list[str]:
    return theme_pair("accent_hover", "accent_pressed_dark")


def card_bg_color() -> list[str]:
    return theme_pair("card_bg", "card_bg_dark")


def page_bg_color() -> list[str]:
    return theme_pair("page_bg", "page_bg_dark")


def card_border_color() -> list[str]:
    return theme_pair("card_border", "card_border_dark")


def on_accent_color() -> list[str]:
    return theme_pair("on_accent", "on_accent_dark")


def ui_font(size: int, weight: str = "normal", family: str = UI_FONT) -> ctk.CTkFont:
    return ctk.CTkFont(family=family, size=size, weight=weight)


def section_header(parent: Any, title: str, *, label_color: list[str] | None = None) -> ctk.CTkFrame:
    """分组标题：加粗标签 + 细分割线。"""
    bar = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        bar,
        text=title,
        font=ui_font(12, "bold"),
        text_color=label_color or text_color(),
    ).pack(side="left", padx=(4, 0))
    ctk.CTkFrame(bar, height=1, fg_color=card_border_color()).pack(
        side="left", fill="x", expand=True, padx=(8, 0),
    )
    return bar


def primary_button_kwargs() -> dict[str, Any]:
    return {
        "fg_color": accent_color(),
        "hover_color": accent_hover_color(),
        "text_color": on_accent_color(),
    }


def secondary_button_kwargs() -> dict[str, Any]:
    return {
        "fg_color": "transparent",
        "border_width": 1,
        "border_color": muted_color(),
        "text_color": text_color(),
    }


def setup_modal(win: ctk.CTkToplevel, parent: Any) -> None:
    """标准模态对话框：transient + 延迟 grab_set。"""
    win.transient(parent)
    win.after(120, win.grab_set)


def close_modal(win: ctk.CTkToplevel) -> None:
    try:
        win.grab_release()
    except Exception:
        pass
    win.destroy()
