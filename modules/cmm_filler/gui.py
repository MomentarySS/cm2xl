"""
CMM 报告自动填充工具 - GUI（CustomTkinter 现代界面）
功能：拖拽文件、OCR 识别预览（可剔除误识别项）、NG 超差统计高亮
"""
import os
import re
import sys
import threading
import json
from collections import defaultdict
import customtkinter as ctk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from pathlib import Path

from .core.filler import CMMReportFiller, load_settings, save_settings
from .core.parse_measurements import measure_dict_key
from .core.sub_item_conflict import (
    SKIP_SUB_ITEM,
    WORST_NG_SUB_ITEM,
    candidate_option_label,
    conflict_summary_line,
)
from .core.report_profile import list_profiles, load_profile, user_profiles_dir, parse_prefix_text
from .app_meta import __version__, APP_TITLE, APP_DESCRIPTION
from utils.paths import paths
from utils.app_icon import apply_window_icon
from utils.audit import audit
from utils.threading_utils import CancellableWorker
from toolbox.protocol import ModuleProtocol


class CMMFillerGUI:
    COLORS = {
        'err': '#e23b3b',
        'ok': '#2e9e4f',
        'warn': '#e6a23c',
        'ng': '#e23b3b',
    }

    def __init__(self, parent=None):
        # ── 挂载模式支持 ──────────────────────────────────────────────
        # parent=None  → 自建根窗口（独立运行，行为不变）
        # parent=Frame → 挂载到传入容器（toolbox 集成）
        self._owns_root = parent is None
        if self._owns_root:
            self.root = ctk.CTk()
            self.root.title(f'{APP_TITLE} v{__version__}')
            self.root.geometry('940x690')
            self.root.minsize(820, 600)
        else:
            # parent 是 CTkFrame（Shell 挂载点），self.root 在两种模式下
            # 都必须指向 CTk window，以保持 .after() / clipboard_*/protocol 等
            # API 的一致性；_container 才是真正的 UI 构建目标。
            self.root = parent.winfo_toplevel()
        self._container = parent if parent is not None else self.root
        # 两种模式都必须初始化 Tkdnd（_require 注册 tkdnd::drop_target 等命令），
        # 挂载模式错过此步会导致任何 drop_target_register 抛 TclError。
        try:
            self.root.TkdndVersion = TkinterDnD._require(self.root)
        except Exception as e:
            import logging
            logging.getLogger('CMMFiller').warning(f'[CMMFiller] TkinterDnD 初始化失败，拖放功能将不可用: {e}')

        config = self._load_config()
        settings = load_settings()

        tpl = settings.get('template_path') or config.get('template_path', '')
        if tpl and os.path.isfile(tpl):
            self.default_template = tpl
        else:
            # 尝试从 paths 获取默认模板
            default_tpl = paths.data_dir / 'cmm_filler' / 'template.xlsx'
            if default_tpl.is_file():
                self.default_template = str(default_tpl)
            else:
                self.default_template = ''

        pdf = settings.get('pdf_folder', '')
        default_pdf = paths.data_dir / 'cmm_filler' / 'pdf'
        self.default_pdf_folder = pdf if pdf and os.path.isdir(pdf) else str(default_pdf)

        out = settings.get('output_folder', '')
        default_out = paths.data_dir / 'cmm_filler' / 'output'
        self.default_output_folder = out if out and os.path.isdir(out) else str(default_out)
        if self.default_output_folder:
            os.makedirs(self.default_output_folder, exist_ok=True)

        self.default_report_profile = settings.get('report_profile', 'default')
        raw_prefixes = settings.get('custom_item_prefixes', '')
        if isinstance(raw_prefixes, list):
            self.default_custom_prefixes = ', '.join(raw_prefixes)
        else:
            self.default_custom_prefixes = raw_prefixes or ''
        self.default_ocr_roi = settings.get('ocr_roi') or {
            'top': 0, 'left': 0, 'bottom': 0, 'right': 0,
        }

        self.filler = None
        self.processing = False
        self._worker = None                 # 当前工作线程（供关闭时取消）
        self._preview_widgets = []          # [{stem, num, var, measured_var, original_measured}]
        self._preview_window = None
        self._summary_files = []            # 汇总导出选中的 PDF（list[Path]，保序）

        self._build_ui()
        if self._owns_root:
            self.root.protocol('WM_DELETE_WINDOW', self._on_close)
            self._maybe_show_first_run_guide()

    # ── 配置 / 设置 ─────────────────────────────
    def _load_config(self):
        config_path = str(paths.config_dir / 'cmm_filler' / 'template_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_paths(self):
        roi = self._read_roi_from_ui()
        save_settings({
            'template_path': self.template_var.get().strip(),
            'pdf_folder': self.pdf_var.get().strip(),
            'output_folder': self.output_var.get().strip(),
            'report_profile': self._get_selected_profile_name(),
            'custom_item_prefixes': self._read_custom_prefixes_from_ui(),
            'ocr_roi': roi,
        })

    def _get_selected_profile_name(self) -> str:
        label = self.profile_var.get()
        for p in self._profile_options:
            if p['label'] == label:
                return p['name']
        return 'default'

    def _read_roi_from_ui(self) -> dict:
        def _pct(var):
            try:
                return max(0.0, min(100.0, float(var.get()))) / 100.0
            except (ValueError, TypeError):
                return 0.0
        return {
            'top': _pct(self.roi_top_var),
            'bottom': _pct(self.roi_bottom_var),
            'left': _pct(self.roi_left_var),
            'right': _pct(self.roi_right_var),
        }

    def _read_custom_prefixes_from_ui(self) -> str:
        return self.custom_prefix_var.get().strip()

    def _read_custom_prefixes_list(self) -> list[str]:
        return parse_prefix_text(self._read_custom_prefixes_from_ui())

    def _create_filler(self, template: str) -> CMMReportFiller:
        return CMMReportFiller(
            template, dpi=300,
            report_profile=self._get_selected_profile_name(),
            ocr_roi=self._read_roi_from_ui(),
            custom_item_prefixes=self._read_custom_prefixes_list(),
        )

    def _on_close(self):
        if self.processing:
            self._cancel_worker()
        if not self.processing:
            self._save_paths()
        if self._owns_root:
            self.root.destroy()

    def _on_profile_changed(self, _choice=None):
        """切换 Profile 时自动填充推荐 ROI。"""
        name = self._get_selected_profile_name()
        profile = load_profile(name)
        roi = profile.get('ocr_roi', {})
        self.roi_top_var.set(str(int(roi.get('top', 0) * 100)))
        self.roi_bottom_var.set(str(int(roi.get('bottom', 0) * 100)))
        self.roi_left_var.set(str(int(roi.get('left', 0) * 100)))
        self.roi_right_var.set(str(int(roi.get('right', 0) * 100)))
        self._save_paths()

    def _open_user_profiles_dir(self):
        """打开用户自定义 Profile 目录。"""
        import subprocess
        path = user_profiles_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except OSError:
            subprocess.Popen(['explorer', str(path)])

    # ── UI 构建 ─────────────────────────────────
    def _build_ui(self):
        header = ctk.CTkFrame(self._container, fg_color="transparent")
        header.pack(pady=(8, 2), padx=14, fill='x')

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill='x')

        ctk.CTkLabel(
            title_row,
            text='📊 PDF报告填充',
            font=ctk.CTkFont(size=20, weight='bold'),
        ).pack(side='left')

        self.tabs = ctk.CTkTabview(self._container)
        self.tabs.pack(pady=(4, 0), padx=8, fill='both', expand=True)
        self.tab_process = self.tabs.add('处理')
        self.tab_summary = self.tabs.add('汇总导出')
        self.tab_ng = self.tabs.add('NG 分析')
        self.tab_result = self.tabs.add('结果')

        self._build_process_tab()
        self._build_summary_tab()
        self._build_ng_tab()
        self._build_result_tab()
        self._show_welcome()

    def _build_process_tab(self):
        t = self.tab_process

        config_card = ctk.CTkFrame(t, fg_color="transparent")
        config_card.pack(pady=(8, 6), padx=10, fill='x')

        ctk.CTkLabel(
            config_card, text='文件配置',
            font=ctk.CTkFont(size=17, weight='bold'),
        ).pack(anchor='w', padx=10, pady=(8, 4))

        # 模板行（B 方案：只读显示 + 改去向导；解决 P3-10 重复设置问题）
        tpl_frame = ctk.CTkFrame(config_card, fg_color="transparent")
        tpl_frame.pack(pady=2, padx=10, fill='x')
        ctk.CTkLabel(tpl_frame, text='📄 Excel 模板:', width=90, anchor='w').pack(side='left')
        self.template_var = ctk.StringVar(value=self.default_template)
        # 单独的展示用 var：实时跟踪 template_var（外部代码改 template_var 也会触发刷新）
        self.template_display_var = ctk.StringVar(value=self._format_template_label())
        self.template_var.trace_add(
            'write', lambda *_: self.template_display_var.set(self._format_template_label())
        )
        self.template_label = ctk.CTkLabel(
            tpl_frame, textvariable=self.template_display_var, height=30, anchor='w',
        )
        self.template_label.pack(side='left', fill='x', expand=True, padx=(0, 6))
        # 不再绑 DnD / 不再放「浏览」按钮：模板唯一改的入口是向导
        ctk.CTkButton(tpl_frame, text='📂 更换', width=72, height=30, command=self._open_wizard).pack(side='left')

        # PDF 行（支持拖拽文件夹/文件）
        pdf_frame = ctk.CTkFrame(config_card, fg_color="transparent")
        pdf_frame.pack(pady=2, padx=10, fill='x')
        ctk.CTkLabel(pdf_frame, text='📁 PDF 文件夹:', width=90, anchor='w').pack(side='left')
        self.pdf_var = ctk.StringVar(value=self.default_pdf_folder)
        self.pdf_entry = ctk.CTkEntry(pdf_frame, textvariable=self.pdf_var, height=30)
        self.pdf_entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
        self._setup_dnd(self.pdf_entry, 'pdf')
        ctk.CTkButton(pdf_frame, text='浏览', width=52, height=30, command=self._browse_pdf).pack(side='left')

        # 输出行
        out_frame = ctk.CTkFrame(config_card, fg_color="transparent")
        out_frame.pack(pady=2, padx=10, fill='x')
        ctk.CTkLabel(out_frame, text='📦 输出文件夹:', width=90, anchor='w').pack(side='left')
        self.output_var = ctk.StringVar(value=self.default_output_folder)
        self.output_entry = ctk.CTkEntry(out_frame, textvariable=self.output_var, height=30)
        self.output_entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
        self._setup_dnd(self.output_entry, 'output')
        ctk.CTkButton(out_frame, text='浏览', width=52, height=30, command=self._browse_output).pack(side='left')

        # 报告 Profile
        profile_frame = ctk.CTkFrame(config_card, fg_color="transparent")
        profile_frame.pack(pady=2, padx=10, fill='x')
        ctk.CTkLabel(profile_frame, text='📋 报告版式:', width=90, anchor='w').pack(side='left')
        self._profile_options = list_profiles()
        profile_labels = [p['label'] for p in self._profile_options]
        default_label = next(
            (p['label'] for p in self._profile_options if p['name'] == self.default_report_profile),
            profile_labels[0] if profile_labels else '默认',
        )
        self.profile_var = ctk.StringVar(value=default_label)
        self.profile_menu = ctk.CTkOptionMenu(
            profile_frame, variable=self.profile_var, values=profile_labels,
            width=220, command=self._on_profile_changed,
        )
        self.profile_menu.pack(side='left', padx=(0, 6))
        ctk.CTkLabel(
            profile_frame, text='切换后重新识别生效',
            font=ctk.CTkFont(size=12), text_color=('gray40', 'gray60'),
        ).pack(side='left')

        # 额外尺寸前缀（叠加在 Profile 之上）
        prefix_frame = ctk.CTkFrame(config_card, fg_color="transparent")
        prefix_frame.pack(pady=2, padx=10, fill='x')
        ctk.CTkLabel(prefix_frame, text='🏷️ 额外前缀:', width=90, anchor='w').pack(side='left')
        self.custom_prefix_var = ctk.StringVar(value=self.default_custom_prefixes)
        self.custom_prefix_entry = ctk.CTkEntry(
            prefix_frame, textvariable=self.custom_prefix_var, height=32,
            placeholder_text='如：检具, SIZE, GD&T（逗号分隔，叠加到 Profile）',
        )
        self.custom_prefix_entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
        ctk.CTkButton(
            prefix_frame, text='Profile 目录', width=82, height=30,
            command=self._open_user_profiles_dir,
        ).pack(side='left')
        ctk.CTkLabel(
            prefix_frame, text='可放自定义 JSON Profile',
            font=ctk.CTkFont(size=12), text_color=('gray40', 'gray60'),
        ).pack(side='left', padx=(8, 0))

        # OCR ROI 裁剪（百分比，裁去页眉/页脚等区域）
        roi_frame = ctk.CTkFrame(config_card, fg_color="transparent")
        roi_frame.pack(pady=2, padx=10, fill='x')
        ctk.CTkLabel(roi_frame, text='✂️ OCR 裁剪:', width=90, anchor='w').pack(side='left')
        roi = self.default_ocr_roi
        self.roi_top_var = ctk.StringVar(value=str(int(roi.get('top', 0) * 100)))
        self.roi_bottom_var = ctk.StringVar(value=str(int(roi.get('bottom', 0) * 100)))
        self.roi_left_var = ctk.StringVar(value=str(int(roi.get('left', 0) * 100)))
        self.roi_right_var = ctk.StringVar(value=str(int(roi.get('right', 0) * 100)))
        for label, var in [('上%', self.roi_top_var), ('下%', self.roi_bottom_var),
                           ('左%', self.roi_left_var), ('右%', self.roi_right_var)]:
            ctk.CTkLabel(roi_frame, text=label, width=28, anchor='e',
                         font=ctk.CTkFont(size=12)).pack(side='left', padx=(3, 0))
            ctk.CTkEntry(roi_frame, textvariable=var, width=38, height=26).pack(side='left', padx=(2, 4))
        ctk.CTkLabel(
            roi_frame, text='跳过页眉/页脚，仅 OCR 测量区',
            font=ctk.CTkFont(size=12), text_color=('gray40', 'gray60'),
        ).pack(side='left', padx=(4, 0))

        # 拖拽提示 + 预览开关
        tip_frame = ctk.CTkFrame(config_card, fg_color="transparent")
        tip_frame.pack(fill='x', padx=10, pady=(2, 8))
        ctk.CTkLabel(
            tip_frame, text='💡 可把文件夹直接拖到「PDF 文件夹」输入框上，省去选择目录',
            font=ctk.CTkFont(size=12), text_color=('gray40', 'gray60'),
        ).pack(side='left')
        self.preview_switch = ctk.CTkSwitch(tip_frame, text='处理前预览识别结果', width=120)
        self.preview_switch.pack(side='right')
        self.preview_switch.select()

        # 按钮
        btn_card = ctk.CTkFrame(t, fg_color="transparent")
        btn_card.pack(pady=4, padx=10, fill='x')
        btn_inner = ctk.CTkFrame(btn_card, fg_color="transparent")
        btn_inner.pack(pady=4, padx=0, fill='x')

        self.start_btn = ctk.CTkButton(
            btn_inner, text='▶ 开始处理',
            font=ctk.CTkFont(size=16, weight='bold'),
            height=40, command=self._start,
        )
        self.start_btn.pack(side='left', padx=(0, 8))

        ctk.CTkButton(btn_inner, text='导出标准模板', height=34, command=self._export_template).pack(side='left', padx=3)
        ctk.CTkButton(btn_inner, text='⚙ 模板配置', height=34, command=self._open_wizard).pack(side='left', padx=3)
        ctk.CTkButton(btn_inner, text='📂 输出路径', height=34, command=self._copy_output_path).pack(side='left', padx=3)
        ctk.CTkButton(btn_inner, text='📃 查看日志', height=34, command=self._show_log_window).pack(side='left', padx=3)
        ctk.CTkButton(btn_inner, text='🧹 清理 OCR 缓存', height=34, command=self._clear_ocr_cache).pack(side='left', padx=3)

        # 进度
        self.progress_frame = ctk.CTkFrame(t, fg_color="transparent")
        self.progress_frame.pack(fill='x', padx=14, pady=(2, 0))
        self.progress_label = ctk.CTkLabel(self.progress_frame, text='', font=ctk.CTkFont(size=13), anchor='w')
        self.progress_label.pack(fill='x')
        self.progress = ctk.CTkProgressBar(self.progress_frame, mode='determinate')
        self.progress.set(0)
        self.progress.pack(fill='x', pady=(2, 6))

        # 日志
        log_card = ctk.CTkFrame(t, fg_color="transparent")
        log_card.pack(pady=(0, 8), padx=10, fill='both', expand=True)
        ctk.CTkLabel(
            log_card, text='处理日志',
            font=ctk.CTkFont(size=17, weight='bold'),
        ).pack(anchor='w', padx=10, pady=(8, 3))
        self.log_text = ctk.CTkTextbox(log_card, font=ctk.CTkFont(family='Consolas', size=15), wrap='word')
        self.log_text.pack(pady=(0, 8), padx=10, fill='both', expand=True)
        self.log_text.configure(state='disabled')
        for tag, color in self.COLORS.items():
            self.log_text.tag_config(tag, foreground=color)

        self.status_bar = ctk.CTkLabel(t, text='就绪', font=ctk.CTkFont(size=13), anchor='w', padx=6)
        self.status_bar.pack(side='bottom', fill='x', pady=(0, 4))

    def _build_summary_tab(self):
        t = self.tab_summary

        # 选文件卡
        file_card = ctk.CTkFrame(t, fg_color="transparent")
        file_card.pack(pady=(8, 6), padx=14, fill='both', expand=True)
        ctk.CTkLabel(
            file_card, text='选择 PDF 文件',
            font=ctk.CTkFont(size=17, weight='bold'),
        ).pack(anchor='w', padx=14, pady=(12, 2))
        ctk.CTkLabel(
            file_card, text='💡 可一次多选；也可把多个 PDF 文件或文件夹直接拖到下方列表区域',
            font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        ).pack(anchor='w', padx=14)

        btn_row = ctk.CTkFrame(file_card, fg_color='transparent')
        btn_row.pack(fill='x', padx=14, pady=6)
        ctk.CTkButton(btn_row, text='＋ 添加 PDF', height=32, command=self._summary_add_files).pack(side='left')
        ctk.CTkButton(
            btn_row, text='清空', height=32, width=70, fg_color='transparent',
            border_width=1, text_color=('gray20', 'gray80'),
            command=self._summary_clear_files,
        ).pack(side='left', padx=(8, 0))
        self.summary_count_label = ctk.CTkLabel(btn_row, text='已选 0 个 PDF', font=ctk.CTkFont(size=14))
        self.summary_count_label.pack(side='right')

        self.summary_file_list = ctk.CTkScrollableFrame(file_card, fg_color='transparent')
        self.summary_file_list.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        self._setup_dnd(file_card, 'summary_files')
        self._setup_dnd(self.summary_file_list, 'summary_files')

        # 输出文件夹（与处理页共用同一设置）
        out_card = ctk.CTkFrame(t, fg_color='transparent')
        out_card.pack(pady=(0, 6), padx=14, fill='x')
        out_row = ctk.CTkFrame(out_card, fg_color='transparent')
        out_row.pack(pady=10, padx=14, fill='x')
        ctk.CTkLabel(out_row, text='📦 输出文件夹:', width=95, anchor='w').pack(side='left')
        out_entry = ctk.CTkEntry(out_row, textvariable=self.output_var, height=32)
        out_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self._setup_dnd(out_entry, 'output')
        ctk.CTkButton(out_row, text='浏览', width=56, height=32, command=self._browse_output).pack(side='left')

        # 生成按钮 + 本页专属进度
        run_card = ctk.CTkFrame(t, fg_color='transparent')
        run_card.pack(pady=(0, 10), padx=14, fill='x')
        run_inner = ctk.CTkFrame(run_card, fg_color='transparent')
        run_inner.pack(pady=10, padx=14, fill='x')
        self.summary_btn = ctk.CTkButton(
            run_inner, text='▶ 生成汇总 Excel',
            font=ctk.CTkFont(size=16, weight='bold'),
            height=40, command=self._summary_start,
        )
        self.summary_btn.pack(side='left')
        ctk.CTkLabel(
            run_inner, text='每个 PDF 一个 Sheet，全部数据汇总到一个 Excel',
            font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        ).pack(side='left', padx=10)

        self.summary_progress_label = ctk.CTkLabel(run_card, text='', font=ctk.CTkFont(size=13), anchor='w')
        self.summary_progress_label.pack(fill='x', padx=14)
        self.summary_progress = ctk.CTkProgressBar(run_card, mode='determinate')
        self.summary_progress.set(0)
        self.summary_progress.pack(fill='x', padx=14, pady=(2, 8))

    def _build_ng_tab(self):
        """NG 统计分析页"""
        t = self.tab_ng

        info_card = ctk.CTkFrame(t, fg_color="transparent")
        info_card.pack(pady=(8, 4), padx=14, fill='x')
        ctk.CTkLabel(
            info_card,
            text='批量分析 PDF 文件夹中各 FAI 项目的 NG 率排行，导出统计 Excel',
            font=ctk.CTkFont(size=14), text_color=('gray30', 'gray70'),
            wraplength=700, justify='left',
        ).pack(anchor='w', padx=14, pady=12)

        hint_card = ctk.CTkFrame(t, fg_color="transparent")
        hint_card.pack(pady=(0, 6), padx=14, fill='x')
        ctk.CTkLabel(
            hint_card,
            text='使用「处理」页的 PDF 文件夹和输出文件夹，以及当前报告版式 / OCR 裁剪设置',
            font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        ).pack(anchor='w', padx=14, pady=8)

        run_card = ctk.CTkFrame(t, fg_color="transparent")
        run_card.pack(pady=(0, 10), padx=14, fill='x')
        run_inner = ctk.CTkFrame(run_card, fg_color='transparent')
        run_inner.pack(pady=10, padx=14, fill='x')
        self.ng_btn = ctk.CTkButton(
            run_inner, text='▶ 导出 NG 统计 Excel',
            font=ctk.CTkFont(size=16, weight='bold'),
            height=40, command=self._ng_start,
        )
        self.ng_btn.pack(side='left')
        ctk.CTkLabel(
            run_inner, text='含 NG 排行、详细记录、FAI 明细 三个 Sheet',
            font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        ).pack(side='left', padx=10)

        self.ng_progress_label = ctk.CTkLabel(run_card, text='', font=ctk.CTkFont(size=13), anchor='w')
        self.ng_progress_label.pack(fill='x', padx=14)
        self.ng_progress = ctk.CTkProgressBar(run_card, mode='determinate')
        self.ng_progress.set(0)
        self.ng_progress.pack(fill='x', padx=14, pady=(2, 8))

        # 通用 PDF 表格提取（可选 pdfplumber）
        table_card = ctk.CTkFrame(t, fg_color="transparent")
        table_card.pack(pady=(0, 10), padx=14, fill='x')
        ctk.CTkLabel(
            table_card, text='通用表格提取（文字型 PDF）',
            font=ctk.CTkFont(size=17, weight='bold'),
        ).pack(anchor='w', padx=14, pady=(10, 4))
        ctk.CTkLabel(
            table_card,
            text='需安装 pdfplumber；扫描件请用 OCR 流程。从汇总导出页选中的 PDF 提取表格。',
            font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        ).pack(anchor='w', padx=14, pady=(0, 8))
        self.table_extract_btn = ctk.CTkButton(
            table_card, text='提取表格 → Excel', height=34,
            command=self._table_extract_start,
        )
        self.table_extract_btn.pack(anchor='w', padx=14, pady=(0, 12))

    def _ng_start(self):
        if self.processing:
            messagebox.showwarning('提示', '正在处理中，请稍候...')
            return
        valid = self._validate_paths(require_template=False)
        if not valid:
            return
        _, pdf_folder, output_folder = valid
        self._save_paths()
        audit('cmm_ng_analysis_start', pdf_folder=pdf_folder)
        self._begin_work()
        self.ng_btn.configure(state='disabled')
        self._start_worker(self._run_ng_analysis, pdf_folder, output_folder)

    def _run_ng_analysis(self, pdf_folder, output_folder):
        gui = self
        try:
            from .core.filler import set_gui_logger, TEMPLATE_PATH
            set_gui_logger(gui)
            template = gui.template_var.get().strip()
            if not template or not os.path.isfile(template):
                template = TEMPLATE_PATH
            gui.filler = gui._create_filler(template)
            gui.filler.cancel_check = gui._is_worker_cancelled
            summary = gui.filler.export_ng_analysis(
                pdf_folder, output_folder,
                progress_callback=lambda c, t, m: gui._update_ng_progress(c, t, m),
            )
            if gui._is_worker_cancelled():
                gui.root.after(0, lambda: gui._log('已取消 NG 分析'))
                return
            text = gui._format_ng_summary(summary)
            gui.root.after(0, lambda: gui._log(text))
            gui.root.after(0, lambda: gui._set_status('NG 分析完成'))
            gui.root.after(0, lambda t=text: messagebox.showinfo('NG 分析完成', t))
            gui.root.after(0, lambda: gui.tabs.set('结果'))
        except Exception as exc:
            err_msg = str(exc)
            gui.root.after(0, lambda msg=err_msg: gui._log(f'错误: {msg}'))
            gui.root.after(0, lambda msg=err_msg: messagebox.showerror('错误', msg))
        finally:
            gui.root.after(0, gui._processing_done)
            gui.root.after(0, lambda: gui.ng_btn.configure(state='normal'))

    def _update_ng_progress(self, current, total, message):
        self.root.after(0, lambda: self._set_ng_progress(current, total, message))

    def _set_ng_progress(self, current, total, message):
        if total > 0:
            self.ng_progress.set(current / total)
        self.ng_progress_label.configure(text=message or '')

    @staticmethod
    def _format_ng_summary(summary: dict) -> str:
        lines = [
            f'分析 PDF: {summary.get("processed_pdfs", 0)}/{summary.get("total_pdfs", 0)}',
            f'FAI 项目: {summary.get("fai_count", 0)}',
            f'NG 总次数: {summary.get("ng_count", 0)}',
        ]
        if summary.get('output_file'):
            lines.append(f'输出: {summary["output_file"]}')
        top = summary.get('top_ng', [])
        if top:
            lines.append('\nNG 率 TOP:')
            for i, r in enumerate(top, 1):
                lines.append(
                    f'  {i}. FAI_{r["num"]:02d} — NG {r["ng_count"]} ({r["ng_rate"]:.1%})'
                )
        fails = summary.get('failed_pdfs', [])
        if fails:
            lines.append(f'\n失败 {len(fails)} 个: ' + ', '.join(f['file'] for f in fails[:3]))
        return '\n'.join(lines)

    def _table_extract_start(self):
        if not self._summary_files:
            messagebox.showwarning('提示', '请先在「汇总导出」页添加 PDF 文件')
            return
        valid = self._validate_paths(require_template=False)
        if not valid:
            return
        _, _, output_folder = valid
        paths = [str(p) for p in self._summary_files]
        self._begin_work()
        self.table_extract_btn.configure(state='disabled')
        self._start_worker(self._run_table_extract, paths, output_folder)

    def _run_table_extract(self, pdf_paths, output_folder):
        gui = self
        try:
            from .core.pdf_table_import import batch_export_pdf_tables, pdfplumber_available
            if not pdfplumber_available():
                raise ImportError('pdfplumber 未安装。请运行: pip install pdfplumber')
            summary = batch_export_pdf_tables(pdf_paths, output_folder)
            text = (
                f'表格提取完成: {summary["processed"]}/{summary["total"]}\n'
                + '\n'.join(Path(f).name for f in summary.get('output_files', [])[:5])
            )
            gui.root.after(0, lambda: gui._log(text))
            gui.root.after(0, lambda t=text: messagebox.showinfo('表格提取完成', t))
        except Exception as exc:
            gui.root.after(0, lambda msg=str(exc): messagebox.showerror('错误', msg))
        finally:
            gui.root.after(0, gui._processing_done)
            gui.root.after(0, lambda: gui.table_extract_btn.configure(state='normal'))

    # ── 汇总导出：文件列表管理 ──────────────────
    def _summary_add_files(self):
        base_dir = Path(__file__).resolve().parent.parent
        initial = self.pdf_var.get() if os.path.isdir(self.pdf_var.get()) else str(base_dir)
        file_paths = filedialog.askopenfilenames(
            title='选择 PDF 文件（可多选）',
            filetypes=[('PDF 文件', '*.pdf *.PDF'), ('所有文件', '*.*')],
            initialdir=initial,
        )
        if file_paths:
            self._summary_extend_files(list(file_paths))

    def _summary_extend_files(self, file_paths):
        """追加 PDF：文件直接加，文件夹展开内部 PDF；按完整路径去重、保持顺序"""
        existing = {str(Path(f).resolve()).lower() for f in self._summary_files}
        added = 0
        for raw in file_paths:
            p = Path(raw)
            if p.is_dir():
                inner = sorted(x for x in p.iterdir() if x.suffix.lower() == '.pdf')
                for f in inner:
                    key = str(f.resolve()).lower()
                    if key not in existing:
                        existing.add(key)
                        self._summary_files.append(f)
                        added += 1
            elif p.is_file() and p.suffix.lower() == '.pdf':
                key = str(p.resolve()).lower()
                if key not in existing:
                    existing.add(key)
                    self._summary_files.append(p)
                    added += 1
        if added:
            self._log(f'汇总导出：已添加 {added} 个 PDF（当前共 {len(self._summary_files)} 个）')
        else:
            self._log('汇总导出：没有新文件被添加（重复或非 PDF）')
        self._refresh_summary_list()

    def _summary_remove_file(self, index):
        if 0 <= index < len(self._summary_files):
            removed = self._summary_files.pop(index)
            self._log(f'汇总导出：已移除 {removed.name}')
            self._refresh_summary_list()

    def _summary_clear_files(self):
        if self._summary_files:
            self._summary_files.clear()
            self._log('汇总导出：已清空文件列表')
            self._refresh_summary_list()

    def _refresh_summary_list(self):
        for w in self.summary_file_list.winfo_children():
            w.destroy()
        for i, f in enumerate(self._summary_files):
            row = ctk.CTkFrame(self.summary_file_list, fg_color='transparent')
            row.pack(fill='x', pady=1)
            ctk.CTkLabel(
                row, text=f'{i + 1}. {f.name}',
                font=ctk.CTkFont(size=14), anchor='w',
            ).pack(side='left', fill='x', expand=True)
            ctk.CTkButton(
                row, text='✕', width=32, height=26, fg_color='transparent',
                border_width=1, text_color=('gray20', 'gray80'),
                command=lambda idx=i: self._summary_remove_file(idx),
            ).pack(side='right', padx=(6, 0))
        self.summary_count_label.configure(text=f'已选 {len(self._summary_files)} 个 PDF')

    def _build_result_tab(self):
        t = self.tab_result

        ctk.CTkLabel(
            t, text='处理结果统计',
            font=ctk.CTkFont(size=17, weight='bold'),
        ).pack(anchor='w', padx=18, pady=(16, 8))

        stats = ctk.CTkFrame(t, fg_color="transparent")
        stats.pack(fill='x', padx=14, pady=(0, 10))
        self.stat_labels = {}
        labels = [
            ('total', 'PDF 总数', '#3b82f6'),
            ('processed', '成功', '#2e9e4f'),
            ('failed', '失败', '#e23b3b'),
            ('skipped', '跳过', '#e6a23c'),
            ('groups', '日期组', '#8b5cf6'),
            ('ng', 'NG 项', '#ef4444'),
        ]
        for i, (key, text, color) in enumerate(labels):
            box = ctk.CTkFrame(stats, corner_radius=10)
            box.grid(row=i // 3, column=i % 3, padx=8, pady=8, sticky='nsew')
            ctk.CTkLabel(box, text=text, font=ctk.CTkFont(size=14), text_color=('gray40', 'gray60')).pack(pady=(10, 0))
            val = ctk.CTkLabel(box, text='-', font=ctk.CTkFont(size=30, weight='bold'), text_color=color)
            val.pack(pady=(0, 10))
            self.stat_labels[key] = val
        stats.grid_columnconfigure((0, 1, 2), weight=1)
        stats.grid_rowconfigure((0, 1), weight=1)

        out_card = ctk.CTkFrame(t, fg_color="transparent")
        out_card.pack(fill='both', expand=True, padx=14, pady=(0, 12))
        ctk.CTkLabel(
            out_card, text='生成文件',
            font=ctk.CTkFont(size=17, weight='bold'),
        ).pack(anchor='w', padx=14, pady=(10, 4))
        self.output_list = ctk.CTkScrollableFrame(out_card, fg_color='transparent')
        self.output_list.pack(fill='both', expand=True, padx=10, pady=(0, 10))

    # ── 剪贴板工具 ──────────────────────────────
    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(text))
        self.root.update_idletasks()

    def _copy_output_path(self):
        folder = self.output_var.get()
        if not os.path.isdir(folder):
            messagebox.showwarning('提示', '输出文件夹不存在')
            return
        self._copy_to_clipboard(folder)
        messagebox.showinfo('已复制', f'输出文件夹路径已复制到剪贴板:\n{folder}\n\n可粘贴到资源管理器地址栏打开。')

    def _show_log_window(self):
        log_path = str(paths.log_dir / 'CMMFiller.log')
        win = ctk.CTkoplevel(self.root.winfo_toplevel())
        win.title('运行日志')
        win.geometry('720x480')
        win.transient(self.root)
        text = ctk.CTkTextbox(win, font=ctk.CTkFont(family='Consolas', size=13), wrap='word')
        text.pack(fill='both', expand=True, padx=12, pady=12)
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError:
            content = '日志文件尚未生成。'
        text.insert('1.0', content)
        text.configure(state='disabled')
        ctk.CTkButton(
            win, text='复制日志路径', width=120,
            command=lambda: (self._copy_to_clipboard(log_path),
                             messagebox.showinfo('已复制', f'日志路径已复制:\n{log_path}')),
        ).pack(pady=(0, 12))

    def _clear_ocr_cache(self) -> None:
        from utils.ocr_cache import clear_ocr_cache

        if not messagebox.askyesno(
            '清理 OCR 缓存',
            '将删除 OCR 渲染缓存图片与 ocr_cache.json。\n'
            '下次识别会重新渲染 PDF（稍慢）。\n\n是否继续？',
        ):
            return
        try:
            result = clear_ocr_cache()
            audit('cleanup_ocr_cache', source='cmm_filler_gui', **result)
            messagebox.showinfo(
                '清理完成',
                f'已删除 {result["png_files"]} 张缓存图'
                + (f'，清除 {result["json_entries_cleared"]} 条 OCR 记录。' if result['json_removed'] else '。'),
            )
            self._log('OCR 缓存已清理。')
        except Exception as exc:
            messagebox.showerror('清理失败', str(exc))

    # ── 拖拽 ─────────────────────────────────────
    def _setup_dnd(self, widget, kind):
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind('<<Drop>>', lambda e: self._on_drop(e, kind))

    @staticmethod
    def _parse_drop_paths(data):
        """DND_FILES 文本可能是 {带空格路径} 的混合，拆出真实路径列表"""
        data = data.strip()
        parts = re.findall(r'\{([^}]*)\}|(\S+)', data)
        return [a or b for a, b in parts]

    def _on_drop(self, event, kind):
        dropped_paths = self._parse_drop_paths(event.data)
        if not dropped_paths:
            return
        if kind == 'template':
            p = dropped_paths[0]
            if p.lower().endswith(('.xlsx', '.xls')):
                self.template_var.set(p)
        elif kind == 'pdf':
            p = dropped_paths[0]
            if os.path.isdir(p):
                self.pdf_var.set(p)
            elif os.path.isfile(p):
                self.pdf_var.set(os.path.dirname(p))
        elif kind == 'output':
            p = dropped_paths[0]
            if os.path.isdir(p):
                self.output_var.set(p)
        elif kind == 'summary_files':
            self._summary_extend_files(dropped_paths)
            return  # 不涉及路径输入框，无需保存设置
        self._save_paths()

    # ── 浏览 ─────────────────────────────────────
    def _browse_template(self):
        base_dir = Path(__file__).resolve().parent.parent
        path = filedialog.askopenfilename(
            title='选择 Excel 模板',
            filetypes=[('Excel 文件', '*.xlsx *.xls'), ('所有文件', '*.*')],
            initialdir=os.path.dirname(self.template_var.get()) if self.template_var.get() else str(base_dir),
        )
        if path:
            self.template_var.set(path)
            self._save_paths()

    def _browse_pdf(self):
        base_dir = Path(__file__).resolve().parent.parent
        path = filedialog.askdirectory(title='选择 PDF 文件夹', initialdir=self.pdf_var.get() or str(base_dir))
        if path:
            self.pdf_var.set(path)
            self._save_paths()

    def _browse_output(self):
        base_dir = Path(__file__).resolve().parent.parent
        path = filedialog.askdirectory(title='选择输出文件夹', initialdir=self.output_var.get() or str(base_dir))
        if path:
            self.output_var.set(path)
            self._save_paths()

    # ── 日志 / 状态 ──────────────────────────────
    def _log(self, msg):
        self.log_text.configure(state='normal')
        start = self.log_text.index('end-1c')
        self.log_text.insert('end', msg + '\n')
        tag = None
        if any(k in msg for k in ('错误', '失败', 'ERROR', '保存失败')):
            tag = 'err'
        elif any(k in msg for k in ('成功', '完成', 'OK')):
            tag = 'ok'
        elif any(k in msg for k in ('警告', 'WARNING', '跳过', '超限')):
            tag = 'warn'
        if tag:
            self.log_text.tag_add(tag, start, 'end-1c')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')
        self.root.update_idletasks()

    def _set_status(self, msg, processing=False):
        prefix = '处理中' if processing else ''
        self.status_bar.configure(text=f'{prefix}: {msg}' if prefix else msg)

    def _show_welcome(self):
        self._log('欢迎使用 PDF报告填充工具！')
        if self.default_template:
            self._log(f'模板: {self.default_template}')
        else:
            self._log('请先在「Excel 模板」处选择模板文件，或直接拖入。')
        if self.default_pdf_folder:
            self._log(f'PDF 文件夹: {self.default_pdf_folder}')
        else:
            self._log('请在「PDF 文件夹」处选择含测量报告的 PDF 目录。')
        self._log(f'输出文件夹: {self.default_output_folder}')
        self._log('点击「开始处理」。可把文件夹拖入输入框；首次 OCR 约需 10~30 秒。')

    # ── 首次运行引导 ────────────────────────────
    def _maybe_show_first_run_guide(self):
        """settings.json 为空视为首次运行，延迟弹出引导窗口（等主窗口渲染完成）"""
        if not load_settings():
            self.root.after(300, self._show_first_run_guide)

    def _show_first_run_guide(self):
        win = ctk.CTkToplevel(self.root.winfo_toplevel())
        win.title('欢迎使用 PDF 报告填充')
        win.geometry('740x460')
        win.minsize(700, 420)
        win.transient(self.root.winfo_toplevel())
        apply_window_icon(win)
        # 点 X 关闭视为跳过：保存当前路径，下次不再打扰
        win.protocol('WM_DELETE_WINDOW', lambda: (self._save_paths(), win.destroy()))
        self._guide_win = win
        self._guide_status_labels = {}

        ctk.CTkLabel(
            win, text='📊 欢迎使用 PDF 报告填充',
            font=ctk.CTkFont(size=22, weight='bold'),
        ).pack(pady=(22, 4))
        ctk.CTkLabel(
            win, text='三步完成第一次处理：① 选 Excel 模板 → ② 选 PDF 文件夹 → ③ 点「开始处理」',
            font=ctk.CTkFont(size=14), text_color=('gray40', 'gray60'),
        ).pack(pady=(0, 12))

        card = ctk.CTkFrame(win)
        card.pack(fill='x', padx=24)

        rows = [
            ('template', '📄 Excel 模板', self.template_var, self._browse_template),
            ('pdf', '📁 PDF 文件夹', self.pdf_var, self._browse_pdf),
            ('output', '📦 输出文件夹', self.output_var, self._browse_output),
        ]
        for key, label, var, browse_cmd in rows:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill='x', padx=14, pady=9)
            ctk.CTkLabel(row, text=label, width=96, anchor='w').pack(side='left')
            entry = ctk.CTkEntry(row, textvariable=var, height=30)
            entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
            self._setup_dnd(entry, key)  # 引导窗口同样支持拖拽
            ctk.CTkButton(row, text='浏览', width=52, height=30, command=browse_cmd).pack(side='left', padx=(0, 6))
            st = ctk.CTkLabel(row, text='…', width=40, font=ctk.CTkFont(size=15, weight='bold'))
            st.pack(side='left')
            self._guide_status_labels[key] = st

        ctk.CTkLabel(
            win, text='💡 也可以把文件夹/模板文件直接拖到对应输入框上',
            font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        ).pack(pady=(8, 4))

        btns = ctk.CTkFrame(win, fg_color='transparent')
        btns.pack(pady=(2, 18))
        ctk.CTkButton(
            btns, text='跳过，我自己配置', width=130, height=36, fg_color='transparent',
            border_width=1, text_color=('gray20', 'gray80'),
            command=lambda: (self._save_paths(), win.destroy()),
        ).pack(side='left', padx=6)
        ctk.CTkButton(
            btns, text='完成 ✓', width=110, height=36,
            font=ctk.CTkFont(size=15, weight='bold'),
            command=self._guide_finish,
        ).pack(side='left', padx=6)

        # 路径变化实时刷新 ✓/✗ 状态（窗口关闭后回调静默失效）
        for var in (self.template_var, self.pdf_var, self.output_var):
            var.trace_add('write', self._guide_refresh)
        self._guide_refresh()
        win.after(120, win.grab_set)  # 模态，等窗口可见后再抓焦点

    def _guide_refresh(self, *args):
        try:
            checks = {
                'template': os.path.isfile(self.template_var.get().strip()),
                'pdf': os.path.isdir(self.pdf_var.get().strip()),
                'output': os.path.isdir(self.output_var.get().strip()),
            }
            for key, ok in checks.items():
                self._guide_status_labels[key].configure(
                    text='✓' if ok else '✗',
                    text_color=self.COLORS['ok'] if ok else self.COLORS['err'],
                )
        except Exception:
            pass  # 引导窗口已销毁，回调自然失效

    def _guide_finish(self):
        tpl = self.template_var.get().strip()
        pdf = self.pdf_var.get().strip()
        if not os.path.isfile(tpl):
            messagebox.showwarning('提示', '请先选择有效的 Excel 模板文件（点「浏览」或拖入 xlsx）')
            return
        if not os.path.isdir(pdf):
            messagebox.showwarning('提示', '请先选择有效的 PDF 文件夹（放测量报告的目录）')
            return
        self._save_paths()
        if getattr(self, '_guide_win', None):
            try:
                self._guide_win.destroy()
            except Exception:
                pass
        self._log('首次配置完成！点击「开始处理」即可开始识别。')

    # ── 校验 ─────────────────────────────────────
    def _validate_paths(self, require_template=True):
        template = self.template_var.get().strip()
        pdf_folder = self.pdf_var.get().strip()
        output_folder = self.output_var.get().strip()

        if require_template and not os.path.isfile(template):
            messagebox.showerror('错误', '请选择有效的 Excel 模板文件')
            return None
        if not os.path.isdir(pdf_folder):
            messagebox.showerror('错误', '请选择有效的 PDF 文件夹')
            return None
        if not os.path.isdir(output_folder):
            try:
                os.makedirs(output_folder, exist_ok=True)
            except OSError:
                messagebox.showerror('错误', '请选择有效的输出文件夹')
                return None
        return template, pdf_folder, output_folder

    # ── 开始处理（可选择先预览）──────────────────
    def _start(self):
        if self.processing:
            messagebox.showwarning('提示', '正在处理中，请稍候...')
            return

        valid_paths = self._validate_paths(require_template=True)
        if not valid_paths:
            return
        template, pdf_folder, output_folder = valid_paths
        self._save_paths()
        audit("cmm_process_start", mode="preview" if self.preview_switch.get() else "batch", pdf_folder=pdf_folder)

        self._begin_work()

        if self.preview_switch.get():
            self._start_worker(self._run_analyze, template, pdf_folder)
        else:
            self._start_worker(self._run_batch, template, pdf_folder, output_folder, None, None)

    # ── 工作线程管理（取消支持）──────────────────
    def _start_worker(self, target, *args, **kwargs):
        """启动可取消工作线程，并保存引用供关闭/卸载时取消。"""
        self._worker = CancellableWorker()
        self._worker.start(target, *args, **kwargs)

    def _is_worker_cancelled(self) -> bool:
        """查询当前工作线程是否已请求取消。"""
        return bool(self._worker and self._worker.is_cancelled())

    def _cancel_worker(self):
        """请求取消工作线程并等待退出（最多 1.5 秒，避免窗口关闭卡顿）。"""
        if self._worker and self._worker.is_running:
            self._worker.request_cancel()
            self._worker.wait(1.5)
        self._worker = None

    def _begin_work(self):
        self.processing = True
        self.start_btn.configure(state='disabled')
        self.summary_btn.configure(state='disabled')
        self.ng_btn.configure(state='disabled')
        self.progress.set(0)
        self.summary_progress.set(0)
        self._set_status('正在处理...', processing=True)
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    # ── 预览阶段 ─────────────────────────────────
    def _run_analyze(self, template, pdf_folder):
        gui = self
        try:
            from .core.filler import set_gui_logger
            set_gui_logger(gui)
            gui.filler = gui._create_filler(template)
            gui.filler.cancel_check = gui._is_worker_cancelled
            gui.root.after(0, lambda: gui._log('正在识别 PDF（只识别不写入，完成后弹预览，可剔除误识别项）...'))
            items = gui.filler.analyze_pdfs(
                pdf_folder,
                progress_callback=lambda c, t, m: gui._update_progress(c, t, m),
            )
            if gui._is_worker_cancelled():
                gui.root.after(0, lambda: gui._log('已取消处理'))
                gui.root.after(0, gui._processing_done)
                return
            if not items:
                gui.root.after(0, lambda: messagebox.showwarning('提示', '未找到可识别的 PDF 文件'))
                gui.root.after(0, gui._processing_done)
                return
            audit("cmm_analyze", count=len(items), pdf_folder=pdf_folder)
            gui.root.after(0, lambda: (gui._show_preview(items), gui._processing_done()))
        except Exception as exc:
            err_msg = str(exc)
            gui.root.after(0, lambda msg=err_msg: gui._log(f'错误: {msg}'))
            gui.root.after(0, lambda msg=err_msg: gui._set_status(f'错误: {msg[:50]}'))
            hint = '请联系软件提供者，并把日志发给他（「查看日志」按钮可打开）。' if len(err_msg) > 80 else ''
            gui.root.after(0, lambda msg=err_msg, h=hint: messagebox.showerror('错误', msg + ('\n\n' + h if h else '')))
            gui.root.after(0, gui._processing_done)

    def _show_preview(self, items):
        if self._preview_window is not None:
            try:
                self._preview_window.destroy()
            except Exception:
                pass
        win = ctk.CTkToplevel(self.root.winfo_toplevel())
        win.title('识别结果预览 - 勾选要保留的测量项')
        win.geometry('900x640')
        win.transient(self.root)
        apply_window_icon(win)
        self._preview_window = win
        self._preview_widgets = []
        self._sub_item_choice_vars = {}
        self._sub_item_choice_maps = {}

        conflicts = []
        if self.filler is not None:
            conflicts = self.filler.analyze_sub_item_conflicts(items)
        conflict_keys: set[str] = set()
        for conflict in conflicts:
            for candidate in conflict['candidates']:
                conflict_keys.add(measure_dict_key(candidate))

        header = ctk.CTkFrame(win)
        header.pack(fill='x', padx=14, pady=(12, 4))
        ctk.CTkLabel(
            header, text='识别结果预览（开始前核对）',
            font=ctk.CTkFont(size=17, weight='bold'),
        ).pack(side='left')
        hint = '取消勾选 = 剔除；实测值列可直接修改；橙色行 = 低置信度'
        if conflict_keys:
            hint += '；紫色行 = 子编号冲突'
        ctk.CTkLabel(
            header, text=hint,
            font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        ).pack(side='right')

        if conflicts:
            conflict_panel = ctk.CTkFrame(win, corner_radius=8, fg_color='#F5EEF8')
            conflict_panel.pack(fill='x', padx=14, pady=(0, 6))
            ctk.CTkLabel(
                conflict_panel,
                text='子编号冲突：多个子项对应模板同一序号，请为每组选择填入项',
                font=ctk.CTkFont(size=14, weight='bold'),
                anchor='w',
            ).pack(fill='x', padx=10, pady=(8, 4))
            for conflict in conflicts:
                row = ctk.CTkFrame(conflict_panel, fg_color='transparent')
                row.pack(fill='x', padx=10, pady=3)
                ctk.CTkLabel(
                    row,
                    text=conflict_summary_line(conflict),
                    font=ctk.CTkFont(size=13),
                    anchor='w',
                    wraplength=420,
                    justify='left',
                ).pack(side='left', fill='x', expand=True, padx=(0, 8))

                labels = [candidate_option_label(c) for c in conflict['candidates']]
                labels.append('都不填')
                labels.append('较差(NG)项')
                choice_map = {
                    candidate_option_label(c): measure_dict_key(c)
                    for c in conflict['candidates']
                }
                choice_map['都不填'] = SKIP_SUB_ITEM
                choice_map['较差(NG)项'] = WORST_NG_SUB_ITEM
                default_label = '较差(NG)项'
                var = ctk.StringVar(value=default_label)
                ctk.CTkOptionMenu(
                    row, values=labels, variable=var, width=360,
                ).pack(side='right')
                template_key = conflict['template_key']
                self._sub_item_choice_vars[template_key] = var
                self._sub_item_choice_maps[template_key] = choice_map
            ctk.CTkLabel(
                conflict_panel,
                text='选项按识别到的子项动态生成（如 FAI_1-1 … FAI_1-N），默认选较差(NG)项',
                font=ctk.CTkFont(size=12),
                text_color=('gray40', 'gray60'),
                anchor='w',
            ).pack(fill='x', padx=10, pady=(2, 8))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill='x', padx=14, pady=(4, 4))
        ctk.CTkButton(btn_row, text='全部勾选', width=90, height=28, command=self._preview_check_all).pack(side='left', padx=(0, 6))
        ctk.CTkButton(btn_row, text='全部取消', width=90, height=28, command=self._preview_check_none).pack(side='left')

        total_ms = sum(len(it['measurements']) for it in items if not it['error'])
        total_ng = sum(it['ng_count'] for it in items)
        ctk.CTkLabel(
            btn_row,
            text=f'共 {len(items)} 份 PDF，识别出 {total_ms} 项测量；NG 超差 {total_ng} 项',
            font=ctk.CTkFont(size=14), text_color=('gray30', 'gray70'),
        ).pack(side='right')

        scroll = ctk.CTkScrollableFrame(win, fg_color='transparent')
        scroll.pack(fill='both', expand=True, padx=10, pady=(0, 6))

        for it in items:
            self._build_preview_card(scroll, it, conflict_keys)

        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.pack(fill='x', padx=14, pady=(0, 12))
        self.preview_confirm_label = ctk.CTkLabel(
            foot, text='', font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
        )
        self.preview_confirm_label.pack(side='left')
        ctk.CTkButton(
            foot, text='取消', height=38, width=80,
            command=lambda: win.destroy(),
        ).pack(side='right', padx=(0, 8))
        ctk.CTkButton(
            foot, text='确认开始处理', height=38,
            font=ctk.CTkFont(size=15, weight='bold'),
            command=self._confirm_preview,
        ).pack(side='right')

        self._preview_update_count()

    def _build_preview_card(self, parent, item, conflict_keys=None):
        conflict_keys = conflict_keys or set()
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill='x', padx=4, pady=3)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill='x', padx=10, pady=(6, 2))
        head_text = f'📄 {item["name"]}' + ('  [识别失败]' if item['error'] else '')
        ctk.CTkLabel(head, text=head_text, font=ctk.CTkFont(size=14, weight='bold')).pack(side='left')
        if item['error']:
            ctk.CTkLabel(
                head, text='该文件将自动跳过',
                font=ctk.CTkFont(size=13), text_color=self.COLORS['err'],
            ).pack(side='left', padx=8)
        else:
            source_labels = {'text': '文字层', 'ocr-table': 'OCR表格', 'ocr-line': 'OCR行解析'}
            src = source_labels.get(item.get('source', ''), item.get('source', ''))
            meta = f"{item['part_name']} | {item['date']}"
            if src:
                meta += f' | {src}'
            ctk.CTkLabel(
                head, text=meta,
                font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'),
            ).pack(side='left', padx=8)
            if item['ng_count']:
                ctk.CTkLabel(
                    head, text=f'⚠ {item["ng_count"]} 项超差',
                    font=ctk.CTkFont(size=13, weight='bold'), text_color=self.COLORS['ng'],
                ).pack(side='right', padx=(8, 4))

        if item['error']:
            err_txt = item['error'][:80]
            ctk.CTkLabel(
                card, text=f'   {err_txt}',
                font=ctk.CTkFont(size=13), text_color=self.COLORS['err'], anchor='w',
            ).pack(fill='x', padx=14, pady=(0, 8))
            return

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill='x', padx=4, pady=(0, 6))
        for m in item['measurements']:
            var = ctk.BooleanVar(value=True)
            measured_var = ctk.StringVar(value=f"{m['measured']:g}")
            ikey = m.get('item_key') or f"{m['num']}"
            label = m.get('label') or f'FAI_{m["num"]:02d}'
            widget = {
                'stem': item['stem'], 'num': m['num'], 'item_key': ikey, 'var': var,
                'measured_var': measured_var,
                'original_measured': m['measured'],
                'nominal': m['nominal'], 'upper_tol': m['upper_tol'], 'lower_tol': m['lower_tol'],
            }
            self._preview_widgets.append(widget)

            low_conf = m.get('low_confidence', False)
            is_conflict = ikey in conflict_keys
            if is_conflict:
                row_bg = '#F5EEF8'
            elif low_conf:
                row_bg = '#FFF3E0'
            else:
                row_bg = 'transparent'
            row = ctk.CTkFrame(body, fg_color=row_bg, corner_radius=4)
            row.pack(fill='x', padx=6, pady=1)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkCheckBox(
                row, text=' ', width=24, variable=var, command=self._preview_update_count,
            ).grid(row=0, column=0, sticky='w')

            ng = m.get('ng', False)
            desc_color = self.COLORS['ng'] if ng else ('gray15', 'gray85')
            if is_conflict and not ng:
                desc_color = '#7D3C98'
            elif low_conf and not ng:
                desc_color = self.COLORS['warn']
            desc_font = ctk.CTkFont(size=13, weight='bold') if (ng or low_conf) else ctk.CTkFont(size=13)

            # 合并 label + desc 为单 Label（省 1 widget/行；保留 tol 列与样式）
            desc_val = m.get('desc', '')
            if is_conflict:
                desc_val = f'⚡ {desc_val}'
            elif low_conf:
                desc_val = f'⚠ {desc_val}'
            ctk.CTkLabel(
                row, text=f"{label}  {desc_val}",
                anchor='w', font=desc_font, text_color=desc_color, justify='left',
            ).grid(row=0, column=1, sticky='ew', padx=(6, 6))

            # tol 列保留：灰色 + size 12 + 右对齐，公差值独立视觉层级
            tol_val = f"{m['nominal']:g} +{m['upper_tol']:g}/-{abs(m['lower_tol']):g}"
            ctk.CTkLabel(
                row, text=tol_val,
                width=130, anchor='e', font=ctk.CTkFont(size=12), text_color=('gray45', 'gray55'),
            ).grid(row=0, column=2, sticky='e', padx=(0, 6))

            meas_entry = ctk.CTkEntry(
                row, textvariable=measured_var, width=90, height=28,
                font=ctk.CTkFont(size=14, weight='bold'),
                border_color=self.COLORS['warn'] if low_conf else None,
            )
            meas_entry.grid(row=0, column=3, sticky='e', padx=(0, 2))
            if ng:
                ctk.CTkLabel(
                    row, text='NG', width=30,
                    font=ctk.CTkFont(size=12, weight='bold'), text_color='white',
                    fg_color=self.COLORS['ng'], corner_radius=6,
                ).grid(row=0, column=4, padx=(4, 0))

    def _preview_check_all(self):
        for w in self._preview_widgets:
            w['var'].set(True)
        self._preview_update_count()
        self.root.after(200, self._confirm_preview)

    def _preview_check_none(self):
        for w in self._preview_widgets:
            w['var'].set(False)
        self._preview_update_count()

    def _preview_update_count(self):
        if not hasattr(self, 'preview_confirm_label'):
            return
        total = len(self._preview_widgets)
        kept = sum(1 for w in self._preview_widgets if w['var'].get())
        edited = sum(
            1 for w in self._preview_widgets
            if w['var'].get() and self._preview_measured_changed(w)
        )
        extra = f'，已修正 {edited} 项' if edited else ''
        self.preview_confirm_label.configure(
            text=f'共 {total} 项，保留 {kept} 项，剔除 {total - kept} 项{extra}'
        )

    @staticmethod
    def _preview_measured_changed(widget) -> bool:
        try:
            return abs(float(widget['measured_var'].get()) - widget['original_measured']) > 1e-9
        except (ValueError, TypeError):
            return True

    def _collect_preview_edits(self) -> dict:
        """收集预览中修改过的实测值 {stem: {num: {measured: ...}}}。"""
        edits = defaultdict(dict)
        for w in self._preview_widgets:
            if not w['var'].get():
                continue
            if self._preview_measured_changed(w):
                try:
                    edits[w['stem']][w['item_key']] = {'measured': float(w['measured_var'].get())}
                except ValueError:
                    pass
        return dict(edits)

    def _confirm_preview(self):
        excluded = defaultdict(set)
        for w in self._preview_widgets:
            if not w['var'].get():
                excluded[w['stem']].add(w['item_key'])
        edited_measures = self._collect_preview_edits()
        sub_item_choices = {}
        for template_key, var in getattr(self, '_sub_item_choice_vars', {}).items():
            label = var.get()
            sub_item_choices[template_key] = self._sub_item_choice_maps[template_key][label]
        template = self.template_var.get().strip()
        pdf_folder = self.pdf_var.get().strip()
        output_folder = self.output_var.get().strip()
        if self._preview_window is not None:
            try:
                self._preview_window.destroy()
            except Exception:
                pass
        if excluded:
            self._log(f'将剔除 {sum(len(v) for v in excluded.values())} 项误识别数据')
        if edited_measures:
            n_edits = sum(len(v) for v in edited_measures.values())
            self._log(f'将应用 {n_edits} 项实测值修正')
        if sub_item_choices:
            self._log(f'子编号冲突：已设置 {len(sub_item_choices)} 组填入规则')
        self._start_worker(
            self._run_batch, template, pdf_folder, output_folder,
            dict(excluded), edited_measures, sub_item_choices or None,
        )

    # ── 批量处理阶段 ─────────────────────────────
    def _run_batch(self, template, pdf_folder, output_folder, excluded_measures,
                   edited_measures=None, sub_item_choices=None):
        gui = self
        try:
            from .core.filler import set_gui_logger
            set_gui_logger(gui)
            if gui.filler is None:
                gui.filler = gui._create_filler(template)
            gui.filler.cancel_check = gui._is_worker_cancelled
            summary = gui.filler.batch_process_by_date(
                pdf_folder, output_folder,
                progress_callback=lambda c, t, m: gui._update_progress(c, t, m),
                excluded_measures=excluded_measures,
                edited_measures=edited_measures,
                sub_item_choices=sub_item_choices,
            )

            if gui._is_worker_cancelled():
                gui.root.after(0, lambda: gui._log('已取消处理'))
                gui.root.after(0, lambda: gui._set_status('已取消'))
                return

            audit("cmm_process_done", processed=summary.get("processed_pdfs", 0),
                  failed=len(summary.get("failed_pdfs", [])), pdf_folder=pdf_folder)

            gui.root.after(0, lambda: gui._log('=' * 50))
            gui.root.after(0, lambda: gui._log('处理完成'))
            gui.root.after(0, lambda t=gui._format_batch_summary(summary): gui._log(t))
            gui.root.after(0, lambda: gui._set_status('处理完成'))
            gui.root.after(0, lambda: gui._show_result_summary(summary))
            gui.root.after(0, lambda: gui.tabs.set('结果'))

            fail_count = len(summary.get('failed_pdfs', []))
            summary_text = gui._format_batch_summary(summary)
            if fail_count:
                gui.root.after(0, lambda t=summary_text: messagebox.showwarning('处理完成（有失败）', t))
            else:
                gui.root.after(0, lambda t=summary_text: messagebox.showinfo('处理完成', t))

        except Exception as exc:
            err_msg = str(exc)
            gui.root.after(0, lambda msg=err_msg: gui._log(f'错误: {msg}'))
            gui.root.after(0, lambda msg=err_msg: gui._set_status(f'错误: {msg[:50]}'))
            hint = '请联系软件提供者，并把日志发给他（「查看日志」按钮可打开）。' if len(err_msg) > 80 else ''
            gui.root.after(0, lambda msg=err_msg, h=hint: messagebox.showerror('错误', msg + ('\n\n' + h if h else '')))
        finally:
            gui.root.after(0, gui._processing_done)

    def _run_export(self, template, pdf_folder, output_folder):
        gui = self
        try:
            from .core.filler import set_gui_logger
            set_gui_logger(gui)
            gui.filler = gui._create_filler(template)
            gui.filler.cancel_check = gui._is_worker_cancelled
            summary = gui.filler.export_standard_template(
                pdf_folder, output_folder,
                progress_callback=lambda c, t, m: gui._update_progress(c, t, m),
            )

            if gui._is_worker_cancelled():
                gui.root.after(0, lambda: gui._log('已取消导出'))
                gui.root.after(0, lambda: gui._set_status('已取消'))
                return

            audit("cmm_export_template_done",
                  processed=summary.get("processed_pdfs", 0),
                  failed=len(summary.get("failed_pdfs", [])), pdf_folder=pdf_folder)

            summary_text = gui._format_export_summary(summary)
            gui.root.after(0, lambda: gui._log('导出完成'))
            gui.root.after(0, lambda t=summary_text: gui._log(t))
            gui.root.after(0, lambda: gui._set_status('导出完成'))
            gui.root.after(0, lambda t=summary_text: messagebox.showinfo('导出完成', t))
        except Exception as exc:
            err_msg = str(exc)
            gui.root.after(0, lambda msg=err_msg: gui._log(f'错误: {msg}'))
            gui.root.after(0, lambda msg=err_msg: gui._set_status(f'错误: {msg[:50]}'))
            hint = '请联系软件提供者，并把日志发给他（「查看日志」按钮可打开）。' if len(err_msg) > 80 else ''
            gui.root.after(0, lambda msg=err_msg, h=hint: messagebox.showerror('错误', msg + ('\n\n' + h if h else '')))
        finally:
            gui.root.after(0, gui._processing_done)

    # ── 导出标准模板 ─────────────────────────────
    def _export_template(self):
        if self.processing:
            messagebox.showwarning('提示', '正在处理中，请稍候...')
            return

        export_paths = self._validate_paths(require_template=False)
        if not export_paths:
            return
        template, pdf_folder, output_folder = export_paths
        self._save_paths()
        audit("cmm_export_template", pdf_folder=pdf_folder)

        self._begin_work()
        self._log('导出标准模板...')
        self._set_status('正在导出模板...', processing=True)
        self._start_worker(self._run_export, template or str(paths.data_dir / 'cmm_filler' / 'template.xlsx'), pdf_folder, output_folder)

    # ── 汇总导出（多 PDF → 单 Excel，每 PDF 一个 Sheet）──
    def _summary_start(self):
        if self.processing:
            messagebox.showwarning('提示', '正在处理中，请稍候...')
            return
        if not self._summary_files:
            messagebox.showwarning('提示', '请先添加 PDF 文件（点「＋ 添加 PDF」或直接拖入）')
            return
        output_folder = self.output_var.get().strip()
        if not os.path.isdir(output_folder):
            try:
                os.makedirs(output_folder, exist_ok=True)
            except OSError:
                messagebox.showerror('错误', '请选择有效的输出文件夹')
                return
        self._save_paths()
        pdf_paths = [str(f) for f in self._summary_files]
        audit("cmm_summary_export", count=len(pdf_paths), output_folder=output_folder)
        self._begin_work()
        self._log(f'汇总导出：共 {len(pdf_paths)} 个 PDF，每个 PDF 生成一个 Sheet...')
        self._set_status('正在汇总导出...', processing=True)
        self._start_worker(self._run_summary_export, pdf_paths, output_folder)

    def _run_summary_export(self, pdf_paths, output_folder):
        gui = self
        try:
            from .core.filler import set_gui_logger
            set_gui_logger(gui)
            if gui.filler is None:
                gui.filler = CMMReportFiller(gui.template_var.get().strip() or str(paths.data_dir / 'cmm_filler' / 'template.xlsx'), dpi=300)
            gui.filler.cancel_check = gui._is_worker_cancelled
            summary = gui.filler.export_summary_workbook(
                pdf_paths, output_folder,
                progress_callback=lambda c, t, m: gui._update_summary_progress(c, t, m),
            )

            if gui._is_worker_cancelled():
                gui.root.after(0, lambda: gui._log('已取消汇总导出'))
                gui.root.after(0, lambda: gui._set_status('已取消'))
                return

            audit("cmm_summary_done", sheets=summary.get("sheet_count", 0),
                  ng=summary.get("ng_count", 0), output_folder=output_folder)

            summary_text = gui._format_summary_text(summary)
            gui.root.after(0, lambda: gui._log('=' * 50))
            gui.root.after(0, lambda: gui._log('汇总导出完成'))
            gui.root.after(0, lambda t=summary_text: gui._log(t))
            gui.root.after(0, lambda: gui._set_status('汇总导出完成'))
            gui.root.after(0, lambda s=summary: gui._show_summary_result(s))
            gui.root.after(0, lambda: gui.tabs.set('结果'))

            fail_count = len(summary.get('failed_pdfs', []))
            if fail_count:
                gui.root.after(0, lambda t=summary_text: messagebox.showwarning('汇总完成（有失败）', t))
            else:
                gui.root.after(0, lambda t=summary_text: messagebox.showinfo('汇总完成', t))
        except Exception as exc:
            err_msg = str(exc)
            gui.root.after(0, lambda msg=err_msg: gui._log(f'错误: {msg}'))
            gui.root.after(0, lambda msg=err_msg: gui._set_status(f'错误: {msg[:50]}'))
            hint = '请联系软件提供者，并把日志发给他（「查看日志」按钮可打开）。' if len(err_msg) > 80 else ''
            gui.root.after(0, lambda msg=err_msg, h=hint: messagebox.showerror('错误', msg + ('\n\n' + h if h else '')))
        finally:
            gui.root.after(0, gui._processing_done)

    def _update_summary_progress(self, current, total, message):
        def _do():
            if total > 0:
                self.summary_progress.set(min(current / total, 1.0))
            self.summary_progress_label.configure(text=f'{current}/{total}  {message}')
            self._set_status(message, processing=True)
        self.root.after(0, _do)

    def _format_summary_text(self, summary):
        lines = [
            f'PDF 总数: {summary.get("total_pdfs", 0)}',
            f'成功: {summary.get("processed_pdfs", 0)}',
            f'失败: {len(summary.get("failed_pdfs", []))}',
            f'生成 Sheet 数: {summary.get("sheet_count", 0)}',
            f'NG 超差项: {summary.get("ng_count", 0)}',
        ]
        if summary.get('output_file'):
            lines.append(f'\n输出: {Path(summary["output_file"]).name}')
        failed = summary.get('failed_pdfs', [])
        if failed:
            lines.append('\n失败文件:')
            for item in failed:
                lines.append(f'  - {item["file"]}: {item["error"][:60]}')
        return '\n'.join(lines)

    def _show_summary_result(self, summary):
        """填结果页徽章与文件列表（日期组/跳过不适用于汇总导出，置 0）"""
        mapping = {
            'total': summary.get('total_pdfs', 0),
            'processed': summary.get('processed_pdfs', 0),
            'failed': len(summary.get('failed_pdfs', [])),
            'skipped': 0,
            'groups': 0,
            'ng': summary.get('ng_count', 0),
        }
        for key, val in mapping.items():
            lbl = self.stat_labels.get(key)
            if lbl:
                lbl.configure(text=str(val))

        for w in self.output_list.winfo_children():
            w.destroy()

        # 表头
        hdr = ctk.CTkFrame(self.output_list, fg_color='transparent')
        hdr.pack(fill='x', pady=(0, 4))
        ctk.CTkLabel(hdr, text='状态', font=ctk.CTkFont(size=13, weight='bold'), width=50, anchor='w').pack(side='left', padx=(8, 0))
        ctk.CTkLabel(hdr, text='文件名', font=ctk.CTkFont(size=13, weight='bold'), anchor='w').pack(side='left', fill='x', expand=True, padx=8)
        ctk.CTkLabel(hdr, text='文件夹', font=ctk.CTkFont(size=13, weight='bold'), anchor='w').pack(side='left', fill='x', expand=True, padx=(0, 8))
        ctk.CTkLabel(hdr, text='', width=82).pack(side='right')

        path = summary.get('output_file')
        if path:
            p = Path(path)
            failed_paths = {Path(fp).name: fp for fp in summary.get('failed_pdfs', [])}
            is_fail = p.name in failed_paths
            row = ctk.CTkFrame(self.output_list, fg_color='transparent')
            row.pack(fill='x', pady=1)
            icon = '🔴' if is_fail else '📄'
            icon_color = self.COLORS['err'] if is_fail else self.COLORS['ok']
            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=14), width=50, anchor='w').pack(side='left', padx=(8, 0))
            ctk.CTkLabel(row, text=p.name, font=ctk.CTkFont(size=14), text_color=icon_color, anchor='w').pack(side='left', fill='x', expand=True, padx=8)
            ctk.CTkLabel(row, text=p.parent.name, font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'), anchor='w').pack(side='left', fill='x', expand=True, padx=(0, 8))
            ctk.CTkButton(
                row, text='复制路径', width=76, height=26,
                command=lambda p=path: (self._copy_to_clipboard(p),
                                        messagebox.showinfo('已复制', f'文件路径已复制:\n{p}')),
            ).pack(side='right', padx=(0, 6))

    # ── 结果展示 ─────────────────────────────
    def _show_result_summary(self, summary):
        mapping = {
            'total': summary.get('total_pdfs', 0),
            'processed': summary.get('processed_pdfs', 0),
            'failed': len(summary.get('failed_pdfs', [])),
            'skipped': len(summary.get('skipped_pdfs', [])),
            'groups': summary.get('date_groups', 0),
            'ng': summary.get('ng_count', 0),
        }
        for key, val in mapping.items():
            lbl = self.stat_labels.get(key)
            if lbl:
                lbl.configure(text=str(val))

        for w in self.output_list.winfo_children():
            w.destroy()

        # 表头
        hdr = ctk.CTkFrame(self.output_list, fg_color='transparent')
        hdr.pack(fill='x', pady=(0, 4))
        ctk.CTkLabel(hdr, text='状态', font=ctk.CTkFont(size=13, weight='bold'), width=50, anchor='w').pack(side='left', padx=(8, 0))
        ctk.CTkLabel(hdr, text='文件名', font=ctk.CTkFont(size=13, weight='bold'), anchor='w').pack(side='left', fill='x', expand=True, padx=8)
        ctk.CTkLabel(hdr, text='文件夹', font=ctk.CTkFont(size=13, weight='bold'), anchor='w').pack(side='left', fill='x', expand=True, padx=(0, 8))
        ctk.CTkLabel(hdr, text='', width=82).pack(side='right')

        failed_paths = {Path(p).name: p for p in summary.get('failed_pdfs', [])}
        files = summary.get('output_files', [])
        for path in files:
            p = Path(path)
            is_fail = p.name in failed_paths
            row = ctk.CTkFrame(self.output_list, fg_color='transparent')
            row.pack(fill='x', pady=1)
            icon = '🔴' if is_fail else '📄'
            icon_color = self.COLORS['err'] if is_fail else self.COLORS['ok']
            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=14), width=50, anchor='w').pack(side='left', padx=(8, 0))
            ctk.CTkLabel(row, text=p.name, font=ctk.CTkFont(size=14), text_color=icon_color, anchor='w').pack(side='left', fill='x', expand=True, padx=8)
            ctk.CTkLabel(row, text=p.parent.name, font=ctk.CTkFont(size=13), text_color=('gray40', 'gray60'), anchor='w').pack(side='left', fill='x', expand=True, padx=(0, 8))
            ctk.CTkButton(
                row, text='复制路径', width=76, height=26,
                command=lambda p=path: (self._copy_to_clipboard(p),
                                        messagebox.showinfo('已复制', f'文件路径已复制:\n{p}')),
            ).pack(side='right', padx=(0, 6))

    # ── 进度 / 摘要文本 ──────────────────────────
    def _update_progress(self, current, total, message):
        def _do():
            if total > 0:
                self.progress.set(min(current / total, 1.0))
            self.progress_label.configure(text=f'{current}/{total}  {message}')
            self._set_status(message, processing=True)
        self.root.after(0, _do)

    def _format_batch_summary(self, summary):
        lines = [
            f'PDF 总数: {summary.get("total_pdfs", 0)}',
            f'成功: {summary.get("processed_pdfs", 0)}',
            f'失败: {len(summary.get("failed_pdfs", []))}',
            f'跳过: {len(summary.get("skipped_pdfs", []))}',
            f'日期组: {summary.get("date_groups", 0)}',
            f'NG 超差项: {summary.get("ng_count", 0)}',
        ]
        outputs = summary.get('output_files', [])
        if outputs:
            lines.append(f'\n生成文件 ({len(outputs)}):')
            for p in outputs:
                lines.append(f'  - {Path(p).name}')
        failed = summary.get('failed_pdfs', [])
        if failed:
            lines.append('\n失败文件:')
            for item in failed:
                lines.append(f'  - {item["file"]}: {item["error"][:60]}')
        return '\n'.join(lines)

    def _format_export_summary(self, summary):
        lines = [
            f'PDF 总数: {summary.get("total_pdfs", 0)}',
            f'成功: {summary.get("processed_pdfs", 0)}',
            f'失败: {len(summary.get("failed_pdfs", []))}',
        ]
        if summary.get('output_file'):
            lines.append(f'\n输出: {Path(summary["output_file"]).name}')
        failed = summary.get('failed_pdfs', [])
        if failed:
            lines.append('\n失败文件:')
            for item in failed:
                lines.append(f'  - {item["file"]}')
        return '\n'.join(lines)

    # ── 向导 / 收尾 ──────────────────────────────
    def _open_wizard(self):
        if self.processing:
            messagebox.showwarning('提示', '正在处理中，请稍候...')
            return
        self._log('启动模板配置向导...')
        self._set_status('向导运行中...')
        try:
            from .template_wizard import TemplateWizard
            # 模态对话框：向导关闭前主窗口不可操作，关闭后自动刷新模板路径
            # P3-10：把当前主页面路径传给向导，避免向导空白起步后配置错列映射
            TemplateWizard(
                self.root.winfo_toplevel(),
                initial_template_path=self.template_var.get(),
            ).run()
        except Exception as exc:
            self._log(f'打开向导失败: {exc}')
        finally:
            self._refresh_template_path()
            self._set_status('就绪')

    def _format_template_label(self) -> str:
        """B 方案：把 self.template_var 渲染成首页 Label 文本。

        - 空：显示「(未配置)」
        - 短路径：显示 basename（路径可能很长，全文显示会撑爆窗口）
        - 完整路径保留在 self.template_var，仅 Label 显示摘要
        """
        path = self.template_var.get().strip()
        if not path:
            return '(未配置)'
        return os.path.basename(path)

    def _refresh_template_path(self):
        config_path = str(paths.config_dir / 'cmm_filler' / 'template_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                tpl = config.get('template_path', '')
                if tpl and os.path.isfile(tpl):
                    self.template_var.set(tpl)
                    self._save_paths()
                    self._log(f'模板路径已更新: {tpl}')
            except Exception:
                pass

    def _processing_done(self):
        self.processing = False
        self.start_btn.configure(state='normal')
        self.summary_btn.configure(state='normal')
        if hasattr(self, 'ng_btn'):
            self.ng_btn.configure(state='normal')
        if hasattr(self, 'table_extract_btn'):
            self.table_extract_btn.configure(state='normal')
        self._preview_window = None
        if self.status_bar.cget('text').startswith('处理中'):
            self._set_status('就绪')

    def run(self):
        if self._owns_root:
            self.root.mainloop()


if __name__ == '__main__':
    app = CMMFillerGUI()
    from .core.filler import set_gui_logger
    set_gui_logger(app)
    app.run()


# ── ModuleProtocol 适配层 ──────────────────────────────────────────────


class CMMFillerModule(ModuleProtocol):
    """
    CMM 报告填充模块（Shell 集成用）
    实现 ModuleProtocol，供 Shell 通过 mount()/unmount() 挂载。
    """

    title = "PDF报告填充"
    icon = "📊"
    version = __version__

    def __init__(self):
        self._instance: CMMFillerGUI | None = None
        self._container: ctk.CTkFrame | None = None

    def mount(self, parent: ctk.CTkFrame) -> None:
        """挂载到 Shell 内容区"""
        self._container = parent
        for widget in parent.winfo_children():
            widget.destroy()
        self._instance = CMMFillerGUI(parent=parent)
        self._instance.shell = self.shell

    def unmount(self) -> None:
        """从 Shell 内容区卸载"""
        if self._instance:
            self._instance._owns_root = False  # 避免 root.destroy() 退出整个进程
            # 取消正在运行的工作线程
            try:
                self._instance._cancel_worker()
            except Exception:
                pass
            # 触发保存设置
            if hasattr(self._instance, '_save_paths'):
                try:
                    self._instance._save_paths()
                except Exception:
                    pass
            self._instance = None
        if self._container:
            for widget in self._container.winfo_children():
                widget.destroy()
            self._container = None

    def on_activate(self) -> None:
        """模块被选中时调用"""
        pass


# 模块注册（由 modules/__init__.py 的 pkgutil 自动发现）
from modules import register_module

register_module("cmm_filler", CMMFillerModule())
