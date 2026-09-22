"""Report Profile 与 ROI 单元测试"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.cmm_filler.core.report_profile import (
    load_profile, list_profiles, roi_cache_suffix,
    merge_item_prefixes, parse_prefix_text, user_profiles_dir,
)
from modules.cmm_filler.core.pdf_extract import _normalize_roi, _page_clip_rect
from modules.cmm_filler.core.filler import CMMReportFiller


class TestReportProfile(unittest.TestCase):
    def test_list_profiles_has_default(self):
        profiles = list_profiles()
        names = [p['name'] for p in profiles]
        self.assertIn('default', names)
        self.assertIn('hexagon_pc_dmis', names)

    def test_load_default_profile(self):
        p = load_profile('default')
        self.assertIn('FAI', p['item_prefixes'])
        self.assertEqual(p['ocr_roi']['top'], 0)

    def test_load_hexagon_profile(self):
        p = load_profile('hexagon_pc_dmis')
        self.assertIn('DIM', p['item_prefixes'])
        self.assertGreater(p['ocr_roi']['top'], 0)

    def test_parse_prefix_text(self):
        self.assertEqual(parse_prefix_text('检具, SIZE;GD&T'), ['检具', 'SIZE', 'GD&T'])

    def test_merge_item_prefixes_dedup_and_longer_first(self):
        merged = merge_item_prefixes(['FAI', 'FAIL'], ['fail', '检具'])
        self.assertEqual(merged[0], 'FAIL')
        self.assertIn('FAI', merged)
        self.assertIn('检具', merged)

    def test_user_profile_overrides_builtin(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_dir = Path(tmp)
            custom = {
                'name': 'default',
                'label': '用户自定义默认',
                'item_prefixes': ['检具', 'SIZE'],
            }
            (user_dir / 'default.json').write_text(
                json.dumps(custom, ensure_ascii=False), encoding='utf-8',
            )
            with patch('modules.cmm_filler.core.report_profile.user_profiles_dir', return_value=user_dir):
                p = load_profile('default')
            self.assertEqual(p['label'], '用户自定义默认')
            self.assertEqual(p['item_prefixes'], ['检具', 'SIZE'])

    def test_filler_merges_extra_prefixes(self):
        settings = {'custom_item_prefixes': '检具, SIZE'}
        profile = {'item_prefixes': ['FAI', 'DIM'], 'skip_lines': [], 'ocr_roi': {}, 'confidence_threshold': 0.85}
        with patch('modules.cmm_filler.core.filler.load_settings', return_value=settings):
            with patch('modules.cmm_filler.core.filler.load_profile', return_value=profile):
                with patch.object(CMMReportFiller, '_load_cache', return_value={}):
                    with patch.object(CMMReportFiller, '_cleanup_cache'):
                        with patch.object(CMMReportFiller, '_load_config', return_value={}):
                            with patch.object(CMMReportFiller, '_smart_config', return_value={}):
                                filler = CMMReportFiller('dummy.xlsx')
        self.assertIn('检具', filler.item_prefixes)
        self.assertIn('FAI', filler.item_prefixes)

    def test_roi_cache_suffix(self):
        s = roi_cache_suffix({'top': 0.18, 'left': 0, 'bottom': 0.02, 'right': 0})
        self.assertIn('0.18', s)


class TestROINormalize(unittest.TestCase):
    def test_clamps_values(self):
        roi = _normalize_roi({'top': -0.5, 'left': 0, 'bottom': 2, 'right': 0})
        self.assertEqual(roi['top'], 0)
        self.assertEqual(roi['bottom'], 1.0)

    def test_page_clip_rect(self):
        class FakeRect:
            width = 100
            height = 200

        class FakePage:
            rect = FakeRect()

        clip = _page_clip_rect(FakePage(), {'top': 0.1, 'left': 0, 'bottom': 0.1, 'right': 0})
        self.assertAlmostEqual(clip.x0, 0)
        self.assertAlmostEqual(clip.y0, 20)
        self.assertAlmostEqual(clip.y1, 180)


if __name__ == '__main__':
    unittest.main()
