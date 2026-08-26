# -*- mode: python ; coding: utf-8 -*-
import Cython
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

_cython_util = str(Path(Cython.__file__).parent / 'Utility')

# 收集 OCR 推理必需的依赖（含 .pyd / .dll）。
# 瘦身：去掉 skimage/scipy/fontTools/imageio/networkx/docx 的全量收集——
#   - scipy 只需 ndimage/special/io 三个子包（paddleocr 实际引用），交给依赖分析按需收集
#   - skimage 仅训练/E2E 路径引用，主推理链已 patch 成 optional，进 excludes
#   - fontTools/imageio/networkx 是 matplotlib/skimage 的连带，主链不用
#   - docx 仅文档生成脚本使用
_collected = [collect_all(pkg) for pkg in (
    'paddle', 'pyclipper', 'shapely', 'PIL', 'cv2',
    'lmdb', 'rapidfuzz', 'lxml', 'yaml',
)]
_extra_datas = []
_extra_bins = []
_extra_hidden = []
for datas, bins, hidden in _collected:
    _extra_datas += datas
    _extra_bins += bins
    _extra_hidden += hidden

# OpenCV 的视频编解码 DLL（videoio_ffmpeg，约 58 MB）OCR 永远用不到，剔除
_extra_bins = [(src, dst) for src, dst in _extra_bins if 'ffmpeg' not in src.lower()]

block_cipher = None

a = Analysis(
    ['cmm_filler_v10.py'],
    pathex=[],
    binaries=_extra_bins,
    datas=[
        ('templates/模板1.xlsx', 'templates/'),
        ('templates/模板2.xlsx', 'templates/'),
        ('models/paddleocr', 'models/paddleocr'),
        (_cython_util, 'Cython/Utility'),
    ] + _extra_datas,
    hiddenimports=list(set(_extra_hidden + [
        'paddle',
        'paddle.base',
        'paddle.base.core',
        'paddle.inference',
        'paddleocr',
        'paddleocr.tools',
        'customtkinter',
        'cmm_filler_gui',
        'template_wizard',
        'ocr_engine',
        'version',
        'tkinterdnd2',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'PIL.ImageStat',
        'shapely',
        'shapely.geometry',
        'shapely.geos',
        'pyclipper',
        # scipy 按需：paddleocr 实际引用的三个子包
        'scipy',
        'scipy.special',
        'scipy.ndimage',
        'scipy.io',
        'lmdb',
        'rapidfuzz',
        'lxml',
        'yaml',
        # paddleocr 的 network.py 顶层 import 这两个（主链必需）。
        # paddleocr 本体由 fix_dist.py 打包后从文件系统复制，PyInstaller
        # 静态分析看不到它的依赖，必须在此显式声明（requests 原本靠
        # imageio 间接带入，瘦身后丢失导致"导出标准模板"报错）
        'requests',
        'tqdm',
        'cv2',
        'imghdr',
        'encodings.idna',
        'tools.infer',
        'tools.infer.predict_system',
        'tools.infer.predict_det',
        'tools.infer.predict_rec',
        'tools.infer.predict_cls',
        'tools.infer.utility',
        'ppocr.postprocess',
        'ppocr.postprocess.db_postprocess',
        'ppocr.postprocess.rec_postprocess',
        'ppocr.postprocess.cls_postprocess',
        'ppocr.utils.logging',
        'ppocr.utils.utility',
    ])),
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/hook-paddleocr_pre.py'],
    # 死重排除：运行时推理链完全不用（paddlex 的连带 + JIT + 绘图 + 已 patch 成 optional 的）
    excludes=[
        'llvmlite', 'numba',
        'matplotlib', 'pandas',
        'skimage',
        'networkx', 'imageio', 'lazy_loader',
        'fontTools',
        'cryptography',
        'docx',
        'IPython', 'pytest', 'tornado',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CMMFiller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CMMFiller',
)
