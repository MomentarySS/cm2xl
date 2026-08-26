"""
PCDMIS Toolbox 2.0 — 文件 I/O 工具
PDF 上下文管理器 + 大小写不敏感 glob + 原子文本写。
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def glob_pdfs(folder: Path) -> list[Path]:
    """
    扫描文件夹返回所有 PDF（含大小写不敏感）。
    修复 cmm_filler_v10.py 的 glob('*.PDF') 只匹配大写问题。
    """
    if not folder.is_dir():
        return []
    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() == ".pdf"
    )


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """
    原子写文本文件（临时文件 + os.replace），防止异常中断留下半截文件。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


@contextmanager
def fitz_open_context(pdf_path: Path):
    """
    PDF 上下文管理器，自动 close。
    修复 cmm_filler_v10.py 的 fitz.open() 无 with / 无 close 句柄泄漏。

    用法：
        with fitz_open_context(pdf_path) as doc:
            text = "".join(page.get_text() for page in doc)
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        yield doc
    finally:
        doc.close()
