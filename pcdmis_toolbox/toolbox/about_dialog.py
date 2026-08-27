"""
PCDMIS Toolbox 2.0 — 关于弹窗
显示应用名 / 版本 / 配置与日志路径 / 版权信息。
"""

import customtkinter as ctk

from toolbox.app_meta import APP_TITLE, APP_VERSION
from utils.paths import paths
from utils.theme import TOOLBOX_THEME


APP_DESCRIPTION = "整合 CMMFiller（OCR 报告填充）+ pc_to_excel（PCDMIS 数据导出）"
COPYRIGHT = "© 2026 PCDMIS Toolbox"


class AboutDialog:
    """
    关于弹窗：版本信息 + 配置/日志路径。

    模式：模态 CTkToplevel，点 X 或"关闭"按钮销毁。
    """

    def __init__(self, parent):
        self._win = ctk.CTkToplevel(parent)
        self._win.title("关于")
        self._win.geometry("460x340")
        self._win.resizable(False, False)
        self._win.transient(parent)
        # 延迟 grab_set（等窗口可见后再设焦点，避免部分 Windows 平台丢焦点）
        self._win.after(120, self._win.grab_set)

        self._build()
        self._win.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        win = self._win
        text_color = [TOOLBOX_THEME["text"], "#E8E6E1"]
        muted = [TOOLBOX_THEME["text_muted"], "#9CA3AF"]

        # 应用名（粗体大字号）
        ctk.CTkLabel(
            win, text=f"📐 {APP_TITLE}",
            font=ctk.CTkFont(family="Microsoft YaHei", size=22, weight="bold"),
            text_color=text_color,
        ).pack(pady=(28, 4))

        # 版本
        ctk.CTkLabel(
            win, text=f"版本 {APP_VERSION}",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=text_color,
        ).pack()

        # 简介
        ctk.CTkLabel(
            win, text=APP_DESCRIPTION,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color=muted, wraplength=400, justify="center",
        ).pack(pady=(12, 8))

        # 分隔线
        ctk.CTkFrame(win, height=1, fg_color=muted).pack(fill="x", padx=30, pady=8)

        # 配置 / 日志路径（左对齐小字号）
        info = (
            f"配置目录:\n{paths.config_dir}\n\n"
            f"日志目录:\n{paths.log_dir}"
        )
        ctk.CTkLabel(
            win, text=info,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=muted, justify="left", anchor="w",
        ).pack(padx=30, fill="x")

        # 版权
        ctk.CTkLabel(
            win, text=COPYRIGHT,
            font=ctk.CTkFont(family="Microsoft YaHei", size=10),
            text_color=muted,
        ).pack(side="bottom", pady=(0, 8))

        # 关闭按钮
        ctk.CTkButton(
            win, text="关闭", width=100, height=30,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            fg_color=[TOOLBOX_THEME["accent"], "#0F766E"],
            hover_color=[TOOLBOX_THEME["accent_hover"], "#14B8A6"],
            text_color="white",
            command=self._close,
        ).pack(side="bottom", pady=(0, 12))

    def _close(self) -> None:
        try:
            self._win.grab_release()
        except Exception:
            pass
        self._win.destroy()