"""
cm2xl — 模块接口协议
所有功能模块必须实现 ModuleProtocol 才能被 Shell 挂载。
"""

from typing import Protocol, runtime_checkable, Optional
import customtkinter as ctk


@runtime_checkable
class ModuleProtocol(Protocol):
    """所有功能模块必须实现的接口。"""

    @property
    def title(self) -> str:
        """模块显示名称（用于左侧导航）"""
        ...

    @property
    def icon(self) -> str:
        """模块图标（emoji 或资源路径）"""
        ...

    @property
    def version(self) -> str:
        """模块版本号"""
        ...

    shell: "ShellProtocol"  # Shell 在 mount 时注入，模块通过它更新状态栏

    def mount(self, parent: ctk.CTkFrame) -> None:
        """挂载到壳的内容区。"""
        ...

    def unmount(self) -> None:
        """从壳的内容区卸载。"""
        ...

    def on_activate(self) -> None:
        """模块被选中时调用（可选）。"""
        ...


class ShellProtocol(Protocol):
    """
    Shell 提供给模块的状态更新回调接口。
    模块通过 self.shell 属性访问（由 Shell 在 mount 时注入）。
    """

    def update_status(self, text: str, level: str) -> None:
        """
        更新状态栏提示信息。
        level: 'info' | 'ok' | 'warn' | 'error'
        """
        ...

    def update_pcdmis_status(self, connected: bool, version: Optional[str] = None) -> None:
        """
        更新 PCDMIS 连接状态（仅 pc_to_excel 模块使用）。
        """
        ...
