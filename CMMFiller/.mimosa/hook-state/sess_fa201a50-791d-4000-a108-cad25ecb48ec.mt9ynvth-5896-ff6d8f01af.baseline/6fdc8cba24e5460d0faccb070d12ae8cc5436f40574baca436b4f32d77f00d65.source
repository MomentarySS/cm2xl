"""
Pre-safe-import-module hook for paddleocr.
Patches paddleocr.py to handle frozen (PyInstaller) environment.
"""
import sys
import os
import importlib
import importlib.util


def pre_safe_import_module(module_graph, module_name, module_dirname, module_code):
    if module_name != 'paddleocr':
        return module_code

    source_path = module_code.co_filename
    if not source_path or not os.path.exists(source_path):
        return module_code

    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()

    if 'FROZEN_ENV_PATCH' in source:
        return module_code

    old = '__dir__ = os.path.dirname(__file__)'
    new = '''__dir__ = os.path.dirname(__file__)
FROZEN_ENV_PATCH = True
if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", "")
    if _meipass:
        if os.path.basename(__file__) in ("paddleocr.py", "paddleocr.pyc"):
            _candidate = os.path.join(_meipass, "paddleocr")
            if os.path.isdir(_candidate):
                __dir__ = _candidate'''

    source = source.replace(old, new, 1)

    tools_block = (
        'tools = _import_file(\n'
        '    "tools", os.path.join(__dir__, "tools/__init__.py"), make_importable=True\n'
        ')'
    )
    tools_fix = tools_block + '\ntools.__path__ = [os.path.join(__dir__, "tools")]  # FROZEN_TOOLS_PATH_FIX'
    if tools_block in source and 'FROZEN_TOOLS_PATH_FIX' not in source:
        source = source.replace(tools_block, tools_fix, 1)

    with open(source_path, 'w', encoding='utf-8') as f:
        f.write(source)

    return compile(source, source_path, 'exec')
