"""模板向导 _save_config 健壮性测试（P3-12）。

现象：用户首启向导保存时，_load_existing_config() 命中 JSON 里的空值/None，
直接 int('') 报 ValueError，整份配置无法保存（2026-09-24 13:54 真机 traceback）。

本测试同时覆盖 _safe_int 单元与 _save_config 集成：
- 空串 → 走默认值
- None → 走默认值
- 非数字 → 走默认值
- 合法 "0" → 不能误判为"空"而回退（0 是合法值）
- 合法整数 → 透传
- 首尾空白 → 透传（strip 后再 parse）
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.cmm_filler.template_wizard import TemplateWizard

# _safe_int 在 template_wizard.py 里是本次新增的辅助函数；
# 不在模块顶层 import，避免"修复前整文件无法 collect"——我们要验证的是
# _save_config 在原始 int() 路径上会真抛 ValueError，不是导入失败。
try:
    from modules.cmm_filler.template_wizard import _safe_int
    _HAS_SAFE_INT = True
except ImportError:
    _HAS_SAFE_INT = False


class _FakeVar:
    """模拟 tk.StringVar，仅需 .get() 接口。"""
    def __init__(self, v):
        self.v = v

    def get(self):
        return self.v


class TestSafeInt(unittest.TestCase):
    """_safe_int 是 _save_config 的兜底层；先单元覆盖全部边界。"""

    @unittest.skipUnless(
        _HAS_SAFE_INT, '_safe_int 不存在 = 修复未到位；跳过此组'
    )

    def test_empty_string_returns_default(self):
        self.assertEqual(_safe_int('', 6), 6)
        self.assertEqual(_safe_int(_FakeVar(''), 6), 6)

    def test_none_returns_default(self):
        self.assertEqual(_safe_int(None, 5), 5)
        self.assertEqual(_safe_int(_FakeVar(None), 5), 5)

    def test_whitespace_only_returns_default(self):
        self.assertEqual(_safe_int('   ', 6), 6)

    def test_non_numeric_returns_default(self):
        self.assertEqual(_safe_int('abc', 6), 6)
        self.assertEqual(_safe_int('6.5', 6), 6)  # 非整数应走默认（向导不接浮点）

    def test_zero_is_not_misread_as_empty(self):
        """关键边界：0 是合法值，必须透传，不能回退默认。"""
        self.assertEqual(_safe_int('0', 6), 0)
        self.assertEqual(_safe_int(0, 6), 0)
        self.assertEqual(_safe_int(_FakeVar('0'), 6), 0)

    def test_valid_integer_passes_through(self):
        self.assertEqual(_safe_int('5', 6), 5)
        self.assertEqual(_safe_int(5, 6), 5)

    def test_whitespace_padded_value_strips(self):
        self.assertEqual(_safe_int('  3  ', 6), 3)


class TestSaveConfigDefaults(unittest.TestCase):
    """_save_config 集成测试：空值场景下不崩 + 落默认值 + 配置文件 JSON 写入正确。"""

    def _make_wizard(self, **overrides):
        """绕开 Tk 实例化（CI 无显示），构造一个只装了 StringVar 的最小 wizard。"""
        wizard = TemplateWizard.__new__(TemplateWizard)

        defaults = {
            'template_path': r'D:\templates\tpl.xlsx',
            'sheet_name': 'FAI',
            'data_start_row': '6',
            'sample_row': '5',
            'main_sample_count': '3',
        }
        defaults.update(overrides)

        wizard.file_var = _FakeVar(defaults['template_path'])
        wizard.sheet_var = _FakeVar(defaults['sheet_name'])
        wizard.data_start_var = _FakeVar(defaults['data_start_row'])
        wizard.sample_row_var = _FakeVar(defaults['sample_row'])
        wizard.main_count_var = _FakeVar(defaults['main_sample_count'])
        wizard.column_vars = {'serial': _FakeVar('A')}
        wizard.sample_vars = {}
        wizard.field_location_vars = {}
        wizard.root = MagicMock()  # _save_config 末尾会 self.root.destroy()
        return wizard

    def test_save_with_empty_int_vars_uses_defaults(self):
        """复现 13:54 真机崩溃：data_start_row/sample_row 为空时不能抛。"""
        wizard = self._make_wizard(data_start_row='', sample_row='')

        captured_config = {}

        def fake_save(path, config):
            captured_config.update(config)

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / 'template_config.json'
            with patch(
                'modules.cmm_filler.template_wizard.CONFIG_PATH', str(config_path)
            ), patch(
                'modules.cmm_filler.template_wizard.save_settings_json_atomic',
                side_effect=fake_save,
            ), patch(
                'modules.cmm_filler.template_wizard.messagebox.showinfo'
            ):
                wizard._save_config()

        self.assertEqual(captured_config['data_start_row'], 6)
        self.assertEqual(captured_config['sample_row'], 5)

    def test_save_with_zero_data_start_row_passes_through(self):
        """0 仍是合法值 —— 不能因为"看起来空"就被回退到默认 6。"""
        wizard = self._make_wizard(data_start_row='0', sample_row='0')

        captured_config = {}

        def fake_save(path, config):
            captured_config.update(config)

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / 'template_config.json'
            with patch(
                'modules.cmm_filler.template_wizard.CONFIG_PATH', str(config_path)
            ), patch(
                'modules.cmm_filler.template_wizard.save_settings_json_atomic',
                side_effect=fake_save,
            ), patch(
                'modules.cmm_filler.template_wizard.messagebox.showinfo'
            ):
                wizard._save_config()

        self.assertEqual(captured_config['data_start_row'], 0)
        self.assertEqual(captured_config['sample_row'], 0)

    def test_save_with_empty_sheet_uses_fai_default(self):
        wizard = self._make_wizard(sheet_name='')

        captured_config = {}

        def fake_save(path, config):
            captured_config.update(config)

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / 'template_config.json'
            with patch(
                'modules.cmm_filler.template_wizard.CONFIG_PATH', str(config_path)
            ), patch(
                'modules.cmm_filler.template_wizard.save_settings_json_atomic',
                side_effect=fake_save,
            ), patch(
                'modules.cmm_filler.template_wizard.messagebox.showinfo'
            ):
                wizard._save_config()

        self.assertEqual(captured_config['sheet_name'], 'FAI')

    def test_save_persists_json_to_disk(self):
        """端到端：返回值真的写到磁盘 JSON。"""
        wizard = self._make_wizard(data_start_row='', sample_row='')

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / 'template_config.json'
            with patch(
                'modules.cmm_filler.template_wizard.CONFIG_PATH', str(config_path)
            ), patch(
                'modules.cmm_filler.template_wizard.messagebox.showinfo'
            ):
                wizard._save_config()

            self.assertTrue(config_path.exists())
            with config_path.open('r', encoding='utf-8') as f:
                saved = json.load(f)
            self.assertEqual(saved['data_start_row'], 6)
            self.assertEqual(saved['sample_row'], 5)


if __name__ == '__main__':
    unittest.main()