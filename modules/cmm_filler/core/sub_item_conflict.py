"""
模板序号与子编号冲突（如 PDF 有 FAI_1-1…FAI_1-N，模板仅序号 1 一行）
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .fixed_page_layout import resolve_measure_location
from .parse_measurements import measure_dict_key, measure_dict_label, _measurement_sort_key

SKIP_SUB_ITEM = '__skip__'
WORST_NG_SUB_ITEM = '__worst_ng__'


def _unique_candidates(candidates: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for m in candidates:
        seen[measure_dict_key(m)] = m
    return sorted(seen.values(), key=_measurement_sort_key)


def pick_worst_ng_candidate(candidates: list[dict]) -> dict:
    """在多个子项中选超差最严重的一项（优先 NG，再比超出量）。"""

    def _severity(m: dict) -> tuple:
        nominal = m['nominal']
        measured = m['measured']
        upper = m['upper_tol']
        lower = m['lower_tol']
        dev = measured - nominal
        if not m.get('ng'):
            return (0, abs(dev))
        if dev > upper:
            return (2, dev - upper)
        if dev < lower:
            return (2, lower - dev)
        return (1, abs(dev))

    return max(candidates, key=_severity)


def detect_parent_row_conflicts(
    measurements: Iterable[dict],
    row_index: dict[str, tuple[str, int]],
) -> list[dict]:
    """
    检测「多个 PDF 子编号争同一模板父序号」的冲突组。

    Returns:
        [{template_key, candidates: [measure_dict, ...]}, ...]
    """
    parent_groups: dict[str, list[dict]] = defaultdict(list)
    for m in measurements:
        if resolve_measure_location(row_index, m):
            continue
        sub = m.get('sub') or ''
        if not sub:
            continue
        parent_key = str(m['num'])
        if parent_key in row_index:
            parent_groups[parent_key].append(m)

    conflicts: list[dict] = []
    for parent_key, raw in sorted(parent_groups.items(), key=lambda x: x[0]):
        candidates = _unique_candidates(raw)
        if len(candidates) < 2:
            continue
        conflicts.append({
            'template_key': parent_key,
            'candidates': candidates,
        })
    return conflicts


def build_parent_auto_picks(
    measurements: Iterable[dict],
    row_index: dict[str, tuple[str, int]],
) -> dict[str, str]:
    """仅一个子项对应父序号时自动选定，无需用户干预。"""
    parent_groups: dict[str, list[dict]] = defaultdict(list)
    for m in measurements:
        if resolve_measure_location(row_index, m):
            continue
        sub = m.get('sub') or ''
        if not sub:
            continue
        parent_key = str(m['num'])
        if parent_key in row_index:
            parent_groups[parent_key].append(m)

    picks: dict[str, str] = {}
    for parent_key, raw in parent_groups.items():
        candidates = _unique_candidates(raw)
        if len(candidates) == 1:
            picks[parent_key] = measure_dict_key(candidates[0])
    return picks


def resolve_parent_picks(
    conflicts: list[dict],
    user_choices: dict[str, str] | None = None,
) -> dict[str, str | None]:
    """
    将用户选择解析为 template_key -> item_key（None 表示都不填）。

    user_choices 值：item_key | SKIP_SUB_ITEM | WORST_NG_SUB_ITEM
    """
    user_choices = user_choices or {}
    picks: dict[str, str | None] = {}
    for conflict in conflicts:
        template_key = conflict['template_key']
        candidates = conflict['candidates']
        choice = user_choices.get(template_key, WORST_NG_SUB_ITEM)
        if choice == SKIP_SUB_ITEM:
            picks[template_key] = None
        elif choice == WORST_NG_SUB_ITEM:
            picks[template_key] = measure_dict_key(pick_worst_ng_candidate(candidates))
        else:
            picks[template_key] = choice
    return picks


def merge_parent_picks(
    auto_picks: dict[str, str],
    resolved_conflicts: dict[str, str | None],
) -> dict[str, str | None]:
    merged: dict[str, str | None] = dict(resolved_conflicts)
    for key, item_key in auto_picks.items():
        if key not in merged:
            merged[key] = item_key
    return merged


def resolve_measure_write_location(
    measure: dict,
    row_index: dict[str, tuple[str, int]],
    parent_picks: dict[str, str | None] | None,
) -> tuple[str, int] | None:
    """精确匹配模板序号；否则按父序号 + 用户/自动子项选择写入。"""
    loc = resolve_measure_location(row_index, measure)
    if loc:
        return loc

    sub = measure.get('sub') or ''
    if not sub or not parent_picks:
        return None

    parent_key = str(measure['num'])
    if parent_key not in row_index:
        return None

    pick = parent_picks.get(parent_key)
    if pick is None:
        return None
    if measure_dict_key(measure) == pick:
        return row_index[parent_key]
    return None


def candidate_option_label(m: dict) -> str:
    label = measure_dict_label(m)
    ng = ' [NG]' if m.get('ng') else ''
    return f'{label}  实测={m["measured"]:g}{ng}'


def conflict_summary_line(conflict: dict) -> str:
    keys = conflict['template_key']
    names = ', '.join(measure_dict_label(c) for c in conflict['candidates'])
    return f'模板序号 {keys} ← {names}'
