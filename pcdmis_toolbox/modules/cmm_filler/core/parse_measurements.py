"""
CMM 测量项解析
==============
- 行文本解析（OCR/文本层通用）
- OCR 坐标表格对齐解析（按 bbox 聚类分行分列）
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from ..ocr.engine import OCRBox

logger = logging.getLogger('CMMFiller')


class ParsedLabel(NamedTuple):
    """解析后的测量项标签。"""
    prefix: str   # FAI / DIM / CC / 尺寸 ...
    num: int      # 主编号，如 34、0
    sub: str      # 子编号：'1'、'a'、'00-A'；无子编号时为空串
    sub_sep: str  # 子编号分隔符：'-'、'.'、'_'；无子编号时为空串
    desc: str     # 描述（标签之后的文本）


def _prefix_alt(item_prefixes: list[str]) -> str:
    return '|'.join(re.escape(p) for p in item_prefixes)


def _compile_label_patterns(item_prefixes: list[str]) -> list[tuple[re.Pattern, str]]:
    """
    按优先级排列的标签正则。返回 (pattern, sub_sep)。

    占位说明（非字面量）：
    - {num}  → 任意整数主编号，如 00、12、34
    - {sub}  → 子编号：数字(1/2/3) 或 字母(a/b/A)
    - 示例：CC_{num}_{sub}、CC_{num}.{sub}、CC_{num}-{sub}、CC{num}-{sub}、CC-{num}
    """
    p = _prefix_alt(item_prefixes)
    # prefix 与数字之间：无分隔 / 下划线 / 连字符（CC12、CC_12、CC-12）
    pfx = rf'(?P<prefix>{p})\s*[_\s]*'
    return [
        # FAI_34-1 / CC12-3 / CC-12-3 / FAI_00-a
        (re.compile(
            rf'^{pfx}-?(?P<num>\d+)\s*-\s*(?P<sub>[a-zA-Z0-9]+)\s*[-\s]*(?P<desc>.*)$',
            re.IGNORECASE,
        ), '-'),
        # FAI_00.1 / CC_12.5
        (re.compile(
            rf'^{pfx}(?P<num>\d+)\s*\.\s*(?P<sub>\d+)\s*[-\s]*(?P<desc>.*)$',
            re.IGNORECASE,
        ), '.'),
        # fai00_00-A / CC_12_3
        (re.compile(
            rf'^{pfx}(?P<num>\d+)\s*_\s*(?P<sub>[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?)\s*[-\s]*(?P<desc>.*)$',
            re.IGNORECASE,
        ), '_'),
        # CC-12（前缀与主号之间连字符，无子编号）
        (re.compile(
            rf'^{pfx}-\s*(?P<num>\d+)(?!\s*-\s*[a-zA-Z0-9])\s*[-\s]*(?P<desc>.*)$',
            re.IGNORECASE,
        ), ''),
        # 无子编号：FAI_10、CC12、DIM 10
        (re.compile(
            rf'^{pfx}(?P<num>\d+)\s*[-\s]*(?P<desc>.*)$',
            re.IGNORECASE,
        ), ''),
    ]


def parse_fai_label(text: str, item_prefixes: list[str]) -> ParsedLabel | None:
    """解析测量项行首标签（兼容多种前缀与子编号格式）。"""
    line = text.strip()
    if not line:
        return None
    for pattern, sub_sep in _compile_label_patterns(item_prefixes):
        m = pattern.match(line)
        if not m:
            continue
        prefix = m.group('prefix')
        num = int(m.group('num'))
        sub = (m.groupdict().get('sub') or '').strip()
        desc = (m.groupdict().get('desc') or '').strip()
        return ParsedLabel(prefix=prefix.upper() if prefix.isascii() else prefix,
                           num=num, sub=sub, sub_sep=sub_sep, desc=desc)
    return None


def find_label_in_row(row_text: str, item_prefixes: list[str]) -> ParsedLabel | None:
    """从行内任意位置定位并解析标签（OCR 表格行首常有「特性」等前缀列）。"""
    p = _prefix_alt(item_prefixes)
    anchor = re.compile(rf'(?:{p})\s*[_\s-]*\d+', re.IGNORECASE)
    m = anchor.search(row_text)
    if not m:
        return None
    return parse_fai_label(row_text[m.start():], item_prefixes)


def _is_numeric_cell(text: str) -> bool:
    t = text.strip().replace(',', '')
    return bool(re.fullmatch(r'[-+]?\d+\.?\d*', t))


def _numeric_values_from_cells(row_cells: list[OCRBox], skip_lines: set[str]) -> list[float]:
    """从表格行中提取纯数字单元格（跳过轴名列、描述列）。"""
    values: list[float] = []
    for cell in row_cells:
        t = cell.text.strip()
        if not t or t in skip_lines:
            continue
        if _is_numeric_cell(t):
            values.append(float(t))
    return values


def _is_table_header_row(row_cells: list[OCRBox]) -> bool:
    text = ' '.join(c.text for c in row_cells).upper()
    return 'NOMINAL' in text and ('MEAS' in text or 'TOL' in text)


def _remainder_after_label(text: str, item_prefixes: list[str]) -> tuple[ParsedLabel, str] | None:
    """解析标签并返回标签之后的剩余文本（用于提取数值）。"""
    line = text.strip()
    for pattern, sub_sep in _compile_label_patterns(item_prefixes):
        m = pattern.match(line)
        if not m:
            continue
        prefix = m.group('prefix')
        num = int(m.group('num'))
        sub = (m.groupdict().get('sub') or '').strip()
        desc = (m.groupdict().get('desc') or '').strip()
        parsed = ParsedLabel(prefix=prefix.upper() if prefix.isascii() else prefix,
                             num=num, sub=sub, sub_sep=sub_sep, desc=desc)
        return parsed, line[m.end():]
    return None


def format_item_label(prefix: str, num: int, sub: str = '', sub_sep: str = '-') -> str:
    """格式化显示标签。"""
    if prefix.isascii() and prefix.upper() in ('FAI', 'FAL', 'FAIL', 'DIM', 'CC', 'CHECK'):
        head = f'{prefix.upper()}_{num}'
    elif prefix:
        head = f'{prefix}_{num}'
    else:
        head = f'FAI_{num}'
    if sub:
        return f'{head}{sub_sep}{sub}'
    return f'{head}' if num >= 100 or prefix in ('尺寸',) else f'{head}'


# 向后兼容别名
def format_fai_label(num: int, sub: str | int = '', sub_sep: str = '-', prefix: str = 'FAI') -> str:
    sub_s = str(sub) if sub else ''
    return format_item_label(prefix, num, sub_s, sub_sep)


def item_key(num: int, sub: str | int = '', sub_sep: str = '-') -> str:
    """测量项唯一键（用于去重、剔除、修正）。"""
    sub_s = str(sub) if sub else ''
    if not sub_s:
        return str(num)
    return f'{num}{sub_sep}{sub_s}'


def measure_row_index(num: int, sub: str | int = '', sub_sep: str = '-') -> int:
    """
    Excel 行偏移。
    - FAI_34-1 → 34，FAI_34-2 → 35
    - FAI_00-a → 1，FAI_00-b → 2（字母子编号）
    - FAI_00.1 → 1（点分式数字子编号）
    """
    sub_s = str(sub) if sub else ''
    if not sub_s:
        return num
    # 点号/下划线 + 数字子号：CC_0_1、CC_0.1 主号为 0 时行号从 1 起
    if sub_sep in ('.', '_') and sub_s.isdigit():
        return num + int(sub_s) if num == 0 else num + int(sub_s) - 1
    if sub_s.isdigit():
        return num + int(sub_s) - 1
    if len(sub_s) == 1 and sub_s.isalpha():
        return num + ord(sub_s.lower()) - ord('a') + 1
    m = re.match(r'(\d+)', sub_s)
    if m:
        return num + int(m.group(1)) - 1
    return num


def _measurement_sort_key(m: dict) -> tuple:
    return (m['num'], m.get('sub', ''), m.get('prefix', ''))


def measure_dict_key(m: dict) -> str:
    return m.get('item_key') or item_key(m['num'], m.get('sub', ''), m.get('sub_sep', '-'))


def measure_dict_label(m: dict) -> str:
    if m.get('label'):
        return m['label']
    return format_item_label(
        m.get('prefix', 'FAI'), m['num'], m.get('sub', ''), m.get('sub_sep', '-'),
    )


def measure_dict_row_index(m: dict) -> int:
    return measure_row_index(m['num'], m.get('sub', ''), m.get('sub_sep', '-'))


def preferred_axis_for_item(
    axis_preferences: dict[str, str] | None,
    num: int,
    sub: str = '',
) -> str | None:
    """从模板「轴」列配置查找指定序号应取的测量轴（D/X/Y/M/A 等）。"""
    if not axis_preferences:
        return None
    for key in (str(num), item_key(num, sub)):
        axis = axis_preferences.get(key)
        if axis:
            return axis.upper()
    return None


def _build_measurement(
    parsed: ParsedLabel,
    nums: list[float],
    is_ng_fn: Callable,
    confidence: float = 1.0,
    confidence_threshold: float = 0.85,
) -> dict:
    label = format_item_label(parsed.prefix, parsed.num, parsed.sub, parsed.sub_sep)
    nominal = nums[0]
    upper, lower = normalize_tolerances(nominal, nums[1], nums[2])
    measured = nums[3]
    return {
        'prefix': parsed.prefix,
        'num': parsed.num,
        'sub': parsed.sub,
        'sub_sep': parsed.sub_sep,
        'item_key': item_key(parsed.num, parsed.sub, parsed.sub_sep),
        'label': label,
        'desc': parsed.desc,
        'nominal': nominal,
        'upper_tol': upper,
        'lower_tol': lower,
        'measured': measured,
        'ng': is_ng_fn(nominal, upper, lower, measured),
        'confidence': round(confidence, 3),
        'low_confidence': confidence < confidence_threshold,
    }


def normalize_tolerances(nominal: float, upper: float, lower: float) -> tuple[float, float]:
    """
    公差归一化（PC-DMIS / OCR 兼容）。

    - 形位公差（名义值≈0 且下公差≈0）：仅上公差有效，下公差保持 0
    - 尺寸公差 OCR 丢负号：上下均为正且相等 → 对称公差
    - 名义值非零而下公差为 0 → 按对称公差处理
    """
    if upper <= 0:
        return upper, lower
    if abs(nominal) < 1e-9 and abs(lower) < 1e-9:
        return upper, 0.0
    if lower > 0 and abs(upper - lower) < 1e-9:
        return upper, -upper
    if abs(nominal) > 1e-9 and abs(lower) < 1e-12:
        return upper, -upper
    return upper, lower


_AXIS_PRIORITY = ('D', 'M', 'A', 'Z', 'X', 'Y')


def _is_ax_header_row(row_cells: list[OCRBox]) -> bool:
    text = ' '.join(c.text for c in row_cells).upper()
    return 'AX' in text and 'NOMINAL' in text and 'MEAS' in text


def _is_plane_feature_row(row_cells: list[OCRBox], skip_lines: set[str]) -> list[float] | None:
    if not row_cells:
        return None
    first = row_cells[0].text.strip()
    if not re.match(r'平面\d+', first) and not re.match(r'plane\s*\d+', first, re.IGNORECASE):
        return None
    nums = _numeric_values_from_cells(row_cells, skip_lines)
    return nums if len(nums) >= 4 else None


def _is_angle_feature_desc(desc: str) -> bool:
    """仅识别角度项。不含「至」：垂直/平面5至平面3 是形位，不是角度。"""
    text = desc or ''
    if re.search(r'垂直|平面度|平行|位置|轮廓|圆度|圆柱度|跳动|倾斜|同轴|对称', text):
        return False
    return bool(re.search(r'角度|angle', text, re.IGNORECASE))


def _parse_ax_data_row(row_cells: list[OCRBox], skip_lines: set[str]) -> tuple[str, list[float]] | None:
    nums = _numeric_values_from_cells(row_cells, skip_lines)
    if len(nums) < 4:
        return None
    first = row_cells[0].text.strip()
    if len(first) == 1 and first.isalpha():
        return first.upper(), nums[:4]
    if _is_numeric_cell(first):
        return '', nums[:4]
    return None


def _pick_primary_ax_nums(
    ax_rows: list[tuple[str, list[float]]],
    preferred_axis: str | None = None,
    item_label: str = '',
) -> list[float] | None:
    if not ax_rows:
        return None
    if preferred_axis:
        pref = preferred_axis.upper()
        for ax, nums in ax_rows:
            if ax == pref:
                return nums[:4]
        available = [ax for ax, _ in ax_rows if ax]
        logger.warning(
            f'  [轴选择] {item_label or "该项"} 模板指定轴 {pref}，'
            f'PDF 仅有 {available or ["(无轴标识)"]}，回退默认优先级'
        )
    for axis in _AXIS_PRIORITY:
        for ax, nums in ax_rows:
            if ax == axis:
                return nums[:4]
    if len(ax_rows) > 1:
        return ax_rows[-1][1][:4]
    return ax_rows[0][1][:4]


def _collect_forward_data_rows(
    rows: list[list[OCRBox]],
    start_idx: int,
    skip_lines: set[str],
    item_prefixes: list[str],
    end_idx: int | None = None,
) -> tuple[list[tuple[str, list[float]]], list[list[float]]]:
    """从标签行之后收集 AX 数据行（跳过平面特征行与表头）。"""
    ax_rows: list[tuple[str, list[float]]] = []
    numeric_rows: list[list[float]] = []
    end = len(rows) if end_idx is None else end_idx
    j = start_idx + 1
    while j < end and j <= start_idx + 12:
        row_text = ' '.join(c.text for c in rows[j])
        if find_label_in_row(row_text, item_prefixes):
            break
        if _is_ax_header_row(rows[j]) or _is_table_header_row(rows[j]):
            j += 1
            continue
        if _is_plane_feature_row(rows[j], skip_lines):
            j += 1
            continue
        ax = _parse_ax_data_row(rows[j], skip_lines)
        if ax:
            ax_rows.append(ax)
            j += 1
            continue
        j += 1
    return ax_rows, numeric_rows


def _collect_ax_blocks_between(
    rows: list[list[OCRBox]],
    start_idx: int,
    end_idx: int,
    skip_lines: set[str],
    item_prefixes: list[str],
) -> list[tuple[list[tuple[str, list[float]]], float]]:
    """两个标签之间按 AX 表头切成多块，每块独立（不把后一块并进第一块）。"""
    blocks: list[tuple[list[tuple[str, list[float]]], float]] = []
    j = start_idx + 1
    while j < end_idx:
        row_text = ' '.join(c.text for c in rows[j])
        if find_label_in_row(row_text, item_prefixes):
            j += 1
            continue
        if not _is_ax_header_row(rows[j]):
            j += 1
            continue
        ax_rows: list[tuple[str, list[float]]] = []
        conf = 1.0
        k = j + 1
        while k < end_idx:
            if find_label_in_row(' '.join(c.text for c in rows[k]), item_prefixes):
                break
            if _is_ax_header_row(rows[k]):
                break
            if _is_table_header_row(rows[k]) or _is_plane_feature_row(rows[k], skip_lines):
                k += 1
                continue
            ax = _parse_ax_data_row(rows[k], skip_lines)
            if ax:
                ax_rows.append(ax)
                conf = _row_confidence(rows[k])
            k += 1
        if ax_rows:
            blocks.append((ax_rows, conf))
        j = k
    return blocks


def _row_confidence(row_cells: list[OCRBox]) -> float:
    confidences = [c.confidence for c in row_cells if c.confidence > 0]
    return min(confidences) if confidences else 1.0


def _try_forward_plane_nums(
    rows: list[list[OCRBox]],
    label_idx: int,
    skip_lines: set[str],
    item_prefixes: list[str],
) -> tuple[list[float] | None, float]:
    j = label_idx + 1
    while j < len(rows) and j <= label_idx + 6:
        row_text = ' '.join(c.text for c in rows[j])
        if find_label_in_row(row_text, item_prefixes):
            break
        if _is_ax_header_row(rows[j]) or _is_table_header_row(rows[j]):
            j += 1
            continue
        plane = _is_plane_feature_row(rows[j], skip_lines)
        if plane:
            return plane[:4], _row_confidence(rows[j])
        j += 1
    return None, 1.0


def _resolve_pc_dmis_nums(
    rows: list[list[OCRBox]],
    label_idx: int,
    parsed: ParsedLabel,
    item_prefixes: list[str],
    skip_lines: set[str],
    axis_preferences: dict[str, str] | None = None,
) -> tuple[list[float] | None, float]:
    """按 PC-DMIS 报告结构解析单个 CC/FAI 标签对应的四元组数值。"""
    row_cells = rows[label_idx]
    row_text = ' '.join(c.text for c in row_cells)

    inline_nums = _extract_floats_from_text(parsed.desc)
    if len(inline_nums) >= 4:
        return inline_nums[:4], _row_confidence(row_cells)

    same_row_nums = _numeric_values_from_cells(row_cells, skip_lines)
    if len(same_row_nums) >= 4:
        return same_row_nums[:4], _row_confidence(row_cells)

    label = format_item_label(parsed.prefix, parsed.num, parsed.sub, parsed.sub_sep)
    pref_axis = None
    if axis_preferences:
        pref_axis = preferred_axis_for_item(axis_preferences, parsed.num, parsed.sub)

    if _is_angle_feature_desc(parsed.desc):
        ax_rows, _ = _collect_forward_data_rows(
            rows, label_idx, skip_lines, item_prefixes,
        )
        nums = _pick_primary_ax_nums(ax_rows, pref_axis or 'A', label)
        if nums:
            conf = _row_confidence(rows[label_idx + 1]) if label_idx + 1 < len(rows) else 1.0
            return nums, conf

    # 形位公差：数据可能在标签前（平面5→CC_4）或标签后（CC_1→平面3）
    if label_idx > 0:
        plane_nums = _is_plane_feature_row(rows[label_idx - 1], skip_lines)
        if plane_nums:
            return plane_nums[:4], _row_confidence(rows[label_idx - 1])

    fwd_plane, fwd_conf = _try_forward_plane_nums(
        rows, label_idx, skip_lines, item_prefixes,
    )
    if fwd_plane:
        return fwd_plane, fwd_conf

    ax_rows, _ = _collect_forward_data_rows(
        rows, label_idx, skip_lines, item_prefixes,
    )
    nums = _pick_primary_ax_nums(ax_rows, pref_axis, label)
    if nums:
        data_idx = label_idx + 1
        while data_idx < len(rows):
            if _parse_ax_data_row(rows[data_idx], skip_lines):
                break
            data_idx += 1
        conf = _row_confidence(rows[data_idx]) if data_idx < len(rows) else 1.0
        return nums, conf

    return None, 1.0


def _infer_orphan_measurements(
    rows: list[list[OCRBox]],
    label_positions: list[tuple[int, ParsedLabel]],
    assigned_nums: set[int],
    item_prefixes: list[str],
    skip_lines: set[str],
    is_ng_fn: Callable,
    confidence_threshold: float,
    axis_preferences: dict[str, str] | None = None,
) -> list[dict]:
    """
    推断 OCR 漏识标签的 CC 项（如 CC_5 标签被读成「垂直|平面5至平面3」）。
    在两个已识别 CC 标签之间，若存在 AX 表头+数据且编号连续缺失，则补全。
    """
    orphans: list[dict] = []
    if not label_positions:
        return orphans

    for li in range(len(label_positions) - 1):
        idx_curr, parsed_curr = label_positions[li]
        idx_next, parsed_next = label_positions[li + 1]
        missing_nums = [
            n for n in range(parsed_curr.num + 1, parsed_next.num)
            if n not in assigned_nums
        ]
        if not missing_nums:
            continue
        blocks = _collect_ax_blocks_between(
            rows, idx_curr, idx_next, skip_lines, item_prefixes,
        )
        for missing, (ax_rows, data_conf) in zip(missing_nums, blocks):
            inferred = ParsedLabel(
                prefix=parsed_curr.prefix, num=missing, sub='', sub_sep='', desc='',
            )
            label = format_item_label(inferred.prefix, inferred.num, inferred.sub, inferred.sub_sep)
            pref_axis = None
            if axis_preferences:
                pref_axis = preferred_axis_for_item(axis_preferences, missing)
            nums = _pick_primary_ax_nums(ax_rows, pref_axis, label)
            if not nums:
                continue
            logger.info(f'  [推断标签] {label}（OCR 未识别标签，按序号 {missing} 补全）')
            orphans.append(_build_measurement(
                inferred, nums, is_ng_fn,
                confidence=data_conf, confidence_threshold=confidence_threshold,
            ))
            assigned_nums.add(missing)
    return orphans


def cluster_ocr_rows(boxes: list[OCRBox], y_tolerance: float | None = None) -> list[list[OCRBox]]:
    """按 Y 坐标将 OCR 框聚类为行，行内按 X 坐标排序。"""
    if not boxes:
        return []

    sorted_boxes = sorted(boxes, key=lambda b: b.y_center)
    if y_tolerance is None:
        heights = [b.y1 - b.y0 for b in sorted_boxes]
        avg_h = sum(heights) / len(heights) if heights else 10.0
        y_tolerance = max(avg_h * 0.6, 5.0)

    rows: list[list[OCRBox]] = []
    current_row = [sorted_boxes[0]]
    current_y = sorted_boxes[0].y_center

    for box in sorted_boxes[1:]:
        if abs(box.y_center - current_y) <= y_tolerance:
            current_row.append(box)
        else:
            rows.append(sorted(current_row, key=lambda b: b.x0))
            current_row = [box]
            current_y = box.y_center
    rows.append(sorted(current_row, key=lambda b: b.x0))
    return rows


def _extract_floats_from_text(text: str) -> list[float]:
    """从文本中提取所有浮点数。"""
    nums: list[float] = []
    for m in re.finditer(r'[-+]?\d+\.?\d*', text):
        token = m.group()
        try:
            nums.append(float(token))
        except ValueError:
            continue
    return nums


def _parse_measurement_row(
    row_text: str,
    row_cells: list[OCRBox] | None,
    item_prefixes: list[str],
    skip_lines: set[str],
    is_ng_fn: Callable,
    confidence_threshold: float = 0.85,
) -> tuple[dict | None, list[str]]:
    """
    解析单行测量数据。

    Returns:
        (measurement_dict | None, warnings)
    """
    warnings: list[str] = []
    parsed = find_label_in_row(row_text, item_prefixes) or parse_fai_label(row_text, item_prefixes)
    if not parsed:
        return None, warnings

    label = format_item_label(parsed.prefix, parsed.num, parsed.sub, parsed.sub_sep)

    numbers: list[float] = []
    if row_cells and len(row_cells) > 1:
        numbers = _numeric_values_from_cells(row_cells, skip_lines)
        if len(numbers) < 4:
            for cell in row_cells[1:]:
                if cell.text.strip() in skip_lines:
                    continue
                cell_nums = _extract_floats_from_text(cell.text)
                if cell_nums:
                    numbers.extend(cell_nums)
    else:
        numbers = _extract_floats_from_text(parsed.desc)

    # 过滤行号伪影：测量项后首个无小数点整数
    if numbers and '.' not in str(numbers[0]) and numbers[0] == int(numbers[0]):
        numbers = numbers[1:]

    if len(numbers) < 4:
        warnings.append(f'{label} 数据不完整（只识别到 {len(numbers)} 个数字）')
        return None, warnings

    nominal, upper, lower, measured = numbers[0], numbers[1], numbers[2], numbers[3]
    upper, lower = normalize_tolerances(nominal, upper, lower)

    confidences = [c.confidence for c in (row_cells or []) if c.confidence > 0]
    confidence = min(confidences) if confidences else 1.0

    return _build_measurement(
        parsed, [nominal, upper, lower, measured], is_ng_fn,
        confidence=confidence, confidence_threshold=confidence_threshold,
    ), warnings


def parse_header_fields(text: str, month_cn_to_num_fn: Callable[[str], str]) -> dict:
    """从全文提取零件名、日期等头信息。"""
    data = {'part_name': '', 'date': ''}
    warnings: list[str] = []

    m = re.search(r'零件名[：:]\s*\n?\s*(\S+)', text)
    if m:
        data['part_name'] = m.group(1).strip()
    else:
        warnings.append('未识别到零件名')

    date_parsed = False
    for sep in ('-', '/', '.'):
        m = re.search(rf'(\d{{4}})\{sep}(\d{{1,2}})\{sep}(\d{{1,2}})', text)
        if m:
            data['date'] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
            date_parsed = True
            break
    if not date_parsed:
        m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
        if m:
            data['date'] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
            date_parsed = True
    if not date_parsed:
        m = re.search(
            r'(一月|二月|三月|四月|五月|六月|七月|八月|九月|十月|十一月|十二月)\s*(\d{1,2}),?\s*(\d{4})',
            text,
        )
        if m:
            month_num = month_cn_to_num_fn(m.group(1))
            data['date'] = f"{m.group(3)}-{month_num}-{m.group(2).zfill(2)}"
            date_parsed = True
    if not date_parsed:
        warnings.append('未识别到日期')

    return data, warnings


def parse_from_text_lines(
    ocr_lines: list[str],
    item_prefixes: list[str],
    skip_lines: set[str],
    is_ng_fn: Callable,
    month_cn_to_num_fn: Callable[[str], str],
) -> dict:
    """从文本行列表解析测量数据（原有行解析逻辑）。"""
    text = '\n'.join(ocr_lines)
    data, warnings = parse_header_fields(text, month_cn_to_num_fn)
    data['measurements'] = []

    def _append_measurement(parsed: ParsedLabel, nums: list[float]):
        if len(nums) >= 4:
            data['measurements'].append(
                _build_measurement(parsed, nums[:4], is_ng_fn)
            )
        elif nums:
            label = format_item_label(parsed.prefix, parsed.num, parsed.sub, parsed.sub_sep)
            warnings.append(f'{label} 数据不完整（只识别到 {len(nums)} 个数字）')

    current: ParsedLabel | None = None
    numbers: list[float] = []

    def _flush_current():
        nonlocal current, numbers
        if not current:
            return
        _append_measurement(current, numbers)
        current = None
        numbers = []

    for line in ocr_lines:
        line = line.strip()
        if not line:
            continue
        parsed = parse_fai_label(line, item_prefixes)
        if parsed:
            _flush_current()
            rest_nums = _extract_floats_from_text(parsed.desc)
            if len(rest_nums) >= 4:
                desc = re.sub(r'[-+]?\d+\.?\d*', '', parsed.desc).strip() or parsed.desc
                pl = parsed._replace(desc=desc)
                _append_measurement(pl, rest_nums[:4])
                continue
            current = parsed
            numbers = []
        else:
            if line in skip_lines:
                continue
            n = re.search(r'[-+]?\d+\.?\d*', line)
            if n:
                token = n.group()
                if '.' not in token and not numbers:
                    continue
                try:
                    numbers.append(float(token))
                except (ValueError, TypeError):
                    pass

    _flush_current()

    for w in warnings:
        logger.warning(w)
    return data


def parse_from_ocr_boxes(
    boxes: list[OCRBox],
    item_prefixes: list[str],
    skip_lines: set[str],
    is_ng_fn: Callable,
    month_cn_to_num_fn: Callable[[str], str],
    confidence_threshold: float = 0.85,
    axis_preferences: dict[str, str] | None = None,
) -> dict:
    """
    从 OCR 坐标框解析测量数据（表格对齐模式）。

    PC-DMIS 等报告常见结构：
    - 形位公差：平面特征行 → CC 标签行（取前行数据）
    - 角度/距离：CC 标签行 → AX 表头 → 数据行
    - 位置度：CC 标签行 → 多轴 X/Y/D（默认 D>M>A…，可由 axis_preferences 按模板覆盖）
    - OCR 漏识标签：按 CC 序号间隙推断（如 CC_5）

    axis_preferences: 模板「轴」列读取的 {序号: 轴字母}，如 {'15': 'X'}。
    """
    text = '\n'.join(b.text for b in sorted(boxes, key=lambda b: (b.y_center, b.x0)))
    data, warnings = parse_header_fields(text, month_cn_to_num_fn)
    data['measurements'] = []

    rows = cluster_ocr_rows(boxes)
    label_positions: list[tuple[int, ParsedLabel]] = []
    for i, row_cells in enumerate(rows):
        row_text = ' '.join(c.text for c in row_cells)
        if row_text.strip() in skip_lines:
            continue
        parsed = find_label_in_row(row_text, item_prefixes)
        if parsed:
            label_positions.append((i, parsed))

    assigned_nums: set[int] = set()
    for i, parsed in label_positions:
        label = format_item_label(parsed.prefix, parsed.num, parsed.sub, parsed.sub_sep)
        nums, confidence = _resolve_pc_dmis_nums(
            rows, i, parsed, item_prefixes, skip_lines, axis_preferences,
        )
        if not nums:
            warnings.append(f'{label} 表格行未找到完整数据')
            continue
        measurement = _build_measurement(
            parsed, nums, is_ng_fn,
            confidence=confidence, confidence_threshold=confidence_threshold,
        )
        key = measurement['item_key']
        if key not in {m['item_key'] for m in data['measurements']}:
            data['measurements'].append(measurement)
            assigned_nums.add(parsed.num)

    orphans = _infer_orphan_measurements(
        rows, label_positions, assigned_nums, item_prefixes, skip_lines,
        is_ng_fn, confidence_threshold, axis_preferences,
    )
    for m in orphans:
        if m['item_key'] not in {x['item_key'] for x in data['measurements']}:
            data['measurements'].append(m)

    data['measurements'].sort(key=_measurement_sort_key)
    for w in warnings:
        logger.warning(w)
    return data
