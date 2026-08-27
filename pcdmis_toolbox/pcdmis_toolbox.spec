# -*- mode: python ; coding: utf-8 -*-
"""
cm2xl — Unified PyInstaller spec
===============================================
Bundles: main.py + Shell + 两个功能模块 (cmm_filler, pc_to_excel)
后处理: build/fix_dist.py (必须在 PyInstaller 完成后执行)
"""
import os
import sys
from pathlib import Path

import Cython
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ── 基础路径 ────────────────────────────────────────────────────────────────
ROOT = Path(SPECPATH).resolve()           # pcdmis_toolbox/
MODULES_DIR = ROOT / "modules"

# ── Cython Utility 目录（hook 需要）──────────────────────────────────────────
_cython_util = str(Path(Cython.__file__).parent / "Utility")

# ══════════════════════════════════════════════════════════════════════════════
# PaddleOCR 相关：与 CMMFiller.spec 完全一致的处理逻辑
# ══════════════════════════════════════════════════════════════════════════════

# 收集 paddle 生态必需的依赖（含 .pyd / .dll）
_collected = [collect_all(pkg) for pkg in (
    "paddle", "pyclipper", "shapely", "PIL", "cv2",
    "lmdb", "rapidfuzz", "lxml", "yaml",
)]
_extra_datas, _extra_bins, _extra_hidden = [], [], []
for datas, bins, hidden in _collected:
    _extra_datas += datas
    _extra_bins += bins
    _extra_hidden += hidden

# 剔除 OpenCV 视频编解码（约 58 MB，OCR 永远用不到）
_extra_bins = [(src, dst) for src, dst in _extra_bins if "ffmpeg" not in src.lower()]

# ══════════════════════════════════════════════════════════════════════════════
# PaddleOCR 模型（已在 CMMFiller/models/paddleocr/，由 download_ocr_models.py 预下载）
# ══════════════════════════════════════════════════════════════════════════════
_cmm_models_src = ROOT.parent / "CMMFiller" / "models" / "paddleocr"
_has_models = _cmm_models_src.exists() and any(_cmm_models_src.rglob("inference.pdmodel"))

# ══════════════════════════════════════════════════════════════════════════════
# BAS 脚本模板（dev 源路径 → 打包后目标路径）
# ══════════════════════════════════════════════════════════════════════════════
_scripts_src = ROOT / "scripts"
_bas_template_src = _scripts_src / "export_current.bas.template"

# ══════════════════════════════════════════════════════════════════════════════
# customtkinter assets
# ══════════════════════════════════════════════════════════════════════════════
import customtkinter
_ctk_dir = Path(customtkinter.__file__).resolve().parent

# ══════════════════════════════════════════════════════════════════════════════
# 所有模块及其子包的隐藏导入（PyInstaller 静态分析不可见）
# ══════════════════════════════════════════════════════════════════════════════
_all_hidden = list(set(_extra_hidden + [
    # ── 主入口 ───────────────────────────────────────────────────────────────
    "main",
    # ── Toolbox 骨架 ─────────────────────────────────────────────────────────
    "toolbox.app_meta",
    "toolbox.protocol",
    "toolbox.shell",
    "toolbox.settings_dialog",
    "toolbox.about_dialog",
    "utils.theme",
    "utils.paths",
    "utils.logging",
    "utils.audit",
    "utils.error_codes",
    "utils.settings",
    "utils.threading_utils",
    "utils.file_io",
    # ── 动态加载的模块（modules/__init__.py 用 pkgutil 运行时发现）────────────
    "modules",
    "modules.cmm_filler",
    "modules.cmm_filler.gui",
    "modules.cmm_filler.core",
    "modules.cmm_filler.core.filler",
    "modules.cmm_filler.ocr",
    "modules.cmm_filler.ocr.engine",
    "modules.cmm_filler.template_wizard",
    "modules.pc_to_excel",
    "modules.pc_to_excel.module",
    "modules.pc_to_excel.gui",
    "modules.pc_to_excel.gui.main_window",
    "modules.pc_to_excel.connector",
    "modules.pc_to_excel.connector.base",
    "modules.pc_to_excel.connector.com_detector",
    "modules.pc_to_excel.connector.pcdmis_connector",
    "modules.pc_to_excel.core",
    "modules.pc_to_excel.core.data_extractor",
    "modules.pc_to_excel.core.models",
    "modules.pc_to_excel.core.report_filter",
    "modules.pc_to_excel.core.tolerance",
    "modules.pc_to_excel.export",
    "modules.pc_to_excel.export.inspection_form_fill",
    "modules.pc_to_excel.export.pcdmis_style_report",
    "modules.pc_to_excel.export.template_report",
    "modules.pc_to_excel.inject",
    "modules.pc_to_excel.inject.command_injector",
    "modules.pc_to_excel.inject.save_helper",
    "modules.pc_to_excel.utils",
    "modules.pc_to_excel.utils.action_hints",
    "modules.pc_to_excel.utils.admin",
    "modules.pc_to_excel.utils.local_settings",
    # ── PaddleOCR 主链（fix_dist.py 修复后从文件系统加载，但仍需声明）────────────
    "paddle",
    "paddle.base",
    "paddle.base.core",
    "paddle.inference",
    "paddleocr",
    "paddleocr.tools",
    "ppocr.postprocess",
    "ppocr.postprocess.db_postprocess",
    "ppocr.postprocess.rec_postprocess",
    "ppocr.postprocess.cls_postprocess",
    "ppocr.utils.logging",
    "ppocr.utils.utility",
    # ── PaddleOCR tools.infer（paddleocr 内部引用）───────────────────────────────
    "tools.infer",
    "tools.infer.predict_system",
    "tools.infer.predict_det",
    "tools.infer.predict_rec",
    "tools.infer.predict_cls",
    "tools.infer.utility",
    # ── 通用第三方库 ───────────────────────────────────────────────────────────
    "customtkinter",
    "tkinterdnd2",
    "openpyxl",
    "pymupdf",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageStat",
    "shapely",
    "shapely.geometry",
    "shapely.geos",
    "pyclipper",
    "scipy",
    "scipy.special",
    "scipy.ndimage",
    "scipy.io",
    "lmdb",
    "rapidfuzz",
    "lxml",
    "yaml",
    "requests",
    "tqdm",
    "cv2",
    "imghdr",
    "encodings.idna",
    # ── pc_to_excel COM ───────────────────────────────────────────────────────
    "win32com",
    "win32com.client",
    "pythoncom",
    "pywintypes",
    # ── 旧入口重定向（Phase 7）──────────────────────────────────────────────────
    "cmm_filler_gui",
    "pc_to_excel_main",
]))

# ══════════════════════════════════════════════════════════════════════════════
# datas / binaries 列表
# ══════════════════════════════════════════════════════════════════════════════
datas = [
    # customtkinter 主题资源
    (str(_ctk_dir / "assets"), "customtkinter/assets"),
    # 自定义主题 JSON（避免冷启动重新生成时丢失 weight 等字段）
    (str(ROOT / "utils" / "theme.json"), "utils"),
    # BAS 脚本模板（pc_to_excel 运行时部署到 LocalAppData）
    (str(_bas_template_src), "scripts"),
]

# CMMFiller 模板（bundled，放在模块目录内，core/filler.py 用 __file__ 相对定位）
_templates_src = MODULES_DIR / "cmm_filler" / "templates"
if _templates_src.is_dir():
    datas.append((str(_templates_src), "modules/cmm_filler/templates"))

# ══════════════════════════════════════════════════════════════════════════════
# pcdmis_toolbox 的 Python 包文件
# PyInstaller 默认只把外部依赖（paddleocr/cv2 等）的 __init__.py 抽到磁盘，
# 本地项目的 __init__.py 都留在 PYZ 归档里。但 modules/__init__.py 用
# pkgutil.iter_modules 扫描文件系统，发现机制依赖子目录有 __init__.py 才能识别
# 为 package。修法：把 pcdmis_toolbox 所有本地包的 __init__.py 显式加入 datas。
# ══════════════════════════════════════════════════════════════════════════════
_local_pkgs = [
    "modules/__init__.py",
    "modules/cmm_filler/__init__.py",
    "modules/cmm_filler/core/__init__.py",
    "modules/cmm_filler/ocr/__init__.py",
    "modules/pc_to_excel/__init__.py",
    "modules/pc_to_excel/connector/__init__.py",
    "modules/pc_to_excel/core/__init__.py",
    "modules/pc_to_excel/export/__init__.py",
    "modules/pc_to_excel/inject/__init__.py",
    "modules/pc_to_excel/utils/__init__.py",
]
for rel in _local_pkgs:
    src = ROOT / rel
    if src.is_file():
        # 目标路径去掉 '__init__.py' 保持目录结构
        target_dir = str(Path(rel).parent).replace("\\", "/")
        datas.append((str(src), target_dir))

# PaddleOCR 模型（如已预下载则打入包）
if _has_models:
    datas.append((str(_cmm_models_src), "models/paddleocr"))

binaries = _extra_bins
hookspath = [str(ROOT / "build" / "hooks")]

block_cipher = None

# ══════════════════════════════════════════════════════════════════════════════
# Analysis
# ══════════════════════════════════════════════════════════════════════════════
a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=_all_hidden,
    hookspath=hookspath,
    hooksconfig={},
    runtime_hooks=[str(ROOT / "build" / "hooks" / "hook-paddleocr_pre.py")],
    excludes=[
        # 瘦身：主推理链完全不用的包
        "llvmlite", "numba",
        "matplotlib", "pandas",
        "skimage",
        "networkx", "imageio", "lazy_loader",
        "fontTools",
        "cryptography",
        "docx",
        "IPython", "pytest", "tornado",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ══════════════════════════════════════════════════════════════════════════════
# PYZ
# ══════════════════════════════════════════════════════════════════════════════
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ══════════════════════════════════════════════════════════════════════════════
# EXE
# ══════════════════════════════════════════════════════════════════════════════
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="cm2xl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI 程序，无需控制台窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ══════════════════════════════════════════════════════════════════════════════
# COLLECT（最终输出 dist/cm2xl/）
# ══════════════════════════════════════════════════════════════════════════════
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="cm2xl",
)
