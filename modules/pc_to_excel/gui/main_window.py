"""主窗口 — CustomTkinter UI。"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

logger = logging.getLogger("pc_to_excel")

from ..app_meta import APP_TITLE, APP_VERSION
from ..connector.com_detector import check_elevation_match, get_pcdmis_pid, is_pcdmis_running
from ..connector.pcdmis_connector import PcdmisConnector
from ..core.models import ToleranceConfig
from ..core.tolerance import apply_tolerance
from ..export.inspection_form_fill import (
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
from ..export.template_report import export_report
from ..inject.command_injector import check_export_command, deploy_bas_script, inject_export_command
from ..inject.toolbar_launcher import (
    INSTALL_STEPS,
    deploy_toolbar_launcher,
    resolve_toolbar_argv,
)
from ..utils.action_hints import format_user_error
from ..utils.admin import admin_status_text, is_admin, is_process_elevated
from ..utils.local_settings import build_export_filename, ensure_default_dirs, load_settings, save_settings
from utils.threading_utils import CancellableWorker
from utils.audit import audit

# 测房友好：青绿主色，避免默认紫系
# 主题由 main.py 中的 apply_theme() 统一设置，本模块只补充 (light, dark) 双值

# 界面色板（浅色 / 深色）— 与 utils.theme.TOOLBOX_THEME 保持一致；额外补充
# 模块内独有的 hover / subtle 等派生色。
def _lp(light: str, dark: str) -> tuple[str, str]:
    """构造 CustomTkinter (light, dark) 配对。"""
    return (light, dark)

_C = {
    # 与 TOOLBOX_THEME 同步（净化版：低饱和、避免深蓝色卡片）
    "accent": _lp("#0F766E", "#14B8A6"),
    "accent_hover": _lp("#0D8A82", "#0D8A82"),
    "primary": _lp("#0F766E", "#0F766E"),
    "primary_hover": _lp("#0D8A82", "#0D8A82"),
    "ok": _lp("#15803D", "#4ADE80"),
    "warn": _lp("#C2410C", "#EA580C"),
    "warn_hover": _lp("#EA580C", "#F97316"),
    "bad": _lp("#B91C1C", "#F87171"),
    # 卡片边框：仍保留极淡描边以兼顾"完全无框"读不出层级的情况
    "card_border": _lp("#E8E8E8", "#3A3A3A"),
    # 仅 pc_to_excel 使用
    "muted": _lp("#666666", "#999999"),
    "muted_hover": _lp("#525252", "#777777"),
    "subtle": _lp("#666666", "#999999"),
    "idle": _lp("#7B8794", "#64748B"),
    # 卡片底色 = 页面底（让卡片融入背景，靠留白分层而非边框）
    "card": _lp("#F5F5F5", "#1F1F1F"),
    "page": _lp("#F5F5F5", "#1F1F1F"),
    "stripe": _lp("#0F766E", "#14B8A6"),
    # 提示区底色 = 略深的页面色（深色模式下深一层，浅色下浅一层）
    "hint_bg": _lp("#FAFAFA", "#2A2A2A"),
}

# For REPORTS_DIR reference
from utils.paths import paths
from utils.app_icon import apply_window_icon


class MainWindow:
    def __init__(self, parent=None) -> None:
        ensure_default_dirs()
        self.settings = load_settings()
        self.connector = PcdmisConnector()
        self._busy = False
        self._wizard_frame = None   # 首次运行向导面板
        self._wizard_done = False  # 向导是否已被用户关闭
        self._status_watcher_running = False
        self._status_watcher_after_id = None
        self._status_watcher_tick_id = None
        # _perm_text() 的 (monotonic, text) 缓存：状态栏展示字段，2s TTL。
        # 避免每次切换模块 / watcher tick 都 spawn tasklist（实测单次 ~190ms）。
        self._perm_text_cache: tuple[float, str] | None = None
        self._perm_text_ttl = 2.0

        # ── 挂载模式支持 ──────────────────────────────────────────────
        # parent=None → 自建根窗口（独立运行，行为不变）
        # parent=Frame → 挂载到传入容器（toolbox 集成）
        self._owns_root = parent is None
        if self._owns_root:
            self.root = ctk.CTk()
            self.root.title(f"{APP_TITLE} v{APP_VERSION}")
            self.root.geometry("940x700")
            self.root.minsize(820, 620)
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
        # 首次运行向导（独立模式、未连接时显示引导）
        self._show_wizard_if_needed()

    # ── 首次运行向导 ───────────────────────────────────────────────────────

    def _show_wizard_if_needed(self) -> None:
        """未连接时显示引导面板（独立模式）；已在连接状态则静默。"""
        if not self._owns_root or self.connector.is_connected():
            return
        self._wizard_frame = self._build_wizard_panel(self._container)
        self._wizard_frame.pack(fill="both", expand=True)

    def _build_wizard_panel(self, parent) -> ctk.CTkFrame:
        """首次运行引导面板：3 步引导卡片 + 检测 PCDMIS 状态。"""
        from ..connector.com_detector import is_pcdmis_running

        panel = ctk.CTkFrame(parent, fg_color="transparent")

        # 标题
        ctk.CTkLabel(
            panel,
            text="欢迎使用 PCDMIS 导出",
            font=self._font(22, True),
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            panel,
            text="按照以下步骤开始导出测量数据",
            font=self._font(13),
            text_color=_C["subtle"],
            anchor="w",
        ).pack(anchor="w", pady=(0, 24))

        # 3 步引导卡片
        steps = [
            ("1", "确认 PCDMIS 运行中", "请先在 PCDMIS 中打开要导出的测量程序（.prg 文件）"),
            ("2", "点击「连接 PCDMIS」", "工具会通过 COM 接口读取当前程序数据，无需额外操作"),
            ("3", "导出 Excel 报告", "点击「一键导出 Excel」，生成包含尺寸、公差、偏差的报告"),
        ]
        cards_frame = ctk.CTkFrame(panel, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, 24))
        for i, (num, title, desc) in enumerate(steps):
            card = ctk.CTkFrame(cards_frame, corner_radius=12)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12) if i < 2 else (0, 0))
            num_label = ctk.CTkLabel(
                card, text=num, font=self._font(18, True),
                text_color=_C["accent"], width=36, height=36,
                corner_radius=18,
            )
            num_label.pack(pady=(16, 8))
            ctk.CTkLabel(card, text=title, font=self._font(13, True), anchor="w").pack(
                anchor="w", padx=16, pady=(0, 4)
            )
            ctk.CTkLabel(
                card, text=desc, font=self._font(11), text_color=_C["subtle"],
                anchor="w", wraplength=200,
            ).pack(anchor="w", padx=16, pady=(0, 16))

        # PCDMIS 运行状态检测
        running = is_pcdmis_running()
        status_frame = ctk.CTkFrame(panel, corner_radius=10)
        status_frame.pack(fill="x", pady=(0, 20))

        if running:
            status_icon = "🟢"
            status_color = _C["ok"]
            status_text = "PC-DMIS 正在运行，可以点击连接了"
        else:
            status_icon = "🔴"
            status_color = _C["bad"]
            status_text = "PC-DMIS 未检测到，请先启动 PCDMIS 并打开测量程序"

        icon_label = ctk.CTkLabel(status_frame, text=status_icon, font=self._font(20))
        icon_label.pack(side="left", padx=14, pady=14)
        ctk.CTkLabel(
            status_frame, text=status_text,
            font=self._font(13), text_color=status_color,
        ).pack(side="left", pady=14)

        # 按钮行
        btn_row = ctk.CTkFrame(panel, fg_color="transparent")
        btn_row.pack(fill="x")
        self._btn_primary(btn_row, "连接 PCDMIS", self._connect, width=148).pack(side="left")
        ctk.CTkLabel(
            btn_row, text="连接成功后此引导将自动收起",
            font=self._font(11), text_color=_C["subtle"],
        ).pack(side="left", padx=14)
        ctk.CTkLabel(btn_row, text="", font=self._font(11)).pack(side="right")  # 占位

        return panel

    def _dismiss_wizard(self) -> None:
        """关闭向导面板。"""
        if self._wizard_frame:
            self._wizard_frame.pack_forget()
            self._wizard_frame.destroy()
            self._wizard_frame = None
            self._wizard_done = True

    def _font(self, size: int = 13, bold: bool = False) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=size, weight="bold" if bold else "normal")

    def _btn_primary(self, parent, text: str, command, *, width: int = 150, height: int = 36):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            corner_radius=6,
            font=self._font(12, True),
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
            corner_radius=6,
            font=self._font(12, True),
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
            corner_radius=6,
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
            corner_radius=6,
            font=self._font(12, True),
            fg_color=_C["warn"],
            hover_color=_C["warn_hover"],
        )

    @staticmethod
    def _checkbox_width(text: str, *, min_width: int = 100) -> int:
        """CTkCheckBox 默认 width=100，中文标签会画出控件边界但点击区域仍只有 100px。"""
        return max(min_width, len(text) * 14 + 44)

    def _checkbox(self, parent, text: str, variable, command=None, **kwargs):
        """可点击复选框：补足宽度，并给背景 canvas 绑点击（CTk 6 空白区默认无响应）。"""
        width = kwargs.pop("width", self._checkbox_width(text))
        cb = ctk.CTkCheckBox(
            parent,
            text=text,
            variable=variable,
            command=command,
            font=self._font(12),
            width=width,
            checkbox_width=18,
            checkbox_height=18,
            border_width=1,
            border_color=_C["card_border"],
            **kwargs,
        )
        cb._bg_canvas.bind("<Button-1>", cb.toggle)
        return cb

    def _sync_shell_pcdmis_status(self) -> None:
        """挂载到 Shell 时同步底栏 PC-DMIS 连接灯。"""
        shell = getattr(self, "shell", None)
        if shell is None or not hasattr(shell, "update_pcdmis_status"):
            return
        if self.connector.is_connected():
            shell.update_pcdmis_status(True, self.connector.version)
        else:
            shell.update_pcdmis_status(False)

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
        # 净化版：去掉卡片边框 + 卡片底色融入页面，靠标题层级 + 留白分层
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", pady=(0, 18))

        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        title_col = ctk.CTkFrame(head, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)
        # 标题更突出（更大、更粗）
        ctk.CTkLabel(
            title_col, text=title,
            font=self._font(15, True), anchor="w",
        ).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                title_col,
                text=subtitle,
                font=self._font(11),
                text_color=_C["subtle"],
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        body = ctk.CTkFrame(outer, fg_color="transparent")

        if collapsible:
            switch_var = tk.BooleanVar(value=expanded)

            def _toggle(*_args) -> None:
                if switch_var.get():
                    body.pack(fill="x", padx=(4, 0))
                else:
                    body.pack_forget()

            ctk.CTkSwitch(
                head,
                text="展开",
                variable=switch_var,
                command=_toggle,
                font=self._font(12),
                width=64,
                progress_color=_C["accent"],
            ).pack(side="right")
            if expanded:
                body.pack(fill="x", padx=(4, 0))
        else:
            body.pack(fill="x", padx=(4, 0))

        return body

    def _build_ui(self) -> None:
        # —— 顶栏 ——
        header = ctk.CTkFrame(self._container, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 6))

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(brand, text=f"📐 {APP_TITLE}", font=self._font(18, True), anchor="w").pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")
        self.conn_badge = ctk.CTkLabel(
            right, textvariable=self.conn_state_var, font=self._font(12, True), text_color=_C["idle"]
        )
        self.conn_badge.pack(side="left", padx=(0, 8))

        scroll = ctk.CTkScrollableFrame(self._container, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        # —— 连接 ——
        conn = self._section(scroll, "PCDMIS 连接", subtitle="与 PCDMIS 同权限运行（都普通或都管理员）")
        row1 = ctk.CTkFrame(conn, fg_color="transparent")
        row1.pack(fill="x")
        self._btn_primary(row1, "连接 PCDMIS", self._connect, width=116, height=32).pack(side="left")
        self._btn_muted(row1, "断开", self._disconnect, width=64, height=32).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(row1, textvariable=self.conn_var, font=self._font(12)).pack(side="left", padx=10)
        ctk.CTkLabel(row1, textvariable=self.perm_var, font=self._font(10), text_color=_C["subtle"]).pack(
            side="right"
        )

        info = ctk.CTkFrame(conn, fg_color=_C["hint_bg"], corner_radius=6)
        info.pack(fill="x", pady=(8, 0))
        inner = ctk.CTkFrame(info, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=7)
        ctk.CTkLabel(inner, text="当前程序", font=self._font(10), text_color=_C["subtle"]).pack(side="left")
        ctk.CTkLabel(inner, textvariable=self.part_var, font=self._font(12, True)).pack(side="left", padx=8)

        # —— 导出（主流程强调）——
        export = self._section(
            scroll,
            "导出 Excel",
            subtitle="读取当前已测数据，生成 PC-DMIS 列格式报告",
            accent=True,
        )
        dir_row = ctk.CTkFrame(export, fg_color="transparent")
        dir_row.pack(fill="x")
        ctk.CTkLabel(dir_row, text="输出目录", width=64, anchor="w", font=self._font(11)).pack(side="left")
        ctk.CTkEntry(dir_row, textvariable=self.export_dir_var, height=30, corner_radius=5).pack(
            side="left", fill="x", expand=True, padx=6
        )
        self._btn_muted(dir_row, "浏览…", self._pick_export_dir, width=68, height=30).pack(side="right")

        scope = ctk.CTkFrame(export, fg_color="transparent")
        scope.pack(fill="x", pady=(8, 0))
        self._checkbox(
            scope,
            text="仅报告窗口数据",
            variable=self.report_only_var,
            command=self._save_settings_from_ui,
        ).pack(side="left")
        self._checkbox(
            scope,
            text="仅 Mark 命令",
            variable=self.require_marked_var,
            command=self._save_settings_from_ui,
        ).pack(side="left", padx=(12, 0))

        btn_row = ctk.CTkFrame(export, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))
        self._btn_primary(btn_row, "一键导出 Excel", self._export_excel, width=150, height=34).pack(side="left")
        self._btn_accent(btn_row, "部署工具栏启动器", self._deploy_toolbar, width=150, height=34).pack(
            side="left", padx=(8, 0)
        )
        self._btn_muted(btn_row, "打开启动器目录", self._open_launcher_dir, width=118, height=34).pack(
            side="left", padx=(8, 0)
        )

        ctk.CTkLabel(
            export,
            text="工具栏启动器：挂到 PC-DMIS 自定义按钮后，测完一点即按「仅 Mark」导出。完整列：NOMINAL / MEAS / ±TOL / BONUS / DEV / OUTTOL",
            font=self._font(10),
            text_color=_C["subtle"],
            anchor="w",
        ).pack(fill="x", pady=(7, 0))

        # —— 出货表 ——
        form = self._section(
            scroll,
            "出货检测表填入",
            subtitle="按序号只写 CMM 行，多件续列；先预览再另存",
            collapsible=True,
            expanded=True,
        )
        form_row1 = ctk.CTkFrame(form, fg_color="transparent")
        form_row1.pack(fill="x")
        self._checkbox(
            form_row1,
            text="启用填入",
            variable=self.form_fill_var,
            command=self._save_settings_from_ui,
            width=100,
        ).pack(side="left")
        ctk.CTkEntry(form_row1, textvariable=self.form_path_var, height=30, corner_radius=5).pack(
            side="left", fill="x", expand=True, padx=6
        )
        self._btn_muted(form_row1, "选出货表…", self._pick_form, width=96, height=30).pack(side="right")

        form_row2 = ctk.CTkFrame(form, fg_color="transparent")
        form_row2.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(form_row2, text="尺寸前缀", width=64, anchor="w", font=self._font(11)).pack(side="left")
        ctk.CTkEntry(form_row2, textvariable=self.id_prefixes_var, width=180, height=30, corner_radius=5).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkLabel(form_row2, text="CMM代号", width=64, anchor="w", font=self._font(11)).pack(side="left")
        ctk.CTkEntry(form_row2, textvariable=self.cmm_codes_var, width=84, height=30, corner_radius=5).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkLabel(form_row2, text="写入列", width=50, anchor="w", font=self._font(11)).pack(side="left")
        ctk.CTkEntry(form_row2, textvariable=self.target_col_var, width=64, height=30, corner_radius=5).pack(
            side="left"
        )
        ctk.CTkLabel(form_row2, text="auto / H / I…", font=self._font(10), text_color=_C["subtle"]).pack(
            side="left", padx=6
        )

        form_row3 = ctk.CTkFrame(form, fg_color="transparent")
        form_row3.pack(fill="x", pady=(8, 0))
        self._checkbox(
            form_row3,
            text="接着上次结果填入",
            variable=self.chain_from_last_var,
            command=self._save_settings_from_ui,
        ).pack(side="left")
        self._btn_muted(form_row3, "清除续填", self._clear_last_fill, width=90, height=30).pack(
            side="left", padx=10
        )
        ctk.CTkLabel(
            form_row3, textvariable=self.last_fill_var, font=self._font(11), text_color=_C["subtle"]
        ).pack(side="left", fill="x", expand=True)

        form_row_piece = ctk.CTkFrame(form, fg_color="transparent")
        form_row_piece.pack(fill="x", pady=(8, 0))
        self._checkbox(
            form_row_piece,
            text="写入件号",
            variable=self.write_piece_id_var,
            command=self._save_settings_from_ui,
            width=110,
        ).pack(side="left")
        ctk.CTkEntry(
            form_row_piece,
            textvariable=self.piece_id_var,
            placeholder_text="送检件号，如 721-001（空则用 PCDMIS 序列号）",
            height=30,
            corner_radius=5,
        ).pack(side="left", fill="x", expand=True, padx=6)
        self._checkbox(
            form_row_piece,
            text="核对规格/名义",
            variable=self.nominal_check_var,
            command=self._save_settings_from_ui,
            width=130,
        ).pack(side="right")

        form_row_map = ctk.CTkFrame(form, fg_color="transparent")
        form_row_map.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(form_row_map, text="手工对照", width=64, anchor="w", font=self._font(11)).pack(side="left")
        ctk.CTkEntry(
            form_row_map,
            textvariable=self.manual_map_var,
            placeholder_text=MANUAL_MAP_PLACEHOLDER,
            height=30,
            corner_radius=5,
        ).pack(side="left", fill="x", expand=True, padx=6)
        self._btn_muted(form_row_map, "恢复默认", self._restore_form_defaults, width=82, height=30).pack(
            side="right"
        )

        form_row4 = ctk.CTkFrame(form, fg_color="transparent")
        form_row4.pack(fill="x", pady=(10, 0))
        self._btn_accent(form_row4, "填入出货检测表", self._fill_inspection_form, width=150, height=34).pack(
            side="left"
        )
        ctk.CTkLabel(
            form_row4,
            text="先预览匹配 → 确认另存；续填自动下一空列（不覆盖已有数据）",
            font=self._font(10),
            text_color=_C["subtle"],
        ).pack(side="left", padx=10)

        # —— 植入 ——
        inject = self._section(
            scroll,
            "PRG 命令植入",
            subtitle="测量中可把光标放到 PC2XL_EXPORT → 从光标执行（CSV）",
            collapsible=True,
            expanded=True,
        )
        self._hint(
            inject,
            "在程序末尾插入导出命令。适合边测边出 CSV；完整 xlsx 请用上方「一键导出」或 PC-DMIS 工具栏。",
        )
        inj_row = ctk.CTkFrame(inject, fg_color="transparent")
        inj_row.pack(fill="x", pady=(4, 0))
        self._btn_muted(inj_row, "部署 BAS 脚本", self._deploy_bas, width=116, height=32).pack(side="left")
        self._btn_warn(inj_row, "植入 / 更新导出命令", self._inject_command, width=152, height=32).pack(
            side="left", padx=6
        )
        self._btn_muted(inj_row, "检查是否已植入", self._check_inject, width=116, height=32).pack(side="left")

        # —— 说明 ——
        help_body = self._section(
            scroll,
            "PCDMIS 内执行说明",
            collapsible=True,
            expanded=True,
        )
        help_text = ctk.CTkTextbox(
            help_body,
            height=210,
            font=ctk.CTkFont(family="Consolas", size=14),
            wrap="word",
            corner_radius=6,
            border_width=1,
            border_color=_C["card_border"],
        )
        help_text.pack(fill="both", expand=True)
        help_text.insert(
            "1.0",
            "【工具栏一键出 Excel】\n"
            "1. 点击「部署工具栏启动器」（写入 LocalAppData 下 vbs/bat）。\n"
            "2. PC-DMIS：视图 → 工具栏 → 自定义 → 创建项目 → 选 cm2xl_toolbar_export.vbs。\n"
            "3. 从「用户自定义命令」拖到工具栏。测完点该按钮即可。\n"
            "4. cm2xl 跳到本页并按「仅 Mark 命令」自动导出 xlsx。已打开则唤醒再导。\n\n"
            "【PRG 植入 CSV】\n"
            "1. 点击「植入 / 更新导出命令」后保存 PRG。\n"
            "2. Edit 窗口光标放在 PC2XL_EXPORT → 文件 → 部分执行 → 从光标执行。\n"
            "3. 脚本导出 CSV；完整 xlsx 请用工具栏或上方「一键导出」。\n\n"
            "注意：PC-DMIS Pro 无 BASIC，工具栏请用 vbs/bat（不要用 .bas）。\n"
            "工具与 PCDMIS 须同为普通用户或同为管理员运行。",
        )
        help_text.configure(state="disabled")

        # —— 底栏 ——
        foot = ctk.CTkFrame(
            self._container,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
            height=26,
        )
        foot.pack(fill="x", padx=14, pady=(0, 2))
        foot_inner = ctk.CTkFrame(foot, fg_color="transparent")
        foot_inner.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(foot_inner, textvariable=self.progress_var, font=self._font(11), text_color=_C["subtle"]).pack(
            side="left"
        )
        ctk.CTkLabel(foot_inner, textvariable=self.status_var, font=self._font(11, True)).pack(side="right")

        self.progress = ctk.CTkProgressBar(
            self._container,
            mode="indeterminate",
            height=3,
            corner_radius=1,
            progress_color=_C["accent"],
        )
        self.progress.pack(fill="x", padx=14, pady=(0, 4))
        self.progress.set(0)

    def _perm_text(self) -> str:
        """状态栏权限/运行状态字符串。

        两次优化：
        1. 只 spawn 一次 tasklist：原实现用 is_pcdmis_running() + 两次
           is_pcdmis_elevated()，内部各调 get_pcdmis_pid()，同一次查询 spawn
           3 个 tasklist.exe（实测 ~190ms/次，合计 ~560ms 阻塞主线程）。
        2. 短 TTL 缓存：本方法被 mount / 连接 / 断开 / watcher tick 反复调用，
           缓存后 2s 内的重复调用零成本。
        """
        now = time.monotonic()
        if self._perm_text_cache is not None and now - self._perm_text_cache[0] < self._perm_text_ttl:
            return self._perm_text_cache[1]

        tool = admin_status_text()
        pid = get_pcdmis_pid()
        if pid is None:
            text = f"{tool}  ·  PCDMIS 未运行"
        else:
            elevated = is_process_elevated(pid)
            if elevated is True:
                pcd = "PCDMIS:管理员"
            elif elevated is False:
                pcd = "PCDMIS:普通"
            else:  # None：查不到 token，保留不确定状态而不是误报"普通"
                pcd = "PCDMIS:?"
            match = "匹配 ✓" if (elevated is not None and elevated == is_admin()) else "权限?"
            text = f"{tool}  ·  {pcd}  ·  {match}"

        self._perm_text_cache = (now, text)
        return text

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

        CancellableWorker().start(work)

    def _on_connected(self, info) -> None:
        self._set_busy(False)
        self.perm_var.set(self._perm_text())
        audit(
            "pcdmis_connect",
            connected=info.connected,
            prog_id=self.connector.prog_id,
            version=self.connector.version,
        )
        if info.connected:
            self.conn_var.set(f"{info.source} · {info.version}")
            self.part_var.set(self.connector.get_active_part_name() or "—")
            self.status_var.set("已连接")
            self._set_conn_visual("ok")
            self._sync_shell_pcdmis_status()
            if self._wizard_frame and not self._wizard_done:
                self._dismiss_wizard()
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
        audit("pcdmis_disconnect")
        self.conn_var.set("未连接")
        self.part_var.set("—")
        self.status_var.set("已断开")
        self.perm_var.set(self._perm_text())
        self._set_conn_visual("idle")
        self._sync_shell_pcdmis_status()

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
        try:
            self.perm_var.set(self._perm_text())
            if self.connector.is_connected():
                ver = self.connector.version or ""
                pid = self.connector.prog_id or ""
                self.conn_var.set(
                    f"{self.connector.name} · {ver}" if ver else (pid or "已连接")
                )
                self.part_var.set(self.connector.get_active_part_name() or "—")
                self._set_conn_visual("ok")
            else:
                self._set_conn_visual("idle")
        except Exception:
            # 连接状态刷新失败不影响主流程，仅记录日志
            logger.exception("刷新连接状态 UI 失败")
        else:
            self._sync_shell_pcdmis_status()

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

        out_dir = Path(self.export_dir_var.get().strip() or paths.pc_excel_reports)
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
                info = self.connector.ensure_session()
                if not info.connected:
                    from utils.error_codes import ErrorCode, ToolboxError

                    raise ToolboxError(
                        ErrorCode.PCDMIS_CONNECT_FAIL,
                        info.message or "无法连接 PCDMIS COM",
                    )
                records = self.connector.extract_features(
                    progress_cb=None,
                    scope=export_scope,
                    require_marked=require_marked,
                )
                if not records:
                    from utils.error_codes import ErrorCode, ToolboxError

                    raise ToolboxError(
                        ErrorCode.PCDMIS_NO_DATA,
                        "未提取到可填入的测量数据（0 条）。",
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
                logger.exception("填入失败: %s", exc)
                self.root.after(
                    0,
                    lambda: self._on_error("填入失败", format_user_error("填入失败", exc, with_trace=True)),
                )

        CancellableWorker().start(work)

    def _on_fill_preview_ready(self, records, form_path, out_dir, piece_id, preview) -> None:
        self._set_busy(False)
        self.status_var.set("待确认填入")
        if preview.will_fill <= 0:
            if preview.cmm_rows <= 0:
                extra = "表中没有识别到 CMM 行（检具列须为 A 或 CMM）。"
            elif preview.extract_count <= 0:
                extra = "未从 PCDMIS 提取到可匹配序号。"
            else:
                extra = "提取到的序号与表中 CMM 行对不上。"
            messagebox.showwarning(
                "没有可填入的数据",
                format_user_error(
                    "没有可填入的数据",
                    "预览结果：预计填入 0 格。\n"
                    + preview.summary_text()
                    + "\n\n"
                    + extra,
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
                logger.exception("填入写入失败: %s", exc)
                self.root.after(
                    0,
                    lambda: self._on_error("填入失败", format_user_error("填入失败", exc, with_trace=True)),
                )

        CancellableWorker().start(work)

    def _on_fill_ok(self, result, extract_count: int) -> None:
        self._set_busy(False)
        self.status_var.set(f"已填入 {result.filled} 格")
        audit("pcdmis_form_fill", filled=result.filled, output=str(result.output_path))
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
        apply_window_icon(win)
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
            font=ctk.CTkFont(family="Consolas", size=14),
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

    def request_auto_export(self) -> None:
        """工具栏启动：稍等界面就绪后走与按钮相同的一键导出（含仅 Mark）。"""
        self.root.after(200, self._export_excel)

    def _export_excel(self) -> None:
        if self._busy:
            return
        self._save_settings_from_ui()
        out_dir = Path(self.export_dir_var.get().strip() or paths.pc_excel_reports)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "输出目录无效",
                format_user_error("输出目录无效", f"无法创建输出目录：{out_dir}\n{exc}"),
            )
            return

        export_scope = self.settings.export_scope
        require_marked = self.settings.require_marked
        filename_pattern = self.settings.filename_pattern
        self._set_busy(True, "正在提取并导出…")
        self.status_var.set("导出中")

        def work():
            try:
                info = self.connector.ensure_session()
                if not info.connected:
                    from utils.error_codes import ErrorCode, ToolboxError

                    raise ToolboxError(
                        ErrorCode.PCDMIS_CONNECT_FAIL,
                        info.message or "无法连接 PCDMIS COM",
                    )
                records = self.connector.extract_features(
                    progress_cb=None,
                    scope=export_scope,
                    require_marked=require_marked,
                )
                if not records:
                    from utils.error_codes import ErrorCode, ToolboxError

                    raise ToolboxError(
                        ErrorCode.PCDMIS_NO_DATA,
                        "未提取到可导出的测量数据（0 条）。",
                    )
                tol = ToleranceConfig.from_dict(self.settings.tolerance)
                apply_tolerance(records, tol)
                header = self.connector.get_report_header_info()
                filename = build_export_filename(
                    header.part_name or header.program_name or "report",
                    filename_pattern,
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
                logger.exception("导出失败: %s", exc)
                self.root.after(
                    0,
                    lambda: self._on_error("导出失败", format_user_error("导出失败", exc, with_trace=True)),
                )

        CancellableWorker().start(work)

    def _on_export_ok(self, path: Path, count: int) -> None:
        self._set_busy(False)
        self.status_var.set(f"已导出 {count} 条")
        audit("pcdmis_export", count=count, path=str(path))
        self._refresh_connection_ui()
        messagebox.showinfo("导出完成", f"共 {count} 条数据\n\n{path}")

    def _deploy_bas(self) -> None:
        try:
            path = deploy_bas_script()
            launcher = deploy_toolbar_launcher()
            target = resolve_toolbar_argv()[0]
            audit("pcdmis_bas_deploy", path=str(path), launcher=str(launcher), target=target)
            messagebox.showinfo(
                "部署完成",
                f"脚本已更新:\n{path}\n\n工具栏将启动：\n{target}\n\n启动器:\n{launcher}",
            )
        except Exception as exc:
            logger.exception("BAS 部署失败: %s", exc)
            messagebox.showerror("部署失败", format_user_error("部署失败", exc))

    def _deploy_toolbar(self) -> None:
        try:
            path = deploy_toolbar_launcher()
            target = resolve_toolbar_argv()[0]
            audit("pcdmis_toolbar_deploy", path=str(path), target=target)
            messagebox.showinfo(
                "工具栏启动器已部署",
                INSTALL_STEPS + f"\n\n将启动：\n{target}\n\n启动器:\n{path}",
            )
        except Exception as exc:
            logger.exception("工具栏启动器部署失败: %s", exc)
            messagebox.showerror("部署失败", format_user_error("部署失败", exc))

    def _open_launcher_dir(self) -> None:
        folder = paths.bas_deploy_dir
        folder.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.startfile(folder)  # noqa: S606 — 打开本机资源管理器
        except Exception as exc:
            messagebox.showerror("无法打开目录", format_user_error("无法打开目录", exc))

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
                from ..connector.com_detector import com_apartment, dispatch_pcdmis

                with com_apartment():
                    app = dispatch_pcdmis(self.connector.prog_id)
                    result = inject_export_command(app, prog_id=self.connector.prog_id)
                self.root.after(0, lambda: self._on_inject_done(result))
            except Exception as exc:
                logger.exception("植入失败: %s", exc)
                self.root.after(
                    0,
                    lambda: self._on_error("植入失败", format_user_error("植入失败", exc, with_trace=True)),
                )

        CancellableWorker().start(work)

    def _on_inject_done(self, result) -> None:
        self._set_busy(False)
        audit("pcdmis_inject", success=result.success, already_exists=result.already_exists)
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
            from ..connector.com_detector import com_apartment, dispatch_pcdmis

            with com_apartment():
                app = dispatch_pcdmis(self.connector.prog_id)
                result = check_export_command(app, prog_id=self.connector.prog_id)
            if result.success:
                messagebox.showinfo("检查结果", result.message)
            else:
                messagebox.showwarning("检查结果", result.message)
        except Exception as exc:
            messagebox.showerror("检查失败", format_user_error("检查失败", exc))

    def _on_error(self, title: str, msg: str) -> None:
        # 所有调用方已通过 format_user_error 格式化，此处直接使用
        self._set_busy(False)
        self.status_var.set(title)
        messagebox.showerror(title, msg)

    def _start_status_watcher(self) -> None:
        """后台每 30 秒检测 COM 会话是否仍有效（ARCHITECTURE 3.19）。"""
        self._stop_status_watcher()
        self._status_watcher_running = True
        self._schedule_status_watch()

    def _stop_status_watcher(self) -> None:
        self._status_watcher_running = False
        for attr in ("_status_watcher_after_id", "_status_watcher_tick_id"):
            after_id = getattr(self, attr, None)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _schedule_status_watch(self) -> None:
        # 本方法由 30s timer 调起时，说明上一个 _status_watcher_after_id 已触发，
        # 先置 None 避免 _stop_status_watcher() 去 after_cancel 一个已执行过的 id。
        self._status_watcher_after_id = None
        if not self._status_watcher_running:
            return
        # 首次 tick 推一帧：after(0) 意思是"当前 UI 事件处理完后下一轮事件循环"，
        # 不是延迟 30 秒。让模块切换立即返回，慢探测在界面切过去之后再跑。
        # 两个 id 分开存，_stop_status_watcher() 才能各自取消。
        self._status_watcher_tick_id = self.root.after(0, self._status_watcher_tick)
        self._status_watcher_after_id = self.root.after(30_000, self._schedule_status_watch)

    def _status_watcher_tick(self) -> None:
        # 已被执行：id 失效，置 None 让 _stop_status_watcher() 不会尝试取消旧 id
        self._status_watcher_tick_id = None
        if not self._status_watcher_running:
            return
        if self._busy:
            return
        try:
            if self.connector.is_connected() and not self.connector.session_alive():
                self.connector.disconnect()
            self._refresh_connection_ui()
            self._sync_shell_pcdmis_status()
        except Exception as exc:
            logger.debug("PCDMIS 状态轮询异常: %s", exc)

    def _refresh_conn_status(self) -> None:
        """模块激活时静默刷新连接状态（不弹错误框）。

        已连接但 COM 会话失效（测第二件常见）时标记断开；
        未连接时保持现状，由用户点「连接」或导出时自动重连。
        """
        if self.connector.is_connected():
            if not self.connector.session_alive():
                self.connector.disconnect()
                self.conn_var.set("未连接")
                self.part_var.set("—")
                self._set_conn_visual("idle")
                self._sync_shell_pcdmis_status()
                return
        self._refresh_connection_ui()

    def _on_close(self) -> None:
        self._stop_status_watcher()
        self._save_settings_from_ui()
        self.connector.disconnect()
        # 挂载模式下 root 属于 Shell，不能 destroy；独立运行时才关窗
        if self._owns_root:
            self.root.destroy()

    def run(self) -> None:
        ok, msg = check_elevation_match()
        if not ok and msg:
            messagebox.showwarning("权限提示", msg)
        if is_pcdmis_running() and not self.connector.is_connected():
            self.root.after(400, self._connect)
        if self._owns_root:
            self._start_status_watcher()
        if self._owns_root:
            self.root.mainloop()


def run_app() -> None:
    MainWindow().run()
