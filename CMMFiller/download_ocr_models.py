"""
预下载 PaddleOCR 中文模型到 models/paddleocr/
打包时会一并打入 dist，用户无需联网下载。

运行: python download_ocr_models.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_BASE = PROJECT_DIR / 'models' / 'paddleocr'


def _dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    return total / 1024 / 1024


def _has_models(base: Path) -> bool:
    return base.exists() and any(base.rglob('inference.pdmodel'))


def download_models(force: bool = False) -> Path:
    os.environ['PADDLE_OCR_BASE_DIR'] = str(MODEL_BASE)
    os.environ.setdefault('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', 'python')

    if not force and _has_models(MODEL_BASE):
        print(f'模型已存在: {MODEL_BASE} ({_dir_size_mb(MODEL_BASE):.1f} MB)')
        return MODEL_BASE

    print(f'下载 OCR 模型到: {MODEL_BASE}')
    print('（det + rec + cls，约 30 MB，需联网）')
    MODEL_BASE.mkdir(parents=True, exist_ok=True)

    from paddleocr import PaddleOCR

    PaddleOCR(lang='ch', show_log=True, use_angle_cls=True)
    print(f'下载完成: {_dir_size_mb(MODEL_BASE):.1f} MB')
    return MODEL_BASE


if __name__ == '__main__':
    force = '--force' in sys.argv
    try:
        download_models(force=force)
    except Exception as e:
        print(f'下载失败: {e}', file=sys.stderr)
        sys.exit(1)
