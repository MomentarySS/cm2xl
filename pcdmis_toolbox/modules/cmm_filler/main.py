"""
CMMFiller 独立运行入口
支持两种模式：
  - 独立窗口模式（默认）：创建独立 GUI 窗口
  - Shell 集成模式：通过 python -m pcdmis_toolbox.main 调用

用法：
  python -m modules.cmm_filler          # 独立 GUI
"""

import sys
import os

# ── PaddleOCR 必须在最早时刻初始化（在所有 import 之前）────────────
# 这些是 cmm_filler_v10.py 原有的环境变量，已移至 toolbox.main.py，
# 但独立运行时也要保护。
import multiprocessing
multiprocessing.freeze_support()
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

import customtkinter as ctk
from utils.theme import apply_theme
from utils.logging import setup_logging
from utils.paths import paths

# 设置青绿主题（独立模式也需要统一外观）
apply_theme()

# CMMFiller 日志落盘（独立运行也写 cmm_filler.log，供「查看日志」读取）
setup_logging("CMMFiller", paths.log_dir)

from .gui import CMMFillerGUI


def main():
    app = CMMFillerGUI(parent=None)
    app.root.mainloop()


if __name__ == '__main__':
    main()
