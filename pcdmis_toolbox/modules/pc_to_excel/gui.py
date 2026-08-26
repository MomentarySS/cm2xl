"""
PCDMIS导出 模块适配层 — Phase 1 存根（实现 ModuleProtocol）
Phase 4 替换为真实 pc_to_excel GUI 挂载。
"""

import customtkinter as ctk
from toolbox.protocol import ModuleProtocol
from utils.theme import TOOLBOX_THEME


class PCToExcelModule(ModuleProtocol):
    title = "PCDMIS导出"
    icon = "📐"
    version = "1.4.5"

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
            text="📐 PCDMIS导出模块\n\n(Phase 4 迁移完成前占位)",
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


# 模块注册
from modules import register_module
register_module("pc_to_excel", PCToExcelModule())
