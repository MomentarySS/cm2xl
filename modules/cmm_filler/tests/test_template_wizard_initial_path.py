"""B 方案 + P3-10 测试：模板向导接收 initial_template_path，主 GUI 展示摘要。

回归覆盖：
- TemplateWizard.__init__ 接收 initial_template_path 并缓存
- gui._format_template_label 把路径渲染成 basename，空路径返回 '(未配置)'
"""

import unittest
from unittest.mock import MagicMock, patch

from modules.cmm_filler.template_wizard import TemplateWizard


class TestWizardInitialPath(unittest.TestCase):
    """P3-10：TemplateWizard 必须能接收主 GUI 传入的初始模板路径。"""

    def _make_wizard_without_tk(self, initial=None):
        """绕开 _build_ui（避免拉起 Tk），手工塞最小属性后验证 _initial_template_path。"""
        mock_root = MagicMock()
        with patch('tkinter.Tk', return_value=mock_root), \
             patch('tkinter.Toplevel', return_value=mock_root), \
             patch.object(TemplateWizard, '_build_ui'), \
             patch.object(TemplateWizard, '_load_existing_config'):
            wizard = TemplateWizard(parent=None, initial_template_path=initial)
        return wizard

    def test_no_initial_path_defaults_to_empty(self):
        """不传参数时退回空串（CLI 场景，保持旧行为）。"""
        wizard = self._make_wizard_without_tk()
        self.assertEqual(wizard._initial_template_path, '')

    def test_explicit_initial_path_is_cached(self):
        """主 GUI 显式传入时，原样缓存到 _initial_template_path。"""
        wizard = self._make_wizard_without_tk(initial=r'D:\templates\foo.xlsx')
        self.assertEqual(wizard._initial_template_path, r'D:\templates\foo.xlsx')

    def test_explicit_empty_string_is_distinguished_from_none(self):
        """传 '' 与不传参数行为一致（都是空串），便于上层判定。"""
        wizard_empty = self._make_wizard_without_tk(initial='')
        wizard_none = self._make_wizard_without_tk(initial=None)
        self.assertEqual(wizard_empty._initial_template_path, '')
        self.assertEqual(wizard_none._initial_template_path, '')


class TestFormatTemplateLabel(unittest.TestCase):
    """B 方案：主页面的 Label 把路径渲染成 basename。"""

    def _format(self, path):
        """直接调用 _format_template_label 静态化（实际是 instance method）。"""
        # 不实例化 GUI（需要 ctk + Tk），仅复用纯字符串逻辑
        from modules.cmm_filler.gui import CMMFillerGUI
        # 构造一个不带 GUI 的实例（绕过 __init__）
        gui = CMMFillerGUI.__new__(CMMFillerGUI)
        gui.template_var = MagicMock()
        gui.template_var.get.return_value = path
        return gui._format_template_label()

    def test_empty_path_shows_unconfigured(self):
        self.assertEqual(self._format(''), '(未配置)')
        self.assertEqual(self._format('   '), '(未配置)')

    def test_short_path_shows_basename(self):
        self.assertEqual(
            self._format(r'D:\templates\检测报告样板-2026.xlsx'),
            '检测报告样板-2026.xlsx',
        )

    def test_unix_path_basename(self):
        self.assertEqual(
            self._format('/home/user/templates/foo.xlsx'),
            'foo.xlsx',
        )

    def test_path_with_directory_components(self):
        """深嵌套路径仍只取 basename。"""
        self.assertEqual(
            self._format(r'D:\AI\work\cm2xl\modules\cmm_filler\templates\模板2.xlsx'),
            '模板2.xlsx',
        )


if __name__ == '__main__':
    unittest.main()