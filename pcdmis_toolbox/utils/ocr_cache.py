"""
CMMFiller OCR 缓存维护（PNG 渲染缓存 + ocr_cache.json）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from utils.paths import paths
from utils.settings import save_settings_json_atomic

logger = logging.getLogger(__name__)

OCR_CACHE_JSON = "ocr_cache.json"
OCR_CACHE_MAX_ENTRIES = 10_000


def clear_ocr_cache(cache_dir: Path | None = None) -> dict:
    """
    手动清理 OCR 缓存：删除 cache 目录下全部 *.png 与 ocr_cache.json。

    返回 {png_files, json_removed, json_entries_cleared}。
    """
    cache_dir = cache_dir or paths.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    png_removed = 0
    for png in cache_dir.glob("*.png"):
        try:
            png.unlink(missing_ok=True)
            png_removed += 1
        except OSError as exc:
            logger.warning("删除 OCR 缓存图片失败 %s: %s", png, exc)

    json_path = cache_dir / OCR_CACHE_JSON
    json_removed = False
    entries = 0
    if json_path.is_file():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                entries = len(data)
        except (OSError, json.JSONDecodeError):
            entries = 0
        try:
            json_path.unlink(missing_ok=True)
            json_removed = True
        except OSError as exc:
            logger.warning("删除 ocr_cache.json 失败: %s", exc)

    logger.info(
        "OCR 缓存已清理: png=%s json_removed=%s entries=%s dir=%s",
        png_removed, json_removed, entries, cache_dir,
    )
    return {
        "png_files": png_removed,
        "json_removed": json_removed,
        "json_entries_cleared": entries,
    }


def trim_ocr_cache_json(
    cache_dir: Path | None = None,
    *,
    max_entries: int = OCR_CACHE_MAX_ENTRIES,
) -> int:
    """按 key 字母序保留最新 max_entries 条（与 filler._cleanup_cache 一致）。"""
    cache_dir = cache_dir or paths.cache_dir
    json_path = cache_dir / OCR_CACHE_JSON
    if not json_path.is_file():
        return 0
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        if not isinstance(cache_data, dict) or len(cache_data) <= max_entries:
            return 0
        sorted_keys = sorted(cache_data.keys())
        remove_count = len(sorted_keys) - max_entries
        for key in sorted_keys[:remove_count]:
            del cache_data[key]
        save_settings_json_atomic(json_path, cache_data)
        return remove_count
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("裁剪 ocr_cache.json 失败: %s", exc)
        return 0
