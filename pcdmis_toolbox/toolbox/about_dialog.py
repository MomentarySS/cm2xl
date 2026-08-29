"""
cm2xl — 关于弹窗
显示应用名 / 版本 / 识别预览颜色说明 / 配置与日志路径 / 版权信息。
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

_FONT = "Microsoft YaHei"
_FONT_PATH = "Consolas"
_FS_HEAD = 22
_FS_VERSION = 14
_FS_DESC = 13
_FS_SECTION = 13
_FS_BODY = 12
_FS_HINT = 11
_FS_PATH = 12
_FS_BTN = 12
_FS_COPYRIGHT = 11

# 与 modules/cmm_filler/gui.py 预览页颜色保持一致
_PREVIEW_LEGEND = (
    ("#FFF3E0", "#e6a23c", "橙色行 + ⚠", "OCR 识别置信度偏低，请对照 PDF 核对实测值；不等于不合格。"),
    ("#F5EEF8", "#7D3C98", "紫色行 + ⚡", "多个子编号（如 FAI_1-1、FAI_1-2）对应模板同一序号，需选择填入哪一项。"),
    (TOOLBOX_THEME["bad"], TOOLBOX_THEME["bad"], "红色 NG 标签", "实测值超出公差范围，判定为不合格。"),
    ("transparent", ("gray15", "gray85"), "普通行", "识别置信度正常；若无 NG 标签，表示当前数值在公差内。"),
)


class AboutDialog:
    """
    关于弹窗：版本信息 + 预览颜色说明 + 用户数据/日志路径。

    模式：模态 CTkToplevel，点 X 或"关闭"按钮销毁。
    """

    def __init__(self, parent):
        self._wrap_labels: list[ctk.CTkLabel] = []
        self._win = ctk.CTkToplevel(parent)
        self._win.title("关于")
        self._win.geometry("560x700")
        self._win.minsize(520, 580)
        self._win.resizable(True, True)
        self._win.transient(parent)
        apply_window_icon(self._win)
        self._win.after(120, self._win.grab_set)

        self._build()
        self._win.bind("<Configure>", self._on_configure, add="+")
        self._win.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        win = self._win
        text_color = [TOOLBOX_THEME["text"], "#E8E6E1"]
        muted = [TOOLBOX_THEME["text_muted"], "#9CA3AF"]
        accent = [TOOLBOX_THEME["accent"], "#0F766E"]
        accent_h = [TOOLBOX_THEME["accent_hover"], "#14B8A6"]

        header = ctk.CTkFrame(win, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack()

        self._logo = get_logo_image(56)
        if self._logo is not None:
            ctk.CTkLabel(
                title_frame, text="", image=self._logo, fg_color="transparent",
            ).pack(pady=(0, 6))

        ctk.CTkLabel(
            title_frame, text=APP_TITLE,
            font=ctk.CTkFont(family=_FONT, size=_FS_HEAD, weight="bold"),
            text_color=text_color,
        ).pack()

        ctk.CTkLabel(
            header, text=f"版本 {APP_VERSION}",
            font=ctk.CTkFont(family=_FONT, size=_FS_VERSION),
            text_color=text_color,
        ).pack(pady=(2, 0))

        self._add_wrapped_label(
            header, APP_DESCRIPTION,
            font=ctk.CTkFont(family=_FONT, size=_FS_DESC),
            text_color=muted, justify="center",
        ).pack(pady=(8, 0))

        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        self._section_title(body, "CMM 识别预览 · 颜色说明", text_color)
        self._add_wrapped_label(
            body,
            "在「处理前预览识别结果」窗口中，各行颜色含义如下：",
            font=ctk.CTkFont(family=_FONT, size=_FS_BODY),
            text_color=muted, anchor="w", justify="left",
        ).pack(fill="x", padx=4, pady=(0, 6))

        for bg, label_color, title, desc in _PREVIEW_LEGEND:
            self._legend_row(body, bg, label_color, title, desc, text_color, muted)

        self._add_wrapped_label(
            body,
            "提示：取消勾选可剔除该行；实测值可直接修改；确认前请对照 PDF 原报告。",
            font=ctk.CTkFont(family=_FONT, size=_FS_HINT),
            text_color=muted, anchor="w", justify="left",
        ).pack(fill="x", padx=4, pady=(4, 10))

        ctk.CTkFrame(body, height=1, fg_color=muted).pack(fill="x", padx=4, pady=8)

        self._section_title(body, "用户数据与日志", text_color)
        self._add_wrapped_label(
            body, paths.user_data_location_hint(),
            font=ctk.CTkFont(family=_FONT, size=_FS_BODY),
            text_color=muted, justify="left", anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 8))

        path_items = [("程序目录", paths.root)]
        if paths.is_frozen():
            path_items.append(("用户数据根目录", paths.data_dir))
        path_items.extend([
            ("配置", paths.config_dir),
            ("日志", paths.log_dir),
            ("日志文件", "toolbox.log / CMMFiller.log / pc_to_excel.log"),
            ("OCR 缓存", paths.cache_dir),
            ("用户文档", paths.docs_dir),
        ])
        for label, value in path_items:
            self._path_row(body, label, value, text_color, muted)

        footer = ctk.CTkFrame(win, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 12))

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            btn_row, text="复制日志路径", width=120, height=32,
            font=ctk.CTkFont(family=_FONT, size=_FS_BTN),
            fg_color=accent, hover_color=accent_h, text_color="white",
            command=self._copy_log_dir,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="打开日志文件夹", width=120, height=32,
            font=ctk.CTkFont(family=_FONT, size=_FS_BTN),
            fg_color="transparent", border_width=1,
            border_color=muted, text_color=text_color,
            command=self._open_log_dir,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="关闭", width=96, height=32,
            font=ctk.CTkFont(family=_FONT, size=_FS_BTN),
            fg_color=accent, hover_color=accent_h, text_color="white",
            command=self._close,
        ).pack(side="right")

        ctk.CTkLabel(
            footer, text=COPYRIGHT,
            font=ctk.CTkFont(family=_FONT, size=_FS_COPYRIGHT),
            text_color=muted,
        ).pack(anchor="w")

        self._update_wraplengths()

    def _add_wrapped_label(self, parent, text: str, **kwargs) -> ctk.CTkLabel:
        label = ctk.CTkLabel(parent, text=text, wraplength=480, **kwargs)
        self._wrap_labels.append(label)
        return label

    def _on_configure(self, _event=None) -> None:
        if self._win.winfo_exists():
            self._update_wraplengths()

    def _update_wraplengths(self) -> None:
        width = max(self._win.winfo_width() - 72, 360)
        for label in self._wrap_labels:
            try:
                label.configure(wraplength=width)
            except Exception:
                pass

    @staticmethod
    def _section_title(parent, title: str, text_color) -> None:
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(family=_FONT, size=_FS_SECTION, weight="bold"),
            text_color=text_color, anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 4))

    def _path_row(self, parent, label: str, value, text_color, muted) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=4, pady=(0, 6))
        ctk.CTkLabel(
            block, text=label,
            font=ctk.CTkFont(family=_FONT, size=_FS_BODY, weight="bold"),
            text_color=text_color, anchor="w",
        ).pack(fill="x")
        self._add_wrapped_label(
            block, str(value),
            font=ctk.CTkFont(family=_FONT_PATH, size=_FS_PATH),
            text_color=muted, anchor="w", justify="left",
        ).pack(fill="x", padx=(8, 0))

    def _legend_row(self, parent, bg, label_color, title, desc, text_color, muted) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=3)

        swatch_bg = bg if bg != "transparent" else [TOOLBOX_THEME["card_bg"], "#252B3A"]
        swatch = ctk.CTkFrame(row, width=32, height=32, corner_radius=6, fg_color=swatch_bg)
        swatch.pack(side="left", padx=(0, 10))
        swatch.pack_propagate(False)

        text_frame = ctk.CTkFrame(row, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True)

        title_color = label_color if not isinstance(label_color, tuple) else label_color
        ctk.CTkLabel(
            text_frame, text=title,
            font=ctk.CTkFont(family=_FONT, size=_FS_BODY, weight="bold"),
            text_color=title_color, anchor="w",
        ).pack(fill="x")
        self._add_wrapped_label(
            text_frame, desc,
            font=ctk.CTkFont(family=_FONT, size=_FS_HINT),
            text_color=muted, anchor="w", justify="left",
        ).pack(fill="x")

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
            messagebox.showerror(
                "无法打开",
                f"请手动在资源管理器中打开：\n{log_dir}\n\n{exc}",
                parent=self._win,
            )

    def _close(self) -> None:
        try:
            self._win.grab_release()
        except Exception:
            pass
        self._win.destroy()
