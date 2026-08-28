"""
Post-build fix script for CMMFiller.
Ensures paddleocr package layout works in frozen builds.
"""
import os
import shutil
import sys
from pathlib import Path


def _copy_paddleocr_package(internal: Path):
    """Copy full paddleocr source tree when PyInstaller layout is incomplete."""
    import paddleocr

    src = Path(paddleocr.__file__).resolve().parent
    dst = internal / 'paddleocr'
    tools_ok = (dst / 'tools' / '__init__.py').exists()

    if not tools_ok:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'),
        )
        print(f'  Copied full paddleocr package -> {dst}')

    # Legacy flat copies for older import paths
    for f in dst.glob('*.py'):
        target = internal / f.name
        if not target.exists():
            shutil.copy2(f, target)
            print(f'  Copied: paddleocr/{f.name} -> {f.name}')

    tools_src = dst / 'tools'
    # 不再复制到 _internal/tools，避免与其他 tools 模块冲突
    if tools_src.is_dir():
        print(f'  paddleocr/tools ready ({len(list(tools_src.rglob("*.py")))} py files)')

    utils_src = dst / 'ppocr' / 'utils'
    utils_dst = internal / 'ppocr' / 'utils'
    if utils_src.is_dir():
        utils_dst.parent.mkdir(parents=True, exist_ok=True)
        for f in utils_src.iterdir():
            if f.suffix in ('.txt', '.json') and f.is_file():
                target = utils_dst / f.name
                if not target.exists():
                    utils_dst.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    print(f'  Copied: ppocr/utils/{f.name}')


    if dst.is_dir():
        _patch_paddleocr_source(dst / 'paddleocr.py')
        _patch_postprocess_init(dst / 'ppocr' / 'postprocess' / '__init__.py')
        _patch_imaug_init(dst / 'ppocr' / 'data' / 'imaug' / '__init__.py')
        _patch_data_init(dst / 'ppocr' / 'data' / '__init__.py')


def _patch_imaug_init(imaug_init: Path):
    """Inference only needs operators; skip training aug modules missing deps."""
    if not imaug_init.is_file():
        return
    text = imaug_init.read_text(encoding='utf-8')
    if 'FROZEN_OPTIONAL_IMAUG' in text:
        return

    marker = 'from .iaa_augment import IaaAugment'
    end_marker = 'from .unimernet_aug import *\n\n\n'
    start = text.find(marker)
    end = text.find('def transform(data, ops=None):')
    if start < 0 or end < 0:
        return

    optional = text[start:end].rstrip()
    # operators must load before create_operators eval()
    replacement = (
        'from .operators import *\n\n'
        'try:\n'
        + '\n'.join('    ' + line for line in optional.splitlines())
        + '\nexcept ImportError:\n'
        '    pass  # FROZEN_OPTIONAL_IMAUG\n\n\n'
    )
    text = text[:start] + replacement + text[end:]
    imaug_init.write_text(text, encoding='utf-8')
    print('  Patched ppocr/data/imaug/__init__.py optional imports')


def _patch_data_init(data_init: Path):
    """Skip training dataset imports not needed for infer."""
    if not data_init.is_file():
        return
    text = data_init.read_text(encoding='utf-8')
    if 'FROZEN_OPTIONAL_DATA' in text:
        return

    text = text.replace('import skimage\n', 'try:\n    import skimage\nexcept ImportError:\n    skimage = None  # FROZEN_OPTIONAL_DATA\n')

    dataset_block = (
        'from ppocr.data.simple_dataset import SimpleDataSet, MultiScaleDataSet\n'
        'from ppocr.data.lmdb_dataset import LMDBDataSet, LMDBDataSetSR, LMDBDataSetTableMaster\n'
        'from ppocr.data.pgnet_dataset import PGDataSet\n'
        'from ppocr.data.pubtab_dataset import PubTabDataSet\n'
        'from ppocr.data.multi_scale_sampler import MultiScaleSampler\n'
        'from ppocr.data.latexocr_dataset import LaTeXOCRDataSet'
    )
    wrapped = (
        'try:\n    '
        + dataset_block.replace('\n', '\n    ')
        + '\nexcept ImportError:\n    pass  # FROZEN_OPTIONAL_DATA\n'
    )
    if dataset_block in text:
        text = text.replace(dataset_block, wrapped, 1)

    data_init.write_text(text, encoding='utf-8')
    print('  Patched ppocr/data/__init__.py optional imports')


def _patch_postprocess_init(postprocess_init: Path):
    """Optional postprocessors need skimage/scipy; skip when deps missing in frozen build."""
    if not postprocess_init.is_file():
        return
    text = postprocess_init.read_text(encoding='utf-8')
    if 'FROZEN_OPTIONAL_POSTPROCESS' in text:
        return

    optional_blocks = [
        'from .pg_postprocess import PGPostProcess',
        'from .vqa_token_ser_layoutlm_postprocess import (\n    VQASerTokenLayoutLMPostProcess,\n    DistillationSerPostProcess,\n)',
        'from .vqa_token_re_layoutlm_postprocess import (\n    VQAReTokenLayoutLMPostProcess,\n    DistillationRePostProcess,\n)',
        'from .table_postprocess import TableMasterLabelDecode, TableLabelDecode',
        'from .picodet_postprocess import PicoDetPostProcess',
        'from .ct_postprocess import CTPostProcess',
        'from .drrg_postprocess import DRRGPostprocess',
        'from .rec_postprocess import CANLabelDecode',
    ]
    for block in optional_blocks:
        wrapped = (
            'try:\n    '
            + block.replace('\n', '\n    ')
            + '\nexcept ImportError:\n    pass  # FROZEN_OPTIONAL_POSTPROCESS\n'
        )
        if block in text:
            text = text.replace(block, wrapped, 1)

    postprocess_init.write_text(text, encoding='utf-8')
    print('  Patched ppocr/postprocess/__init__.py optional imports')


def _patch_paddleocr_source(paddleocr_py: Path):
    """Ensure tools package has __path__ and optional ppstructure imports in frozen builds."""
    if not paddleocr_py.is_file():
        return
    text = paddleocr_py.read_text(encoding='utf-8')
    changed = False

    tools_block = (
        'tools = _import_file(\n'
        '    "tools", os.path.join(__dir__, "tools/__init__.py"), make_importable=True\n'
        ')'
    )
    tools_fix = tools_block + '\ntools.__path__ = [os.path.join(__dir__, "tools")]  # FROZEN_TOOLS_PATH_FIX'
    if 'FROZEN_TOOLS_PATH_FIX' not in text and tools_block in text:
        text = text.replace(tools_block, tools_fix, 1)
        changed = True

    ppstructure_block = (
        'ppstructure = importlib.import_module("ppstructure", "paddleocr")\n'
        'from ppocr.utils.logging import get_logger\n'
        '\n'
        'from ppocr.utils.utility import (\n'
        '    check_and_read,\n'
        '    get_image_file_list,\n'
        '    alpha_to_color,\n'
        '    binarize_img,\n'
        ')\n'
        'from ppocr.utils.network import (\n'
        '    maybe_download,\n'
        '    download_with_progressbar,\n'
        '    is_link,\n'
        '    confirm_model_dir_url,\n'
        ')\n'
        'from tools.infer import predict_system\n'
        'from tools.infer.utility import draw_ocr, str2bool, check_gpu\n'
        'from ppstructure.utility import init_args, draw_structure_result\n'
        'from ppstructure.predict_system import StructureSystem, save_structure_res, to_excel\n'
        'from ppstructure.recovery.recovery_to_doc import sorted_layout_boxes, convert_info_docx\n'
        'from ppstructure.recovery.recovery_to_markdown import convert_info_markdown'
    )
    ppstructure_fix = (
        'try:\n'
        '    ppstructure = importlib.import_module("ppstructure", "paddleocr")\n'
        'except ImportError:\n'
        '    ppstructure = None  # FROZEN_OPTIONAL_PPSTRUCTURE\n'
        'from ppocr.utils.logging import get_logger\n'
        '\n'
        'from ppocr.utils.utility import (\n'
        '    check_and_read,\n'
        '    get_image_file_list,\n'
        '    alpha_to_color,\n'
        '    binarize_img,\n'
        ')\n'
        'from ppocr.utils.network import (\n'
        '    maybe_download,\n'
        '    download_with_progressbar,\n'
        '    is_link,\n'
        '    confirm_model_dir_url,\n'
        ')\n'
        'from tools.infer import predict_system\n'
        'from tools.infer.utility import draw_ocr, str2bool, check_gpu\n'
        'try:\n'
        '    from ppstructure.utility import init_args, draw_structure_result\n'
        'except ImportError:\n'
        '    init_args = draw_structure_result = None  # FROZEN_SPLIT_INITARGS\n'
        'try:\n'
        '    from ppstructure.predict_system import StructureSystem, save_structure_res, to_excel\n'
        '    from ppstructure.recovery.recovery_to_doc import sorted_layout_boxes, convert_info_docx\n'
        '    from ppstructure.recovery.recovery_to_markdown import convert_info_markdown\n'
        'except ImportError:\n'
        '    StructureSystem = save_structure_res = to_excel = None\n'
        '    sorted_layout_boxes = convert_info_docx = convert_info_markdown = None  # FROZEN_OPTIONAL_PPSTRUCTURE'
    )
    if 'FROZEN_OPTIONAL_PPSTRUCTURE' not in text and ppstructure_block in text:
        text = text.replace(ppstructure_block, ppstructure_fix, 1)
        changed = True

    if 'class PPStructure(StructureSystem):' in text:
        text = text.replace(
            'class PPStructure(StructureSystem):',
            'class PPStructure(StructureSystem if StructureSystem is not None else object):  # FROZEN_PPSTRUCTURE_STUB',
            1,
        )
        changed = True

    if changed:
        paddleocr_py.write_text(text, encoding='utf-8')
        print('  Patched paddleocr.py frozen imports')


def _verify_cython_utility(internal: Path) -> bool:
    """OCR 依赖链（pyclipper/scipy）运行时需要 Cython/Utility/CppSupport.cpp。"""
    cpp = internal / 'Cython' / 'Utility' / 'CppSupport.cpp'
    if cpp.is_file():
        print(f'  Cython Utility OK: {cpp.name}')
        return True
    print(f'  ERROR: missing {cpp} — add (_cython_util, "Cython/Utility") to spec datas')
    return False


def fix_dist(dist_path):
    internal = Path(dist_path) / '_internal'
    if not internal.is_dir():
        print(f'Error: {internal} not found')
        return False

    _copy_paddleocr_package(internal)
    ok = _verify_cython_utility(internal)

    print('\nFix complete!' if ok else '\nFix incomplete — see errors above')
    return ok


if __name__ == '__main__':
    if len(sys.argv) < 2:
        dist_path = Path.cwd() / 'dist' / 'CMMFiller'
    else:
        dist_path = Path(sys.argv[1])

    if not fix_dist(dist_path):
        sys.exit(1)
