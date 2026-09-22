"""
CMM 报告解析 Profile 管理
=========================
从 report_profiles/*.json 加载可切换的报告版式配置。
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from utils.paths import paths

logger = logging.getLogger('CMMFiller')

# 内置默认值（Profile 文件缺失时回退）
_BUILTIN_DEFAULT = {
    'name': 'default',
    'label': '默认 (FAI/FAL/DIM)',
    'item_prefixes': ['FAI', 'FAL', 'FAIL', '尺寸', 'CC', 'DIM', 'CHECK'],
    'skip_lines': ['毫米', 'mm', '中', 'A/2', '1/1'],
    'ocr_roi': {'top': 0, 'left': 0, 'bottom': 0, 'right': 0},
    'confidence_threshold': 0.85,
}


def _profiles_dir() -> Path:
    """定位内置 report_profiles 目录（开发 / 打包环境）。"""
    base = Path(__file__).resolve().parent.parent / 'report_profiles'
    if base.is_dir():
        return base
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (
            exe_dir / '_internal' / 'modules' / 'cmm_filler' / 'report_profiles',
            exe_dir / 'modules' / 'cmm_filler' / 'report_profiles',
        ):
            if candidate.is_dir():
                return candidate
    return base


def user_profiles_dir() -> Path:
    """用户可写的自定义 Profile 目录（发布后可自行添加 JSON）。"""
    d = paths.config_dir / 'cmm_filler' / 'report_profiles'
    d.mkdir(parents=True, exist_ok=True)
    _ensure_user_profile_example(d)
    return d


def _ensure_user_profile_example(profile_dir: Path) -> None:
    """首次使用时写入示例 Profile，方便用户复制修改。"""
    if any(profile_dir.glob('*.json')):
        return
    example = profile_dir / '_example.my_factory.json'
    if example.exists():
        return
    payload = {
        'name': 'my_factory',
        'label': '示例：我司报告（复制后改名）',
        'item_prefixes': ['FAI', '检具', 'SIZE', 'DIM'],
        'skip_lines': ['毫米', 'mm', '中'],
        'ocr_roi': {'top': 0, 'left': 0, 'bottom': 0, 'right': 0},
        'confidence_threshold': 0.85,
    }
    try:
        with open(example, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.debug(f'[Profile] 写入示例失败: {e}')


def parse_prefix_text(text: str) -> list[str]:
    """解析用户输入的前缀列表（逗号/分号/空格分隔）。"""
    if not text or not str(text).strip():
        return []
    parts = re.split(r'[,，;；\s]+', str(text).strip())
    return [p for p in parts if p]


def merge_item_prefixes(*groups: list[str]) -> list[str]:
    """合并多组前缀，去重；较长前缀优先（避免短前缀误匹配）。"""
    seen: set[str] = set()
    merged: list[str] = []
    items: list[str] = []
    for group in groups:
        items.extend(group or [])
    for prefix in sorted(items, key=len, reverse=True):
        token = prefix.strip()
        if not token:
            continue
        key = token.upper() if token.isascii() else token
        if key in seen:
            continue
        seen.add(key)
        merged.append(token)
    return merged


def _resolve_profile_path(name: str | None) -> Path | None:
    """用户目录同名 Profile 覆盖内置。"""
    profile_name = name or 'default'
    user_path = user_profiles_dir() / f'{profile_name}.json'
    if user_path.is_file():
        return user_path
    builtin_path = _profiles_dir() / f'{profile_name}.json'
    if builtin_path.is_file():
        return builtin_path
    if profile_name == 'default':
        return builtin_path
    return None


def _iter_profile_files() -> list[Path]:
    by_name: dict[str, Path] = {}
    builtin = _profiles_dir()
    if builtin.is_dir():
        for path in sorted(builtin.glob('*.json')):
            by_name[path.stem] = path
    user = user_profiles_dir()
    for path in sorted(user.glob('*.json')):
        by_name[path.stem] = path
    return list(by_name.values())


def list_profiles() -> list[dict]:
    """返回所有可用 Profile 摘要 [{name, label, user}, ...]。"""
    profiles = []
    user_dir = user_profiles_dir()
    for path in _iter_profile_files():
        if path.name.startswith('_'):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            profiles.append({
                'name': data.get('name', path.stem),
                'label': data.get('label', path.stem),
                'user': user_dir in path.parents,
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f'[Profile] 跳过无效配置 {path.name}: {e}')
    if not profiles:
        profiles.append({'name': 'default', 'label': _BUILTIN_DEFAULT['label'], 'user': False})
    return profiles


def load_profile(name: str | None = None) -> dict:
    """加载指定 Profile，合并内置默认值。"""
    merged = dict(_BUILTIN_DEFAULT)
    path = _resolve_profile_path(name)

    if path and path.is_file():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            merged.update({k: v for k, v in data.items() if k != 'name' or v})
            merged['name'] = data.get('name', name or 'default')
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f'[Profile] 加载 {path.name} 失败，使用内置默认: {e}')
    elif name and name != 'default':
        logger.warning(f'[Profile] 未找到 "{name}"，回退 default')

    # 规范化 ROI
    roi = merged.get('ocr_roi') or {}
    merged['ocr_roi'] = {
        'top': float(roi.get('top', 0)),
        'left': float(roi.get('left', 0)),
        'bottom': float(roi.get('bottom', 0)),
        'right': float(roi.get('right', 0)),
    }
    return merged


def roi_cache_suffix(roi: dict) -> str:
    """ROI 配置的短哈希后缀，用于 OCR 缓存 key。"""
    t = roi.get('top', 0)
    l = roi.get('left', 0)
    b = roi.get('bottom', 0)
    r = roi.get('right', 0)
    return f'{t:.2f}_{l:.2f}_{b:.2f}_{r:.2f}'
