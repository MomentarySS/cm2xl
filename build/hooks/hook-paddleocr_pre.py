"""
Pre-safe-import-module hook for paddleocr.
Patches importlib.util.spec_from_file_location to handle the tools/ path redirect.
"""
import sys
import os
import importlib
import importlib.util

_original_spec = importlib.util.spec_from_file_location

def _patched_spec(name, location, *, loader=None, submodule_search_locations=None):
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass and name == 'tools':
            expected = location
            actual = os.path.join(meipass, 'paddleocr', 'tools', '__init__.py')
            if not os.path.exists(expected) and os.path.exists(actual):
                location = actual
    return _original_spec(name, location, loader=loader, submodule_search_locations=submodule_search_locations)

importlib.util.spec_from_file_location = _patched_spec

# 打包环境：尽早指向内置 OCR 模型，避免首次运行联网下载
if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', '')
    _exe_dir = os.path.dirname(sys.executable)
    for _candidate in (
        os.path.join(_meipass, 'models', 'paddleocr') if _meipass else '',
        os.path.join(_exe_dir, '_internal', 'models', 'paddleocr'),
        os.path.join(_exe_dir, 'models', 'paddleocr'),
    ):
        if _candidate and os.path.isdir(_candidate):
            os.environ.setdefault('PADDLE_OCR_BASE_DIR', _candidate)
            break

    _paddleocr_dir = os.path.join(_meipass, 'paddleocr') if _meipass else ''
    if _paddleocr_dir and os.path.isdir(_paddleocr_dir):
        if _paddleocr_dir not in sys.path:
            sys.path.insert(0, _paddleocr_dir)
        for _mod in ('tools', 'ppocr', 'ppstructure'):
            if _mod in sys.modules and not hasattr(sys.modules[_mod], '__path__'):
                del sys.modules[_mod]
        _tools_dir = os.path.join(_paddleocr_dir, 'tools')
        _tools_init = os.path.join(_tools_dir, '__init__.py')
        if os.path.isfile(_tools_init) and 'tools' not in sys.modules:
            _spec = importlib.util.spec_from_file_location(
                'tools', _tools_init, submodule_search_locations=[_tools_dir],
            )
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules['tools'] = _mod
            _spec.loader.exec_module(_mod)
