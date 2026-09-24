"""模板向导 Tk 回调异常处理（P3-13）。

现象：CTk 5.x 在 widget 被销毁但 mouse-wheel 事件仍在飞时，
_check_if_valid_scroll 抛 'str' object has no attribute 'master'，
traceback 刷屏 600+ 行但不影响功能。

TemplateWizard._silence_destroyed_widget_callback 必须**只**静音该特定路径，
其它异常照常输出（不能掩盖真问题）。
"""

import io
import sys
import traceback
import unittest
from unittest.mock import patch

from modules.cmm_filler.template_wizard import TemplateWizard


class TestSilenceCallback(unittest.TestCase):
    """_silence_destroyed_widget_callback：精准放行 vs 默认行为。"""

    @staticmethod
    def _raise_in_pretend_ctk_frame():
        """在名字里带 ctk_scrollable_frame 的函数里抛 AttributeError。"""
        def pretend_ctk_scrollable_frame_callback():
            x = 'a string'
            return x.master  # AttributeError: 'str' has no attribute 'master'
        try:
            pretend_ctk_scrollable_frame_callback()
        except AttributeError:
            return sys.exc_info()

    @staticmethod
    def _raise_in_user_frame():
        try:
            None.split()
        except AttributeError:
            return sys.exc_info()

    @staticmethod
    def _raise_runtime_error():
        try:
            raise RuntimeError('something real broke')
        except RuntimeError:
            return sys.exc_info()

    def test_ctk_master_attribute_error_is_silenced(self):
        """CTk 滚轮的特定 AttributeError 不打 stderr。"""
        exc, val, tb = self._raise_in_pretend_ctk_frame()

        buf = io.StringIO()
        with patch.object(sys, 'stderr', buf):
            TemplateWizard._silence_destroyed_widget_callback(exc, val, tb)
        self.assertEqual(buf.getvalue(), '')

    def test_unrelated_attribute_error_still_prints(self):
        """非 CTk 帧里的 AttributeError 必须照常打 stderr（不能全静音）。"""
        exc, val, tb = self._raise_in_user_frame()

        buf = io.StringIO()
        with patch.object(sys, 'stderr', buf):
            TemplateWizard._silence_destroyed_widget_callback(exc, val, tb)
        self.assertNotEqual(buf.getvalue(), '')

    def test_non_attribute_error_still_prints(self):
        """非 AttributeError 一律照常打 stderr。"""
        exc, val, tb = self._raise_runtime_error()

        buf = io.StringIO()
        with patch.object(sys, 'stderr', buf):
            TemplateWizard._silence_destroyed_widget_callback(exc, val, tb)
        self.assertNotEqual(buf.getvalue(), '')


if __name__ == '__main__':
    unittest.main()