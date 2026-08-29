"""PDF 提取与解析单元测试（纯函数，无需 OCR 模型）"""

import unittest
from dataclasses import dataclass

from modules.cmm_filler.core.parse_measurements import (
    cluster_ocr_rows,
    normalize_tolerances,
    parse_from_text_lines,
    parse_from_ocr_boxes,
)
from modules.cmm_filler.core.pdf_extract import TEXT_CHARS_THRESHOLD
from modules.cmm_filler.ocr.engine import OCRBox


def _is_ng(nominal, upper, lower, measured):
    dev = measured - nominal
    return dev < lower or dev > upper


def _month_cn_to_num(month_cn: str) -> str:
    mapping = {'十二月': '12', '一月': '01'}
    return mapping.get(month_cn, '01')


class TestClusterOCRRows(unittest.TestCase):
    def test_groups_by_y_coordinate(self):
        boxes = [
            OCRBox('FAI_01', 10, 100, 60, 120),
            OCRBox('12.345', 200, 102, 260, 118),
            OCRBox('FAI_02', 10, 200, 60, 220),
            OCRBox('5.678', 200, 202, 260, 218),
        ]
        rows = cluster_ocr_rows(boxes, y_tolerance=15)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0].text, 'FAI_01')
        self.assertEqual(rows[1][0].text, 'FAI_02')


class TestParseFromTextLines(unittest.TestCase):
    def test_parses_fai_measurements(self):
        lines = [
            '零件名：TestPart',
            '日期：2024-01-15',
            'FAI_01 孔径 12.345 0.100 0.100 12.350',
        ]
        data = parse_from_text_lines(lines, ['FAI'], set(), _is_ng, _month_cn_to_num)
        self.assertEqual(data['part_name'], 'TestPart')
        self.assertEqual(data['date'], '2024-01-15')
        self.assertEqual(len(data['measurements']), 1)
        m = data['measurements'][0]
        self.assertEqual(m['num'], 1)
        self.assertAlmostEqual(m['nominal'], 12.345)
        self.assertAlmostEqual(m['measured'], 12.350)
        self.assertFalse(m['ng'])

    def test_detects_ng(self):
        lines = ['FAI_01 尺寸 10.0 0.1 0.1 10.5']
        data = parse_from_text_lines(lines, ['FAI'], set(), _is_ng, _month_cn_to_num)
        self.assertTrue(data['measurements'][0]['ng'])


class TestParseFromOCRBoxes(unittest.TestCase):
    def test_table_alignment(self):
        boxes = [
            OCRBox('FAI_01', 10, 100, 80, 120),
            OCRBox('孔径', 90, 100, 130, 120),
            OCRBox('12.345', 200, 102, 260, 118),
            OCRBox('0.100', 280, 102, 330, 118),
            OCRBox('0.100', 350, 102, 400, 118),
            OCRBox('12.350', 420, 102, 480, 118),
        ]
        data = parse_from_ocr_boxes(boxes, ['FAI'], set(), _is_ng, _month_cn_to_num)
        self.assertEqual(len(data['measurements']), 1)
        m = data['measurements'][0]
        self.assertAlmostEqual(m['nominal'], 12.345)
        self.assertAlmostEqual(m['measured'], 12.350)

    def test_pc_dmis_label_header_data_rows(self):
        """PC-DMIS 三行结构：标签 → 表头 → 数据"""
        boxes = [
            OCRBox('特性', 10, 100, 50, 120),
            OCRBox('FAI_22-圆5', 60, 100, 150, 120),
            OCRBox('AX', 10, 130, 40, 150),
            OCRBox('NOMINAL', 50, 130, 120, 150),
            OCRBox('+TOL', 130, 130, 180, 150),
            OCRBox('-TOL', 190, 130, 240, 150),
            OCRBox('MEAS', 250, 130, 300, 150),
            OCRBox('D', 10, 160, 40, 180),
            OCRBox('14.000', 50, 160, 120, 180),
            OCRBox('0.007', 130, 160, 180, 180),
            OCRBox('-0.005', 190, 160, 240, 180),
            OCRBox('14.010', 250, 160, 310, 180),
        ]
        data = parse_from_ocr_boxes(boxes, ['FAI'], set(), _is_ng, _month_cn_to_num)
        self.assertEqual(len(data['measurements']), 1)
        m = data['measurements'][0]
        self.assertEqual(m['num'], 22)
        self.assertAlmostEqual(m['nominal'], 14.0)
        self.assertAlmostEqual(m['measured'], 14.01)


class TestNormalizeTolerances(unittest.TestCase):
    def test_geometric_tolerance_keeps_zero_lower(self):
        upper, lower = normalize_tolerances(0.0, 0.01, 0.0)
        self.assertEqual(upper, 0.01)
        self.assertEqual(lower, 0.0)

    def test_symmetric_when_ocr_drops_minus(self):
        upper, lower = normalize_tolerances(16.0, 0.01, 0.01)
        self.assertEqual(upper, 0.01)
        self.assertEqual(lower, -0.01)

    def test_dimensional_zero_lower_becomes_symmetric(self):
        upper, lower = normalize_tolerances(90.0, 0.01, 0.0)
        self.assertEqual(lower, -0.01)


class TestPCDMISOrphanAndMultiAxis(unittest.TestCase):
    def test_infer_missing_cc5_between_cc4_and_cc6(self):
        """CC_5 标签 OCR 丢失时，从 AX 数据块按序号推断。"""
        boxes = [
            OCRBox('CC_4', 10, 100, 60, 120),
            OCRBox('垂直', 10, 130, 50, 150),
            OCRBox('平面5至平面3', 60, 130, 200, 150),
            OCRBox('AX', 10, 160, 40, 180),
            OCRBox('NOMINAL', 50, 160, 120, 180),
            OCRBox('+TOL', 130, 160, 180, 180),
            OCRBox('-TOL', 190, 160, 240, 180),
            OCRBox('MEAS', 250, 160, 300, 180),
            OCRBox('90.000', 50, 190, 120, 210),
            OCRBox('0.010', 130, 190, 180, 210),
            OCRBox('-0.010', 190, 190, 240, 210),
            OCRBox('90.001', 250, 190, 310, 210),
            OCRBox('CC_6-平面3至平面6', 10, 220, 200, 240),
            OCRBox('AX', 10, 250, 40, 270),
            OCRBox('NOMINAL', 50, 250, 120, 270),
            OCRBox('+TOL', 130, 250, 180, 270),
            OCRBox('-TOL', 190, 250, 240, 270),
            OCRBox('MEAS', 250, 250, 300, 270),
            OCRBox('89.998', 50, 280, 120, 300),
            OCRBox('0.010', 130, 280, 180, 300),
            OCRBox('-0.010', 190, 280, 240, 300),
            OCRBox('89.998', 250, 280, 310, 300),
        ]
        data = parse_from_ocr_boxes(boxes, ['CC'], set(), _is_ng, _month_cn_to_num)
        nums = {m['num']: m for m in data['measurements']}
        self.assertIn(5, nums)
        self.assertAlmostEqual(nums[5]['nominal'], 90.0)
        self.assertAlmostEqual(nums[5]['measured'], 90.001)

    def test_position_picks_diameter_axis(self):
        boxes = [
            OCRBox('特性', 10, 100, 50, 120),
            OCRBox('CC_15-圆柱1', 60, 100, 180, 120),
            OCRBox('AX', 10, 130, 40, 150),
            OCRBox('NOMINAL', 50, 130, 120, 150),
            OCRBox('+TOL', 130, 130, 180, 150),
            OCRBox('-TOL', 190, 130, 240, 150),
            OCRBox('MEAS', 250, 130, 300, 150),
            OCRBox('X', 10, 160, 30, 180),
            OCRBox('0.000', 50, 160, 120, 180),
            OCRBox('0.010', 130, 160, 180, 180),
            OCRBox('-0.010', 190, 160, 240, 180),
            OCRBox('0.000', 250, 160, 310, 180),
            OCRBox('Y', 10, 190, 30, 210),
            OCRBox('0.000', 50, 190, 120, 210),
            OCRBox('0.010', 130, 190, 180, 210),
            OCRBox('0.010', 190, 190, 240, 210),
            OCRBox('0.000', 250, 190, 310, 210),
            OCRBox('D', 10, 220, 30, 240),
            OCRBox('10.000', 50, 220, 120, 240),
            OCRBox('0.010', 130, 220, 180, 240),
            OCRBox('-0.010', 190, 220, 240, 240),
            OCRBox('10.192', 250, 220, 310, 240),
        ]
        data = parse_from_ocr_boxes(boxes, ['CC'], set(), _is_ng, _month_cn_to_num)
        m = data['measurements'][0]
        self.assertEqual(m['num'], 15)
        self.assertAlmostEqual(m['nominal'], 10.0)
        self.assertAlmostEqual(m['measured'], 10.192)
        self.assertAlmostEqual(m['lower_tol'], -0.01)

    def test_position_respects_template_axis_preference(self):
        boxes = [
            OCRBox('CC_15-圆柱1', 10, 100, 180, 120),
            OCRBox('AX', 10, 130, 40, 150),
            OCRBox('NOMINAL', 50, 130, 120, 150),
            OCRBox('X', 10, 160, 30, 180),
            OCRBox('0.000', 50, 160, 120, 180),
            OCRBox('0.010', 130, 160, 180, 180),
            OCRBox('-0.010', 190, 160, 240, 180),
            OCRBox('0.123', 250, 160, 310, 180),
            OCRBox('D', 10, 220, 30, 240),
            OCRBox('10.000', 50, 220, 120, 240),
            OCRBox('0.010', 130, 220, 180, 240),
            OCRBox('-0.010', 190, 220, 240, 240),
            OCRBox('10.192', 250, 220, 310, 240),
        ]
        data = parse_from_ocr_boxes(
            boxes, ['CC'], set(), _is_ng, _month_cn_to_num,
            axis_preferences={'15': 'X'},
        )
        m = data['measurements'][0]
        self.assertAlmostEqual(m['measured'], 0.123)

    def test_geometric_uses_plane_row_before_label(self):
        boxes = [
            OCRBox('平面5', 10, 70, 60, 90),
            OCRBox('0.000', 100, 70, 150, 90),
            OCRBox('0.010', 160, 70, 210, 90),
            OCRBox('0.000', 220, 70, 270, 90),
            OCRBox('0.001', 280, 70, 330, 90),
            OCRBox('CC_4', 10, 100, 60, 120),
            OCRBox('垂直', 70, 100, 120, 120),
            OCRBox('平面6', 10, 130, 60, 150),
            OCRBox('0.000', 100, 130, 150, 150),
            OCRBox('0.010', 160, 130, 210, 150),
            OCRBox('0.000', 220, 130, 270, 150),
            OCRBox('0.000', 280, 130, 330, 150),
        ]
        data = parse_from_ocr_boxes(boxes, ['CC'], set(), _is_ng, _month_cn_to_num)
        m = data['measurements'][0]
        self.assertEqual(m['num'], 4)
        self.assertAlmostEqual(m['measured'], 0.001)
        self.assertEqual(m['lower_tol'], 0.0)

    def test_geometric_uses_plane_row_after_label(self):
        boxes = [
            OCRBox('CC_1', 10, 100, 60, 120),
            OCRBox('特性', 70, 100, 120, 120),
            OCRBox('特性', 10, 130, 50, 150),
            OCRBox('NOMINAL', 100, 130, 150, 150),
            OCRBox('平面3', 10, 160, 60, 180),
            OCRBox('0.000', 100, 160, 150, 180),
            OCRBox('0.010', 160, 160, 210, 180),
            OCRBox('0.000', 220, 160, 270, 180),
            OCRBox('0.002', 280, 160, 330, 180),
        ]
        data = parse_from_ocr_boxes(boxes, ['CC'], set(), _is_ng, _month_cn_to_num)
        m = data['measurements'][0]
        self.assertEqual(m['num'], 1)
        self.assertAlmostEqual(m['measured'], 0.002)


class TestPDFExtractConstants(unittest.TestCase):
    def test_text_threshold(self):
        self.assertEqual(TEXT_CHARS_THRESHOLD, 50)


if __name__ == '__main__':
    unittest.main()
