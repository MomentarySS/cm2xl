"""
cm2xl — 模块注册表
自动发现并注册所有 modules/<name>/gui.py 中的模块。
"""

import importlib
import pkgutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

REGISTRY: dict = {}


def _discover_modules():
    """遍历当前包的所有子包，加载 module.py（优先，含 register_module）+ gui。

    不再做文件系统检查（PyInstaller 打包后子包文件可能只在 PYZ 归档里）。
    优先 module.py —— 它是适配层（含 register_module 调用），然后再加载
    gui.py/gui/ 子包作为 GUI 实现。
    """
    pkg_path = Path(__file__).parent
    for _, name, is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if not is_pkg:
            continue
        # 优先 module.py（适配层 + register_module），再尝试 gui.py / gui/（GUI 类）
        for entry in ("module", "gui"):
            try:
                importlib.import_module(f"modules.{name}.{entry}")
            except ModuleNotFoundError:
                # 该入口不存在（cmm_filler 没有 module.py，pc_to_excel 没有 gui.py），
                # 静默跳过。
                continue
            except Exception as e:
                logger.error(
                    f"模块 '{name}' 入口 '{entry}' 加载失败: {e}"
                )


def register_module(name: str, module) -> None:
    """注册一个功能模块。"""
    REGISTRY[name] = module


# 自动发现并注册所有模块
_discover_modules()
