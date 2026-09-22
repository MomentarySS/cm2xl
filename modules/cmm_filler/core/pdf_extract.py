"""
PDF 文本/图像提取
=================
- 类型检测（文字型 vs 扫描件）
- 多页文本层快速提取
- 多页渲染为 PNG（供 OCR）
- ROI 区域裁剪（跳过页眉页脚）
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TypedDict

from .report_profile import roi_cache_suffix
from utils.file_io import fitz_open_context

# 平均每页可提取字符数超过此阈值 → 判定为文字型 PDF
TEXT_CHARS_THRESHOLD = 50


class ROIRect(TypedDict, total=False):
    top: float
    left: float
    bottom: float
    right: float


def _normalize_roi(roi: ROIRect | dict | None) -> ROIRect:
    """ROI 比例值 0.0–1.0，表示从各边裁去的比例。"""
    if not roi:
        return {'top': 0, 'left': 0, 'bottom': 0, 'right': 0}
    return {
        'top': max(0.0, min(1.0, float(roi.get('top', 0)))),
        'left': max(0.0, min(1.0, float(roi.get('left', 0)))),
        'bottom': max(0.0, min(1.0, float(roi.get('bottom', 0)))),
        'right': max(0.0, min(1.0, float(roi.get('right', 0)))),
    }


def _page_clip_rect(page, roi: ROIRect):
    """根据 ROI 计算页面裁剪矩形。"""
    import fitz

    rect = page.rect
    w, h = rect.width, rect.height
    x0 = w * roi['left']
    y0 = h * roi['top']
    x1 = w * (1 - roi['right'])
    y1 = h * (1 - roi['bottom'])
    if x1 <= x0 or y1 <= y0:
        return rect
    return fitz.Rect(x0, y0, x1, y1)


def detect_pdf_type(pdf_path: str | Path, sample_pages: int = 3) -> str:
    """
    检测 PDF 类型。

    Returns:
        'text'   — 有可用文本层，可直接 get_text()
        'scanned' — 扫描件/图片型，需 OCR
    """
    with fitz_open_context(Path(pdf_path)) as doc:
        pages_checked = min(sample_pages, len(doc))
        total_chars = 0
        for i in range(pages_checked):
            total_chars += len(doc[i].get_text('text').strip())
        avg_chars = total_chars / max(pages_checked, 1)
    return 'text' if avg_chars > TEXT_CHARS_THRESHOLD else 'scanned'


def extract_text_lines(pdf_path: str | Path, roi: ROIRect | dict | None = None) -> list[str]:
    """从所有页提取文本行（文字型 PDF 快速通道）。ROI 对文本层暂不裁剪。"""
    lines: list[str] = []
    with fitz_open_context(Path(pdf_path)) as doc:
        for page in doc:
            text = page.get_text('text')
            for line in text.splitlines():
                s = line.strip()
                if s:
                    lines.append(s)
    return lines


def _path_cache_suffix(pdf_path: Path) -> str:
    """解析后完整路径的短哈希。

    缓存图片名必须能区分「同名但不同目录」的 PDF —— 否则第二个 PDF 会命中第一个的
    OCR 结果（filler._cache_key() 按图片**路径**做 MD5，图片名相同即同一条缓存）。
    """
    resolved = str(pdf_path.resolve()).encode('utf-8')
    return hashlib.md5(resolved).hexdigest()[:8]


def pdf_to_images(
    pdf_path: str | Path,
    cache_dir: str | Path,
    dpi: int = 300,
    roi: ROIRect | dict | None = None,
) -> list[str]:
    """
    将 PDF 所有页渲染为 PNG 图片。

    单页 PDF：{stem}_{路径哈希}.png
    多页 PDF：{stem}_{路径哈希}_p1.png, {stem}_{路径哈希}_p2.png, ...
    带 ROI ：再追加 `_roi_{top_left_bottom_right}`。

    **文件名必须由全部渲染输入决定**（源路径 + 页号 + ROI）：缓存 key 是图片路径的
    MD5（见 filler._cache_key），输入不同而文件名相同就会读到别人的 OCR 结果。

    dpi 目前**不进**文件名：它由构造参数固定为 300，GUI / CLI 都没有暴露入口，
    因此不构成实际冲突。若将来开放 dpi 设置，此处需一并补上。

    roi: 裁剪区域，值为 0.0–1.0 表示从各边裁去的比例。
         例如 top=0.2 表示裁掉顶部 20%（常用于跳过页眉）。
    """
    pdf_path = Path(pdf_path)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem
    path_suffix = _path_cache_suffix(pdf_path)
    paths: list[str] = []
    roi = _normalize_roi(roi)

    # ROI 非零时文件名带**实际比例**。旧实现只加一个布尔后缀 `_roi`：图片每次都会
    # 重新渲染，但 OCR 结果按文件名命中缓存 —— 于是把 ROI 从 0.2 改成 0.3 之后，
    # 拿到的仍是旧 ROI 的识别结果。roi_cache_suffix() 本来就是为此写的（此前无人调用）。
    roi_suffix = ''
    if any(roi[k] > 0 for k in ('top', 'left', 'bottom', 'right')):
        roi_suffix = f'_roi_{roi_cache_suffix(roi)}'

    with fitz_open_context(pdf_path) as doc:
        multi_page = len(doc) > 1
        for i, page in enumerate(doc):
            clip = _page_clip_rect(page, roi)
            pix = page.get_pixmap(dpi=dpi, clip=clip)
            page_suffix = f'_p{i + 1}' if multi_page else ''
            img_path = cache_dir / f'{stem}_{path_suffix}{page_suffix}{roi_suffix}.png'
            pix.save(str(img_path))
            paths.append(str(img_path))
    return paths
