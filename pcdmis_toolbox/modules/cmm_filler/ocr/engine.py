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


def _get_user_ocr_settings() -> tuple:
    """
    从 toolbox settings 读取 OCR 配置。
    返回 (ocr_model_dir: str, ocr_model_tier: str)
    """
    try:
        from utils.settings import load_toolbox_settings
        s = load_toolbox_settings()
        return (s.get("ocr_model_dir", "") or "", s.get("ocr_model_tier", "server") or "server")
    except Exception:
        return ("", "server")


# 模型目录名（tier → (det_subdir, rec_subdir)）
_TIER_MODEL_NAMES: dict = {
    "server": ("ch_PP-OCRv4_det_infer", "ch_PP-OCRv4_rec_infer"),
    "mobile": ("ch_ppocr_mobile_v2.0_det_infer", "ch_ppocr_mobile_v2.0_rec_infer"),
}


def _search_model_dir(model_subdir: str, custom_dir: str) -> Path | None:
    """
    在以下位置搜索 model_subdir：
    1. 用户自定义路径 / model_subdir
    2. 打包内置（frozen: _internal/models/paddleocr, dev: modules/.../models/paddleocr）
    3. 用户 ~/.paddleocr/whl（仅 dev 模式）
    返回完整的模型目录路径，或 None。
    """
    _frozen = getattr(sys, "frozen", False)
    exe_dir = Path(sys.executable).resolve().parent

    search_bases: list[Path] = []
    if custom_dir:
        search_bases.append(Path(custom_dir))
    if _frozen:
        search_bases.extend([
            exe_dir / '_internal' / 'models' / 'paddleocr',
            exe_dir / 'models' / 'paddleocr',
        ])
    else:
        search_bases.append(Path(__file__).resolve().parent.parent / 'models' / 'paddleocr')
        # dev 模式也查用户下载缓存
        search_bases.append(Path(os.path.expanduser("~/.paddleocr/whl")))

    for base in search_bases:
        # 标准嵌套结构：whl/{det,rec}/ch/<model_subdir>
        for component in ("det", "rec"):
            model_dir = base / "whl" / component / "ch" / model_subdir
            if model_dir.exists():
                return model_dir
        # 自定义根目录直接含 <model_subdir>
        direct = base / model_subdir
        if direct.exists() and any(direct.rglob("inference.pdmodel")):
            return direct
    return None


def _resolve_paddleocr_model_dirs(tier: str, custom_dir: str) -> tuple:
    """
    返回 (det_model_dir: str, rec_model_dir: str)
    根据 tier 查找对应精度模型，返回空字符串表示未找到（引擎初始化时会报清晰错误）。
    """
    det_name, rec_name = _TIER_MODEL_NAMES.get(tier, ("ch_PP-OCRv4_det_infer", "ch_PP-OCRv4_rec_infer"))
    det_dir = _search_model_dir(det_name, custom_dir)
    rec_dir = _search_model_dir(rec_name, custom_dir)
    return (str(det_dir) if det_dir else "", str(rec_dir) if rec_dir else "")


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

        # 读取用户设置
        custom_dir, tier = _get_user_ocr_settings()
        tier_label = "高精度(Server)" if tier == "server" else "轻量(Mobile)"

        # 解析 det / rec 模型目录（按精度档位）
        det_dir, rec_dir = _resolve_paddleocr_model_dirs(tier, custom_dir)

        if not det_dir or not rec_dir:
            logger.error(
                f'未找到 {tier_label} OCR 模型'
                f'（精度: {tier}，自定义: "{custom_dir or "未设置"}"）'
            )
            raise ToolboxError(
                ErrorCode.MODEL_MISSING,
                f'OCR {tier_label}模型文件缺失，无法离线识别。\n'
                f'当前精度档位：{tier_label}\n\n'
                '请在「设置 → OCR 模型」中指定包含完整模型的目录，\n'
                '或联系软件提供者重新获取完整安装包。',
            ) from None

        logger.info(f'使用 OCR {tier_label} 模型 (det={det_dir})')
        logger.info(f'初始化 PaddleOCR 引擎 (tier={tier}, lang={lang}) ...')
        self._ocr = PaddleOCR(
            lang=lang,
            show_log=False,
            det_model_dir=det_dir,
            rec_model_dir=rec_dir,
        )
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
