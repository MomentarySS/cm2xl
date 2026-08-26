"""
PCDMIS Toolbox 2.0 — 模块注册表
自动发现并注册所有 modules/<name>/gui.py 中的模块。
"""

import importlib
import pkgutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

REGISTRY: dict = {}


def _discover_modules():
    """遍历当前包的所有子包，加载 gui.py（或 module.py）并执行注册。"""
    pkg_path = Path(__file__).parent
    for _, name, is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if is_pkg:
            # 适配层入口：优先 gui.py；存在 gui/ 子包时（与 gui.py 同名冲突），
            # 适配层在 module.py（见 modules/pc_to_excel/module.py）
            entry = "gui" if (pkg_path / name / "gui.py").is_file() else "module"
            try:
                importlib.import_module(f"modules.{name}.{entry}")
            except Exception as e:
                logger.error(
                    f"模块 '{name}' 加载失败，已跳过。请检查依赖是否安装。({e})"
                )


def register_module(name: str, module) -> None:
    """注册一个功能模块。"""
    REGISTRY[name] = module


# 自动发现并注册所有模块
_discover_modules()
