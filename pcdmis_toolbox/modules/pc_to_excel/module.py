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
            if hasattr(self._instance, "_stop_status_watcher"):
                try:
                    self._instance._stop_status_watcher()
                except Exception:
                    pass
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
        """模块被选中时调用 — 刷新连接状态并启动后台轮询（ARCHITECTURE 3.19）"""
        if self._instance and hasattr(self._instance, "connector"):
            self._instance.root.after(0, self._instance._refresh_conn_status)
            if hasattr(self._instance, "_start_status_watcher"):
                self._instance._start_status_watcher()

    def on_deactivate(self) -> None:
        """模块被隐藏时停止轮询，但保留界面实例以便快速切回。"""
        if self._instance and hasattr(self._instance, "_stop_status_watcher"):
            self._instance._stop_status_watcher()

    def request_auto_export(self) -> None:
        """PC-DMIS 工具栏 / IPC：连接当前程序并一键导出 Excel。"""
        if self._instance and hasattr(self._instance, "request_auto_export"):
            self._instance.request_auto_export()


# 模块注册（由 modules/__init__.py 的 pkgutil 自动发现）
from modules import register_module

register_module("pc_to_excel", PCToExcelModule())
