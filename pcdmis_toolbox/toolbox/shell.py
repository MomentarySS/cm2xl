"""
cm2xl — 壳主窗口
左侧导航 + 内容区 + 状态栏，模块挂载/卸载，状态通知。
"""

import sys
import logging
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from toolbox.app_meta import APP_TITLE, APP_VERSION
from toolbox.ui_components import (
    accent_hover_color,
    card_bg_color,
    muted_color,
    on_accent_color,
    page_bg_color,
    primary_button_kwargs,
    text_color,
)
from utils.app_icon import apply_window_icon, get_logo_image
from utils.paths import paths
from utils.audit import audit
from utils.theme import TOOLBOX_THEME

logger = logging.getLogger(__name__)


class Shell:
    """
    主窗口 Shell。

    布局：
    ┌──────────────────────────────────────────────────────────┐
    │  cm2xl              [关于] [设置] [_][□][X]  │
    ├──────────┬─────────────────────────────────────────────┤
    │          │                                              │
    │  📊 CMM报告填充 │        模块内容区                      │
    │  📐 PCDMIS导出 │        (挂载当前模块的 GUI)             │
    │          │                                              │
    ├──────────┴─────────────────────────────────────────────┤
    │  状态栏: PCDMIS连接 | 当前模块 | 操作提示                │
    └──────────────────────────────────────────────────────────┘
    """

    NAV_WIDTH = 156

    def __init__(
        self,
        root: ctk.CTk,
        *,
        start_module: Optional[str] = None,
        auto_export: bool = False,
    ):
        self.root = root
        self._active_module: Optional[object] = None
        self._active_module_name: Optional[str] = None
        self._modules: dict[str, object] = {}
        self._module_hosts: dict[str, ctk.CTkFrame] = {}
        self._mounted_modules: set[str] = set()
        self._running = True
        self._start_module = start_module
        self._auto_export = auto_export
        self._ipc_after_id = None

        self._apply_toolbox_settings()    # 启动时应用外观/日志设置
        self._build_layout()
        self._load_modules()
        self._select_startup_module()
        self._start_ipc_poll()
        if auto_export:
            self.root.after(500, self._run_auto_export)
        self._schedule_migration_notices()
        logger.info("Shell 初始化完成")

    def _apply_toolbox_settings(self) -> None:
        """启动时应用 toolbox 全局设置：外观模式 + 日志级别（OCR 模型目录懒加载）。"""
        try:
            from utils.settings import load_toolbox_settings
            settings = load_toolbox_settings()
            # 外观模式（运行时立即生效）
            mode = settings.get("appearance_mode", "system")
            if mode in ("light", "dark", "system"):
                ctk.set_appearance_mode(mode)
            # 日志级别（运行时立即生效）
            log_level = settings.get("log_level", "INFO")
            from utils.logging import set_log_level
            for name in ("CMMFiller", "pc_to_excel", "toolbox"):
                set_log_level(name, log_level)
        except Exception as e:
            logger.warning(f"应用 toolbox 设置失败（用默认）: {e}")

    def _show_settings(self) -> None:
        """打开设置弹窗。"""
        from toolbox.settings_dialog import SettingsDialog
        SettingsDialog(self.root.winfo_toplevel(), self)

    def _show_about(self) -> None:
        """打开关于弹窗。"""
        from toolbox.about_dialog import AboutDialog
        AboutDialog(self.root.winfo_toplevel())

    def _schedule_migration_notices(self) -> None:
        """主窗口就绪后展示配置迁移结果（ARCHITECTURE Phase 5a）。"""
        from toolbox.startup_notices import pop_migration_notices

        notices = pop_migration_notices()
        if notices:
            self.root.after(400, lambda n=notices: self._show_migration_notices(n))

    def _show_migration_notices(self, notices) -> None:
        from tkinter import messagebox

        lines = []
        for item in notices:
            lines.append(f"【{item.title}】\n{item.detail}")
        messagebox.showinfo(
            "配置已自动迁移",
            "\n\n—\n\n".join(lines),
            parent=self.root,
        )
        audit("settings_migration_notice", count=len(notices))

    # ── 布局 ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        root = self.root

        # 顶栏 — 改用中性 surface 色（白/暗石板），把青绿留给 accent
        self._header = ctk.CTkFrame(root, height=40, corner_radius=0)
        self._header.pack(fill="x", side="top")
        self._header.configure(fg_color=card_bg_color())

        title_frame = ctk.CTkFrame(self._header, fg_color="transparent")
        title_frame.pack(side="left", padx=12, pady=0)

        self._header_logo = get_logo_image(22)
        if self._header_logo is not None:
            ctk.CTkLabel(
                title_frame, text="", image=self._header_logo, fg_color="transparent",
            ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            title_frame,
            text=f"{APP_TITLE} {APP_VERSION}",
            font=("Microsoft YaHei", 13, "bold"),
            text_color=text_color(),
        ).pack(side="left", pady=0)

        # 顶栏右侧：关于 + 设置（清理日志 / OCR 缓存见设置面板）
        ctk.CTkButton(
            self._header, text="关于", width=58, height=24,
            font=("Microsoft YaHei", 11),
            **{**primary_button_kwargs(), "command": self._show_about},
        ).pack(side="right", padx=(4, 6), pady=8)

        ctk.CTkButton(
            self._header, text="设置", width=58, height=24,
            font=("Microsoft YaHei", 11),
            **{**primary_button_kwargs(), "command": self._show_settings},
        ).pack(side="right", padx=(4, 10), pady=8)

        # 主区域：左侧导航 + 内容
        self._body = ctk.CTkFrame(root, corner_radius=0, fg_color="transparent")
        self._body.pack(fill="both", expand=True, side="top")

        # 左侧导航
        self._nav = ctk.CTkFrame(self._body, width=self.NAV_WIDTH, corner_radius=0)
        self._nav.pack(fill="y", side="left", padx=0, pady=0)
        self._nav.pack_propagate(False)
        self._nav.configure(fg_color=card_bg_color())

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._content_frame = ctk.CTkFrame(self._body, corner_radius=0, fg_color=page_bg_color())
        self._content_frame.pack(fill="both", expand=True, side="left")

        # 状态栏 — 改用 page_bg（柔和灰/深蓝），文字跟随主题
        self._statusbar = ctk.CTkFrame(root, height=24, corner_radius=0)
        self._statusbar.pack(fill="x", side="bottom")
        self._statusbar.configure(fg_color=page_bg_color())

        self._pcdmis_label = ctk.CTkLabel(
            self._statusbar,
            text="PC-DMIS: 未连接",
            font=("Microsoft YaHei", 10),
            text_color=muted_color(),
        )
        self._pcdmis_label.pack(side="left", padx=(10, 18))

        self._module_label = ctk.CTkLabel(
            self._statusbar,
            text="",
            font=("Microsoft YaHei", 10),
            text_color=text_color(),
        )
        self._module_label.pack(side="left", padx=0)

        self._msg_label = ctk.CTkLabel(
            self._statusbar,
            text="就绪",
            font=("Microsoft YaHei", 10),
            text_color=muted_color(),
        )
        self._msg_label.pack(side="right", padx=10)

        # 内容区占位提示
        self._placeholder = ctk.CTkLabel(
            self._content_frame,
            text="未选择模块",
            font=("Microsoft YaHei", 16),
            text_color=muted_color(),
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ── 模块加载 ───────────────────────────────────────────────────────────

    def _load_modules(self):
        """从 modules 包注册表加载模块。"""
        try:
            from modules import REGISTRY
        except ImportError:
            logger.warning("modules 包未找到，跳过模块加载")
            return

        for name, mod in REGISTRY.items():
            self._add_nav_button(name, mod)

    def _add_nav_button(self, name: str, module):
        """向左侧导航添加一个模块按钮。"""
        btn = ctk.CTkButton(
            self._nav,
            text=f"{module.icon}  {module.title}",
            height=36,
            corner_radius=0,
            font=("Microsoft YaHei", 12),
            anchor="w",
            fg_color="transparent",
            hover_color=accent_hover_color(),
            text_color=text_color(),
            command=lambda n=name: self._activate_module(n),
        )
        btn.pack(fill="x", pady=0, padx=0)
        btn.configure(fg_color="transparent")
        self._nav_buttons[name] = btn
        self._modules[name] = module
        logger.debug(f"导航项注册: {name}")

    def _select_first_module(self):
        """自动选中第一个模块。"""
        names = list(self._modules.keys())
        if names:
            self._activate_module(names[0])

    def _select_startup_module(self):
        """按启动参数选模块；未指定或名称无效时回退第一个。"""
        name = self._start_module
        if name and name in self._modules:
            self._activate_module(name)
            return
        self._select_first_module()

    def _bring_to_front(self) -> None:
        root = self.root
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
            root.attributes("-topmost", True)
            root.after(700, lambda: root.attributes("-topmost", False))
        except Exception:
            logger.debug("前置窗口失败", exc_info=True)

    def _run_auto_export(self) -> None:
        """工具栏 / IPC：切到 PCDMIS 导出并触发一键导出。"""
        if not self._running:
            return
        self._bring_to_front()
        if self._active_module_name != "pc_to_excel":
            self._activate_module("pc_to_excel")
        mod = self._active_module
        if mod is None or not hasattr(mod, "request_auto_export"):
            self.update_status("自动导出失败：导出模块未就绪", "error")
            return
        self.update_status("工具栏一键导出…", "info")
        try:
            mod.request_auto_export()
        except Exception as e:
            logger.exception("自动导出触发失败: %s", e)
            self.update_status(f"自动导出失败: {e}", "error")

    def _start_ipc_poll(self) -> None:
        self._poll_ipc()

    def _poll_ipc(self) -> None:
        if not self._running:
            return
        try:
            from utils.ipc import CMD_AUTO_EXPORT, consume_command

            cmd = consume_command()
            if cmd and cmd.get("cmd") == CMD_AUTO_EXPORT:
                logger.info("收到 IPC 自动导出指令")
                self._run_auto_export()
        except Exception:
            logger.exception("IPC 轮询失败")
        self._ipc_after_id = self.root.after(400, self._poll_ipc)

    # ── 模块激活 / 卸载 ───────────────────────────────────────────────────

    def _activate_module(self, name: str):
        """切换到指定模块。"""
        if name not in self._modules:
            return
        if name == self._active_module_name:
            return

        # 隐藏当前模块。模块实例保留，避免每次切换都重建整页 UI。
        if self._active_module is not None:
            old_name = self._active_module_name or "?"
            try:
                if hasattr(self._active_module, "on_deactivate"):
                    self._active_module.on_deactivate()
                host = self._module_hosts.get(old_name)
                if host is not None:
                    host.pack_forget()
                audit("module_deactivate", module=old_name)
            except Exception as e:
                logger.exception(f"deactivate {old_name} 失败: {e}")

        # 切换高亮 — 选中态用更柔和的 accent_hover/primary 浅色
        for n, btn in self._nav_buttons.items():
            if n == name:
                btn.configure(
                    fg_color=accent_hover_color(),
                    text_color=on_accent_color(),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=text_color(),
                )

        # 挂载或显示新模块
        module = self._modules[name]
        try:
            self._placeholder.place_forget()
            # Shell 在 mount 时注入自己作为 shell 引用
            module.shell = self
            host = self._module_hosts.get(name)
            if host is None:
                host = ctk.CTkFrame(self._content_frame, corner_radius=0, fg_color=page_bg_color())
                self._module_hosts[name] = host
            host.pack(fill="both", expand=True)
            if name not in self._mounted_modules:
                module.mount(host)
                self._mounted_modules.add(name)
            module.on_activate()
            self._active_module = module
            self._active_module_name = name
            self._module_label.configure(text=module.title)
            self.update_status("就绪", "info")
            audit("module_activate", module=name, version=module.version)
            logger.info(f"模块已激活: {name}")
        except Exception as e:
            logger.exception(f"mount {name} 失败: {e}")
            self.update_status(f"加载失败: {e}", "error")

    # ── 状态栏接口（ShellProtocol 实现）───────────────────────────────────

    @staticmethod
    def _module_config_path(module_name: str) -> Path:
        """模块配置文件路径（ARCH 3.9：统一在 config_dir 下）。"""
        return paths.config_dir / module_name / "settings.json"

    def _export_legacy_settings(self) -> None:
        """导出 1.x 格式配置给旧工具使用（ARCH 3.9.2，不自动降级）。"""
        from tkinter import filedialog, messagebox
        from utils.settings import export_legacy_settings, load_and_migrate_settings

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
                config = load_and_migrate_settings(
                    module_name, self._module_config_path(module_name)
                )
                target = base.with_name(f"{base.stem}_{module_name}{base.suffix}")
                export_legacy_settings(module_name, target, config)
            audit("export_legacy_settings", path=path)
            messagebox.showinfo(
                "已导出", f"旧版配置已导出（每模块一个文件）：\n{base.parent}"
            )
        except Exception as e:
            logger.exception(f"导出旧版配置失败: {e}")
            messagebox.showerror("导出失败", f"导出旧版配置失败：\n{e}")

    def update_status(self, text: str, level: str = "info"):
        """
        更新状态栏消息。
        level: 'info' | 'ok' | 'warn' | 'error'
        """
        color_map = {
            "info": muted_color(),
            "ok": TOOLBOX_THEME["ok"],
            "warn": TOOLBOX_THEME["warn"],
            "error": TOOLBOX_THEME["bad"],
        }
        self._msg_label.configure(text=text, text_color=color_map.get(level, muted_color()))

    def update_pcdmis_status(self, connected: bool, version: str | None = None):
        """更新 PCDMIS 连接状态。"""
        if connected:
            ver_str = f" v{version}" if version else ""
            self._pcdmis_label.configure(
                text=f"🟢 PC-DMIS: 已连接{ver_str}",
                text_color=TOOLBOX_THEME["ok"],
            )
        else:
            self._pcdmis_label.configure(
                text=f"🔴 PC-DMIS: 未连接",
                text_color=muted_color(),
            )

    # ── 关闭处理 ──────────────────────────────────────────────────────────

    def on_close(self, root):
        """窗口关闭回调：请求取消工作线程 → 断开 PCDMIS → 退出。

        加 2 秒 watchdog：任何阻塞的 unmount 步骤（OCR worker cancel / COM
        disconnect）超过 2 秒则强制销毁窗口，避免用户面对假死的窗口。
        """
        self._running = False
        if self._ipc_after_id is not None:
            try:
                root.after_cancel(self._ipc_after_id)
            except Exception:
                pass
            self._ipc_after_id = None
        audit("app_close")

        # watchdog：2 秒后若仍未销毁则强制 root.destroy()
        watchdog = root.after(2000, lambda: (
            logger.error("on_close 超时，强制退出"),
            root.destroy(),
        ))

        # 卸载所有已创建模块。切换时模块会缓存，退出时统一清理。
        for name in list(self._mounted_modules):
            module = self._modules.get(name)
            if module is None:
                continue
            try:
                module.unmount()
            except Exception as e:
                logger.exception(f"unmount {name} 异常: {e}")
        self._mounted_modules.clear()
        self._module_hosts.clear()

        # 正常退出路径：取消 watchdog 后销毁
        try:
            root.after_cancel(watchdog)
        except Exception:
            pass
        logger.info("Shell 关闭")
        root.destroy()
