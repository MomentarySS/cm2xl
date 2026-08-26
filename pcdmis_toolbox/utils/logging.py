"""
PCDMIS Toolbox 2.0 — 统一日志系统
控制台 + 按大小轮转主日志 + 按天切分审计日志 + GUI Handler。
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
    audit_backup_count: int = 30,
    when: str = "midnight",
) -> logging.Logger:
    """
    统一日志配置：控制台 + 按大小轮转主日志 + 按天切分审计日志。

    日志目录: {data_dir}/logs/
    主日志:   {module_name}.log          (5MB × 3)
    审计日志: {module_name}.audit.log   (每天切 × 30天)
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

        # 3. 审计日志：按天切分
        ah = TimedRotatingFileHandler(
            log_dir / f"{module_name}.audit.log",
            when=when,
            backupCount=audit_backup_count,
            encoding="utf-8",
        )
        ah.setLevel(logging.INFO)
        ah.setFormatter(formatter)
        logger.addHandler(ah)

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
