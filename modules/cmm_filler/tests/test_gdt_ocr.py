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
    _looks_like_gdt_spec,
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])