"""
PaddleOCR fix for PyInstaller frozen environment.
Handles module path resolution for paddleocr.tools
"""
import os
import sys

def _fix_paddleocr_path():
    if not getattr(sys, 'frozen', False):
        return
    meipass = getattr(sys, '_MEIPASS', '')
    if not meipass:
        return
    tools_path = os.path.join(meipass, 'paddleocr', 'tools')
    if tools_path not in sys.path and os.path.isdir(tools_path):
        sys.path.insert(0, tools_path)

_fix_paddleocr_path()
