"""
cm2xl — 线程管理工具
提供 CancellableWorker，替代 bare threading.Thread(daemon=True)。
"""

import threading
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class CancellableWorker:
    """
    可取消的工作线程。

    用法：
        worker = CancellableWorker()
        worker.start(self._do_work, arg1, arg2)
        # ... 工作中 ...
        worker.request_cancel()   # 请求取消
        worker.wait(timeout=10)  # 等待线程结束（最多 10s）
    """

    def __init__(self):
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._target: Callable | None = None
        self._args: tuple = ()
        self._kwargs: dict = {}

    def start(self, target: Callable, *args, **kwargs) -> None:
        """启动工作线程。"""
        self._cancel_event.clear()
        self._thread = threading.Thread(
            target=self._wrapper,
            args=(target,) + args,
            kwargs=kwargs,
            daemon=True,
        )
        self._thread.start()
        logger.debug(f"CancellableWorker started: {target.__name__}")

    def _wrapper(self, target: Callable, *args, **kwargs) -> None:
        """包装目标函数，在其运行期间检查取消事件。"""
        try:
            # 每执行完一轮后检查取消标记（由业务代码在循环内自行检查取消点）
            self._target = target
            self._args = args
            self._kwargs = kwargs
            target(*args, **kwargs)
        except Exception as e:
            logger.exception(f"CancellableWorker {target.__name__} raised: {e}")
            raise

    def request_cancel(self) -> None:
        """请求取消工作线程。"""
        self._cancel_event.set()
        logger.debug("CancellableWorker cancel requested")

    def is_cancelled(self) -> bool:
        """查询是否已请求取消。"""
        return self._cancel_event.is_set()

    def wait(self, timeout: float = 5.0) -> bool:
        """
        等待线程结束。
        返回 True 表示线程已退出，False 表示超时。
        """
        if self._thread:
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()
        return True

    @property
    def is_running(self) -> bool:
        """线程是否仍在运行。"""
        return self._thread is not None and self._thread.is_alive()
