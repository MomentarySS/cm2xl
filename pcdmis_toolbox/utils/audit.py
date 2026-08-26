"""
PCDMIS Toolbox 2.0 — 审计日志
所有用户可见操作必须调用 audit() 记录，格式固定为 [时间] action | k=v。
audit logger 独立写入专用 audit 文件（按天切分 × 30 天），不混入主日志。
"""

import logging
from datetime import datetime

AUDIT_LOG_NAME = "toolbox.audit"


def audit(action: str, **fields) -> None:
    """
    记录一次用户操作。

    示例：
        audit("export_excel", count=123, path="/path/to.xlsx", duration_s=2.3)
        audit("pcdmis_connect", prog_id="PCDLRN.Application.19.1", version="2024.1")
    """
    logger = logging.getLogger(AUDIT_LOG_NAME)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    field_str = " ".join(f"{k}={v!r}" for k, v in fields.items())
    logger.info(f"[{timestamp}] {action} | {field_str}")


def setup_audit_logging(log_dir=None) -> logging.Logger:
    """为审计日志单独配置（独立写入专用 audit 文件，不冒泡到主 logger）。"""
    logger = logging.getLogger(AUDIT_LOG_NAME)
    logger.setLevel(logging.INFO)

    # 防冒泡：audit 消息只写专用文件，不混入 toolbox.log
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. 控制台（开发模式可见）
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        # 专用 audit 文件（按天切分），不与主日志混淆
        ah = logging.handlers.TimedRotatingFileHandler(
            log_dir / f"{AUDIT_LOG_NAME}.audit.log",
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        ah.setLevel(logging.INFO)
        ah.setFormatter(formatter)
        logger.addHandler(ah)

    return logger
