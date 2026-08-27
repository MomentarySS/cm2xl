"""
PCDMIS Toolbox 2.0 — 壳主窗口
左侧导航 + 内容区 + 状态栏，模块挂载/卸载，状态通知。
"""

import sys
import logging
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from toolbox.app_meta import APP_TITLE, APP_VERSION
from utils.paths import paths
from utils.audit import audit
from utils.theme import TOOLBOX_THEME

logger = logging.getLogger(__name__)


class Shell:
    """
    主窗口 Shell。

    布局：
    ┌──────────────────────────────────────────────────────────┐
    │  PCDMIS Toolbox 2.0                       [版本] [_][□][X] │
    ├──────────┬─────────────────────────────────────────────┤
    │          │                                              │
    │  📊 CMM报告填充 │        模块内容区                      │
    │  📐 PCDMIS导出 │        (挂载当前模块的 GUI)             │
    │  ⚙️ 设置   │                                              │
    │          │                                              │
    ├──────────┴─────────────────────────────────────────────┤
    │  状态栏: PCDMIS连接 | 当前模块 | 操作提示                │
    └──────────────────────────────────────────────────────────┘
    """

    NAV_WIDTH = 180

    def __init__(self, root: ctk.CTk):
        self.root = root
        self._active_module: Optional[object] = None
        self._active_module_name: Optional[str] = None
        self._modules: dict[str, object] = {}
        self._running = True

        self._build_layout()
        self._load_modules()
        self._select_first_module()
        logger.info("Shell 初始化完成")

    # ── 布局 ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        root = self.root

        # 顶栏 — 改用中性 surface 色（白/暗石板），把青绿留给 accent
        self._header = ctk.CTkFrame(root, height=48, corner_radius=0)
        self._header.pack(fill="x", side="top")
        self._header.configure(
            fg_color=[TOOLBOX_THEME["card_bg"], "#252B3A"]
        )

        ctk.CTkLabel(
            self._header,
            text=f"{APP_TITLE} {APP_VERSION}",
            font=("Microsoft YaHei", 14, "bold"),
            text_color=[TOOLBOX_THEME["text"], "#E8E6E1"],
        ).pack(side="left", padx=16, pady=0)

        # "导出旧版配置" 按钮：去掉白边，用 accent 填充色与系统一致
        ctk.CTkButton(
            self._header, text="导出旧版配置", width=120, height=28,
            font=("Microsoft YaHei", 11),
            fg_color=[TOOLBOX_THEME["accent"], "#0F766E"],
            hover_color=[TOOLBOX_THEME["accent_hover"], "#14B8A6"],
            text_color="white",
            command=self._export_legacy_settings,
        ).pack(side="right", padx=12, pady=10)

        # 主区域：左侧导航 + 内容
        self._body = ctk.CTkFrame(root, corner_radius=0, fg_color="transparent")
        self._body.pack(fill="both", expand=True, side="top")

        # 左侧导航
        self._nav = ctk.CTkFrame(self._body, width=self.NAV_WIDTH, corner_radius=0)
        self._nav.pack(fill="y", side="left", padx=0, pady=0)
        self._nav.pack_propagate(False)
        self._nav.configure(fg_color=[TOOLBOX_THEME["card_bg"], "#252B3A"])

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._content_frame = ctk.CTkFrame(self._body, corner_radius=0)
        self._content_frame.pack(fill="both", expand=True, side="left")

        # 状态栏 — 改用 page_bg（柔和灰/深蓝），文字跟随主题
        self._statusbar = ctk.CTkFrame(root, height=28, corner_radius=0)
        self._statusbar.pack(fill="x", side="bottom")
        self._statusbar.configure(
            fg_color=[TOOLBOX_THEME["page_bg"], "#1A1F2B"]
        )

        self._pcdmis_label = ctk.CTkLabel(
            self._statusbar,
            text="PC-DMIS: 未连接",
            font=("Microsoft YaHei", 11),
            text_color=[TOOLBOX_THEME["text_muted"], "#9CA3AF"],
        )
        self._pcdmis_label.pack(side="left", padx=(12, 24))

        self._module_label = ctk.CTkLabel(
            self._statusbar,
            text="",
            font=("Microsoft YaHei", 11),
            text_color=[TOOLBOX_THEME["text"], "#E8E6E1"],
        )
        self._module_label.pack(side="left", padx=0)

        self._msg_label = ctk.CTkLabel(
            self._statusbar,
            text="就绪",
            font=("Microsoft YaHei", 11),
            text_color=[TOOLBOX_THEME["text_muted"], "#9CA3AF"],
        )
        self._msg_label.pack(side="right", padx=12)

        # 内容区占位提示
        self._placeholder = ctk.CTkLabel(
            self._content_frame,
            text="未选择模块",
            font=("Microsoft YaHei", 16),
            text_color=[TOOLBOX_THEME["text_muted"], "#9CA3AF"],
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
            height=44,
            corner_radius=0,
            font=("Microsoft YaHei", 13),
            anchor="w",
            fg_color="transparent",
            hover_color=[TOOLBOX_THEME["accent_hover"], "#0D9488"],
            text_color=[TOOLBOX_THEME["text"], "#E8E6E1"],
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

    # ── 模块激活 / 卸载 ───────────────────────────────────────────────────

    def _activate_module(self, name: str):
        """切换到指定模块。"""
        if name not in self._modules:
            return

        # 卸载当前模块
        if self._active_module is not None:
            old_name = self._active_module_name or "?"
            try:
                self._active_module.unmount()
                audit("module_deactivate", module=old_name)
            except Exception as e:
                logger.exception(f"unmount {old_name} 失败: {e}")

        # 切换高亮 — 选中态用更柔和的 accent_hover/primary 浅色
        for n, btn in self._nav_buttons.items():
            if n == name:
                btn.configure(
                    fg_color=[TOOLBOX_THEME["accent_hover"], "#14B8A6"],
                    text_color="white",
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=[TOOLBOX_THEME["text"], "#E8E6E1"],
                )

        # 清空内容区
        for w in self._content_frame.winfo_children():
            w.destroy()

        # 挂载新模块
        module = self._modules[name]
        try:
            # Shell 在 mount 时注入自己作为 shell 引用
            module.shell = self
            module.mount(self._content_frame)
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
            "info": "#9CA3AF",
            "ok": TOOLBOX_THEME["ok"],
            "warn": TOOLBOX_THEME["warn"],
            "error": TOOLBOX_THEME["bad"],
        }
        self._msg_label.configure(text=text, text_color=color_map.get(level, "#9CA3AF"))

    def update_pcdmis_status(self, connected: bool, version: str | None = None):
        """更新 PCDMIS 连接状态。"""
        if connected:
            ver_str = f" v{version}" if version else ""
            self._pcdmis_label.configure(
                text=f"PC-DMIS: 已连接{ver_str}",
                text_color=TOOLBOX_THEME["ok"],
            )
        else:
            self._pcdmis_label.configure(
                text="PC-DMIS: 未连接",
                text_color="#9CA3AF",
            )

    # ── 关闭处理 ──────────────────────────────────────────────────────────

    def on_close(self, root):
        """窗口关闭回调：请求取消工作线程 → 断开 PCDMIS → 退出。

        加 2 秒 watchdog：任何阻塞的 unmount 步骤（OCR worker cancel / COM
        disconnect）超过 2 秒则强制销毁窗口，避免用户面对假死的窗口。
        """
        self._running = False
        audit("app_close")

        # watchdog：2 秒后若仍未销毁则强制 root.destroy()
        watchdog = root.after(2000, lambda: (
            logger.error("on_close 超时，强制退出"),
            root.destroy(),
        ))

        # 卸载当前模块
        if self._active_module is not None:
            try:
                self._active_module.unmount()
            except Exception as e:
                logger.exception(f"unmount 异常: {e}")

        # 正常退出路径：取消 watchdog 后销毁
        try:
            root.after_cancel(watchdog)
        except Exception:
            pass
        logger.info("Shell 关闭")
        root.destroy()
