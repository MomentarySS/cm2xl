"""
CMMFiller 模块适配层 — Phase 1 存根（实现 ModuleProtocol）
Phase 3 替换为真实 CMMFiller GUI 挂载。
"""

import customtkinter as ctk
from toolbox.protocol import ModuleProtocol
from utils.theme import TOOLBOX_THEME


class CMMFillerModule(ModuleProtocol):
    title = "CMM报告填充"
    icon = "📊"
    version = "1.0.0"

    def __init__(self):
        self._instance = None
        self._container: ctk.CTkFrame | None = None
        self.shell = None

    def mount(self, parent: ctk.CTkFrame) -> None:
        self._container = parent
        for w in parent.winfo_children():
            w.destroy()

        # Phase 1: 简单占位
        ctk.CTkLabel(
            parent,
            text="📊 CMM报告填充模块\n\n(Phase 3 迁移完成前占位)",
            font=("Microsoft YaHei", 14),
            text_color=TOOLBOX_THEME["text_muted"],
        ).place(relx=0.5, rely=0.5, anchor="center")

    def unmount(self) -> None:
        if self._container:
            for w in self._container.winfo_children():
                w.destroy()
            self._container = None
        self._instance = None

    def on_activate(self) -> None:
        pass


# 模块注册（由 Shell 在 _load_modules 时发现）
from modules import register_module
register_module("cmm_filler", CMMFillerModule())
