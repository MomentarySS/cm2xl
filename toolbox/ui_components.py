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


def sidebar_bg_color() -> list[str]:
    return theme_pair("sidebar_bg", "sidebar_bg_dark")


def page_bg_color() -> list[str]:
    return theme_pair("page_bg", "page_bg_dark")


def card_border_color() -> list[str]:
    return theme_pair("card_border", "card_border_dark")


def nav_hover_color() -> list[str]:
    """侧边栏按钮 hover 底色：透明叠加，不抢眼。"""
    return [TOOLBOX_THEME["hint_bg"], "#333333"]


def on_accent_color() -> list[str]:
    return theme_pair("on_accent", "on_accent_dark")


def ui_font(size: int, weight: str = "normal", family: str = UI_FONT) -> ctk.CTkFont:
    return ctk.CTkFont(family=family, size=size, weight=weight)


def section_header(parent: Any, title: str, *, label_color: list[str] | None = None) -> ctk.CTkFrame:
    """分组标题：纯文字小标签，靠留白分隔。"""
    bar = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        bar,
        text=title,
        font=ui_font(11, "bold"),
        text_color=label_color or muted_color(),
    ).pack(side="left", padx=(4, 0))
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


def hide_modal(win: ctk.CTkToplevel) -> None:
    """关闭模态对话框但保留实例，供下次快速重开。

    close_modal() 会 destroy 窗口；而 About/Settings 每次重开都要重建全部
    widget（实测 About 60 个 ≈82ms、Settings 28 个 ≈71ms，其中 CTkToplevel
    本身只占 4ms，其余全是 CustomTkinter widget 构造）。这里改为 withdraw，
    下次 reopen_modal() 即可，重开成本接近 0。
    """
    try:
        win.grab_release()
    except Exception:
        pass
    win.withdraw()


def _regrab_modal(win: ctk.CTkToplevel) -> None:
    """延迟补回模态 grab（win 可能已在 120ms 内被销毁）。"""
    try:
        if win.winfo_exists():
            win.grab_set()
    except Exception:
        pass


def reopen_modal(win: ctk.CTkToplevel) -> bool:
    """重新显示被 hide_modal() 隐藏的模态窗口。

    必须补一次 grab：hide_modal() 做过 grab_release()，直接 deiconify 会让
    背后主窗口仍可点击交互，丧失模态语义。延迟 120ms 与 setup_modal() 一致
    （等窗口映射稳定再抢，避免抢早导致事件丢）。
    """
    try:
        if not win.winfo_exists():
            return False
        win.deiconify()
        win.lift()
        win.focus_set()
        win.after(120, _regrab_modal, win)
        return True
    except Exception:
        return False
