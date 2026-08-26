"""主窗口 — CustomTkinter UI。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config import APP_TITLE, APP_VERSION, REPORTS_DIR
from connector.com_detector import check_elevation_match, is_pcdmis_elevated, is_pcdmis_running
from connector.pcdmis_connector import PcdmisConnector
from core.models import ToleranceConfig
from core.tolerance import apply_tolerance
from export.inspection_form_fill import (
    MANUAL_MAP_PLACEHOLDER,
    FormFillConfig,
    default_fill_output_path,
    default_form_fill_config,
    fill_inspection_form,
    format_manual_map_text,
    parse_manual_map_text,
    preview_form_fill,
    summarize_fill_result,
)
from export.template_report import export_report
from inject.command_injector import check_export_command, deploy_bas_script, inject_export_command
from utils.action_hints import format_user_error
from utils.admin import admin_status_text, is_admin
from utils.settings import build_export_filename, ensure_default_dirs, load_settings, save_settings

# 测房友好：青绿主色，避免默认紫系
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("green")

# 界面色板（浅色 / 深色）— 青绿 + 石板灰，偏测房工作台
_C = {
    "accent": ("#0F766E", "#14B8A6"),
    "accent_hover": ("#0D9488", "#2DD4BF"),
    "primary": ("#115E59", "#0F766E"),
    "primary_hover": ("#0F766E", "#14B8A6"),
    "muted": ("#64748B", "#475569"),
    "muted_hover": ("#475569", "#334155"),
    "warn": ("#C2410C", "#EA580C"),
    "warn_hover": ("#EA580C", "#F97316"),
    "subtle": ("#64748B", "#94A3B8"),
    "ok": ("#15803D", "#4ADE80"),
    "idle": ("#94A3B8", "#64748B"),
    "bad": ("#B91C1C", "#F87171"),
    "card": ("#FFFFFF", "#1E293B"),
    "card_border": ("#E2E8F0", "#334155"),
    "page": ("#F1F5F9", "#0F172A"),
    "stripe": ("#0F766E", "#14B8A6"),
    "hint_bg": ("#F0FDFA", "#134E4A"),
}


class MainWindow:
    def __init__(self, parent=None) -> None:
        ensure_default_dirs()
        self.settings = load_settings()
        self.connector = PcdmisConnector()
        self._busy = False

        # ── 挂载模式支持 ──────────────────────────────────────────────
        # parent=None → 自建根窗口（独立运行，行为不变）
        # parent=Frame → 挂载到传入容器（toolbox 集成）
        self._owns_root = parent is None
        if self._owns_root:
            self.root = ctk.CTk()
            self.root.title(f"{APP_TITLE} v{APP_VERSION}")
            self.root.geometry("1000x780")
            self.root.minsize(880, 700)
            self.root.configure(fg_color=_C["page"])
        else:
            self.root = parent.winfo_toplevel()
        self._container = parent if parent else self.root

        ff = self.settings.form_fill
        self.status_var = tk.StringVar(value="就绪")
        self.conn_var = tk.StringVar(value="未连接")
        self.conn_state_var = tk.StringVar(value="● 未连接")
        self.part_var = tk.StringVar(value="—")
        self.perm_var = tk.StringVar(value="")
        self.export_dir_var = tk.StringVar(value=str(self.settings.resolved_export_dir()))
        self.report_only_var = tk.BooleanVar(value=self.settings.export_scope == "report")
        self.require_marked_var = tk.BooleanVar(value=self.settings.require_marked)
        self.form_fill_var = tk.BooleanVar(value=ff.enabled)
        self.form_path_var = tk.StringVar(value=ff.form_path)
        self.id_prefixes_var = tk.StringVar(value=",".join(ff.id_prefixes))
        self.cmm_codes_var = tk.StringVar(value=",".join(ff.cmm_codes))
        self.target_col_var = tk.StringVar(value=ff.target_col or "auto")
        self.piece_id_var = tk.StringVar(value=ff.piece_id)
        self.write_piece_id_var = tk.BooleanVar(value=ff.write_piece_id)
        self.nominal_check_var = tk.BooleanVar(value=ff.nominal_check)
        self.manual_map_var = tk.StringVar(
            value=ff.manual_map_text or format_manual_map_text(ff.manual_map)
        )
        self.chain_from_last_var = tk.BooleanVar(value=ff.chain_from_last)
        self.last_fill_var = tk.StringVar(value=self._format_last_fill(ff.last_fill_output))
        self.progress_var = tk.StringVar(value="")

        self._build_ui()
        self.perm_var.set(self._perm_text())
        self._set_conn_visual("idle")
        if self._owns_root:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _font(self, size: int = 13, bold: bool = False) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=size, weight="bold" if bold else "normal")

    def _btn_primary(self, parent, text: str, command, *, width: int = 150, height: int = 36):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            corner_radius=10,
            font=self._font(13, True),
            fg_color=_C["primary"],
            hover_color=_C["primary_hover"],
        )

    def _btn_accent(self, parent, text: str, command, *, width: int = 150, height: int = 36):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            corner_radius=10,
            font=self._font(13, True),
            fg_color=_C["accent"],
            hover_color=_C["accent_hover"],
        )

    def _btn_muted(self, parent, text: str, command, *, width: int = 100, height: int = 34):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            corner_radius=10,
            font=self._font(12),
            fg_color=_C["muted"],
            hover_color=_C["muted_hover"],
        )

    def _btn_warn(self, parent, text: str, command, *, width: int = 150, height: int = 34):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            corner_radius=10,
            font=self._font(12, True),
            fg_color=_C["warn"],
            hover_color=_C["warn_hover"],
        )

    def _hint(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=self._font(11),
            text_color=_C["subtle"],
            anchor="w",
            justify="left",
            wraplength=920,
        ).pack(fill="x", pady=(0, 8))

    def _set_conn_visual(self, state: str) -> None:
        """state: idle | ok | bad"""
        if not hasattr(self, "conn_badge"):
            return
        colors = {"idle": _C["idle"], "ok": _C["ok"], "bad": _C["bad"]}
        labels = {"idle": "● 未连接", "ok": "● 已连接", "bad": "● 连接失败"}
        self.conn_state_var.set(labels.get(state, labels["idle"]))
        self.conn_badge.configure(text_color=colors.get(state, _C["idle"]))

    def _section(
        self,
        parent,
        title: str,
        *,
        subtitle: str = "",
        collapsible: bool = False,
        expanded: bool = True,
        accent: bool = False,
    ) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", pady=(0, 14))

        if accent:
            stripe = ctk.CTkFrame(outer, width=4, corner_radius=2, fg_color=_C["stripe"])
            stripe.pack(side="left", fill="y", padx=(0, 0))

        card = ctk.CTkFrame(
            outer,
            corner_radius=16,
            border_width=1,
            border_color=_C["card_border"],
            fg_color=_C["card"],
        )
        card.pack(side="left", fill="both", expand=True)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 4))
        title_col = ctk.CTkFrame(head, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_col, text=title, font=self._font(15, True), anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                title_col,
                text=subtitle,
                font=self._font(11),
                text_color=_C["subtle"],
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        body = ctk.CTkFrame(card, fg_color="transparent")

        if collapsible:
            switch_var = tk.BooleanVar(value=expanded)

            def _toggle(*_args) -> None:
                if switch_var.get():
                    body.pack(fill="x", padx=18, pady=(6, 16))
                else:
                    body.pack_forget()

            ctk.CTkSwitch(
                head,
                text="展开",
                variable=switch_var,
                command=_toggle,
                font=self._font(12),
                width=72,
                progress_color=_C["accent"],
            ).pack(side="right")
            if expanded:
                body.pack(fill="x", padx=18, pady=(6, 16))
        else:
            body.pack(fill="x", padx=18, pady=(6, 16))

        return body

    def _build_ui(self) -> None:
        # —— 顶栏 ——
        header = ctk.CTkFrame(self._container, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 10))

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(brand, text=APP_TITLE, font=self._font(24, True), anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text=f"v{APP_VERSION}  ·  测到一半也能出表  ·  出货表按序号填入",
            font=self._font(12),
            text_color=_C["subtle"],
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")
        self.conn_badge = ctk.CTkLabel(
            right, textvariable=self.conn_state_var, font=self._font(12, True), text_color=_C["idle"]
        )
        self.conn_badge.pack(side="left", padx=(0, 12))
        appearance = ctk.CTkSegmentedButton(
            right,
            values=["浅色", "深色", "系统"],
            command=self._on_appearance,
            width=168,
            height=30,
            font=self._font(12),
            selected_color=_C["accent"],
            selected_hover_color=_C["accent_hover"],
        )
        appearance.set("系统")
        appearance.pack(side="right")

        scroll = ctk.CTkScrollableFrame(self._container, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=22, pady=(0, 8))

        # —— 连接 ——
        conn = self._section(scroll, "PCDMIS 连接", subtitle="与 PCDMIS 同权限运行（都普通或都管理员）")
        row1 = ctk.CTkFrame(conn, fg_color="transparent")
        row1.pack(fill="x")
        self._btn_primary(row1, "连接 PCDMIS", self._connect, width=132).pack(side="left")
        self._btn_muted(row1, "断开", self._disconnect, width=72).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(row1, textvariable=self.conn_var, font=self._font(13)).pack(side="left", padx=14)
        ctk.CTkLabel(row1, textvariable=self.perm_var, font=self._font(11), text_color=_C["subtle"]).pack(
            side="right"
        )

        info = ctk.CTkFrame(conn, fg_color=_C["hint_bg"], corner_radius=10)
        info.pack(fill="x", pady=(12, 0))
        inner = ctk.CTkFrame(info, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(inner, text="当前程序", font=self._font(11), text_color=_C["subtle"]).pack(side="left")
        ctk.CTkLabel(inner, textvariable=self.part_var, font=self._font(13, True)).pack(side="left", padx=10)

        # —— 导出（主流程强调）——
        export = self._section(
            scroll,
            "导出 Excel",
            subtitle="读取当前已测数据，生成 PC-DMIS 列格式报告",
            accent=True,
        )
        dir_row = ctk.CTkFrame(export, fg_color="transparent")
        dir_row.pack(fill="x")
        ctk.CTkLabel(dir_row, text="输出目录", width=72, anchor="w", font=self._font(12)).pack(side="left")
        ctk.CTkEntry(dir_row, textvariable=self.export_dir_var, height=34, corner_radius=8).pack(
            side="left", fill="x", expand=True, padx=8
        )
        self._btn_muted(dir_row, "浏览…", self._pick_export_dir, width=78, height=34).pack(side="right")

        scope = ctk.CTkFrame(export, fg_color="transparent")
        scope.pack(fill="x", pady=(12, 0))
        ctk.CTkCheckBox(
            scope,
            text="仅报告窗口数据",
            variable=self.report_only_var,
            command=self._save_settings_from_ui,
            font=self._font(12),
        ).pack(side="left")
        ctk.CTkCheckBox(
            scope,
            text="仅 Mark 命令",
            variable=self.require_marked_var,
            command=self._save_settings_from_ui,
            font=self._font(12),
        ).pack(side="left", padx=(18, 0))

        btn_row = ctk.CTkFrame(export, fg_color="transparent")
        btn_row.pack(fill="x", pady=(16, 0))
        self._btn_primary(btn_row, "一键导出 Excel", self._export_excel, width=168, height=40).pack(side="left")
        ctk.CTkLabel(
            btn_row,
            text="尺寸 · 描述 · NOMINAL · MEAS · +TOL · −TOL · BONUS · DEV · OUTTOL",
            font=self._font(11),
            text_color=_C["subtle"],
        ).pack(side="left", padx=14)

        # —— 出货表 ——
        form = self._section(
            scroll,
            "出货检测表填入",
            subtitle="按序号只写 CMM 行，多件续列；先预览再另存",
            collapsible=True,
            expanded=False,
        )
        form_row1 = ctk.CTkFrame(form, fg_color="transparent")
        form_row1.pack(fill="x")
        ctk.CTkCheckBox(
            form_row1,
            text="启用填入",
            variable=self.form_fill_var,
            command=self._save_settings_from_ui,
            width=100,
            font=self._font(12),
        ).pack(side="left")
        ctk.CTkEntry(form_row1, textvariable=self.form_path_var, height=34, corner_radius=8).pack(
            side="left", fill="x", expand=True, padx=8
        )
        self._btn_muted(form_row1, "选出货表…", self._pick_form, width=104, height=34).pack(side="right")

        form_row2 = ctk.CTkFrame(form, fg_color="transparent")
        form_row2.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(form_row2, text="尺寸前缀", width=70, anchor="w", font=self._font(12)).pack(side="left")
        ctk.CTkEntry(form_row2, textvariable=self.id_prefixes_var, width=200, height=34, corner_radius=8).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkLabel(form_row2, text="CMM代号", width=70, anchor="w", font=self._font(12)).pack(side="left")
        ctk.CTkEntry(form_row2, textvariable=self.cmm_codes_var, width=90, height=34, corner_radius=8).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkLabel(form_row2, text="写入列", width=55, anchor="w", font=self._font(12)).pack(side="left")
        ctk.CTkEntry(form_row2, textvariable=self.target_col_var, width=70, height=34, corner_radius=8).pack(
            side="left"
        )
        ctk.CTkLabel(form_row2, text="auto / H / I…", font=self._font(11), text_color=_C["subtle"]).pack(
            side="left", padx=8
        )

        form_row3 = ctk.CTkFrame(form, fg_color="transparent")
        form_row3.pack(fill="x", pady=(12, 0))
        ctk.CTkCheckBox(
            form_row3,
            text="接着上次结果填入",
            variable=self.chain_from_last_var,
            command=self._save_settings_from_ui,
            font=self._font(12),
        ).pack(side="left")
        self._btn_muted(form_row3, "清除续填", self._clear_last_fill, width=90, height=30).pack(
            side="left", padx=10
        )
        ctk.CTkLabel(
            form_row3, textvariable=self.last_fill_var, font=self._font(11), text_color=_C["subtle"]
        ).pack(side="left", fill="x", expand=True)

        form_row_piece = ctk.CTkFrame(form, fg_color="transparent")
        form_row_piece.pack(fill="x", pady=(12, 0))
        ctk.CTkCheckBox(
            form_row_piece,
            text="写入件号",
            variable=self.write_piece_id_var,
            command=self._save_settings_from_ui,
            width=90,
            font=self._font(12),
        ).pack(side="left")
        ctk.CTkEntry(
            form_row_piece,
            textvariable=self.piece_id_var,
            placeholder_text="送检件号，如 721-001（空则用 PCDMIS 序列号）",
            height=34,
            corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkCheckBox(
            form_row_piece,
            text="核对规格/名义",
            variable=self.nominal_check_var,
            command=self._save_settings_from_ui,
            width=120,
            font=self._font(12),
        ).pack(side="right")

        form_row_map = ctk.CTkFrame(form, fg_color="transparent")
        form_row_map.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(form_row_map, text="手工对照", width=70, anchor="w", font=self._font(12)).pack(side="left")
        ctk.CTkEntry(
            form_row_map,
            textvariable=self.manual_map_var,
            placeholder_text=MANUAL_MAP_PLACEHOLDER,
            height=34,
            corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=8)
        self._btn_muted(form_row_map, "恢复默认", self._restore_form_defaults, width=90, height=34).pack(
            side="right"
        )

        form_row4 = ctk.CTkFrame(form, fg_color="transparent")
        form_row4.pack(fill="x", pady=(16, 0))
        self._btn_accent(form_row4, "填入出货检测表", self._fill_inspection_form, width=168, height=40).pack(
            side="left"
        )
        ctk.CTkLabel(
            form_row4,
            text="先预览匹配 → 确认另存；续填自动下一空列（不覆盖已有数据）",
            font=self._font(11),
            text_color=_C["subtle"],
        ).pack(side="left", padx=14)

        # —— 植入 ——
        inject = self._section(
            scroll,
            "PRG 命令植入",
            subtitle="测量中可把光标放到 PC2XL_EXPORT → 从光标执行",
            collapsible=True,
            expanded=False,
        )
        self._hint(
            inject,
            "在程序末尾插入导出命令。适合边测边出 CSV；需要完整 xlsx 列格式时请用上方「一键导出」。",
        )
        inj_row = ctk.CTkFrame(inject, fg_color="transparent")
        inj_row.pack(fill="x", pady=(4, 0))
        self._btn_muted(inj_row, "部署 BAS 脚本", self._deploy_bas, width=130).pack(side="left")
        self._btn_warn(inj_row, "植入 / 更新导出命令", self._inject_command, width=168).pack(
            side="left", padx=8
        )
        self._btn_muted(inj_row, "检查是否已植入", self._check_inject, width=130).pack(side="left")

        # —— 说明 ——
        help_body = self._section(
            scroll,
            "PCDMIS 内执行说明",
            collapsible=True,
            expanded=False,
        )
        help_text = ctk.CTkTextbox(
            help_body,
            height=150,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            corner_radius=10,
            border_width=1,
            border_color=_C["card_border"],
        )
        help_text.pack(fill="both", expand=True)
        help_text.insert(
            "1.0",
            "1. 点击「植入 / 更新导出命令」后保存 PRG。\n"
            "2. 正常测量，测到一半也可导出。\n"
            "3. 在 Edit 窗口将光标放在 PC2XL_EXPORT 命令行。\n"
            "4. 菜单：文件 → 部分执行 → 从光标执行（或选中命令块 → 执行块）。\n"
            "5. 脚本导出 CSV；BAS 在 %LOCALAPPDATA%\\PCDMIS_ExcelExporter\\scripts\\\n"
            "   （避免路径含空格时 PCDMIS 报「未找到脚本文件」）。\n\n"
            "注意：PC-DMIS Pro 无 BASIC 扩展，请用外部「一键导出」。\n"
            "工具与 PCDMIS 须同为普通用户或同为管理员运行。",
        )
        help_text.configure(state="disabled")

        # —— 底栏 ——
        foot = ctk.CTkFrame(
            self._container,
            fg_color=_C["card"],
            corner_radius=12,
            border_width=1,
            border_color=_C["card_border"],
            height=44,
        )
        foot.pack(fill="x", padx=22, pady=(0, 8))
        foot_inner = ctk.CTkFrame(foot, fg_color="transparent")
        foot_inner.pack(fill="x", padx=14, pady=8)
        ctk.CTkLabel(foot_inner, textvariable=self.progress_var, font=self._font(12), text_color=_C["subtle"]).pack(
            side="left"
        )
        ctk.CTkLabel(foot_inner, textvariable=self.status_var, font=self._font(12, True)).pack(side="right")

        self.progress = ctk.CTkProgressBar(
            self._container,
            mode="indeterminate",
            height=5,
            corner_radius=3,
            progress_color=_C["accent"],
        )
        self.progress.pack(fill="x", padx=22, pady=(0, 14))
        self.progress.set(0)

    def _on_appearance(self, value: str) -> None:
        mapping = {"浅色": "Light", "深色": "Dark", "系统": "System"}
        ctk.set_appearance_mode(mapping.get(value, "System"))

    def _perm_text(self) -> str:
        tool = admin_status_text()
        if is_pcdmis_running():
            pcd = "PCDMIS:管理员" if is_pcdmis_elevated() else "PCDMIS:普通"
            elevated = is_pcdmis_elevated()
            match = (
                "匹配 ✓"
                if (elevated is not None and elevated == is_admin())
                else "权限?"
            )
            return f"{tool}  ·  {pcd}  ·  {match}"
        return f"{tool}  ·  PCDMIS 未运行"

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._busy = busy
        if busy:
            self.progress.start()
            self.progress_var.set(msg)
        else:
            self.progress.stop()
            self.progress.set(0)
            self.progress_var.set("")

    def _connect(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "正在连接…")
        self.status_var.set("连接中")
        self.perm_var.set(self._perm_text())

        def work():
            info = self.connector.connect()
            self.root.after(0, lambda: self._on_connected(info))

        threading.Thread(target=work, daemon=True).start()

    def _on_connected(self, info) -> None:
        self._set_busy(False)
        self.perm_var.set(self._perm_text())
        if info.connected:
            self.conn_var.set(f"{info.source} · {info.version}")
            self.part_var.set(self.connector.get_active_part_name() or "—")
            self.status_var.set("已连接")
            self._set_conn_visual("ok")
        else:
            self.conn_var.set("连接失败")
            self._set_conn_visual("bad")
            messagebox.showerror(
                "连接失败",
                format_user_error("连接失败", info.message or "无法连接 PCDMIS COM"),
            )
            self.status_var.set("连接失败")

    def _disconnect(self) -> None:
        self.connector.disconnect()
        self.conn_var.set("未连接")
        self.part_var.set("—")
        self.status_var.set("已断开")
        self.perm_var.set(self._perm_text())
        self._set_conn_visual("idle")

    def _save_settings_from_ui(self) -> None:
        self.settings.export_dir = self.export_dir_var.get().strip()
        self.settings.export_scope = "report" if self.report_only_var.get() else "all"
        self.settings.require_marked = bool(self.require_marked_var.get())

        prefixes = [p.strip() for p in self.id_prefixes_var.get().split(",") if p.strip()]
        codes = [c.strip().upper() for c in self.cmm_codes_var.get().split(",") if c.strip()]
        target = self.target_col_var.get().strip().lower() or "auto"
        map_text = self.manual_map_var.get().strip()
        prev = self.settings.form_fill
        self.settings.form_fill = FormFillConfig(
            enabled=bool(self.form_fill_var.get()),
            form_path=self.form_path_var.get().strip(),
            id_prefixes=prefixes or list(prev.id_prefixes),
            cmm_codes=codes or list(prev.cmm_codes),
            serial_col=prev.serial_col,
            instrument_col=prev.instrument_col,
            data_start_col=prev.data_start_col,
            spec_col=prev.spec_col,
            target_col=target,
            hyphen_to_dot=prev.hyphen_to_dot,
            manual_map=parse_manual_map_text(map_text),
            manual_map_text=map_text,
            header_scan_row=prev.header_scan_row,
            data_start_row=prev.data_start_row,
            chain_from_last=bool(self.chain_from_last_var.get()),
            last_fill_output=prev.last_fill_output,
            write_piece_id=bool(self.write_piece_id_var.get()),
            piece_id=self.piece_id_var.get().strip(),
            nominal_check=bool(self.nominal_check_var.get()),
            nominal_tol=prev.nominal_tol,
        )
        save_settings(self.settings)

    @staticmethod
    def _format_last_fill(path: str) -> str:
        text = (path or "").strip()
        if not text:
            return "上次结果：无（将从选出的出货表开始）"
        return f"上次结果：{Path(text).name}"

    def _clear_last_fill(self) -> None:
        self.settings.form_fill.last_fill_output = ""
        self.last_fill_var.set(self._format_last_fill(""))
        self._save_settings_from_ui()

    def _restore_form_defaults(self) -> None:
        """恢复出货表常用默认（保留已选出货表路径与续填记录）。"""
        defaults = default_form_fill_config()
        keep_path = self.form_path_var.get().strip()
        keep_last = self.settings.form_fill.last_fill_output
        self.form_fill_var.set(True)
        self.id_prefixes_var.set(",".join(defaults.id_prefixes))
        self.cmm_codes_var.set(",".join(defaults.cmm_codes))
        self.target_col_var.set(defaults.target_col)
        self.chain_from_last_var.set(defaults.chain_from_last)
        self.write_piece_id_var.set(defaults.write_piece_id)
        self.nominal_check_var.set(defaults.nominal_check)
        self.manual_map_var.set("")
        self.piece_id_var.set("")
        self.form_path_var.set(keep_path)
        self.settings.form_fill.last_fill_output = keep_last
        self.last_fill_var.set(self._format_last_fill(keep_last))
        self._save_settings_from_ui()
        self.status_var.set("已恢复出货表默认配置")

    def _refresh_connection_ui(self) -> None:
        """导出/填入后刷新程序名与连接灯（多件连续测不必手点连接）。"""
        self.perm_var.set(self._perm_text())
        if self.connector.is_connected():
            ver = self.connector.version or ""
            pid = self.connector.prog_id or ""
            self.conn_var.set(f"{self.connector.name} · {ver}" if ver else (pid or "已连接"))
            self.part_var.set(self.connector.get_active_part_name() or "—")
            self._set_conn_visual("ok")
        else:
            self._set_conn_visual("idle")

    def _ensure_connected(self, *, action: str) -> bool:
        """导出/填入前自动保持会话；失效则静默重连，无需每件手点「连接」。"""
        info = self.connector.ensure_session()
        if info.connected:
            self._refresh_connection_ui()
            return True
        messagebox.showerror(
            "无法连接 PCDMIS",
            format_user_error(
                "无法连接",
                f"执行「{action}」时未能附着 PCDMIS。\n"
                f"{info.message or '无法连接 PCDMIS COM'}",
            ),
        )
        self._set_conn_visual("bad")
        return False

    def _pick_export_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.export_dir_var.get())
        if path:
            self.export_dir_var.set(path)
            self._save_settings_from_ui()

    def _pick_form(self) -> None:
        initial = self.form_path_var.get().strip() or str(Path.home() / "Desktop")
        path = filedialog.askopenfilename(
            initialdir=str(Path(initial).parent) if initial else str(Path.home()),
            filetypes=[("出货检测表", "*.xlsx"), ("所有文件", "*.*")],
        )
        if path:
            self.form_path_var.set(path)
            self.form_fill_var.set(True)
            self.settings.form_fill.last_fill_output = ""
            self.last_fill_var.set(self._format_last_fill(""))
            self._save_settings_from_ui()

    def _fill_inspection_form(self) -> None:
        if self._busy:
            return
        self._save_settings_from_ui()
        if not self.form_fill_var.get():
            ok = messagebox.askyesno(
                "未启用填入",
                "「启用填入」未勾选。是否现在启用并继续？",
            )
            if not ok:
                return
            self.form_fill_var.set(True)
            self._save_settings_from_ui()
        if not self._ensure_connected(action="填入出货检测表"):
            return

        form_path, chained = self.settings.form_fill.resolve_input_form()
        if form_path is None:
            messagebox.showerror(
                "缺少出货表",
                format_user_error(
                    "缺少出货表",
                    "未找到可用的出货检测表。请先选出货表 xlsx。",
                ),
            )
            return
        if not form_path.is_file():
            messagebox.showerror(
                "出货表无效",
                format_user_error(
                    "出货表无效",
                    f"出货检测表不存在或无法读取：\n{form_path}",
                ),
            )
            return

        out_dir = Path(self.export_dir_var.get().strip() or REPORTS_DIR)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "输出目录无效",
                format_user_error("输出目录无效", f"无法创建输出目录：{out_dir}\n{exc}"),
            )
            return

        # 主线程快照，避免工作线程读 Tk 变量
        piece_id_ui = self.piece_id_var.get().strip()
        export_scope = self.settings.export_scope
        require_marked = self.settings.require_marked
        form_cfg = self.settings.form_fill

        tip = "续填：正在提取并预览…" if chained else "正在提取并预览…"
        self._set_busy(True, tip)
        self.status_var.set("预览中")

        def work():
            try:
                records = self.connector.extract_features(
                    progress_cb=lambda i, n, m: self.root.after(0, lambda: self.progress_var.set(m)),
                    scope=export_scope,
                    require_marked=require_marked,
                )
                if not records:
                    raise RuntimeError(
                        "未提取到可填入的测量数据（0 条）。"
                    )
                tol = ToleranceConfig.from_dict(self.settings.tolerance)
                apply_tolerance(records, tol)
                piece_id = piece_id_ui
                if not piece_id:
                    try:
                        header = self.connector.get_report_header_info()
                        piece_id = (header.serial_number or "").strip()
                    except Exception:
                        piece_id = ""
                preview = preview_form_fill(
                    records,
                    form_path,
                    config=form_cfg,
                    piece_id=piece_id,
                    chained=chained,
                )
                self.root.after(
                    0,
                    lambda: self._on_fill_preview_ready(
                        records, form_path, out_dir, piece_id, preview
                    ),
                )
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: self._on_error("填入失败", format_user_error("填入失败", exc, with_trace=True)),
                )

        threading.Thread(target=work, daemon=True).start()

    def _on_fill_preview_ready(self, records, form_path, out_dir, piece_id, preview) -> None:
        self._set_busy(False)
        self.status_var.set("待确认填入")
        if preview.will_fill <= 0:
            messagebox.showwarning(
                "没有可填入的数据",
                format_user_error(
                    "没有可填入的数据",
                    "预览结果：预计填入 0 格。\n"
                    + preview.summary_text()
                    + "\n\n未提取到匹配序号，或表中无 CMM 行。",
                ),
            )
            return

        ok = messagebox.askokcancel("确认填入出货表", preview.summary_text() + "\n\n是否继续写入？")
        if not ok:
            self.status_var.set("已取消填入")
            return

        self._set_busy(True, "正在写入出货表…")
        self.status_var.set("填入中")

        def work():
            try:
                name_base = Path(self.form_path_var.get().strip() or form_path)
                out_path = default_fill_output_path(name_base, out_dir)
                result = fill_inspection_form(
                    records,
                    form_path,
                    out_path,
                    config=self.settings.form_fill,
                    piece_id=piece_id,
                )
                result.chained = preview.chained
                self.root.after(0, lambda: self._on_fill_ok(result, len(records)))
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: self._on_error("填入失败", format_user_error("填入失败", exc, with_trace=True)),
                )

        threading.Thread(target=work, daemon=True).start()

    def _on_fill_ok(self, result, extract_count: int) -> None:
        self._set_busy(False)
        self.status_var.set(f"已填入 {result.filled} 格")
        self.settings.form_fill.last_fill_output = str(result.output_path)
        self.last_fill_var.set(self._format_last_fill(str(result.output_path)))
        save_settings(self.settings)
        self._refresh_connection_ui()
        self._show_fill_result_dialog(summarize_fill_result(result, extract_count))

    def _show_fill_result_dialog(self, summary: str) -> None:
        win = ctk.CTkToplevel(self.root)
        win.title("填入完成")
        win.geometry("660x480")
        win.configure(fg_color=_C["page"])
        win.transient(self.root)
        win.grab_set()

        card = ctk.CTkFrame(
            win,
            corner_radius=16,
            border_width=1,
            border_color=_C["card_border"],
            fg_color=_C["card"],
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(card, text="出货表填入结果", font=self._font(17, True)).pack(
            anchor="w", padx=18, pady=(16, 4)
        )
        ctk.CTkLabel(
            card,
            text="可复制摘要核对未匹配 / 冲突 / 规格警告",
            font=self._font(11),
            text_color=_C["subtle"],
        ).pack(anchor="w", padx=18, pady=(0, 10))
        box = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            corner_radius=10,
            border_width=1,
            border_color=_C["card_border"],
        )
        box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        box.insert("1.0", summary)
        box.configure(state="disabled")

        def _copy() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(summary)
            self.status_var.set("结果已复制")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 16))
        self._btn_accent(btn_row, "复制结果", _copy, width=110, height=34).pack(side="left")
        self._btn_muted(btn_row, "关闭", win.destroy, width=90, height=34).pack(side="right")

    def _export_excel(self) -> None:
        if self._busy:
            return
        self._save_settings_from_ui()
        if not self._ensure_connected(action="一键导出 Excel"):
            return
        out_dir = Path(self.export_dir_var.get().strip() or REPORTS_DIR)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "输出目录无效",
                format_user_error("输出目录无效", f"无法创建输出目录：{out_dir}\n{exc}"),
            )
            return

        self._set_busy(True, "正在提取并导出…")
        self.status_var.set("导出中")

        def work():
            try:
                records = self.connector.extract_features(
                    progress_cb=lambda i, n, m: self.root.after(0, lambda: self.progress_var.set(m)),
                    scope=self.settings.export_scope,
                    require_marked=self.settings.require_marked,
                )
                if not records:
                    raise RuntimeError("未提取到可导出的测量数据（0 条）。")
                tol = ToleranceConfig.from_dict(self.settings.tolerance)
                apply_tolerance(records, tol)
                header = self.connector.get_report_header_info()
                filename = build_export_filename(
                    header.part_name or header.program_name or "report",
                    self.settings.filename_pattern,
                )
                out_path = out_dir / filename
                export_report(
                    records,
                    out_path,
                    part_name=header.part_name,
                    program_path=header.program_name,
                    header=header,
                )
                self.root.after(0, lambda: self._on_export_ok(out_path, len(records)))
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: self._on_error("导出失败", format_user_error("导出失败", exc, with_trace=True)),
                )

        threading.Thread(target=work, daemon=True).start()

    def _on_export_ok(self, path: Path, count: int) -> None:
        self._set_busy(False)
        self.status_var.set(f"已导出 {count} 条")
        self._refresh_connection_ui()
        messagebox.showinfo("导出完成", f"共 {count} 条数据\n\n{path}")

    def _deploy_bas(self) -> None:
        try:
            path = deploy_bas_script()
            messagebox.showinfo("部署完成", f"脚本已更新:\n{path}")
        except Exception as exc:
            messagebox.showerror("部署失败", format_user_error("部署失败", exc))

    def _inject_command(self) -> None:
        if self._busy:
            return
        if not self.connector.is_connected():
            info = self.connector.connect()
            if not info.connected:
                messagebox.showerror(
                    "连接失败",
                    format_user_error("连接失败", info.message or "无法连接 PCDMIS COM"),
                )
                return
        self._set_busy(True, "正在植入命令…")

        def work():
            try:
                from connector.com_detector import com_apartment, dispatch_pcdmis

                with com_apartment():
                    app = dispatch_pcdmis(self.connector.prog_id)
                    result = inject_export_command(app)
                self.root.after(0, lambda: self._on_inject_done(result))
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: self._on_error("植入失败", format_user_error("植入失败", exc, with_trace=True)),
                )

        threading.Thread(target=work, daemon=True).start()

    def _on_inject_done(self, result) -> None:
        self._set_busy(False)
        if result.success:
            self.status_var.set("命令已植入")
            messagebox.showinfo("植入完成", result.message)
        else:
            messagebox.showerror("植入失败", format_user_error("植入失败", result.message))

    def _check_inject(self) -> None:
        if not self.connector.is_connected():
            info = self.connector.connect()
            if not info.connected:
                messagebox.showerror(
                    "连接失败",
                    format_user_error("连接失败", info.message or "无法连接 PCDMIS COM"),
                )
                return
        try:
            from connector.com_detector import com_apartment, dispatch_pcdmis

            with com_apartment():
                app = dispatch_pcdmis(self.connector.prog_id)
                result = check_export_command(app)
            if result.success:
                messagebox.showinfo("检查结果", result.message)
            else:
                messagebox.showwarning("检查结果", result.message)
        except Exception as exc:
            messagebox.showerror("检查失败", format_user_error("检查失败", exc))

    def _on_error(self, title: str, msg: str) -> None:
        self._set_busy(False)
        self.status_var.set(title)
        # msg 可能已是 format_user_error 结果
        messagebox.showerror(title, msg if msg.startswith("【") else format_user_error(title, msg))

    def _on_close(self) -> None:
        self._save_settings_from_ui()
        self.connector.disconnect()
        self.root.destroy()

    def run(self) -> None:
        ok, msg = check_elevation_match()
        if not ok and msg:
            messagebox.showwarning("权限提示", msg)
        if is_pcdmis_running() and not self.connector.is_connected():
            self.root.after(400, self._connect)
        if self._owns_root:
            self.root.mainloop()


def run_app() -> None:
    MainWindow().run()
