"""固定 A4 分页版式单元测试"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from openpyxl import Workbook
import openpyxl

from modules.cmm_filler.core.fixed_page_layout import (
    build_sheet_row_index,
    load_axis_preferences_from_template,
    measure_lookup_keys,
    resolve_measure_location,
    serial_cell_keys,
)
from modules.cmm_filler.core.filler import CMMReportFiller, _looks_like_serial


def _bind_real(cls, template_path, config):
    """构造只绑定「版式推断」相关真实方法的 CMMReportFiller 替身。

    刻意不走 __init__：那会读本机 data/config 下的真实配置并加载 OCR 引擎，
    让测试依赖环境状态。
    """
    filler = MagicMock(spec=cls)
    filler.config = config
    filler.template_path = str(template_path)
    filler._sheet_name_cache = 'A'
    for name in (
        '_get_sheet_name',
        '_get_data_start_row',
        '_get_column_letter',
        '_get_template_layout_config',
        '_get_template_sheet_names',
        '_get_max_data_row',
    ):
        setattr(filler, name, getattr(cls, name).__get__(filler, cls))
    return filler


class TestFixedPageLayout(unittest.TestCase):
    def test_serial_cell_keys_decimal_sub(self):
        self.assertIn('34.1', serial_cell_keys(34.1))
        self.assertIn('34-1', serial_cell_keys(34.1))

    def test_measure_lookup_keys_hyphen_sub(self):
        keys = measure_lookup_keys({
            'num': 34, 'sub': '1', 'sub_sep': '-', 'item_key': '34-1',
        })
        self.assertIn('34.1', keys)
        self.assertIn('34-1', keys)

    def test_build_sheet_row_index(self):
        wb = Workbook()
        ws = wb.active
        ws.title = 'A'
        ws['A6'] = 1
        ws['A7'] = 34.1
        ws['A8'] = 34.2
        index = build_sheet_row_index(wb, ['A'], serial_col=1, data_start_row=6, max_data_row=10)
        self.assertEqual(index['1'], ('A', 6))
        self.assertEqual(index['34.1'], ('A', 7))
        self.assertEqual(resolve_measure_location(index, {
            'num': 34, 'sub': '2', 'sub_sep': '-', 'item_key': '34-2',
        }), ('A', 8))

    def test_main_sample_count_from_config(self):
        filler = MagicMock(spec=CMMReportFiller)
        filler.config = {'main_sample_count': 3}
        self.assertEqual(CMMReportFiller._get_main_sample_count(filler), 3)

    def test_batch_output_filename(self):
        self.assertEqual(
            CMMReportFiller._batch_output_filename('2026-08-28', 1, 6, multi_batch=False),
            '2026-08-28_项目汇总.xlsx',
        )
        self.assertEqual(
            CMMReportFiller._batch_output_filename('2026-08-28', 1, 6, multi_batch=True),
            '2026-08-28_项目汇总_样品1-6.xlsx',
        )
        self.assertEqual(
            CMMReportFiller._batch_output_filename('2026-08-28', 7, 10, multi_batch=True),
            '2026-08-28_项目汇总_样品7-10.xlsx',
        )

    def test_prepare_sample_batches_splits_when_over_capacity(self):
        filler = MagicMock(spec=CMMReportFiller)
        filler._overflow_samples_enabled = lambda: False
        filler._chunk_samples = CMMReportFiller._chunk_samples.__get__(filler, CMMReportFiller)
        items = [{'path': i} for i in range(10)]
        batches = CMMReportFiller._prepare_sample_batches(filler, items, 6)
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 6)
        self.assertEqual(len(batches[1]), 4)

    def test_renumber_batch_items(self):
        batch = [{'stem': 'a', 'sample_num': 7}, {'stem': 'b', 'sample_num': 8}]
        out = CMMReportFiller._renumber_batch_items(batch)
        self.assertEqual(out[0]['sample_num'], 1)
        self.assertEqual(out[1]['sample_num'], 2)
        self.assertEqual(out[0]['stem'], 'a')

    def test_load_axis_preferences_from_workbook(self):
        wb = Workbook()
        ws = wb.active
        ws.title = 'A'
        ws['A6'] = 15
        ws['G6'] = 'X'
        ws['A7'] = 16
        ws['G7'] = 'D'
        path = self._tmpdir / 'axis_tpl.xlsx'
        wb.save(path)
        wb.close()
        prefs = load_axis_preferences_from_template(
            str(path), ['A'], serial_col=1, axis_col=7,
            data_start_row=6, max_data_row=10,
        )
        self.assertEqual(prefs.get('15'), 'X')
        self.assertEqual(prefs.get('16'), 'D')

    # ── 数据区下界推断（回归：只扫规格列会把空白报告表截断）────────────────

    def test_looks_like_serial_rejects_header_text(self):
        """序号列里的说明性文字不能被当成序号 —— 否则锚点会被拉到表头行。"""
        for good in (1, 34.1, '1', '34.1', '1-1', '1_1', 2.5):
            self.assertTrue(_looks_like_serial(good), good)
        for bad in (None, True, '', '   ', '图纸版本:', '图面标准', 'ISO 1101'):
            self.assertFalse(_looks_like_serial(bad), bad)

    def test_max_data_row_spans_serial_column_not_spec_column(self):
        """规格列只有表头时，锚点必须靠序号列兜住整个数据区。

        旧实现只扫规格列：空白报告表的规格列只有表头 → max_data_row 落在
        「表头行 + 50」，序号 51+ 的行根本不进 row_index（规格/公差静默跳过）。
        """
        path = self._tmpdir / 'blank_form.xlsx'
        wb = Workbook()
        ws = wb.active
        ws.title = 'A'
        ws['A6'] = '图纸版本:'      # 说明性文字：不能被当成序号
        ws['B9'] = '规格'           # 规格列唯一的非空单元格（表头）
        for i in range(1, 101):
            ws.cell(row=9 + i, column=1, value=i)   # 序号 1..100 → 第 10..109 行
        wb.save(path)
        wb.close()

        filler = _bind_real(CMMReportFiller, path, {})
        max_row = filler._get_max_data_row()

        self.assertGreaterEqual(max_row, 109, 'max_data_row 必须覆盖到最后一个序号行')
        index = build_sheet_row_index(
            openpyxl.load_workbook(str(path)), ['A'],
            serial_col=1, data_start_row=6, max_data_row=max_row,
        )
        self.assertEqual(index['1'], ('A', 10))
        self.assertEqual(index['100'], ('A', 109), '序号 100 必须被索引到')

    def test_shipped_template_covers_all_serials(self):
        """随包模板（真实回归目标）：修复前 模板2 只索引到序号 50。

        期望值从模板自身推导，避免模板更新后测试变成假失败。
        """
        tpl = Path(__file__).resolve().parent.parent / 'templates' / '模板2.xlsx'
        filler = _bind_real(CMMReportFiller, tpl, {})
        max_row = filler._get_max_data_row()

        wb = openpyxl.load_workbook(str(tpl))
        ws = wb[filler._get_template_sheet_names()[0]]
        serial_rows = [
            r for r in range(1, ws.max_row + 1)
            if _looks_like_serial(ws.cell(row=r, column=1).value)
        ]
        wb.close()

        self.assertTrue(serial_rows, '模板2 的序号列应当有序号')
        self.assertGreaterEqual(
            max_row, max(serial_rows),
            f'max_data_row({max_row}) 未覆盖最后一个序号行({max(serial_rows)})',
        )

    def test_max_data_row_respects_explicit_config(self):
        """显式配置的短路优先级不能变。"""
        filler = _bind_real(
            CMMReportFiller, self._tmpdir / 'missing.xlsx',
            {'fixed_pages': {'max_data_row': 42}},
        )
        self.assertEqual(filler._get_max_data_row(), 42)

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._tmpdir = Path(tempfile.mkdtemp())


if __name__ == '__main__':
    unittest.main()
