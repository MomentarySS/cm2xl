"""
PCDMIS 导出模块 — 实现 ModuleProtocol 适配层
包装 gui/main_window.py 的 MainWindow 类，供 Shell 通过 mount()/unmount() 挂载。
"""

from .app_meta import __version__
from toolbox.protocol import ModuleProtocol


class PCToExcelModule(ModuleProtocol):
    """
    PCDMIS 数据导出模块（Shell 集成用）。
    实现 ModuleProtocol，供 Shell 通过 mount()/unmount()/on_activate() 使用。
    """

    title = "PCDMIS导出"
    icon = "📐"
    version = __version__

    def __init__(self):
        self._instance = None
        self._container = None

    def mount(self, parent) -> None:
        """挂载到 Shell 内容区"""
        self._container = parent
        for widget in parent.winfo_children():
            widget.destroy()
        self._instance = self._create_window(parent)
        self._instance.shell = self.shell

    def _create_window(self, parent):
        """工厂方法 — 延迟 import GUI，注册层不依赖具体窗口实现。"""
        from .gui.main_window import MainWindow

        return MainWindow(parent=parent)

    def unmount(self) -> None:
        """从 Shell 内容区卸载"""
        if self._instance:
            if hasattr(self._instance, "_on_close"):
                try:
                    self._instance._on_close()
                except Exception:
                    pass
            self._instance = None
        if self._container:
            for widget in self._container.winfo_children():
                widget.destroy()
            self._container = None

    def on_activate(self) -> None:
        """模块被选中时调用 — 静默刷新连接状态（不弹框）"""
        if self._instance and hasattr(self._instance, "connector"):
            self._instance.root.after(0, self._instance._refresh_conn_status)


# 模块注册（由 modules/__init__.py 的 pkgutil 自动发现）
from modules import register_module

register_module("pc_to_excel", PCToExcelModule())
