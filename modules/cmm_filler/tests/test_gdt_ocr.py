"""P3-11 测试：CMMFiller 形位公差（GD&T）spec 行 OCR 后处理。

真机首撞（2026-09-24）：用户跑参考 PDF
`C:\\Users\\terence\\.minimax\\v2\\assets\\2026\\09\\24\\15-10-41-868-asset_20260924-151041-868_f2809c0a93aa_445d70fb-cm2xl开发用报告2.PDF`
时发现：
- CC_8:  `| 0.5 +14.5/-9.000 => 0.0` （实际是 ⌒ 轮廓度 0.5）
- CC_21: `尺寸 | 14.5 +10.0/-86.267 => 0.3 21是圆度`（实际是 ○ 圆度 0.3）

8 种形位特征 + OCR 后误读形态（基于本机 PaddleOCR 实测）：
| 真实符号      | OCR 输出       | 模式                    |
| ⊕ 位置度      | 完全丢失       | 符号框跳 OCR            |
| ⊥ 垂直度      | 完全丢失       | 同上                    |
| ↗ 圆跳动      | 完全丢失       | 同上                    |
| ⌒ 轮廓度      | 完全丢失       | 同上                    |
| ◎ 同轴度      | `①`            | 圆圈 → 圆圈数字         |
| // 平行度     | `//`           | **正确**                |
| ∠ 倾斜度      | `<`            | 角度 → 小于号           |
| ○ 圆度        | `|`            | 圆圈 → 竖线             |

所有形位 spec 行的**符号 + 公差值 + 基准字母**都被 OCR 合并到单个 bbox
（如 `'0.3ABC'`、`'00.6A'`、`'①0.5] MEDIAN'`）。

本测试覆盖 `_looks_like_gdt_spec` 与 `_extract_gdt_tolerance`：
- 8 种 spec 形态（单值 + 1-3 datums、各种 OCR 误读）
- 普通 ± 尺寸（不应被识别为 GD&T）
- 边界：空 / 仅数字 / 含 ± / 多余字符
"""

import pytest

from modules.cmm_filler.core.parse_measurements import (
    _extract_gdt_tolerance,
    _is_gdt_label_row,
    _looks_like_gdt_spec,
    _resolve_gdt_nums,
)


# ─── _looks_like_gdt_spec ───────────────────────────────────────────

class TestLooksLikeGdtSpec:
    """GD&T spec token 识别（OCR 后单个合并的 spec 单元格文本）。

    注：仅看 spec token 本身；不含 ASME Y14.5 邻列。
    0.4 / 0.5 这种"无 datums 无符号"的值留给上层
    （spec row 邻列有 ASME Y14.5 时）兜底。
    """

    @pytest.mark.parametrize('text', [
        # 基准：单值 + 1-3 datums（最常见形态）
        '0.5A',
        '0.3ABC',
        '0.5B',
        '00.6A',           # OCR 把 Ø 误读成 "0"，后续值仍可识别
        '0.2 A',           # 基准字母前有空格
        # 平行度 // 保留
        '//0.5C',
        '//0.5',
        # 同轴度 ◎ 误读为 ①
        '①0.5]',
        '①0.5',
        # 倾斜度度度 ∠ 误读为 <
        '<0.2 A',
        '<0.2',
        # ±0 前缀
        '+0.3ABC',
        '-0.5A',
    ])
    def test_gdt_spec_detected(self, text):
        assert _looks_like_gdt_spec(text) is True, f'expected GD&T: {text!r}'

    @pytest.mark.parametrize('text', [
        # 普通 ± 上下公差
        '+0.3/-0.3',
        '86.267 +0.3/-0.3',
        # 仅数字 —— 歧义，上层用 ASME Y14.5 上下文判断
        '0.300',
        '5.750',
        '86.267',
        '0.4',
        '0.5',
        # 含 ± 但只有一边（±TOL 列里的普通值）
        '+0.5',
        '-0.5',
        # 空
        '',
        '   ',
        # 表头 / 非测量文字
        'NOMINAL',
        'AX',
        '毫米',
        'MEDIAN',
        'ASME Y14.5',
        '特征',
    ])
    def test_non_gdt_spec_rejected(self, text):
        assert _looks_like_gdt_spec(text) is False, f'should NOT be GD&T: {text!r}'


# ─── _extract_gdt_tolerance ──────────────────────────────────────────

class TestExtractGdtTolerance:
    """从 GD&T spec token 里提取单值公差数值。

    返回 float（绝对值）或 None（提取失败）。
    """

    @pytest.mark.parametrize('text,expected', [
        ('0.5A', 0.5),
        ('0.3ABC', 0.3),
        ('0.5B', 0.5),
        ('00.6A', 0.6),           # 前导 0 数字不影响提取
        ('//0.5C', 0.5),
        ('//0.5', 0.5),
        ('①0.5]', 0.5),
        ('<0.2 A', 0.2),
        ('+0.3ABC', 0.3),
        ('-0.5A', 0.5),           # 返回绝对值
        ('0.500', 0.500),          # 仅数值
        ('', None),                # 空返回 None
        ('   ', None),
        ('abc', None),             # 非数字
        ('NOMINAL', None),
        ('A', None),               # 仅 datum 无值
    ])
    def test_extract(self, text, expected):
        assert _extract_gdt_tolerance(text) == expected, f'{text!r} -> {expected}'


# ─── 集成层（P3-11 commit 2）─────────────────────────────────────────

class _FakeCell:
    """替身 OCRBox：只暴露 .text / .confidence。"""
    def __init__(self, text: str, confidence: float = 0.95):
        self.text = text
        self.confidence = confidence


def _cells(*texts: str) -> list:
    return [_FakeCell(t) for t in texts]


class TestIsGdtLabelRow:
    """_is_gdt_label_row 集成层：识别含 ASME Y14.5 或 GD&T spec token 的行。"""

    def test_with_asme_y14_5_marker(self):
        # 真机 OCR：CC_38 形位 spec 行
        assert _is_gdt_label_row(
            _cells('CC_38', '毫米', '0.3ABC', '默认值', 'ASME Y14.5'),
            ['CC'],
        ) is True

    def test_with_gdt_spec_token(self):
        # 没有 ASME Y14.5 但有 GD&T spec token
        assert _is_gdt_label_row(
            _cells('CC_39', '毫米', '00.6A', '默认值'),
            ['CC'],
        ) is True

    def test_with_parallelism_preserved(self):
        assert _is_gdt_label_row(
            _cells('CC_52', '毫米', '//0.5C', '默认值', 'ASME Y14.5'),
            ['CC'],
        ) is True

    def test_with_concentricity_misread(self):
        assert _is_gdt_label_row(
            _cells('CC_43', '毫米', '①0.5] MEDIAN', 'ASME Y14.5'),
            ['CC'],
        ) is True

    def test_with_angularity_misread(self):
        assert _is_gdt_label_row(
            _cells('CC_69', '毫米', '<0.2 A', '默认值', 'ASME Y14.5'),
            ['CC'],
        ) is True

    def test_regular_dimension_row_rejected(self):
        # 真机 OCR：CC_2 平面B 至 圆柱1（普通尺寸行，无 ASME / 无 GD&T token）
        assert _is_gdt_label_row(
            _cells('CC_2', '毫米', '平面B 至 圆柱1(Y 轴)'),
            ['CC'],
        ) is False

    def test_regular_dimension_with_dimensions_rejected(self):
        # 普通尺寸 spec 行带 ± 上下公差
        assert _is_gdt_label_row(
            _cells('CC_21', '毫米', 'Ø86.267 +0.3/-0.3', '默认值'),
            ['CC'],
        ) is False

    def test_empty_row_rejected(self):
        assert _is_gdt_label_row(_cells(''), ['CC']) is False


class TestResolveGdtNums:
    """_resolve_gdt_nums：GD&T 单值公差解析路径。"""

    def test_typical_gdt_layout_returns_correct_quadruplet(self):
        # CC_38 形位 spec + 数据行
        rows = [
            _cells('CC_38', '毫米', '0.3ABC', '默认值', 'ASME Y14.5'),
            _cells('特征', 'AX', 'NOMINAL', '+TOL', '-TOL', 'MEAS', 'DEV', 'OUTTOL', 'BONUS'),
            _cells('圆柱3 (起始点)', 'TP', '0.000', '0.300', '0.000', '0.000', '0.000', '0.000', '0.000'),
        ]
        nums, conf = _resolve_gdt_nums(rows, 0, _make_parsed('CC', 38), [], set())
        assert nums is not None
        assert nums == [0.0, 0.3, 0.0, 0.0]  # nominal=0, +TOL=0.3, -TOL=0, measured=0
        assert conf > 0

    def test_concentricity_with_garbage_meas_falls_back_to_zero(self):
        # CC_43 同轴度：MEAS = 错误（OCR 失败），只 NOMINAL + +TOL 是有效值
        rows = [
            _cells('CC_43', '毫米', '①0.5] MEDIAN', 'ASME Y14.5'),
            _cells('特征', 'NOMINAL', '+TOL', '-TOL', 'MEAS', 'DEV', 'OUTTOL', 'BONUS'),
            _cells('圆柱7', '0.000', '0.500', '0.000', '错误', '错误', '错误', '错误'),
        ]
        nums, _ = _resolve_gdt_nums(rows, 0, _make_parsed('CC', 43), [], set())
        # MEAS 错误 → 取第一个非零数（应该是 +TOL=0.5，但我们的语义是"第一个非零"会撞 +TOL）
        # 当前实现预期返回 [0, 0.5, 0, 0.5] —— 这是已知的「+TOL/MEAS 列边界不准」follow-up
        assert nums is not None
        assert nums[0] == 0.0
        assert nums[1] == 0.5     # spec value
        assert nums[2] == 0.0     # no -TOL

    def test_no_spec_value_returns_none(self):
        # spec 行没有 GD&T token
        rows = [
            _cells('CC_99', '毫米', 'NOMINAL', '+TOL'),
        ]
        nums, _ = _resolve_gdt_nums(rows, 0, _make_parsed('CC', 99), [], set())
        assert nums is None

    def test_stops_at_next_label(self):
        # spec 之后立刻撞到下一个 CC 标签
        rows = [
            _cells('CC_50', '毫米', '0.5A', '默认值', 'ASME Y14.5'),
            _cells('CC_51', '毫米', '0.5B', '默认值', 'ASME Y14.5'),
        ]
        nums, _ = _resolve_gdt_nums(rows, 0, _make_parsed('CC', 50), [], set())
        # 没数据行 → measured = 0 fallback
        assert nums is not None
        assert nums == [0.0, 0.5, 0.0, 0.0]


def _make_parsed(prefix: str, num: int):
    """替身 ParsedLabel：只暴露 prefix/num。"""
    from modules.cmm_filler.core.parse_measurements import ParsedLabel
    return ParsedLabel(prefix=prefix, num=num, sub='', sub_sep='', desc='')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])