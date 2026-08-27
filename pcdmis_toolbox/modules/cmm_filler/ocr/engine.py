"""
OCR 引擎抽象层
==============

使用方式:
    from modules.cmm_filler.ocr.engine import OCREngine, PaddleOCREngine

    # 默认使用 PaddleOCR
    engine = PaddleOCREngine()
    lines = engine.recognize('image.png')

    # 切换引擎只需改一行（后续补充 EasyOCR、Tesseract 实现即可）
    engine = EasyOCREngine()
"""

import os
import sys
from pathlib import Path
from abc import ABC, abstractmethod

from utils.error_codes import ErrorCode, ToolboxError


def _resolve_bundled_model_base() -> Path | None:
    """定位项目或打包内置的 PaddleOCR 模型目录"""
    candidates = []
    _frozen = getattr(sys, "frozen", False)
    if _frozen:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / '_internal' / 'models' / 'paddleocr',
            exe_dir / 'models' / 'paddleocr',
        ])
    else:
        # 相对于本文件位置向上两级找到 modules/cmm_filler/models/paddleocr
        candidates.append(Path(__file__).resolve().parent.parent / 'models' / 'paddleocr')

    for base in candidates:
        if base.exists() and any(base.rglob('inference.pdmodel')):
            return base
    return None


def _resolve_model_base(custom_dir: str = "") -> Path | None:
    """
    按优先级定位 PaddleOCR 模型目录：
    1. 用户自定义路径（toolbox settings 中的 ocr_model_dir）
    2. 打包内置 / 项目内置（fallback）

    返回 None 表示都找不到（OCR 引擎启动时会抛清晰错误）。
    """
    if custom_dir:
        p = Path(custom_dir)
        if p.exists() and any(p.rglob('inference.pdmodel')):
            return p
    return _resolve_bundled_model_base()


def _get_user_ocr_model_dir() -> str:
    """从 toolbox settings 读取用户自定义 OCR 模型目录（空字符串表示用内置）。"""
    try:
        from utils.settings import load_toolbox_settings
        return load_toolbox_settings().get("ocr_model_dir", "") or ""
    except Exception:
        return ""


def _bootstrap_paddleocr_for_frozen():
    """打包环境从 _internal/paddleocr 文件系统加载，绕过 PyInstaller 归档缺陷"""
    if not getattr(sys, 'frozen', False):
        return
    import importlib.util

    meipass = getattr(sys, '_MEIPASS', '')
    exe_dir = Path(sys.executable).resolve().parent
    paddleocr_dir = None
    for candidate in (
        Path(meipass) / 'paddleocr' if meipass else None,
        exe_dir / '_internal' / 'paddleocr',
    ):
        if candidate and (candidate / 'paddleocr.py').is_file():
            paddleocr_dir = candidate
            break
    if not paddleocr_dir:
        return

    root = str(paddleocr_dir)
    if root not in sys.path:
        sys.path.insert(0, root)

    for name in list(sys.modules):
        if name in ('paddleocr', 'tools', 'ppocr', 'ppstructure') or name.startswith(
            ('paddleocr.', 'tools.', 'ppocr.', 'ppstructure.')
        ):
            del sys.modules[name]

    def _load_pkg(pkg_name, pkg_root):
        init_py = os.path.join(pkg_root, '__init__.py')
        if not os.path.isfile(init_py):
            return
        spec = importlib.util.spec_from_file_location(
            pkg_name, init_py, submodule_search_locations=[pkg_root],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[pkg_name] = module
        spec.loader.exec_module(module)

    _load_pkg('tools', os.path.join(root, 'tools'))
    _load_pkg('ppocr', os.path.join(root, 'ppocr'))
    _load_pkg('ppstructure', os.path.join(root, 'ppstructure'))

    po_py = os.path.join(root, 'paddleocr.py')
    spec = importlib.util.spec_from_file_location('paddleocr.paddleocr', po_py)
    po_mod = importlib.util.module_from_spec(spec)
    sys.modules['paddleocr.paddleocr'] = po_mod
    spec.loader.exec_module(po_mod)

    _load_pkg('paddleocr', root)


class OCREngine(ABC):
    """OCR 引擎抽象基类，便于后续切换引擎"""

    @abstractmethod
    def recognize(self, img_path: str) -> list[str]:
        """识别图片，返回文本行列表"""
        ...


class PaddleOCREngine(OCREngine):
    """PaddleOCR 引擎（当前默认）"""

    def __init__(self, lang: str = 'ch'):
        import logging
        logger = logging.getLogger('CMMFiller')
        _bootstrap_paddleocr_for_frozen()
        from paddleocr import PaddleOCR
        # 优先用 settings 中的自定义路径，否则回退到内置
        custom_dir = _get_user_ocr_model_dir()
        model_base = _resolve_model_base(custom_dir)
        if model_base and any(Path(model_base).rglob('inference.pdmodel')):
            os.environ['PADDLE_OCR_BASE_DIR'] = str(model_base)
            logger.info(f'使用 OCR 模型: {model_base}')
        else:
            logger.error(f'未找到 OCR 模型（自定义: "{custom_dir or "未设置"}"，内置查找位置: {"_internal/models/paddleocr" if getattr(sys, "frozen", False) else "modules/cmm_filler/models/paddleocr"}）')
            raise ToolboxError(
                ErrorCode.MODEL_MISSING,
                'OCR 模型文件缺失，无法离线识别。\n'
                '请在「设置 → OCR 模型」中指定模型目录，\n'
                '或重新复制完整的 PCDMIS Toolbox 文件夹\n'
                f'（需包含 {"_internal/" if getattr(sys, "frozen", False) else "modules/cmm_filler/"}models/paddleocr 子目录，约 18 MB），\n'
                '或联系软件提供者重新获取完整安装包。',
            ) from None
        logger.info(f'初始化 PaddleOCR 引擎 (lang={lang}) ...')
        self._ocr = PaddleOCR(lang=lang, show_log=False)
        logger.info('PaddleOCR 引擎就绪')

    def recognize(self, img_path: str) -> list[str]:
        result = self._ocr.ocr(img_path, rec=True)
        lines = []
        if result and result[0]:
            for line in result[0]:
                text, conf = line[1]
                lines.append(text)
        return lines


class EasyOCREngine(OCREngine):
    """EasyOCR 引擎（备用，更轻量，中文识别率略低于 PaddleOCR）
    需要安装: pip install easyocr
    """

    def __init__(self, lang: str = 'ch_sim'):
        import logging
        logger = logging.getLogger('CMMFiller')
        logger.info(f'初始化 EasyOCR 引擎 (lang={lang}) ...')
        import easyocr
        self._reader = easyocr.Reader([lang], gpu=False)
        logger.info('EasyOCR 引擎就绪')

    def recognize(self, img_path: str) -> list[str]:
        results = self._reader.readtext(img_path, detail=0)
        return [str(r) for r in results]


class TesseractEngine(OCREngine):
    """Tesseract 引擎（备用，开源，中文需额外安装语言包）
    需要安装 Tesseract: https://github.com/tesseract-ocr/tesseract
    """

    def __init__(self, lang: str = 'chi_sim'):
        import logging
        logger = logging.getLogger('CMMFiller')
        logger.info(f'初始化 Tesseract 引擎 (lang={lang}) ...')
        import pytesseract
        self._pytesseract = pytesseract
        self._lang = lang
        logger.info('Tesseract 引擎就绪')

    def recognize(self, img_path: str) -> list[str]:
        import pytesseract
        from PIL import Image
        img = Image.open(img_path)
        text = pytesseract.image_to_string(img, lang=self._lang)
        return [line.strip() for line in text.split('\n') if line.strip()]
