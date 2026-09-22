"""测量项标签解析测试（多前缀、多子编号格式）"""

import unittest

from modules.cmm_filler.core.parse_measurements import (
    ParsedLabel,
    parse_fai_label,
    format_item_label,
    format_fai_label,
    item_key,
    measure_row_index,
    parse_from_text_lines,
)

PREFIXES = ['FAI', 'FAL', 'FAIL', '尺寸', 'CC', 'DIM', 'CHECK']


def _is_ng(n, u, l, m):
    return m - n < l or m - n > u


def _month(_):
    return '01'


class TestFAISubNumber(unittest.TestCase):
    def test_parse_numeric_sub(self):
        r = parse_fai_label('FAI_34-1-圆63', PREFIXES)
        self.assertEqual(r, ParsedLabel('FAI', 34, '1', '-', '圆63'))

    def test_parse_plain(self):
        r = parse_fai_label('FAI_10 平面13', PREFIXES)
        self.assertEqual(r, ParsedLabel('FAI', 10, '', '', '平面13'))

    def test_parse_letter_sub(self):
        r = parse_fai_label('fai_00-a 孔径', PREFIXES)
        self.assertEqual(r.prefix, 'FAI')
        self.assertEqual(r.num, 0)
        self.assertEqual(r.sub, 'a')
        self.assertEqual(r.sub_sep, '-')

    def test_parse_underscore_sub(self):
        r = parse_fai_label('fai00_00-A 长度', PREFIXES)
        self.assertEqual(r.prefix, 'FAI')
        self.assertEqual(r.num, 0)
        self.assertEqual(r.sub, '00-A')
        self.assertEqual(r.sub_sep, '_')

    def test_parse_dot_sub(self):
        r = parse_fai_label('fai_00.1 宽度', PREFIXES)
        self.assertEqual(r.prefix, 'FAI')
        self.assertEqual(r.num, 0)
        self.assertEqual(r.sub, '1')
        self.assertEqual(r.sub_sep, '.')

    def test_parse_dim_prefix(self):
        r = parse_fai_label('DIM_10-b 面', PREFIXES)
        self.assertEqual(r, ParsedLabel('DIM', 10, 'b', '-', '面'))

    def test_format_label(self):
        self.assertEqual(format_fai_label(34, 1), 'FAI_34-1')
        self.assertEqual(format_fai_label(10), 'FAI_10')
        self.assertEqual(format_item_label('DIM', 10, 'b'), 'DIM_10-b')

    def test_item_key(self):
        self.assertEqual(item_key(34, 1), '34-1')
        self.assertEqual(item_key(10), '10')
        self.assertEqual(item_key(0, 'a'), '0-a')
        self.assertEqual(item_key(0, '1', '.'), '0.1')
        self.assertEqual(item_key(0, '00-A', '_'), '0_00-A')

    def test_row_index(self):
        self.assertEqual(measure_row_index(34, 1), 34)
        self.assertEqual(measure_row_index(34, 2), 35)
        self.assertEqual(measure_row_index(10), 10)
        self.assertEqual(measure_row_index(0, 'a'), 1)
        self.assertEqual(measure_row_index(0, 'b'), 2)
        self.assertEqual(measure_row_index(0, '1', '.'), 1)

    def test_parse_two_sub_items(self):
        lines = [
            'FAI_34-1 圆63 9.0 0.1 0.1 9.12',
            'FAI_34-2 圆64 9.0 0.1 0.1 9.08',
        ]
        data = parse_from_text_lines(lines, PREFIXES, set(), _is_ng, _month)
        self.assertEqual(len(data['measurements']), 2)
        self.assertEqual(data['measurements'][0]['item_key'], '34-1')
        self.assertEqual(data['measurements'][1]['item_key'], '34-2')

    def test_parse_cc_compact_and_hyphen_num(self):
        """CC{num}-{sub}、CC-{num}（主号/子号为任意数字）"""
        r1 = parse_fai_label('CC12-3 孔径', PREFIXES)
        self.assertEqual(r1, ParsedLabel('CC', 12, '3', '-', '孔径'))
        r2 = parse_fai_label('CC-12 宽度', PREFIXES)
        self.assertEqual(r2, ParsedLabel('CC', 12, '', '', '宽度'))
        r3 = parse_fai_label('CC-12-3 面', PREFIXES)
        self.assertEqual(r3, ParsedLabel('CC', 12, '3', '-', '面'))
        self.assertEqual(item_key(12, '3'), '12-3')
        self.assertEqual(item_key(12), '12')

    def test_cc12_vs_cc_hyphen_distinct(self):
        lines = [
            'CC12-3 孔 1.0 0.1 0.1 1.05',
            'CC-12 宽 2.0 0.1 0.1 2.01',
            'CC-12-4 面 3.0 0.1 0.1 3.02',
        ]
        data = parse_from_text_lines(lines, PREFIXES, set(), _is_ng, _month)
        keys = {m['item_key'] for m in data['measurements']}
        self.assertEqual(keys, {'12-3', '12', '12-4'})

    def test_parse_cc_formats(self):
        """CC_{num}_{sub} / CC_{num}.{sub} / CC_{num}-{sub}（num/sub 为任意数字或字母）"""
        r1 = parse_fai_label('CC_12_3 孔径', PREFIXES)
        self.assertEqual(r1, ParsedLabel('CC', 12, '3', '_', '孔径'))
        r2 = parse_fai_label('CC_12.5 宽度', PREFIXES)
        self.assertEqual(r2, ParsedLabel('CC', 12, '5', '.', '宽度'))
        r3 = parse_fai_label('CC_12-b 面', PREFIXES)
        self.assertEqual(r3, ParsedLabel('CC', 12, 'b', '-', '面'))
        self.assertEqual(item_key(12, '3', '_'), '12_3')
        self.assertEqual(item_key(12, '5', '.'), '12.5')
        self.assertEqual(item_key(12, 'b'), '12-b')

    def test_cc_distinct_from_fai(self):
        lines = [
            'CC_0_1 孔 1.0 0.1 0.1 1.05',
            'CC_0_2 孔 1.0 0.1 0.1 0.98',
            'CC_0.1 宽 2.0 0.1 0.1 2.01',
            'CC_0-a 面 3.0 0.1 0.1 3.02',
        ]
        data = parse_from_text_lines(lines, PREFIXES, set(), _is_ng, _month)
        keys = {m['item_key'] for m in data['measurements']}
        self.assertEqual(len(keys), 4)
        self.assertEqual(keys, {'0_1', '0_2', '0.1', '0-a'})

    def test_row_index_cc_underscore(self):
        self.assertEqual(measure_row_index(0, '1', '_'), 1)
        self.assertEqual(measure_row_index(12, '3', '_'), 14)

    def test_mixed_formats_distinct(self):
        lines = [
            'fai_00-a 孔 1.0 0.1 0.1 1.05',
            'fai_00-b 孔 1.0 0.1 0.1 0.98',
            'fai_00.1 宽 2.0 0.1 0.1 2.01',
            'DIM_10 面 3.0 0.1 0.1 3.02',
        ]
        data = parse_from_text_lines(lines, PREFIXES, set(), _is_ng, _month)
        keys = {m['item_key'] for m in data['measurements']}
        self.assertEqual(len(keys), 4)
        self.assertIn('0-a', keys)
        self.assertIn('0-b', keys)
        self.assertIn('0.1', keys)
        self.assertIn('10', keys)


if __name__ == '__main__':
    unittest.main()
