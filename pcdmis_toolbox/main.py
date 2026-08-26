"""
PCDMIS Toolbox 2.0 — 统一启动入口

必须在所有 import 之前执行：
  1. multiprocessing.freeze_support()   ← PyInstaller 打包多进程必需
  2. PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION = 'python'  ← PaddleOCR 兼容
  3. 64 位检测
  4. ctk.set_default_color_theme         ← 只调一次，避免主题冲突

然后初始化日志 + 审计日志 + 异常处理 + Shell 窗口。
"""

# ── 最早处：多进程 + 环境变量 + 位数检测（不可移后）─────────────────────────
import multiprocessing
multiprocessing.freeze_support()

import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import struct

def _check_bitness() -> None:
    bits = struct.calcsize("P") * 8
    if bits != 64:
        raise RuntimeError(
            f"[E1002] 当前 Python 为 {bits} 位，"
            "PC-DMIS 2022+（64-bit）需要 64 位 Python。\n"
            "请使用 64 位 Python 运行本工具。"
        )

_check_bitness()
del _check_bitness  # 不留在全局命名空间

# ── 主题（必须在 customtkinter 首次 import 前调一次）─────────────────────
import customtkinter as ctk
from utils.theme import apply_theme

apply_theme()  # 只调一次；各模块禁止再调 set_default_color_theme

# ── 标准库 ─────────────────────────────────────────────────────────────────
import sys
import traceback
from pathlib import Path

# ── 本地模块 ───────────────────────────────────────────────────────────────
from toolbox.app_meta import APP_TITLE, APP_VERSION
from utils.paths import paths
from utils.logging import setup_logging
from utils.audit import audit, setup_audit_logging
from utils.error_codes import format_user_error

# ── 日志初始化 ─────────────────────────────────────────────────────────────
logger = setup_logging("toolbox", paths.log_dir)
audit_logger = setup_audit_logging(paths.log_dir)

logger.info(f"{APP_TITLE} {APP_VERSION} 启动中...")
audit("app_start", version=APP_VERSION, frozen=paths.is_frozen())

# ── 全局异常处理 ────────────────────────────────────────────────────────────
def _global_exception_handler(exc_type, exc_val, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
    crash_log = paths.log_dir / "crash.log"
    with open(crash_log, "a", encoding="utf-8") as f:
        f.write(tb)

    title, hint = format_user_error(exc_val)
    msg = title
    if hint:
        msg += f"\n\n提示：{hint}"
    msg += "\n\n详情已写入日志。"

    # 延迟 import 避免 tkinter 在异常前被触发
    from tkinter import messagebox
    messagebox.showerror("程序异常", msg)
    sys.exit(1)

sys.excepthook = _global_exception_handler

# ── atexit 清理 ─────────────────────────────────────────────────────────────
import atexit
import logging

def _cleanup_on_exit():
    # 清理临时 PDF
    for tmp in paths.cache_dir.glob("*.tmp.pdf"):
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    logging.shutdown()

atexit.register(_cleanup_on_exit)

# ── Shell 入口 ──────────────────────────────────────────────────────────────
def main():
    logger.info("初始化 Shell...")
    try:
        from toolbox.shell import Shell

        root = ctk.CTk()
        root.title(f"{APP_TITLE} {APP_VERSION}")
        root.geometry("1100x700")
        root.minsize(900, 600)

        shell = Shell(root)
        root.protocol("WM_DELETE_WINDOW", lambda: shell.on_close(root))
        root.mainloop()
    except Exception as e:
        logger.exception("Shell 初始化失败")
        raise

if __name__ == "__main__":
    main()
