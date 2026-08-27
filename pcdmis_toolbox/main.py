"""
cm2xl — 统一启动入口

必须在所有 import 之前执行：
  1. multiprocessing.freeze_support()   ← PyInstaller 打包多进程必需
  2. 64 位检测
  3. apply_theme()                       ← 只调一次，避免主题冲突

然后初始化日志 + 审计日志 + 异常处理 + Shell 窗口。
"""

# ── 最早处：多进程 + 位数检测（不可移后）───────────────────────────────────
import multiprocessing
multiprocessing.freeze_support()

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
setup_logging("CMMFiller", paths.log_dir)        # CMMFiller 日志落盘
setup_logging("pc_to_excel", paths.log_dir)     # pc_to_excel 日志落盘（连接/导出/植入等异常可定位）

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

# ── 配置迁移 + 实例锁 ───────────────────────────────────────────────────────

def _migrate_module_settings() -> None:
    """启动时对两个模块执行配置迁移：
    1) 基础位置迁移：旧路径 → 新路径（复制 + 旧文件改 .bak，见 ARCH 3.9）
    2) 版本升级链：补 _version 字段 + 迁移函数 + 备份（见 ARCH 3.9.1）
    """
    from utils.settings import load_and_migrate_settings, migrate_settings_if_needed

    # 1) cmm_filler：旧路径 data/cmm_filler → 新路径 config_dir/cmm_filler
    cmm_cfg = paths.config_dir / "cmm_filler"
    for name in ("settings.json", "template_config.json"):
        old = paths.data_dir / "cmm_filler" / name
        new = cmm_cfg / name
        if old.exists() and not new.exists():
            try:
                migrate_settings_if_needed("cmm_filler", old, new)
            except Exception as e:
                logger.warning(f"[settings] {name} 位置迁移跳过: {e}")

    # 2) 版本升级链
    targets = (
        ("cmm_filler", cmm_cfg / "settings.json"),
        ("pc_to_excel", paths.config_dir / "pc_to_excel" / "settings.json"),
    )
    for module_name, config_path in targets:
        try:
            load_and_migrate_settings(module_name, config_path)
        except Exception as e:
            logger.warning(f"[settings] {module_name} 配置迁移跳过: {e}")


def _acquire_instance_lock():
    """检测是否已有 Toolbox 实例（FileLock 超时 5s 则弹窗询问）。

    拿到锁的实例持有锁直到进程退出；用户选择"仍启动"则放弃锁继续运行。
    """
    from utils.settings import FileLock

    lock = FileLock(paths.data_dir / "toolbox.lock", timeout=5.0)
    locked = lock.__enter__()
    if not locked:
        from tkinter import messagebox

        again = messagebox.askyesno(
            "已有实例在运行",
            "检测到已有 cm2xl 在运行。\n\n"
            "是否仍要启动第二个实例？\n"
            "（两个实例会共用同一份配置文件）",
        )
        if not again:
            sys.exit(0)
        return None
    # 持有锁直到进程退出
    atexit.register(lambda: lock.__exit__(None, None, None))
    return lock


# ── Shell 入口 ──────────────────────────────────────────────────────────────
def _preload_ocr():
    """后台线程：仅做 PaddleOCR 预加载（唯一耗时操作）。"""
    from paddleocr import PaddleOCR as _OCR
    _OCR(use_angle_cls=True, lang='ch', show_log=False)


def _create_shell():
    """在主线程创建 Shell 窗口（必须在主线程调用）。"""
    from toolbox.shell import Shell

    root = ctk.CTk()
    root.title(f"{APP_TITLE} {APP_VERSION}")
    root.geometry("1100x700")
    root.minsize(900, 600)
    shell = Shell(root)
    root.protocol("WM_DELETE_WINDOW", lambda: shell.on_close(root))
    return root, shell


def main():
    logger.info("初始化 Shell...")
    _acquire_instance_lock()
    _migrate_module_settings()

    # Splash Screen：后台线程预加载 PaddleOCR，主线程显示进度
    from toolbox.splash import SplashScreen

    splash = SplashScreen(min_display_ms=1200)
    try:
        splash.show_and_wait(_preload_ocr)
    except Exception as e:
        logger.exception("PaddleOCR 初始化失败: %s", e)
        raise

    # Splash 已关闭，创建 Shell 窗口（主线程）
    logger.info("创建 Shell...")
    try:
        root, shell = _create_shell()
    except Exception as e:
        logger.exception("Shell 初始化失败")
        raise

    root.mainloop()

if __name__ == "__main__":
    main()
