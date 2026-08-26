"""
Runtime hook for paddleocr - fixes __dir__ in frozen environment
"""
import os
import sys

if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', '')
    if _meipass:
        try:
            import paddleocr
            if hasattr(paddleocr, '__dir__'):
                candidate = os.path.join(_meipass, 'paddleocr')
                if os.path.isdir(candidate):
                    paddleocr.__dir__ = candidate
        except ImportError:
            pass
