"""
cm2xl — 设置弹窗

布局：
┌─ 设置 ─────────────────────────────────────┐
│  [外观]                                     │
│    ○ 浅色  ○ 深色  ○ 系统                  │
│                                            │
│  [OCR 模型]                                 │
│    路径: [_______________] [浏览] [重置]   │
│    当前状态: ✓ 内置 / ⚠ 自定义（重启生效）│
│                                            │
│  [日志]                                     │
│    级别: ○ DEBUG  ● INFO  ○ WARNING       │
│                                            │
│  [兼容性]                                   │
│    [导出旧版配置] (从顶栏移入)             │
│                                            │
│         [恢复默认]  [取消]  [保存]        │
└────────────────────────────────────────────┘

保存行为：
- 外观模式 + 日志级别：运行时立即生效
- OCR 模型目录：仅写入 settings.json，下次启动 OCR 时生效
"""

import logging
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from utils.paths import paths
from utils.settings import (
    TOOLBOX_DEFAULT_SETTINGS,
    export_legacy_settings,
    load_and_migrate_settings,
    load_toolbox_settings,
    save_toolbox_settings,
)
from utils.theme import TOOLBOX_THEME

logger = logging.getLogger(__name__)


class SettingsDialog:
    """
    设置弹窗：4 个分组（外观 / OCR 模型 / 日志 / 兼容性）+ 底部按钮。
    模态 CTkToplevel，点 X 或"取消"放弃修改。
    """

    APPEARANCE_OPTIONS = [("浅色", "light"), ("深色", "dark"), ("系统", "system")]
    OCR_TIER_OPTIONS = [("高精度(Server)", "server"), ("轻量(Mobile)", "mobile")]
    LOG_LEVEL_OPTIONS = ["DEBUG", "INFO", "WARNING"]

    def __init__(self, parent, shell):
        self._shell = shell
        self._win = ctk.CTkToplevel(parent)
        self._win.title("设置")
        self._win.geometry("640x500")
        self._win.minsize(560, 460)
        self._win.transient(parent)
        self._win.after(120, self._win.grab_set)

        # 工作副本（未保存不写盘）
        self._working = load_toolbox_settings()

        self._build()
        self._win.protocol("WM_DELETE_WINDOW", self._cancel)

    # ── 构建 ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        text_color = [TOOLBOX_THEME["text"], "#E8E6E1"]
        muted = [TOOLBOX_THEME["text_muted"], "#9CA3AF"]
        accent = [TOOLBOX_THEME["accent"], "#0F766E"]
        accent_h = [TOOLBOX_THEME["accent_hover"], "#14B8A6"]

        # 滚动容器（如设置项增多可启用 ScrollableFrame）
        body = ctk.CTkFrame(self._win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        # 1. 外观分组
        self._build_section(body, "外观", text_color).pack(fill="x", pady=(0, 10))
        self._appearance_var = ctk.StringVar(value=self._label_for(self.APPEARANCE_OPTIONS, self._working.get("appearance_mode", "system")))
        ctk.CTkSegmentedButton(
            body, values=[label for label, _ in self.APPEARANCE_OPTIONS],
            variable=self._appearance_var, height=32,
            selected_color=accent, selected_hover_color=accent_h,
        ).pack(fill="x", padx=4)

        # 2. OCR 模型分组
        self._build_section(body, "OCR 模型", text_color).pack(fill="x", pady=(10, 6))
        # 精度选择
        self._ocr_tier_var = ctk.StringVar(
            value=self._label_for(self.OCR_TIER_OPTIONS, self._working.get("ocr_model_tier", "server"))
        )
        ctk.CTkSegmentedButton(
            body, values=[label for label, _ in self.OCR_TIER_OPTIONS],
            variable=self._ocr_tier_var, height=32,
            selected_color=accent, selected_hover_color=accent_h,
        ).pack(fill="x", padx=4)
        ctk.CTkLabel(
            body, text="高精度(Server)：质量最佳，适合正式报告；轻量(Mobile)：速度更快，精度略低",
            font=ctk.CTkFont(family="Microsoft YaHei", size=10),
            text_color=muted,
        ).pack(anchor="w", padx=4, pady=(2, 6))
        # 路径选择
        ocr_row = ctk.CTkFrame(body, fg_color="transparent")
        ocr_row.pack(fill="x", padx=4, pady=(0, 0))
        self._ocr_var = ctk.StringVar(value=self._working.get("ocr_model_dir", ""))
        ctk.CTkEntry(ocr_row, textvariable=self._ocr_var, height=30, placeholder_text="留空使用内置模型").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(ocr_row, text="浏览", width=70, height=30, command=self._browse_ocr_dir).pack(side="left", padx=2)
        ctk.CTkButton(ocr_row, text="重置", width=70, height=30, command=self._reset_ocr_dir).pack(side="left", padx=(2, 0))
        self._ocr_hint = ctk.CTkLabel(
            body, text="",
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            text_color=muted,
        )
        self._ocr_hint.pack(anchor="w", padx=4, pady=(4, 0))
        self._ocr_var.trace_add("write", lambda *_: self._refresh_ocr_hint())
        self._ocr_tier_var.trace_add("write", lambda *_: self._refresh_ocr_hint())
        self._refresh_ocr_hint()

        # 3. 日志分组
        self._build_section(body, "日志", text_color).pack(fill="x", pady=(10, 6))
        self._log_level_var = ctk.StringVar(value=self._working.get("log_level", "INFO"))
        ctk.CTkSegmentedButton(
            body, values=self.LOG_LEVEL_OPTIONS,
            variable=self._log_level_var, height=32,
            selected_color=accent, selected_hover_color=accent_h,
        ).pack(fill="x", padx=4)

        # 4. 兼容性分组
        self._build_section(body, "兼容性", text_color).pack(fill="x", pady=(10, 6))
        ctk.CTkButton(
            body, text="导出旧版配置 (1.x 格式)", height=32,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            fg_color=accent, hover_color=accent_h, text_color="white",
            command=self._export_legacy_settings,
        ).pack(fill="x", padx=4)
        ctk.CTkLabel(
            body, text="导出 cmm_filler + pc_to_excel 配置为 1.x 格式，给旧工具使用",
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            text_color=muted,
        ).pack(anchor="w", padx=4, pady=(4, 0))

        # 底部按钮
        btn_bar = ctk.CTkFrame(self._win, fg_color="transparent")
        btn_bar.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            btn_bar, text="恢复默认", width=100, height=32,
            fg_color="transparent", border_width=1,
            border_color=muted, text_color=text_color,
            command=self._restore_defaults,
        ).pack(side="left")
        ctk.CTkButton(
            btn_bar, text="取消", width=100, height=32,
            fg_color="transparent", border_width=1,
            border_color=muted, text_color=text_color,
            command=self._cancel,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            btn_bar, text="保存", width=100, height=32,
            fg_color=accent, hover_color=accent_h, text_color="white",
            command=self._save,
        ).pack(side="right")

    @staticmethod
    def _build_section(parent, title: str, text_color):
        """分组标题（用细线 + Label 模拟 group header）。"""
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(
            bar, text=title,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            text_color=text_color,
        ).pack(side="left", padx=(4, 0))
        ctk.CTkFrame(bar, height=1, fg_color=[TOOLBOX_THEME["card_border"], "#374151"]).pack(side="left", fill="x", expand=True, padx=(8, 0))
        return bar

    @staticmethod
    def _label_for(options, value):
        for label, v in options:
            if v == value:
                return label
        return options[-1][0]

    def _refresh_ocr_hint(self) -> None:
        """根据 OCR 路径和精度显示当前状态（内置 / 自定义 / 无效）。"""
        tier = self._value_for(self.OCR_TIER_OPTIONS, self._ocr_tier_var.get())
        tier_label = next((l for l, v in self.OCR_TIER_OPTIONS if v == tier), "高精度")
        path = self._ocr_var.get().strip()

        if not path:
            base_note = "✓ 使用内置 OCR 模型"
        elif Path(path).exists() and any(Path(path).rglob("inference.pdmodel")):
            base_note = f"✓ 自定义路径有效"
        else:
            base_note = f"⚠ 路径无效（找不到 inference.pdmodel）"

        if tier == "mobile":
            self._ocr_hint.configure(
                text=f"{base_note} · 精度: {tier_label} · ⚠ 需重启后生效\n  {path or '(内置/默认下载路径)'}")
        else:
            self._ocr_hint.configure(
                text=f"{base_note} · 精度: {tier_label} · 重启后生效\n  {path or '(内置模型)'}")

    # ─ ─ 交互 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

    def _browse_ocr_dir(self) -> None:
        path = filedialog.askdirectory(title="选择 PaddleOCR 模型根目录")
        if path:
            self._ocr_var.set(path)

    def _reset_ocr_dir(self) -> None:
        self._ocr_var.set("")

    def _export_legacy_settings(self) -> None:
        """从设置面板直接导出旧版配置（复用 shell._export_legacy_settings 逻辑）。"""
        from tkinter import messagebox
        path = filedialog.asksaveasfilename(
            title="导出旧版配置",
            defaultextension=".json",
            initialfile="legacy_settings.json",
            filetypes=[("JSON 文件", "*.json")],
        )
        if not path:
            return
        base = Path(path)
        try:
            for module_name in ("cmm_filler", "pc_to_excel"):
                config_path = paths.config_dir / module_name / "settings.json"
                config = load_and_migrate_settings(module_name, config_path)
                target = base.with_name(f"{base.stem}_{module_name}{base.suffix}")
                export_legacy_settings(module_name, target, config)
            messagebox.showinfo(
                "已导出",
                f"旧版配置已导出（每模块一个文件）：\n{base.parent}",
            )
        except Exception as e:
            logger.exception(f"导出旧版配置失败: {e}")
            messagebox.showerror("导出失败", f"导出旧版配置失败：\n{e}")

    def _restore_defaults(self) -> None:
        self._working = dict(TOOLBOX_DEFAULT_SETTINGS)
        self._appearance_var.set(self._label_for(self.APPEARANCE_OPTIONS, self._working["appearance_mode"]))
        self._ocr_tier_var.set(self._label_for(self.OCR_TIER_OPTIONS, self._working["ocr_model_tier"]))
        self._ocr_var.set(self._working["ocr_model_dir"])
        self._log_level_var.set(self._working["log_level"])

    def _save(self) -> None:
        """收集 UI 值 → 写盘 → 应用运行时变更。"""
        # 收集
        self._working["appearance_mode"] = self._value_for(self.APPEARANCE_OPTIONS, self._appearance_var.get())
        self._working["ocr_model_tier"] = self._value_for(self.OCR_TIER_OPTIONS, self._ocr_tier_var.get())
        self._working["ocr_model_dir"] = self._ocr_var.get().strip()
        self._working["log_level"] = self._log_level_var.get()

        # 写盘
        try:
            save_toolbox_settings(self._working)
        except Exception as e:
            logger.exception(f"保存 toolbox 设置失败: {e}")
            from tkinter import messagebox
            messagebox.showerror("保存失败", f"无法保存设置：\n{e}")
            return

        # 运行时应用
        try:
            ctk.set_appearance_mode(self._working["appearance_mode"])
        except Exception:
            pass
        try:
            from utils.logging import set_log_level
            for name in ("CMMFiller", "pc_to_excel", "toolbox"):
                set_log_level(name, self._working["log_level"])
        except Exception:
            pass

        from utils.audit import audit
        audit("settings_saved", **self._working)
        self._close()

    def _cancel(self) -> None:
        self._close()

    def _close(self) -> None:
        try:
            self._win.grab_release()
        except Exception:
            pass
        self._win.destroy()

    @staticmethod
    def _value_for(options, label):
        for l, v in options:
            if l == label:
                return v
        return options[-1][1]