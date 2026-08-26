"""
PCDMIS Toolbox 2.0 — 壳主窗口（Phase 1 实现，当前为临时 stub）
"""

import customtkinter as ctk
from tkinter import messagebox
from toolbox.app_meta import APP_TITLE, APP_VERSION


class Shell:
    """临时存根，Phase 1 替换为完整实现。"""

    def __init__(self, root: ctk.CTk):
        self.root = root

        # 简单占位 UI
        ctk.CTkLabel(root, text=f"{APP_TITLE} {APP_VERSION}\n\n(Phase 0 骨架阶段)", font=("Microsoft YaHei", 18)).pack(
            expand=True
        )

    def on_close(self, root):
        root.destroy()
