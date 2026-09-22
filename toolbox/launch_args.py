"""cm2xl 启动参数（打包 exe / 开发 python main.py 共用）。

工具栏一键出报告：
    cm2xl.exe --module pc_to_excel --auto-export

开发快速看界面：
    python main.py --skip-ocr
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWN_MODULES = frozenset({"pc_to_excel", "cmm_filler"})


@dataclass(frozen=True)
class LaunchArgs:
    module: str | None = None
    auto_export: bool = False
    skip_ocr: bool = False


def parse_launch_args(argv: list[str] | None = None) -> LaunchArgs:
    """解析 argv。未知参数忽略，避免 windowed exe 上 argparse 无控制台可显示。"""
    if argv is None:
        import sys

        argv = sys.argv[1:]

    module: str | None = None
    auto_export = False
    skip_ocr = False
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--auto-export":
            auto_export = True
        elif token == "--skip-ocr":
            skip_ocr = True
        elif token.startswith("--module="):
            module = token.split("=", 1)[1].strip() or None
        elif token == "--module" and i + 1 < len(argv):
            module = argv[i + 1].strip() or None
            i += 1
        i += 1

    if auto_export:
        module = "pc_to_excel"
    elif module not in KNOWN_MODULES:
        module = None

    skip_ocr = skip_ocr or auto_export or module == "pc_to_excel"
    return LaunchArgs(module=module, auto_export=auto_export, skip_ocr=skip_ocr)
