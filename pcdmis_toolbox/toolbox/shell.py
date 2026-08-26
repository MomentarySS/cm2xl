"""
PCDMIS Toolbox 2.0 — 壳主窗口
左侧导航 + 内容区 + 状态栏，模块挂载/卸载，状态通知。
"""

import sys
import logging
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

        # 顶栏
        self._header = ctk.CTkFrame(root, height=48, corner_radius=0)
        self._header.pack(fill="x", side="top")
        self._header.configure(fg_color=[TOOLBOX_THEME["primary"], "#0F766E"])

        ctk.CTkLabel(
            self._header,
            text=f"{APP_TITLE} {APP_VERSION}",
            font=("Microsoft YaHei", 14, "bold"),
            text_color="white",
        ).pack(side="left", padx=16, pady=0)

        # 主区域：左侧导航 + 内容
        self._body = ctk.CTkFrame(root, corner_radius=0, fg_color="transparent")
        self._body.pack(fill="both", expand=True, side="top")

        # 左侧导航
        self._nav = ctk.CTkFrame(self._body, width=self.NAV_WIDTH, corner_radius=0)
        self._nav.pack(fill="y", side="left", padx=0, pady=0)
        self._nav.pack_propagate(False)
        self._nav.configure(fg_color=[TOOLBOX_THEME["card_bg"], "#1E293B"])

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._content_frame = ctk.CTkFrame(self._body, corner_radius=0)
        self._content_frame.pack(fill="both", expand=True, side="left")

        # 状态栏
        self._statusbar = ctk.CTkFrame(root, height=28, corner_radius=0)
        self._statusbar.pack(fill="x", side="bottom")
        self._statusbar.configure(
            fg_color=[TOOLBOX_THEME["muted"], "#475569"]
        )

        self._pcdmis_label = ctk.CTkLabel(
            self._statusbar,
            text="PC-DMIS: 未连接",
            font=("Microsoft YaHei", 11),
            text_color="white",
        )
        self._pcdmis_label.pack(side="left", padx=(12, 24))

        self._module_label = ctk.CTkLabel(
            self._statusbar,
            text="",
            font=("Microsoft YaHei", 11),
            text_color="white",
        )
        self._module_label.pack(side="left", padx=0)

        self._msg_label = ctk.CTkLabel(
            self._statusbar,
            text="就绪",
            font=("Microsoft YaHei", 11),
            text_color="#94A3B8",
        )
        self._msg_label.pack(side="right", padx=12)

        # 内容区占位提示
        self._placeholder = ctk.CTkLabel(
            self._content_frame,
            text="未选择模块",
            font=("Microsoft YaHei", 16),
            text_color=[TOOLBOX_THEME["text_muted"], "#94A3B8"],
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
            text_color=[TOOLBOX_THEME["text"], "#F1F5F9"],
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

        # 切换高亮
        for n, btn in self._nav_buttons.items():
            if n == name:
                btn.configure(
                    fg_color=[TOOLBOX_THEME["accent"], "#0F766E"],
                    text_color="white",
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=[TOOLBOX_THEME["text"], "#F1F5F9"],
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

    def update_status(self, text: str, level: str = "info"):
        """
        更新状态栏消息。
        level: 'info' | 'ok' | 'warn' | 'error'
        """
        color_map = {
            "info": "#94A3B8",
            "ok": TOOLBOX_THEME["ok"],
            "warn": TOOLBOX_THEME["warn"],
            "error": TOOLBOX_THEME["bad"],
        }
        self._msg_label.configure(text=text, text_color=color_map.get(level, "#94A3B8"))

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
                text_color="#94A3B8",
            )

    # ── 关闭处理 ──────────────────────────────────────────────────────────

    def on_close(self, root):
        """窗口关闭回调：请求取消工作线程 → 断开 PCDMIS → 退出。"""
        self._running = False
        audit("app_close")

        # 卸载当前模块
        if self._active_module is not None:
            try:
                self._active_module.unmount()
            except Exception:
                pass

        logger.info("Shell 关闭")
        root.destroy()
