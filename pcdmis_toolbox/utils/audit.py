"""
PCDMIS Toolbox 2.0 — 审计日志
所有用户可见操作必须调用 audit() 记录，格式固定为 [时间] action | k=v。
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
    """为审计日志单独配置（由 main.py 调用）。"""
    from utils.logging import setup_logging

    return setup_logging(
        AUDIT_LOG_NAME,
        log_dir,
        level=logging.INFO,
        max_bytes=5 * 1024 * 1024,
        backup_count=30,
        when="midnight",
    )
