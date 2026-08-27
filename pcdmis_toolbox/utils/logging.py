"""
cm2xl — 统一日志系统
控制台 + 按大小轮转主日志（按 logger 命名）+ 审计日志 Handler。

每个 logger 只挂主日志（{name}.log）；audit 日志由独立 audit logger 处理。
"""

import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logging(
    module_name: str,
    log_dir: Optional[Path] = None,
    *,
    level: int = logging.DEBUG,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """
    统一日志配置：控制台 + 按大小轮转主日志。

    日志目录: {data_dir}/logs/
    主日志:   {module_name}.log          (5MB × 3)
    """
    logger = logging.getLogger(module_name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. 控制台 handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 2. 主日志：按 5MB 轮转
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / f"{module_name}.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


class GuiLogHandler(logging.Handler):
    """
    将日志实时推送到 GUI 日志区的 Handler。
    各模块用此 Handler 把处理过程输出到界面日志面板。

    使用方式：
        from utils.logging import GuiLogHandler
        h = GuiLogHandler(gui_instance, root_after_fn)
        h.setLevel(logging.DEBUG)
        logger.addHandler(h)

    root_after_fn 通常是 gui.root.after，负责把日志消息派发到 GUI 线程的安全队列。
    """

    def __init__(self, gui_instance, root_after_fn=None, level=logging.DEBUG):
        super().__init__()
        self._gui = gui_instance
        self._root_after = root_after_fn or (lambda delay, fn: fn())
        self.setLevel(level)
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        )

    def emit(self, record):
        try:
            msg = self.format(record)
            self._root_after(0, lambda m=msg: self._gui._log(m))
        except Exception:
            self.handleError(record)


def set_log_level(name: str, level: str) -> None:
    """
    动态改指定 logger 的级别（影响已注册的所有 handler）。

    用于"设置"面板运行时切换日志级别，无需重启。

    Args:
        name: logger 名（如 "CMMFiller"、"pc_to_excel"），传 None 表示根 logger
        level: "DEBUG" / "INFO" / "WARNING" / "ERROR"
    """
    import logging as _logging
    lvl = getattr(_logging, level.upper(), _logging.INFO)
    if name is None:
        logger = _logging.getLogger()
    else:
        logger = _logging.getLogger(name)
    logger.setLevel(lvl)
    for h in logger.handlers:
        h.setLevel(lvl)
