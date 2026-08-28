"""
cm2xl — 应用图标统一入口
窗口标题栏图标 + 界面内 Logo 均从这里加载。
"""

from __future__ import annotations

import logging
from typing import Any

import customtkinter as ctk

from utils.paths import paths

logger = logging.getLogger(__name__)

_LOGO_CACHE: dict[tuple[int, int], ctk.CTkImage] = {}


def icon_ico_path():
    """返回 cm2xl.ico 路径（开发 / 打包均可用）。"""
    for candidate in (
        paths.bundle / "cm2xl.ico",
        paths.root / "cm2xl.ico",
    ):
        if candidate.is_file():
            return candidate
    return None


def logo_png_path():
    """返回界面内 Logo PNG 路径；缺失时从 ico 生成缓存。"""
    for candidate in (
        paths.bundle / "assets" / "app_logo.png",
        paths.root / "assets" / "app_logo.png",
    ):
        if candidate.is_file():
            return candidate

    ico = icon_ico_path()
    if ico is None:
        return None

    try:
        from PIL import Image

        out = paths.cache_dir / "app_logo.png"
        if not out.exists() or out.stat().st_mtime < ico.stat().st_mtime:
            img = Image.open(ico)
            img.save(out, format="PNG")
        return out
    except Exception as e:
        logger.warning("无法从 ico 生成 logo png: %s", e)
        return None


def apply_window_icon(window: Any) -> None:
    """为 CTk / CTkToplevel / Tk 窗口设置标题栏图标。"""
    ico = icon_ico_path()
    if ico is None:
        return
    try:
        window.iconbitmap(default=str(ico))
    except Exception:
        try:
            window.tk.call("wm", "iconbitmap", window._w, str(ico))
        except Exception as e:
            logger.debug("设置窗口图标失败: %s", e)


def get_logo_image(size: int = 64) -> ctk.CTkImage | None:
    """获取指定尺寸的 Logo（Splash / 关于 / 顶栏复用）。"""
    key = (size, size)
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]

    png = logo_png_path()
    if png is None:
        return None

    img = ctk.CTkImage(light_image=str(png), dark_image=str(png), size=key)
    _LOGO_CACHE[key] = img
    return img
