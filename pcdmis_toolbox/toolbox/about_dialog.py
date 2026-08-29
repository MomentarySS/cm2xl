"""
cm2xl — 关于弹窗
显示应用名 / 版本 / 配置与日志路径 / 版权信息。
"""

import os
from tkinter import messagebox

import customtkinter as ctk

from toolbox.app_meta import APP_TITLE, APP_VERSION
from utils.app_icon import apply_window_icon, get_logo_image
from utils.paths import paths
from utils.theme import TOOLBOX_THEME


APP_DESCRIPTION = "整合 CMMFiller（OCR 报告填充）+ pc_to_excel（PCDMIS 数据导出）"
COPYRIGHT = "© 2026 cm2xl"


class AboutDialog:
    """
    关于弹窗：版本信息 + 用户数据/日志路径说明。

    模式：模态 CTkToplevel，点 X 或"关闭"按钮销毁。
    """

    def __init__(self, parent):
        self._win = ctk.CTkToplevel(parent)
        self._win.title("关于")
        self._win.geometry("500x500")
        self._win.resizable(False, False)
        self._win.transient(parent)
        apply_window_icon(self._win)
        self._win.after(120, self._win.grab_set)

        self._build()
        self._win.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        win = self._win
        text_color = [TOOLBOX_THEME["text"], "#E8E6E1"]
        muted = [TOOLBOX_THEME["text_muted"], "#9CA3AF"]
        accent = [TOOLBOX_THEME["accent"], "#0F766E"]
        accent_h = [TOOLBOX_THEME["accent_hover"], "#14B8A6"]

        title_frame = ctk.CTkFrame(win, fg_color="transparent")
        title_frame.pack(pady=(20, 4))

        self._logo = get_logo_image(64)
        if self._logo is not None:
            ctk.CTkLabel(
                title_frame, text="", image=self._logo, fg_color="transparent",
            ).pack(pady=(0, 8))

        ctk.CTkLabel(
            title_frame, text=APP_TITLE,
            font=ctk.CTkFont(family="Microsoft YaHei", size=22, weight="bold"),
            text_color=text_color,
        ).pack()

        ctk.CTkLabel(
            win, text=f"版本 {APP_VERSION}",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=text_color,
        ).pack()

        ctk.CTkLabel(
            win, text=APP_DESCRIPTION,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color=muted, wraplength=440, justify="center",
        ).pack(pady=(10, 6))

        ctk.CTkFrame(win, height=1, fg_color=muted).pack(fill="x", padx=28, pady=6)

        ctk.CTkLabel(
            win, text="用户数据与日志",
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            text_color=text_color, anchor="w",
        ).pack(fill="x", padx=28, pady=(0, 4))

        ctk.CTkLabel(
            win, text=paths.user_data_location_hint(),
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            text_color=muted, wraplength=440, justify="left", anchor="w",
        ).pack(fill="x", padx=28, pady=(0, 6))

        install_line = f"程序目录:\n{paths.root}"
        if paths.is_frozen():
            user_block = (
                f"用户数据根目录:\n{paths.data_dir}\n\n"
                f"配置:\n{paths.config_dir}\n\n"
                f"日志:\n{paths.log_dir}\n"
                f"  · toolbox.log / CMMFiller.log / pc_to_excel.log\n\n"
                f"OCR 缓存:\n{paths.cache_dir}\n\n"
                f"用户文档:\n{paths.docs_dir}"
            )
        else:
            user_block = (
                f"配置:\n{paths.config_dir}\n\n"
                f"日志:\n{paths.log_dir}\n\n"
                f"OCR 缓存:\n{paths.cache_dir}\n\n"
                f"用户文档:\n{paths.docs_dir}"
            )

        ctk.CTkLabel(
            win,
            text=install_line + "\n\n" + user_block,
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=muted, justify="left", anchor="w",
        ).pack(fill="x", padx=28)

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=28, pady=(8, 4))
        ctk.CTkButton(
            btn_row, text="复制日志路径", width=110, height=28,
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            fg_color=accent, hover_color=accent_h, text_color="white",
            command=self._copy_log_dir,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="打开日志文件夹", width=110, height=28,
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            fg_color="transparent", border_width=1,
            border_color=muted, text_color=text_color,
            command=self._open_log_dir,
        ).pack(side="left")

        ctk.CTkLabel(
            win, text=COPYRIGHT,
            font=ctk.CTkFont(family="Microsoft YaHei", size=10),
            text_color=muted,
        ).pack(side="bottom", pady=(0, 6))

        ctk.CTkButton(
            win, text="关闭", width=100, height=30,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            fg_color=accent, hover_color=accent_h, text_color="white",
            command=self._close,
        ).pack(side="bottom", pady=(0, 12))

    def _copy_log_dir(self) -> None:
        self._win.clipboard_clear()
        self._win.clipboard_append(str(paths.log_dir))
        self._win.update_idletasks()
        messagebox.showinfo(
            "已复制",
            f"日志文件夹路径已复制到剪贴板：\n{paths.log_dir}",
            parent=self._win,
        )

    def _open_log_dir(self) -> None:
        log_dir = paths.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(log_dir)  # noqa: S606 — Windows 专用工具，项目仅支持 Windows
        except OSError as exc:
            messagebox.showerror("无法打开", f"请手动在资源管理器中打开：\n{log_dir}\n\n{exc}", parent=self._win)

    def _close(self) -> None:
        try:
            self._win.grab_release()
        except Exception:
            pass
        self._win.destroy()
