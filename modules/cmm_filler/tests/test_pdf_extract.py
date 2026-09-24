"""PDF 提取与解析单元测试（纯函数，无需 OCR 模型）"""

import unittest
from dataclasses import dataclass
from pathlib import Path

from modules.cmm_filler.core.parse_measurements import (
    cluster_ocr_rows,
    normalize_tolerances,
    parse_from_text_lines,
    parse_from_ocr_boxes,
)
from modules.cmm_filler.core.pdf_extract import TEXT_CHARS_THRESHOLD, pdf_to_images
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

    def test_infer_two_orphans_two_ax_blocks(self):
        """缺口 4、5 各自对应一块 AX，不得共用第一块。"""
        boxes = [
            OCRBox('CC_3', 10, 10, 60, 30),
            OCRBox('1.000', 100, 10, 150, 30),
            OCRBox('0.010', 160, 10, 210, 30),
            OCRBox('-0.010', 220, 10, 270, 30),
            OCRBox('1.001', 280, 10, 330, 30),
            OCRBox('AX', 10, 50, 40, 70),
            OCRBox('NOMINAL', 50, 50, 120, 70),
            OCRBox('MEAS', 250, 50, 300, 70),
            OCRBox('A', 10, 80, 30, 100),
            OCRBox('90.000', 50, 80, 120, 100),
            OCRBox('0.010', 130, 80, 180, 100),
            OCRBox('-0.010', 190, 80, 240, 100),
            OCRBox('90.111', 250, 80, 310, 100),
            OCRBox('AX', 10, 130, 40, 150),
            OCRBox('NOMINAL', 50, 130, 120, 150),
            OCRBox('MEAS', 250, 130, 300, 150),
            OCRBox('A', 10, 160, 30, 180),
            OCRBox('45.000', 50, 160, 120, 180),
            OCRBox('0.010', 130, 160, 180, 180),
            OCRBox('-0.010', 190, 160, 240, 180),
            OCRBox('45.222', 250, 160, 310, 180),
            OCRBox('CC_6', 10, 200, 60, 220),
            OCRBox('2.000', 100, 200, 150, 220),
            OCRBox('0.010', 160, 200, 210, 220),
            OCRBox('-0.010', 220, 200, 270, 220),
            OCRBox('2.003', 280, 200, 330, 220),
        ]
        data = parse_from_ocr_boxes(boxes, ['CC'], set(), _is_ng, _month_cn_to_num)
        nums = {m['num']: m for m in data['measurements']}
        self.assertAlmostEqual(nums[3]['measured'], 1.001)
        self.assertAlmostEqual(nums[4]['measured'], 90.111)
        self.assertAlmostEqual(nums[5]['measured'], 45.222)
        self.assertAlmostEqual(nums[6]['measured'], 2.003)

    def test_angle_prefers_a_when_d_also_present(self):
        boxes = [
            OCRBox('CC_8-角度平面1至平面2', 10, 100, 240, 120),
            OCRBox('AX', 10, 130, 40, 150),
            OCRBox('NOMINAL', 50, 130, 120, 150),
            OCRBox('MEAS', 250, 130, 300, 150),
            OCRBox('A', 10, 160, 30, 180),
            OCRBox('90.000', 50, 160, 120, 180),
            OCRBox('0.010', 130, 160, 180, 180),
            OCRBox('-0.010', 190, 160, 240, 180),
            OCRBox('89.999', 250, 160, 310, 180),
            OCRBox('D', 10, 190, 30, 210),
            OCRBox('10.000', 50, 190, 120, 210),
            OCRBox('0.010', 130, 190, 180, 210),
            OCRBox('-0.010', 190, 190, 240, 210),
            OCRBox('10.192', 250, 190, 310, 210),
        ]
        data = parse_from_ocr_boxes(boxes, ['CC'], set(), _is_ng, _month_cn_to_num)
        m = data['measurements'][0]
        self.assertAlmostEqual(m['measured'], 89.999)

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


class TestPdfToImagesCacheName(unittest.TestCase):
    """缓存图片名必须由全部渲染输入决定。

    缓存 key 是图片**路径**的 MD5（filler._cache_key），所以两个不同输入只要渲染出
    同一个文件名，第二个就会读到第一个的 OCR 结果。
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._tmp = Path(tempfile.mkdtemp())
        cls._cache = cls._tmp / 'cache'

    @staticmethod
    def _make_pdf(path: Path) -> None:
        import fitz
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open()
        doc.new_page()
        doc.save(str(path))
        doc.close()

    def test_same_stem_in_different_dirs_gets_different_image(self):
        """同名不同目录的 PDF 必须落到不同缓存图片（旧实现只看 stem）。"""
        a = self._tmp / 'a' / '001.pdf'
        b = self._tmp / 'b' / '001.pdf'
        self._make_pdf(a)
        self._make_pdf(b)

        img_a = pdf_to_images(a, self._cache)[0]
        img_b = pdf_to_images(b, self._cache)[0]

        self.assertNotEqual(
            img_a, img_b,
            '同名不同目录的 PDF 渲染到了同一张缓存图片 → 第二个 PDF 会复用第一个的 OCR 结果',
        )

    def test_different_roi_gets_different_image(self):
        """ROI 值必须进文件名：旧实现只加布尔 `_roi`，改 ROI 后仍命中旧 OCR。"""
        p = self._tmp / 'roi.pdf'
        self._make_pdf(p)

        full = pdf_to_images(p, self._cache)[0]
        roi_20 = pdf_to_images(p, self._cache, roi={'top': 0.2})[0]
        roi_30 = pdf_to_images(p, self._cache, roi={'top': 0.3})[0]

        self.assertNotEqual(full, roi_20, '有 ROI 与无 ROI 必须分开缓存')
        self.assertNotEqual(roi_20, roi_30, '不同 ROI 值必须分开缓存')

    def test_filename_keeps_stem_readable(self):
        """文件名里必须保留 stem —— 日志与人工排查都靠它认图。"""
        p = self._tmp / 'WF-2026-08-27-001.pdf'
        self._make_pdf(p)

        img = pdf_to_images(p, self._cache)[0]

        self.assertIn('WF-2026-08-27-001', Path(img).name)


if __name__ == '__main__':
    unittest.main()
