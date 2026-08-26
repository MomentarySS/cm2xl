"""PCDMIS 按需 Excel 测量报告 — 入口。"""

from __future__ import annotations


def _check_elevation_warning() -> None:
    try:
        from .connector.com_detector import check_elevation_match, is_pcdmis_running
        from tkinter import messagebox

        if not is_pcdmis_running():
            return
        ok, msg = check_elevation_match()
        if not ok and msg:
            messagebox.showwarning("PCDMIS COM 权限不一致", msg)
    except Exception:
        pass


def main() -> None:
    _check_elevation_warning()
    # pc_to_excel 日志落盘（独立运行模式也写到 log_dir）
    from utils.logging import setup_logging
    from utils.paths import paths

    setup_logging("pc_to_excel", paths.log_dir)

    from .gui.main_window import run_app

    run_app()


if __name__ == "__main__":
    main()
