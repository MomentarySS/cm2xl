"""
CMM 报告自动填充工具 v10
匹配用户修改后的模板结构：
- Sheet A: 1#-5# 主样品（001-005）
- Sheet B: 6#+ 溢出样品（006-010），基于原始模板创建，保持格式
- 忽略误操作文件（如 003-1.PDF）
- OCR 失败自动重试
- 保存时文件锁检测 + 自动备份
- 中间结果预览（GUI 模式）
"""
import logging
import os
import sys
import time
import multiprocessing
multiprocessing.freeze_support()

import re
import json
from pathlib import Path
from collections import defaultdict

import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

from ..ocr.engine import OCREngine, PaddleOCREngine, OCRBox
from .pdf_extract import detect_pdf_type, extract_text_lines, pdf_to_images
from .parse_measurements import (
    parse_from_text_lines, parse_from_ocr_boxes,
    measure_dict_key, measure_dict_label, measure_dict_row_index,
    _measurement_sort_key,
)
from .report_profile import load_profile, roi_cache_suffix, merge_item_prefixes, parse_prefix_text
from .fixed_page_layout import (
    build_sheet_row_index, resolve_measure_location,
    load_axis_preferences_from_template,
)
from .sub_item_conflict import (
    SKIP_SUB_ITEM, WORST_NG_SUB_ITEM,
    build_parent_auto_picks, detect_parent_row_conflicts,
    merge_parent_picks, resolve_measure_write_location,
    resolve_parent_picks,
)
from .ng_analysis import collect_ng_stats, export_ng_workbook, format_ng_summary_text
from utils.file_io import glob_pdfs
from utils.paths import paths
from utils.settings import save_settings_json_atomic, stamp_settings

# ── 日志 ──────────────────────────────────────────────
logger = logging.getLogger('CMMFiller')


class _GuiHandler(logging.Handler):
    """将日志输出同步到 GUI 日志区的 Handler"""
    def __init__(self, gui_instance):
        super().__init__()
        self._gui = gui_instance
        self.setFormatter(logging.Formatter('%(message)s'))

    def emit(self, record):
        msg = self.format(record)
        if self._gui:
            self._gui.root.after(0, lambda m=msg: self._gui._log(m))


def set_gui_logger(gui_instance):
    """将日志输出也同步到 GUI 日志区（自动清理旧 handler，避免重复）"""
    to_remove = [h for h in logger.handlers if isinstance(h, _GuiHandler)]
    for h in to_remove:
        logger.removeHandler(h)
    h = _GuiHandler(gui_instance)
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)

# ── 路径 ──────────────────────────────────────────────
def _resource_path(*parts: str) -> Path:
    """定位打包内置或开发环境的资源文件"""
    rel = Path(*parts)
    if getattr(sys, 'frozen', False):
        for root in (BASE_DIR / '_internal', Path(getattr(sys, '_MEIPASS', '')), BASE_DIR):
            if root and (candidate := root / rel).exists():
                return candidate
    return BASE_DIR / rel


def _get_config_path():
    """优先 %APPDATA% 配置，回退项目目录配置"""
    appdata_config = Path(APP_DATA_DIR) / 'template_config.json'
    project_config = BASE_DIR / 'template_config.json'
    if appdata_config.exists():
        return str(appdata_config)
    if project_config.exists():
        return str(project_config)
    return str(appdata_config)  # 用于首次保存

def _get_base_dir() -> Path:
    """开发模式用源码目录，打包后用 exe 所在目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()

APP_DATA_DIR = str(paths.config_dir / 'cmm_filler')  # 统一到 {data}/config/cmm_filler（ARCH 3.9）
Path(APP_DATA_DIR).mkdir(parents=True, exist_ok=True)

CACHE_DIR = paths.cache_dir
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE_PATH = str(Path(__file__).resolve().parent.parent / 'templates' / '模板2.xlsx')
if getattr(sys, 'frozen', False):
    PDF_FOLDER = ''
    OUTPUT_FOLDER = str(Path(APP_DATA_DIR) / 'outputs')
    Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)
else:
    PDF_FOLDER = str(BASE_DIR / 'samples')
    OUTPUT_FOLDER = str(BASE_DIR / 'outputs')
DPI = 300
CACHE_PATH = str(CACHE_DIR / 'ocr_cache.json')
CONFIG_PATH = str(Path(APP_DATA_DIR) / 'template_config.json')
SETTINGS_PATH = str(Path(APP_DATA_DIR) / 'settings.json')
LOG_PATH = str(Path(APP_DATA_DIR) / 'run.log')


def load_settings() -> dict:
    """读取 GUI 路径记忆"""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(data: dict):
    """保存 GUI 路径记忆（原子写 + schema 版本戳，避免中断留下半截文件）

    必须盖章：文件里没有 _version 时，下次启动会被当成 0.0.0 走一遍迁移链，
    每次弹「配置已升级」并生成 .bak。
    """
    try:
        Path(APP_DATA_DIR).mkdir(parents=True, exist_ok=True)
        save_settings_json_atomic(
            Path(SETTINGS_PATH), stamp_settings(data, 'cmm_filler')
        )
    except OSError as e:
        logger.warning(f'保存设置失败: {e}')


def _write_cell(ws, cell_coord, value):
    """写入单元格，自动处理合并单元格（写入左上角）"""
    cell = ws[cell_coord]
    if isinstance(cell, MergedCell):
        for merged_range in ws.merged_cells.ranges:
            if cell.coordinate in merged_range:
                top_left = ws.cell(row=merged_range.min_row, column=merged_range.min_col)
                top_left.value = value
                return
    cell.value = value


# 可配置的测量项前缀列表，遇到新前缀直接加这里
ITEM_PREFIXES = ['FAI', 'FAL', 'FAIL', '尺寸', 'CC', 'DIM', 'CHECK']

# OCR 行跳过列表：纯标注性文字，不含测量数值
OCR_SKIP_LINES = {'毫米', 'mm', '中', 'A/2', '1/1'}

# 默认列映射（向后兼容）
DEFAULT_COLUMNS = {
    'serial': 'A',
    'spec': 'B',
    'upper_tol': 'C',
    'lower_tol': 'D',
    'upper_limit': 'E',
    'lower_limit': 'F',
    'instrument': 'G',
}
DEFAULT_SAMPLE_COLS = {'1#': 'H', '2#': 'I', '3#': 'J', '4#': 'K', '5#': 'L'}
DEFAULT_DATA_START_ROW = 6
DEFAULT_SAMPLE_ROW = 5
DEFAULT_MAIN_SAMPLE_COUNT = 5

# 默认字段写入位置（向后兼容）
DEFAULT_FIELD_LOCATIONS = {
    'part_name': 'A3',
    'date': 'L2',
}

# 汇总导出表头（CMM Dimensions Report 汇总样式；坐标系/补偿在源 PDF 中无数据，保留空列）
SUMMARY_HEADERS = ['序号', '注释', '坐标系', '补偿', '理论值', '实际值', '误差', '下公差', '上公差', '趋势']


def _safe_sheet_title(stem, used_titles):
    """把 PDF stem 转成合法 sheet 名：替换非法字符、截断 31 字符、重名加后缀"""
    title = re.sub(r'[\[\]:*?/\\]', '_', stem).strip() or 'Sheet'
    title = title[:31]
    base = title
    n = 2
    while title.lower() in used_titles:
        suffix = f'_{n}'
        title = base[:31 - len(suffix)] + suffix
        n += 1
    used_titles.add(title.lower())
    return title


def month_cn_to_num(month_cn: str) -> str:
    mapping = {'十一': '11', '十二': '12', '一': '01', '二': '02', '三': '03', '四': '04',
               '五': '05', '六': '06', '七': '07', '八': '08', '九': '09', '十': '10'}
    for k, v in mapping.items():
        if k in month_cn:
            return v
    return month_cn


class CMMReportFiller:
    def __init__(self, template_path, dpi=300, ocr_engine=None,
                 report_profile=None, ocr_roi=None, custom_item_prefixes=None):
        self.template_path = template_path
        self.dpi = dpi
        self.ocr = ocr_engine or PaddleOCREngine()
        self.cache = self._load_cache()
        self._cleanup_cache()

        # 取消检查回调（由 GUI 注入，如 CancellableWorker.is_cancelled）：
        # 循环内检测到 True 时提前退出，返回结构带 cancelled=True
        self.cancel_check = None

        # 报告 Profile（前缀、ROI、置信度阈值）
        settings = load_settings()
        profile_name = report_profile or settings.get('report_profile', 'default')
        self.profile = load_profile(profile_name)
        extra_prefixes = self._resolve_custom_prefixes(settings, custom_item_prefixes)
        self.item_prefixes = merge_item_prefixes(
            self.profile.get('item_prefixes', ITEM_PREFIXES),
            extra_prefixes,
        )
        self.skip_lines = set(self.profile.get('skip_lines', OCR_SKIP_LINES))
        self.confidence_threshold = float(self.profile.get('confidence_threshold', 0.85))
        # ROI：显式传入 > settings.json > Profile 默认值
        self.ocr_roi = ocr_roi or settings.get('ocr_roi') or self.profile.get('ocr_roi', {})

        # 加载配置后智能合并（自动检测模板结构补全缺失项）
        raw_config = self._load_config()
        self.config = self._smart_config(raw_config)

        self._sheet_name_cache = None  # 缓存 sheet 名，避免重复打开工作簿
        self._axis_prefs_cache: dict[str, str] | None = None

    @staticmethod
    def _resolve_custom_prefixes(settings: dict, override) -> list[str]:
        if override is not None:
            if isinstance(override, list):
                return override
            return parse_prefix_text(str(override))
        raw = settings.get('custom_item_prefixes', [])
        if isinstance(raw, str):
            return parse_prefix_text(raw)
        return list(raw or [])

    def invalidate_sheet_cache(self):
        """模板切换后调用，清除缓存的 sheet 名与轴偏好"""
        self._sheet_name_cache = None
        self._axis_prefs_cache = None

    def _load_config(self):
        path = _get_config_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            logger.debug(f'无配置文件: {path}')
            return {}

    def _auto_detect_template(self):
        """从模板文件中自动检测关键配置项（sheet名、列映射等），
        用于模板切换时自动适配，避免手动重新运行向导。"""
        try:
            wb = openpyxl.load_workbook(self.template_path)
            sheets = wb.sheetnames
            if not sheets:
                return {}

            detected = {}

            # 1. 检测 sheet 名：优先第一个非空 sheet
            sheet_name = sheets[0]
            detected['sheet_name'] = sheet_name
            detected['_sheetnames'] = sheets  # 临时用于后续验证

            # 2. 读取第一行表头，自动匹配列
            ws = wb[sheet_name]
            headers = {}
            for col in range(1, ws.max_column + 1):
                v = ws.cell(row=1, column=col).value
                if v:
                    headers[str(v).strip()] = get_column_letter(col)

            # 3. 根据表头关键词自动匹配列
            col_mapping = {}
            keyword_map = {
                'serial': ['序号', '编号', 'No.', 'No', '#'],
                'spec': ['规格', '名义值', 'Nominal', '名义'],
                'upper_tol': ['上公差', '上偏差', '+', '上'],
                'lower_tol': ['下公差', '下偏差', '-', '下'],
                'upper_limit': ['上限', 'MAX', '最大'],
                'lower_limit': ['下限', 'MIN', '最小'],
                'instrument': ['仪器', '设备', 'Instrument'],
                'axis': ['轴', 'AX', 'Axis', '测量轴'],
            }
            for field, keywords in keyword_map.items():
                for header_name, col_letter in headers.items():
                    if any(kw.lower() in header_name.lower() for kw in keywords):
                        col_mapping[field] = col_letter
                        break

            if col_mapping:
                detected['columns'] = col_mapping

            # 4. 检测样品序号行：找包含 001 或 1# 的行
            for row in range(1, min(ws.max_row + 1, 20)):
                for col in range(1, ws.max_column + 1):
                    v = ws.cell(row=row, column=col).value
                    if v and str(v).strip() in ('001', '1#', 'NO.1', 'No.1', '1'):
                        detected['sample_row'] = row
                        break
                if 'sample_row' in detected:
                    break

            # 5. 检测数据起始行：sample_row + 1 或第一行有数值的行
            if 'sample_row' in detected:
                detected['data_start_row'] = detected['sample_row'] + 1
            else:
                # 找第一个有数值的行
                for row in range(1, ws.max_row + 1):
                    for col in range(1, ws.max_column + 1):
                        v = ws.cell(row=row, column=col).value
                        if isinstance(v, (int, float)):
                            detected['data_start_row'] = row
                            break
                    if 'data_start_row' in detected:
                        break

            # 6. 检测零件名和日期的写入位置
            for row in range(1, min(ws.max_row + 1, 15)):
                for col in range(1, ws.max_column + 1):
                    v = ws.cell(row=row, column=col).value
                    if v and '零件' in str(v):
                        detected['field_locations'] = detected.get('field_locations', {})
                        detected['field_locations']['part_name'] = f'{get_column_letter(col)}{row}'
                    if v and '日期' in str(v):
                        detected['field_locations'] = detected.get('field_locations', {})
                        detected['field_locations']['date'] = f'{get_column_letter(col)}{row}'

            wb.close()
            logger.info(f'[自动检测] 模板结构: sheet="{sheet_name}", '
                       f'列映射={col_mapping}, 数据起始行={detected.get("data_start_row", "?")}')

            return detected

        except Exception as e:
            logger.warning(f'[自动检测] 无法分析模板: {e}')
            return {}

    def _smart_config(self, raw_config):
        """智能合并配置：优先用户配置，缺失时自动检测补充，
        关键配置（sheet名）不匹配时自动修正。"""
        detected = self._auto_detect_template()
        if not detected:
            return raw_config

        # 检查配置是否与模板匹配，不匹配则修正
        merged = dict(raw_config)

        # Sheet 名必须匹配
        if 'sheet_name' in detected:
            config_sheet = merged.get('sheet_name', '')
            avail_sheets = detected.get('_sheetnames', [])
            if config_sheet and config_sheet not in avail_sheets:
                logger.info(f'[配置修正] Sheet "{config_sheet}" 不存在，'
                           f'自动切换到 "{detected["sheet_name"]}"')
                merged['sheet_name'] = detected['sheet_name']

        # 缺失的列映射用自动检测的补充
        if 'columns' in detected:
            config_cols = merged.get('columns', {})
            for field, col in detected['columns'].items():
                if field not in config_cols:
                    config_cols[field] = col
            merged['columns'] = config_cols

        # 缺失的其他配置用自动检测的补充
        for key in ('data_start_row', 'sample_row'):
            if key in detected and key not in merged:
                merged[key] = detected[key]

        if 'field_locations' in detected:
            config_locs = merged.get('field_locations', {})
            for field, loc in detected['field_locations'].items():
                if field not in config_locs:
                    config_locs[field] = loc
            merged['field_locations'] = config_locs

        return merged

    def _get_column_letter(self, field):
        """获取字段对应的列字母，优先用配置文件，否则用默认值"""
        config_cols = self.config.get('columns', {})
        if field in config_cols:
            return config_cols[field]
        return DEFAULT_COLUMNS.get(field, 'A')

    def _get_sheet_b_name(self):
        """根据当前 sheet 名推算 Sheet B 的名称（避免与已有 sheet 冲突）"""
        base_sheet = self._get_sheet_name()
        return 'B' if base_sheet != 'B' else 'BB'

    def _get_sheet_name(self):
        if self._sheet_name_cache is not None:
            return self._sheet_name_cache

        sheet = self.config.get('sheet_name', 'A')
        # 验证配置的 sheet 是否存在于模板中，不存在则回退到第一个
        try:
            wb = openpyxl.load_workbook(self.template_path)
            if sheet not in wb.sheetnames:
                logger.warning(f'[配置修正] Sheet "{sheet}" 不存在于模板中，已自动切换到 "{wb.sheetnames[0]}"')
                sheet = wb.sheetnames[0]
            wb.close()
        except Exception:
            pass
        self._sheet_name_cache = sheet
        return sheet

    def _get_field_location(self, field):
        """获取字段写入位置（如 'A5'），优先用配置文件，否则用默认值"""
        tpl_locs = self._get_template_layout_config().get('field_locations', {})
        if field in tpl_locs:
            return tpl_locs[field]
        config_locs = self.config.get('field_locations', {})
        if field in config_locs:
            return config_locs[field]
        return DEFAULT_FIELD_LOCATIONS.get(field, 'A3')

    def _overflow_samples_enabled(self) -> bool:
        """是否启用样品溢出自动复制 Sheet（默认关，出货表模板直接按原表写入）。"""
        return bool(self.config.get('overflow_samples', False))

    def _get_template_layout_config(self) -> dict:
        """模板版式配置（兼容旧 fixed_pages 字段）。"""
        defaults = {
            'sheets': None,
            'max_data_row': None,
            'sample_id_plain': True,
            'field_locations': {},
        }
        merged = dict(defaults)
        merged.update(self.config.get('fixed_pages', {}))
        merged.update(self.config.get('template', {}))
        return merged

    def _get_template_sheet_names(self) -> list[str]:
        configured = self._get_template_layout_config().get('sheets')
        if configured:
            return list(configured)
        skip = {'CPK', 'cpk'}
        try:
            wb = openpyxl.load_workbook(self.template_path, read_only=True)
            names = [s for s in wb.sheetnames if s not in skip and not s.startswith('~')]
            wb.close()
            if names:
                return names
        except Exception:
            pass
        return [self._get_sheet_name()]

    def _load_cache(self):
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        save_settings_json_atomic(Path(CACHE_PATH), self.cache)

    def _safe_save(self, wb, path, backup=True):
        """保存工作簿，带文件锁检测和自动备份"""
        path = str(path)
        max_retries = 5
        retry_interval = 2  # 秒

        for attempt in range(1, max_retries + 1):
            try:
                if backup and os.path.exists(path):
                    # 自动备份：重命名旧文件
                    backup_path = f"{os.path.splitext(path)[0]}_bak_{time.strftime('%H%M%S')}{os.path.splitext(path)[1]}"
                    try:
                        os.rename(path, backup_path)
                        logger.info(f'[备份] {Path(path).name} -> {Path(backup_path).name}')
                    except OSError:
                        pass  # 如果备份失败（文件被锁），继续尝试保存
                wb.save(path)
                return True
            except PermissionError:
                if attempt < max_retries:
                    logger.warning(f'[文件锁] {Path(path).name} 被占用，{retry_interval}s 后重试 ({attempt}/{max_retries})...')
                    time.sleep(retry_interval)
                else:
                    logger.error(f'[保存失败] {Path(path).name} 被占用，已重试 {max_retries} 次')
                    raise
            except Exception as e:
                logger.error(f'[保存失败] {Path(path).name}: {e}')
                raise

    def _ocr_with_retry(self, img_path, max_retries=2):
        """OCR 识别，失败自动重试"""
        for attempt in range(1, max_retries + 1):
            try:
                return self.ocr.recognize(img_path)
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f'[OCR 重试] {Path(img_path).name} 识别失败，重试中 ({attempt}/{max_retries}): {e}')
                    time.sleep(1)
                else:
                    logger.error(f'[OCR 失败] {Path(img_path).name} 识别失败（已重试 {max_retries} 次）: {e}')
                    raise

    def _preview_pdf_data(self, pdf_path, data):
        """打印单个 PDF 的中间结果预览"""
        part = data.get('part_name', '未知')
        date = data.get('date', '未知')
        measures = data.get('measurements', [])
        source = data.get('_source', 'unknown')
        source_labels = {
            'text': '文字层',
            'ocr-table': 'OCR表格',
            'ocr-line': 'OCR行解析',
        }
        src_label = source_labels.get(source, source)
        low_conf = sum(1 for m in measures if m.get('low_confidence'))
        extra = f', 低置信 {low_conf} 项' if low_conf else ''
        logger.info(
            f'  [预览] {Path(pdf_path).name}: 零件={part}, 日期={date}, '
            f'{len(measures)} 项测量, 来源={src_label}{extra}'
        )
        for m in measures:
            ng = ' [NG!]' if m.get('ng') else ''
            low = ' [低置信]' if m.get('low_confidence') else ''
            label = measure_dict_label(m)
            logger.info(
                f'    {label}: {m["desc"]} | {m["nominal"]} '
                f'+{m["upper_tol"]}/-{abs(m["lower_tol"]):.3f} => {m["measured"]}{ng}{low}'
            )

    @staticmethod
    def _is_ng(nominal, upper, lower, measured):
        """判断实测值是否超差（NG）。公差符号异常时不做判断。"""
        try:
            dev = measured - nominal
            eps = 1e-9
            if upper >= -eps and lower <= eps:
                return dev < lower - eps or dev > upper + eps
        except TypeError:
            pass
        return False

    def _cleanup_cache(self, max_age_days=30):
        """清理超过指定天数的缓存图片和过大的 ocr_cache.json"""
        cutoff = time.time() - max_age_days * 86400
        cleaned = 0
        try:
            for f in CACHE_DIR.glob('*.png'):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    cleaned += 1
        except OSError:
            pass
        if cleaned:
            logger.info(f'清理了 {cleaned} 个过期缓存图片')

        # ocr_cache.json 按数量清理：> 10000 条按字母序删旧
        try:
            cache_file = Path(CACHE_PATH)
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if len(cache_data) > 10000:
                    sorted_keys = sorted(cache_data.keys())
                    keep_count = 10000
                    remove_count = len(sorted_keys) - keep_count
                    for key in sorted_keys[:remove_count]:
                        del cache_data[key]
                    save_settings_json_atomic(cache_file, cache_data)
                    logger.info(f'清理了 {remove_count} 条过期 OCR 缓存记录')
        except (OSError, json.JSONDecodeError):
            pass

    def _get_sample_col(self, label):
        """获取样品列字母，优先用配置文件，否则用默认值"""
        config_sample_cols = self.config.get('sample_cols', {})
        if label in config_sample_cols:
            return column_index_from_string(config_sample_cols[label])
        col = DEFAULT_SAMPLE_COLS.get(label)
        if col:
            return column_index_from_string(col)
        # 溢出样品（6#+）不走此回退——调用方应按样品位顺序映射；
        # 到这里说明配置缺失，明确告警并落 H 列兜底
        logger.warning(f'样品列 {label} 未配置，回退 H 列')
        return column_index_from_string('H')

    def _is_fixed_pages_mode(self) -> bool:
        """已废弃：保留别名，始终按模板序号列写入。"""
        return True

    def _get_fixed_pages_config(self) -> dict:
        """已废弃：请用 _get_template_layout_config。"""
        return self._get_template_layout_config()

    def _get_main_sample_count(self):
        """样品位数量，由 template_config 的 sample_cols / main_sample_count 决定。"""
        configured = self.config.get('main_sample_count')
        if configured is not None:
            try:
                return max(1, min(int(configured), 50))
            except (TypeError, ValueError):
                pass
        sample_cols = self.config.get('sample_cols', {})
        if sample_cols:
            return max(1, min(len(sample_cols), 50))
        return DEFAULT_MAIN_SAMPLE_COUNT

    def _chunk_samples(self, items: list, chunk_size: int) -> list[list]:
        """将样品列表按 chunk_size 分块（每块对应一个 Sheet）。"""
        return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    @staticmethod
    def _batch_output_filename(date_str: str, batch_start: int, batch_end: int, *, multi_batch: bool) -> str:
        """多样品拆分输出文件名。"""
        if not multi_batch:
            return f'{date_str}_项目汇总.xlsx'
        return f'{date_str}_项目汇总_样品{batch_start}-{batch_end}.xlsx'

    def _prepare_sample_batches(self, items: list, main_count: int) -> list[list]:
        """
        按模板样品位容量分批。overflow_samples 模式不拆分（整批走旧版 Sheet 复制逻辑）。
        """
        if self._overflow_samples_enabled() or len(items) <= main_count:
            return [items]
        batches = self._chunk_samples(items, main_count)
        logger.info(
            f'[模板] {len(items)} 个样品超过模板容量 {main_count} 列，'
            f'将拆分为 {len(batches)} 个 Excel 文件'
        )
        return batches

    @staticmethod
    def _renumber_batch_items(batch: list, local_start: int = 1) -> list[dict]:
        """每份出货表内样品位从 1# 起编号。"""
        out: list[dict] = []
        for offset, item in enumerate(batch):
            row = dict(item)
            row['sample_num'] = local_start + offset
            out.append(row)
        return out

    def _allocate_overflow_sheet_name(self, wb, chunk_index: int) -> str:
        """为第 chunk_index 个溢出块分配 Sheet 名（chunk_index=1 → 第一块溢出）。"""
        used = set(wb.sheetnames)
        base = self._get_sheet_name()
        if chunk_index == 1:
            candidate = self._get_sheet_b_name()
            if candidate not in used:
                return candidate
        for letter in 'BCDEFGHIJKLMNOPQRSTUVWXYZ':
            name = letter if letter != base else f'{letter}2'
            if name not in used:
                return name
        return f'样品{chunk_index}'[:31]

    def _prepare_overflow_sheet(self, wb, base_ws, sheet_name: str, sample_col_slots, sample_row, max_data_row):
        """从主 Sheet 复制创建溢出 Sheet，并清空样品位数据。"""
        new_ws = wb.copy_worksheet(base_ws)
        new_ws.title = sheet_name
        for col in sample_col_slots:
            _write_cell(new_ws, f'{get_column_letter(col)}{sample_row}', None)
        data_start = self._get_data_start_row()
        for row in range(data_start, max_data_row + 1):
            for col in sample_col_slots:
                new_ws.cell(row=row, column=col).value = None
        return new_ws

    def _fill_samples_on_sheet(
        self, ws, samples, sample_col_slots, sample_row, data_start_row,
        max_data_row, excluded_measures, edited_measures, sheet_label: str,
    ):
        """在指定 Sheet 上填入一组样品的序号和实测值。"""
        for slot_idx, item in enumerate(samples):
            if slot_idx >= len(sample_col_slots):
                logger.warning(
                    f'[样品位不足] {item["path"].name} 超出 Sheet {sheet_label} 列容量，已跳过'
                )
                continue
            sample_num = item['sample_num']
            sample_col = sample_col_slots[slot_idx]
            _write_cell(ws, f'{get_column_letter(sample_col)}{sample_row}', f'{sample_num:03d}')
            logger.info(
                f'  Sheet {sheet_label}: {item["path"].name} -> {sample_num}# '
                f'(列{sample_col}, 序号{sample_num:03d})'
            )
            for measure in item['data'].get('measurements', []):
                eff = self._get_effective_measure(
                    measure, item['stem'], excluded_measures, edited_measures,
                )
                if eff is None:
                    continue
                row = data_start_row - 1 + self._measure_row(eff)
                if row > max_data_row:
                    lbl = measure_dict_label(eff)
                    logger.warning(
                        f'[超出数据区] {lbl} 落在行 {row}（数据区上限 {max_data_row}），已跳过'
                    )
                    continue
                ws.cell(row=row, column=sample_col, value=eff['measured'])

    def _fill_template_for_date_group(
        self,
        wb,
        items: list,
        date_str: str,
        sample_col_slots: list[int],
        sample_row: int,
        data_start_row: int,
        max_data_row: int,
        excluded_measures: dict,
        edited_measures: dict,
        parent_picks: dict[str, str | None] | None = None,
    ) -> tuple[int, int]:
        """
        按出货表模板写入：根据各 Sheet 序号列定位行，填入规格/公差与实测值。
        返回 (写入单元格数, 未匹配项数)。
        """
        tpl = self._get_template_layout_config()
        sheet_names = self._get_template_sheet_names()
        serial_col = column_index_from_string(self._get_column_letter('serial'))
        row_index = build_sheet_row_index(
            wb, sheet_names, serial_col, data_start_row, max_data_row,
        )
        if not row_index:
            logger.warning('[模板] 未在序号列中扫描到任何尺寸行')

        part_name = ''
        for item in items:
            if item['data'].get('part_name'):
                part_name = item['data']['part_name']
                break

        plain_ids = bool(tpl.get('sample_id_plain', True))
        for sheet_name in sheet_names:
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            if part_name:
                _write_cell(ws, self._get_field_location('part_name'), part_name)
            if date_str:
                _write_cell(ws, self._get_field_location('date'), date_str)

        spec_col = column_index_from_string(self._get_column_letter('spec'))
        upper_col = column_index_from_string(self._get_column_letter('upper_tol'))
        lower_col = column_index_from_string(self._get_column_letter('lower_tol'))

        # 规格/公差：与动态模式一致，从 PDF 去重后按模板序号列定位写入
        all_measurements: list[dict] = []
        seen_keys: set[str] = set()
        for item in items:
            for m in item['data'].get('measurements', []):
                key = measure_dict_key(m)
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_measurements.append(m)
        all_measurements.sort(key=_measurement_sort_key)

        spec_filled = 0
        for measure in all_measurements:
            loc = resolve_measure_write_location(measure, row_index, parent_picks)
            if not loc:
                continue
            sheet_name, row = loc
            if row > max_data_row:
                continue
            ws = wb[sheet_name]
            ws.cell(row=row, column=spec_col, value=measure['nominal'])
            ws.cell(row=row, column=upper_col, value=measure['upper_tol'])
            ws.cell(row=row, column=lower_col, value=measure['lower_tol'])
            spec_filled += 1
        if spec_filled:
            logger.info(f'[模板] 已填入 {spec_filled} 项规格/公差')

        written = 0
        unmatched = 0
        for slot_idx, item in enumerate(items):
            if slot_idx >= len(sample_col_slots):
                logger.warning(
                    f'[模板] 样品位不足，跳过 {item["path"].name} '
                    f'（模板最多 {len(sample_col_slots)} 个样品列）'
                )
                continue
            sample_col = sample_col_slots[slot_idx]
            sample_label = (
                item['sample_num'] if plain_ids else f'{item["sample_num"]:03d}'
            )
            for sheet_name in sheet_names:
                if sheet_name not in wb.sheetnames:
                    continue
                _write_cell(
                    wb[sheet_name],
                    f'{get_column_letter(sample_col)}{sample_row}',
                    sample_label,
                )
            logger.info(
                f'  样品 {item["path"].name} -> {item["sample_num"]}# '
                f'(列 {get_column_letter(sample_col)})'
            )

            for measure in item['data'].get('measurements', []):
                eff = self._get_effective_measure(
                    measure, item['stem'], excluded_measures, edited_measures,
                )
                if eff is None:
                    continue
                loc = resolve_measure_write_location(eff, row_index, parent_picks)
                if not loc:
                    if self._is_skipped_sub_competitor(eff, row_index, parent_picks):
                        continue
                    unmatched += 1
                    logger.warning(
                        f'[模板] 模板中未找到 {measure_dict_label(eff)} 对应行'
                    )
                    continue
                sheet_name, row = loc
                if row > max_data_row:
                    logger.warning(
                        f'[模板] {measure_dict_label(eff)} 行 {row} 超出上限 {max_data_row}'
                    )
                    continue
                wb[sheet_name].cell(row=row, column=sample_col, value=eff['measured'])
                written += 1

        return written, unmatched

    def _get_sample_col_slots(self):
        """主表全部样品位的列号列表（支持非连续列，如 H,K,N）"""
        return [self._get_sample_col(f'{i}#') for i in range(1, self._get_main_sample_count() + 1)]

    def _get_data_start_row(self):
        return self.config.get('data_start_row', DEFAULT_DATA_START_ROW)

    def _get_sample_row(self):
        return self.config.get('sample_row', DEFAULT_SAMPLE_ROW)

    def _get_max_data_row(self):
        """数据区最后一行：优先 template 配置，否则扫描模板规格列。"""
        configured = self._get_template_layout_config().get('max_data_row')
        if configured is None:
            configured = self.config.get('max_data_row')
        if configured:
            return int(configured)

        default_max = self._get_data_start_row() + 28
        try:
            wb = openpyxl.load_workbook(self.template_path)
            ws = wb[self._get_sheet_name()]
            spec_col = column_index_from_string(self._get_column_letter('spec'))
            data_start = self._get_data_start_row()
            last_data_row = None
            for row in range(data_start, min(ws.max_row, data_start + 200) + 1):
                if ws.cell(row=row, column=spec_col).value is not None:
                    last_data_row = row
            wb.close()
            if last_data_row:
                # 增大缓冲量：从 5 → 50，兼容一次性处理多份 PDF 新增大量测量项的场景
                return min(last_data_row + 50, data_start + 200)
        except Exception:
            pass
        return default_max

    def _get_axis_preferences(self) -> dict[str, str]:
        """从模板「轴」列读取各序号应取的测量轴（D/X/Y/M/A 等）。"""
        if self._axis_prefs_cache is not None:
            return self._axis_prefs_cache

        axis_col_letter = self.config.get('columns', {}).get('axis')
        if not axis_col_letter:
            self._axis_prefs_cache = {}
            return self._axis_prefs_cache

        sheet_names = self._get_template_sheet_names()

        self._axis_prefs_cache = load_axis_preferences_from_template(
            self.template_path,
            sheet_names,
            column_index_from_string(self._get_column_letter('serial')),
            column_index_from_string(axis_col_letter),
            self._get_data_start_row(),
            self._get_max_data_row(),
        )
        return self._axis_prefs_cache

    def build_template_row_index(self, wb: openpyxl.Workbook | None = None) -> dict[str, tuple[str, int]]:
        """扫描模板序号列，建立 lookup_key -> (sheet, row)。"""
        own_wb = wb is None
        if own_wb:
            wb = openpyxl.load_workbook(self.template_path, read_only=True, data_only=True)
        try:
            return build_sheet_row_index(
                wb,
                self._get_template_sheet_names(),
                column_index_from_string(self._get_column_letter('serial')),
                self._get_data_start_row(),
                self._get_max_data_row(),
            )
        finally:
            if own_wb:
                wb.close()

    def analyze_sub_item_conflicts(self, analyze_items: list) -> list[dict]:
        """分析预览数据中的「多子编号争同一模板序号」冲突。"""
        measurements: list[dict] = []
        for item in analyze_items:
            if item.get('error'):
                continue
            measurements.extend(item.get('measurements', []))
        if not measurements:
            return []
        row_index = self.build_template_row_index()
        return detect_parent_row_conflicts(measurements, row_index)

    def _build_parent_picks(
        self,
        measurements: list[dict],
        row_index: dict[str, tuple[str, int]],
        sub_item_choices: dict[str, str] | None,
    ) -> dict[str, str | None] | None:
        conflicts = detect_parent_row_conflicts(measurements, row_index)
        auto = build_parent_auto_picks(measurements, row_index)
        resolved = resolve_parent_picks(conflicts, sub_item_choices)
        merged = merge_parent_picks(auto, resolved)
        if not merged:
            return None
        for tk, pick in sorted(merged.items()):
            if pick is None:
                logger.info(f'  [子编号] 模板序号 {tk}：用户选择不填入')
            else:
                logger.info(f'  [子编号] 模板序号 {tk} → {pick}')
        return merged

    @staticmethod
    def _is_skipped_sub_competitor(
        measure: dict,
        row_index: dict[str, tuple[str, int]],
        parent_picks: dict[str, str | None] | None,
    ) -> bool:
        if not parent_picks:
            return False
        sub = measure.get('sub') or ''
        if not sub:
            return False
        parent_key = str(measure['num'])
        if parent_key not in row_index or parent_key not in parent_picks:
            return False
        if resolve_measure_location(row_index, measure):
            return False
        pick = parent_picks[parent_key]
        if pick is None:
            return True
        return measure_dict_key(measure) != pick

    def _compute_required_max_row(self, items):
        """根据所有 PDF 解析出的最大测量编号，计算写入所需的最大行号。
        用于 batch_process_by_date 动态扩展上限，避免固定 buffer 截断有效数据。"""
        max_num = 0
        for item in items:
            for m in item['data'].get('measurements', []):
                if self._measure_row(m) > max_num:
                    max_num = self._measure_row(m)
        if max_num == 0:
            return None
        return self._get_data_start_row() - 1 + max_num

    def pdf_to_image(self, pdf_path):
        """渲染 PDF 第 1 页为图片（向后兼容）。"""
        images = pdf_to_images(pdf_path, CACHE_DIR, dpi=self.dpi, roi=self.ocr_roi)
        return images[0]

    def pdf_to_all_images(self, pdf_path):
        """渲染 PDF 所有页为图片。"""
        return pdf_to_images(pdf_path, CACHE_DIR, dpi=self.dpi, roi=self.ocr_roi)

    def _pdf_cache_key(self, pdf_path: str) -> str:
        """PDF 级缓存 key（基于完整路径 MD5）。"""
        import hashlib
        return hashlib.md5(str(Path(pdf_path).resolve()).encode('utf-8')).hexdigest()[:16]

    def _cache_key(self, img_path: str) -> str:
        """生成缓存 key：完整路径的 MD5（避免同名 PDF 不同路径冲突）。"""
        import hashlib
        return hashlib.md5(img_path.encode('utf-8')).hexdigest()[:16]

    def ocr_image(self, img_path):
        cache_key = self._cache_key(img_path)
        if cache_key in self.cache:
            return self.cache[cache_key]

        lines = self._ocr_with_retry(img_path)
        self.cache[cache_key] = lines
        self._save_cache()
        return lines

    def ocr_image_detailed(self, img_path) -> list[OCRBox]:
        """OCR 识别并返回带坐标的 OCRBox 列表。"""
        cache_key = f'det:{self._cache_key(img_path)}'
        if cache_key in self.cache:
            return [OCRBox(**b) for b in self.cache[cache_key]]

        boxes = self._ocr_detailed_with_retry(img_path)
        self.cache[cache_key] = [
            {'text': b.text, 'x0': b.x0, 'y0': b.y0, 'x1': b.x1, 'y1': b.y1, 'confidence': b.confidence}
            for b in boxes
        ]
        self._save_cache()
        return boxes

    def _ocr_detailed_with_retry(self, img_path, max_retries=2) -> list[OCRBox]:
        """OCR 识别（含坐标），失败自动重试。"""
        for attempt in range(1, max_retries + 1):
            try:
                return self.ocr.recognize_detailed(img_path)
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f'[OCR 重试] {Path(img_path).name} 坐标识别失败，重试中 ({attempt}/{max_retries}): {e}'
                    )
                    time.sleep(1)
                else:
                    logger.error(
                        f'[OCR 失败] {Path(img_path).name} 坐标识别失败（已重试 {max_retries} 次）: {e}'
                    )
                    raise

    def extract_pdf_data(self, pdf_path: str) -> dict:
        """
        统一 PDF 提取入口：
        1. 文字型 PDF → get_text() 快速通道
        2. 扫描件 → 多页 OCR + 坐标表格解析
        3. 表格解析无结果 → 回退行文本解析
        """
        pdf_path = str(pdf_path)
        profile_tag = self.profile.get('name', 'default')
        roi_tag = roi_cache_suffix(self.ocr_roi)
        axis_prefs = self._get_axis_preferences()
        axis_tag = ''
        if axis_prefs:
            import hashlib
            axis_tag = hashlib.md5(
                json.dumps(axis_prefs, sort_keys=True).encode('utf-8')
            ).hexdigest()[:8]
        cache_key = f'pdf:{self._pdf_cache_key(pdf_path)}:{profile_tag}:{roi_tag}:ax{axis_tag}'
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if isinstance(cached, dict) and 'measurements' in cached:
                return cached

        pdf_type = detect_pdf_type(pdf_path)
        source = 'text'

        if pdf_type == 'text':
            lines = extract_text_lines(pdf_path, roi=self.ocr_roi)
            data = self.parse_from_text(lines)
            logger.info(f'  [提取] {Path(pdf_path).name}: 文字层快速通道 ({len(lines)} 行)')
        else:
            all_lines: list[str] = []
            page_box_groups: list[list[OCRBox]] = []
            img_paths = self.pdf_to_all_images(pdf_path)
            for img_path in img_paths:
                boxes = self.ocr_image_detailed(img_path)
                page_box_groups.append(boxes)
                all_lines.extend(b.text for b in boxes)

            merged_measurements: list[dict] = []
            seen_keys: set[str] = set()
            table_data: dict = {'part_name': '', 'date': '', 'measurements': []}
            for boxes in page_box_groups:
                page_data = parse_from_ocr_boxes(
                    boxes, self.item_prefixes, self.skip_lines,
                    self._is_ng, month_cn_to_num,
                    confidence_threshold=self.confidence_threshold,
                    axis_preferences=axis_prefs or None,
                )
                if not table_data.get('part_name') and page_data.get('part_name'):
                    table_data['part_name'] = page_data['part_name']
                if not table_data.get('date') and page_data.get('date'):
                    table_data['date'] = page_data['date']
                for m in page_data.get('measurements', []):
                    key = m['item_key']
                    if key not in seen_keys:
                        seen_keys.add(key)
                        merged_measurements.append(m)
            table_data['measurements'] = merged_measurements
            data = table_data

            line_data = self.parse_from_text(all_lines)
            table_count = len(data.get('measurements', []))
            line_count = len(line_data.get('measurements', []))

            if table_count >= line_count and table_count > 0:
                source = 'ocr-table'
                if not data.get('part_name') and line_data.get('part_name'):
                    data['part_name'] = line_data['part_name']
                if not data.get('date') and line_data.get('date'):
                    data['date'] = line_data['date']
                logger.info(
                    f'  [提取] {Path(pdf_path).name}: OCR 坐标表格解析 '
                    f'({len(img_paths)} 页, {table_count} 项, 行解析 {line_count} 项)'
                )
            else:
                data = line_data
                source = 'ocr-line'
                if table_count > 0:
                    logger.info(
                        f'  [提取] {Path(pdf_path).name}: 表格解析 {table_count} 项 '
                        f'少于行解析 {line_count} 项，回退行解析'
                    )
                else:
                    logger.info(f'  [提取] {Path(pdf_path).name}: 坐标解析无结果，回退行解析')

        data['_source'] = source
        self.cache[cache_key] = data
        self._save_cache()
        return data

    @staticmethod
    def _apply_measure_override(measure: dict, override: dict | None) -> dict:
        """应用预览阶段的实测值修正。"""
        if not override:
            return measure
        m = dict(measure)
        for key in ('nominal', 'upper_tol', 'lower_tol', 'measured', 'desc'):
            if key in override and override[key] is not None:
                m[key] = override[key]
        m['ng'] = CMMReportFiller._is_ng(
            m['nominal'], m['upper_tol'], m['lower_tol'], m['measured'],
        )
        m['low_confidence'] = False
        return m

    def _measure_row(self, measure: dict) -> int:
        """测量项对应的 Excel 数据行偏移。"""
        return measure_dict_row_index(measure)

    def _get_effective_measure(self, measure, stem, excluded_measures, edited_measures):
        """合并剔除/修正后的测量项。"""
        key = measure_dict_key(measure)
        if key in excluded_measures.get(stem, set()):
            return None
        override = (edited_measures or {}).get(stem, {}).get(key)
        return self._apply_measure_override(measure, override)

    def parse_from_text(self, ocr_lines):
        return parse_from_text_lines(
            ocr_lines, self.item_prefixes, self.skip_lines,
            self._is_ng, month_cn_to_num,
        )

    def _scan_and_parse(self, pdf_folder, progress_callback=None):
        """扫描文件夹，过滤误操作文件，逐份 OCR+解析。

        返回 dict（文件夹为空时返回 None）：
          infos:  [{path, stem, date, data}] 成功解析的 PDF
          skipped: 被过滤的误操作文件名列表
          failed:  解析失败的 [{file, error}]
          scanned_total: 参与解析的 PDF 总数（过滤后）
        """
        pdfs = glob_pdfs(Path(pdf_folder))
        if not pdfs:
            logger.warning('未找到PDF文件')
            return None

        def _report(current, total, message):
            if progress_callback:
                progress_callback(current, total, message)

        # 过滤掉误操作文件（如 003-1.PDF 是 003.PDF 的重复保存）
        base_stems = {pdf.stem for pdf in pdfs}
        filtered = []
        skipped = []
        for pdf in pdfs:
            m = re.match(r'^(.+)-(\d+)$', pdf.stem)
            if m and m.group(1) in base_stems:
                logger.warning(f'[跳过误操作文件] {pdf.name} (存在同名文件 {m.group(1)}.PDF)')
                skipped.append(pdf.name)
                continue
            filtered.append(pdf)

        infos = []
        failed = []
        cancelled = False
        total = len(filtered)
        for idx, pdf in enumerate(filtered, start=1):
            if self.cancel_check and self.cancel_check():
                logger.info('用户已取消处理')
                cancelled = True
                break
            _report(idx - 1, total, f'OCR 识别: {pdf.name}')
            try:
                data = self.extract_pdf_data(str(pdf))
                self._preview_pdf_data(pdf, data)
                infos.append({
                    'path': pdf,
                    'stem': pdf.stem,
                    'date': data.get('date', ''),
                    'data': data,
                })
            except Exception as e:
                logger.error(f'[处理失败] {pdf.name}: {e}')
                failed.append({'file': pdf.name, 'error': str(e)})

        return {'infos': infos, 'skipped': skipped, 'failed': failed,
                'scanned_total': total, 'cancelled': cancelled}

    def analyze_pdfs(self, pdf_folder, progress_callback=None):
        """只做 OCR+解析（不写 Excel），返回供 GUI 预览的结构化列表。

        每项: {stem, name, date, part_name, ng_count, measurements, error}
        """
        result = self._scan_and_parse(pdf_folder, progress_callback)
        if result is None:
            return []

        items = []
        for info in result['infos']:
            data = info['data']
            ms = data.get('measurements', [])
            items.append({
                'stem': info['stem'],
                'name': info['path'].name,
                'date': data.get('date', ''),
                'part_name': data.get('part_name', ''),
                'ng_count': sum(1 for m in ms if m.get('ng')),
                'measurements': ms,
                'source': data.get('_source', ''),
                'error': None,
            })
        for f in result['failed']:
            items.append({
                'stem': None, 'name': f['file'], 'date': '', 'part_name': '',
                'ng_count': 0, 'measurements': [], 'error': f['error'],
            })
        return items

    def batch_process_by_date(self, pdf_folder, output_folder, progress_callback=None,
                              excluded_measures=None, edited_measures=None,
                              sub_item_choices: dict[str, str] | None = None):
        """
        按日期批量处理：
        - Sheet A: 样品1#-5#（001-005）
        - Sheet B: 样品6#+ 溢出样品（006-010），基于原始模板创建，保持格式一致
        - 忽略误操作文件（如 003-1.PDF）
        - excluded_measures: {pdf_stem: {measure_num, ...}}，这些 PDF 的对应测量项
          不写入实测值（用于预览时剔除误识别项）
        - edited_measures: {pdf_stem: {measure_num: {measured, ...}}}，预览修正值

        progress_callback(current, total, message) 可选，用于 GUI 进度更新。
        返回处理摘要 dict。
        """
        summary = {
            'total_pdfs': 0,
            'processed_pdfs': 0,
            'skipped_pdfs': [],
            'failed_pdfs': [],
            'output_files': [],
            'date_groups': 0,
            'ng_count': 0,
            'cancelled': False,
        }

        def _report(current, total, message):
            if progress_callback:
                progress_callback(current, total, message)

        data_start_row = self._get_data_start_row()
        max_data_row = self._get_max_data_row()

        scan = self._scan_and_parse(pdf_folder, progress_callback)
        if scan is None:
            return summary
        pdf_info = scan['infos']
        summary['skipped_pdfs'] = scan['skipped']
        summary['failed_pdfs'] = scan['failed']
        summary['total_pdfs'] = scan['scanned_total']
        summary['processed_pdfs'] = len(pdf_info)
        summary['ng_count'] = sum(
            1 for info in pdf_info
            for m in info['data'].get('measurements', []) if m.get('ng')
        )
        if not pdf_info:
            logger.warning('过滤后无有效 PDF 文件')
            return summary

        # 按模板写入（默认）；overflow_samples=true 时启用旧版自动扩展 Sheet
        required_max = None
        if self._overflow_samples_enabled():
            required_max = self._compute_required_max_row(pdf_info)
        if required_max is not None and required_max > max_data_row:
            logger.info(f'[数据区扩展] {max_data_row} → {required_max}（根据测量编号自动扩展）')
            max_data_row = required_max

        excluded_measures = excluded_measures or {}
        edited_measures = edited_measures or {}
        total = scan['scanned_total']
        _report(total, total, '按日期分组并写入 Excel...')

        # 2. 按日期分组
        date_groups = defaultdict(list)
        for info in pdf_info:
            date = info['date'] if info['date'] else '未知日期'
            date_groups[date].append(info)

        summary['date_groups'] = len(date_groups)
        logger.info(f'发现 {len(date_groups)} 个日期组')

        # 3. 处理每个日期组
        for date, items in sorted(date_groups.items()):
            if self.cancel_check and self.cancel_check():
                logger.info('用户已取消处理')
                summary['cancelled'] = True
                break
            logger.info(f'\n=== 日期组: {date} ({len(items)} 个样品) ===')

            # 按文件名排序，顺序分配全局样品序号（用于拆分文件名）
            items.sort(key=lambda x: x['path'].name)
            for idx, item in enumerate(items, start=1):
                item['sample_num'] = idx

            main_count = self._get_main_sample_count()
            sample_batches = self._prepare_sample_batches(items, main_count)
            multi_batch = len(sample_batches) > 1
            data_start_row = self._get_data_start_row()
            sample_row = self._get_sample_row()
            sample_col_slots = self._get_sample_col_slots()[:main_count]
            date_str = date

            row_index = self.build_template_row_index()
            all_ms = []
            for item in items:
                all_ms.extend(item['data'].get('measurements', []))
            parent_picks = self._build_parent_picks(all_ms, row_index, sub_item_choices)

            if self._overflow_samples_enabled():
                if len(items) > main_count:
                    logger.warning(
                        f'样品数 {len(items)} 超过模板样品位 {main_count}，'
                        f'将溢出到新 Sheet（overflow_samples 模式）'
                    )
                batch_items = items
                wb = openpyxl.load_workbook(self.template_path)
                part_name = ''
                for item in batch_items:
                    if item['data'].get('part_name'):
                        part_name = item['data']['part_name']
                        break

                # ── 可选：样品溢出时自动复制 Sheet（旧版动态扩展）──
                all_measurements = []
                seen_keys = set()
                for item in batch_items:
                    for m in item['data'].get('measurements', []):
                        key = (measure_dict_key(m),
                               m['nominal'], m['upper_tol'], m['lower_tol'])
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_measurements.append(m)
                all_measurements.sort(key=_measurement_sort_key)

                ws = wb[self._get_sheet_name()]
                _write_cell(ws, self._get_field_location('part_name'), part_name)
                _write_cell(ws, self._get_field_location('date'), date_str)

                filled = 0
                spec_col = column_index_from_string(self._get_column_letter("spec"))
                upper_col = column_index_from_string(self._get_column_letter("upper_tol"))
                lower_col = column_index_from_string(self._get_column_letter("lower_tol"))
                for item in all_measurements:
                    row = data_start_row - 1 + measure_dict_row_index(item)
                    if row > max_data_row:
                        lbl = measure_dict_label(item)
                        logger.warning(f'[超出数据区] {lbl} 落在行 {row}（数据区上限 {max_data_row}），已跳过')
                        continue
                    ws.cell(row=row, column=spec_col, value=item['nominal'])
                    ws.cell(row=row, column=upper_col, value=item['upper_tol'])
                    ws.cell(row=row, column=lower_col, value=item['lower_tol'])
                    filled += 1
                logger.info(f'[初始化完成] 已填入 {filled} 项规格/公差（来自 {len(batch_items)} 个PDF）')

                sample_chunks = self._chunk_samples(batch_items, main_count)
                logger.info(
                    f'  共 {len(batch_items)} 个样品，分 {len(sample_chunks)} 个 Sheet'
                    f'（每 Sheet 最多 {main_count} 个）'
                )

                out_wb = wb
                out_ws = out_wb[self._get_sheet_name()]
                base_sheet_name = self._get_sheet_name()

                for chunk_idx, chunk in enumerate(sample_chunks):
                    if chunk_idx == 0:
                        target_ws = out_ws
                        sheet_label = base_sheet_name
                    else:
                        sheet_name = self._allocate_overflow_sheet_name(out_wb, chunk_idx)
                        target_ws = self._prepare_overflow_sheet(
                            out_wb, out_ws, sheet_name, sample_col_slots, sample_row, max_data_row,
                        )
                        sheet_label = sheet_name
                        cpk_sheets = [s for s in out_wb._sheets if s.title == 'CPK']
                        if cpk_sheets:
                            sheets = out_wb._sheets
                            t_idx = sheets.index(target_ws)
                            cpk_idx = sheets.index(cpk_sheets[0])
                            if t_idx > cpk_idx:
                                sheets[t_idx], sheets[cpk_idx] = sheets[cpk_idx], sheets[t_idx]

                    self._fill_samples_on_sheet(
                        target_ws, chunk, sample_col_slots, sample_row,
                        data_start_row, max_data_row, excluded_measures, edited_measures,
                        sheet_label,
                    )

                out_path = str(Path(output_folder) / self._batch_output_filename(
                    date_str, 1, len(batch_items), multi_batch=False,
                ))
                self._safe_save(wb, out_path)
                wb.close()
                summary['output_files'].append(out_path)
                logger.info(f'  [完成] {out_path}')
            else:
                for batch_idx, batch in enumerate(sample_batches):
                    if self.cancel_check and self.cancel_check():
                        logger.info('用户已取消处理')
                        summary['cancelled'] = True
                        break

                    global_start = batch_idx * main_count + 1
                    global_end = global_start + len(batch) - 1
                    batch_items = self._renumber_batch_items(batch, local_start=1)

                    wb = openpyxl.load_workbook(self.template_path)
                    written, unmatched = self._fill_template_for_date_group(
                        wb, batch_items, date_str, sample_col_slots, sample_row,
                        data_start_row, max_data_row, excluded_measures, edited_measures,
                        parent_picks=parent_picks,
                    )
                    logger.info(
                        f'[模板] 样品 {global_start}-{global_end}：'
                        f'已写入 {written} 个实测值，未匹配 {unmatched} 项'
                    )

                    out_path = str(Path(output_folder) / self._batch_output_filename(
                        date_str, global_start, global_end, multi_batch=multi_batch,
                    ))
                    self._safe_save(wb, out_path)
                    wb.close()
                    summary['output_files'].append(out_path)
                    logger.info(f'  [完成] {out_path}')

                if summary.get('cancelled'):
                    break

        return summary

    def export_standard_template(self, pdf_folder, output_folder=None, progress_callback=None):
        """
        从 PDF 生成标准模板文件（含规格/公差，不含实测值）。
        用于独立导出供核对使用。
        """
        if output_folder is None:
            output_folder = str(Path(self.template_path).parent)

        summary = {
            'total_pdfs': 0,
            'processed_pdfs': 0,
            'failed_pdfs': [],
            'output_file': None,
            'cancelled': False,
        }

        def _report(current, total, message):
            if progress_callback:
                progress_callback(current, total, message)

        data_start_row = self._get_data_start_row()
        max_data_row = self._get_max_data_row()
        pdfs = glob_pdfs(Path(pdf_folder))
        if not pdfs:
            logger.warning('未找到PDF文件')
            return summary

        # 过滤误操作文件
        base_stems = {pdf.stem for pdf in pdfs}
        filtered_pdfs = []
        for pdf in pdfs:
            stem = pdf.stem
            m = re.match(r'^(.+)-(\d+)$', stem)
            if m:
                base = m.group(1)
                if base in base_stems:
                    continue
            filtered_pdfs.append(pdf)

        summary['total_pdfs'] = len(filtered_pdfs)
        logger.info(f'收集 {len(filtered_pdfs)} 个 PDF 的测量项...')

        all_measurements = []
        seen_keys = set()
        total = len(filtered_pdfs)
        for idx, pdf in enumerate(filtered_pdfs, start=1):
            if self.cancel_check and self.cancel_check():
                logger.info('用户已取消导出')
                summary['cancelled'] = True
                break
            _report(idx - 1, total, f'提取规格: {pdf.name}')
            try:
                data = self.extract_pdf_data(str(pdf))
                for m in data.get('measurements', []):
                    key = (measure_dict_key(m),
                           m['nominal'], m['upper_tol'], m['lower_tol'])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_measurements.append(m)
                summary['processed_pdfs'] += 1
            except Exception as e:
                logger.error(f'[导出失败] {pdf.name}: {e}')
                summary['failed_pdfs'].append({'file': pdf.name, 'error': str(e)})

        _report(total, total, '写入标准模板...')

        all_measurements.sort(key=_measurement_sort_key)

        wb = openpyxl.load_workbook(self.template_path)
        ws = wb[self._get_sheet_name()]

        spec_col = column_index_from_string(self._get_column_letter("spec"))
        upper_col = column_index_from_string(self._get_column_letter("upper_tol"))
        lower_col = column_index_from_string(self._get_column_letter("lower_tol"))

        filled = 0
        for item in all_measurements:
            row = data_start_row - 1 + measure_dict_row_index(item)
            if row > max_data_row:
                lbl = measure_dict_label(item)
                logger.warning(f'[超出数据区] {lbl} 落在行 {row}（数据区上限 {max_data_row}），已跳过')
                continue
            ws.cell(row=row, column=spec_col, value=item['nominal'])
            ws.cell(row=row, column=upper_col, value=item['upper_tol'])
            ws.cell(row=row, column=lower_col, value=item['lower_tol'])
            filled += 1

        out_path = str(Path(output_folder) / f'标准模板_{len(filtered_pdfs)}个样品.xlsx')
        self._safe_save(wb, out_path)
        wb.close()
        summary['output_file'] = out_path
        logger.info(f'[导出完成] 已填入 {filled} 项规格/公差，保存至: {out_path}')
        return summary

    def export_summary_workbook(self, pdf_paths, output_folder, progress_callback=None):
        """把挑选的多份 PDF 汇总到一个 Excel 文件：每个 PDF 一个 Sheet。

        Sheet 样式（CMM Dimensions Report 汇总）：
        行1 合并大标题（含文件名）、行2 报告信息（零件名/日期/序列号）、
        行3 表头（SUMMARY_HEADERS 共 10 列）、行4+ 每测量项一行；
        NG 行的 实际值/误差/趋势 红字，趋势列只在超差时填超差量。

        注意：pdf_paths 是用户显式挑选的文件列表，不套用误操作文件过滤。

        progress_callback(current, total, message) 可选。
        返回 {total_pdfs, processed_pdfs, failed_pdfs, output_file, ng_count, sheet_count}
        """
        summary = {
            'total_pdfs': 0,
            'processed_pdfs': 0,
            'failed_pdfs': [],
            'output_file': None,
            'ng_count': 0,
            'sheet_count': 0,
            'cancelled': False,
        }

        def _report(current, total, message):
            if progress_callback:
                progress_callback(current, total, message)

        pdfs = [Path(p) for p in pdf_paths if str(p).lower().endswith('.pdf')]
        if not pdfs:
            logger.warning('未选择任何 PDF 文件')
            return summary
        summary['total_pdfs'] = len(pdfs)

        infos = []
        total = len(pdfs)
        for idx, pdf in enumerate(pdfs, start=1):
            if self.cancel_check and self.cancel_check():
                logger.info('用户已取消汇总导出')
                summary['cancelled'] = True
                break
            _report(idx - 1, total, f'汇总提取: {pdf.name}')
            try:
                data = self.extract_pdf_data(str(pdf))
                infos.append({'path': pdf, 'data': data})
                summary['processed_pdfs'] += 1
            except Exception as e:
                logger.error(f'[汇总失败] {pdf.name}: {e}')
                summary['failed_pdfs'].append({'file': pdf.name, 'error': str(e)})
        if not infos:
            logger.error('所有 PDF 均提取失败，未生成汇总文件')
            return summary

        _report(total, total, '生成汇总 Excel...')

        thin = Side(style='thin', color='999999')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill('solid', fgColor='D9D9D9')
        header_font = Font(bold=True)
        title_font = Font(bold=True, size=14)
        info_font = Font(size=10, color='595959')
        red_font = Font(color='FF0000', bold=True)
        center = Alignment(horizontal='center', vertical='center')
        left = Alignment(horizontal='left', vertical='center')

        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        used_titles = set()
        ng_total = 0
        for info in infos:
            pdf, data = info['path'], info['data']
            ws = wb.create_sheet(_safe_sheet_title(pdf.stem, used_titles))

            # 行1：大标题（合并 A1:J1）
            ws.merge_cells('A1:J1')
            c = ws.cell(row=1, column=1, value=f'CMM Dimensions Report 汇总 — {pdf.name}')
            c.font = title_font
            c.alignment = center

            # 行2：报告信息（合并 A2:J2）
            ws.merge_cells('A2:J2')
            part = data.get('part_name') or '未知'
            date = data.get('date') or '未知'
            c = ws.cell(row=2, column=1, value=f'零件名: {part}    日期: {date}    序列号: {pdf.stem}')
            c.font = info_font
            c.alignment = center

            # 行3：表头
            for col, name in enumerate(SUMMARY_HEADERS, start=1):
                c = ws.cell(row=3, column=col, value=name)
                c.font = header_font
                c.fill = header_fill
                c.border = border
                c.alignment = center

            # 行4+：数据（按测量项编号排序）
            measures = sorted(data.get('measurements', []), key=_measurement_sort_key)
            ng_total += sum(1 for m in measures if m.get('ng'))
            for r, m in enumerate(measures, start=4):
                dev = round(m['measured'] - m['nominal'], 4)
                trend = None
                if m.get('ng'):
                    # 趋势 = 超出公差的量（与参考样式一致：仅超差行填写）
                    trend = round(dev - m['upper_tol'], 4) if dev > m['upper_tol'] else round(dev - m['lower_tol'], 4)
                values = [m['num'], m['desc'], None, None,
                          m['nominal'], m['measured'], dev,
                          m['lower_tol'], m['upper_tol'], trend]
                for col, val in enumerate(values, start=1):
                    c = ws.cell(row=r, column=col, value=val)
                    c.border = border
                    c.alignment = left if col == 2 else center
                    if col >= 5 and val is not None:
                        c.number_format = '0.0000'
                    if m.get('ng') and col in (6, 7, 10):  # 实际值/误差/趋势 红字
                        c.font = red_font

            # 列宽与冻结表头
            ws.column_dimensions['A'].width = 6
            ws.column_dimensions['B'].width = 40
            for col in ('C', 'D'):
                ws.column_dimensions[col].width = 10
            for col in ('E', 'F', 'G', 'H', 'I', 'J'):
                ws.column_dimensions[col].width = 12
            ws.freeze_panes = 'A4'

        summary['ng_count'] = ng_total
        summary['sheet_count'] = len(wb.sheetnames)

        Path(output_folder).mkdir(parents=True, exist_ok=True)
        out_path = str(Path(output_folder) / f'数据汇总_{time.strftime("%Y%m%d_%H%M")}.xlsx')
        self._safe_save(wb, out_path)
        wb.close()
        summary['output_file'] = out_path
        logger.info(f'[汇总完成] {summary["sheet_count"]} 个 Sheet，NG {ng_total} 项，保存至: {out_path}')
        return summary

    def export_ng_analysis(self, pdf_folder, output_folder, progress_callback=None):
        """
        批量分析 PDF 文件夹，导出 NG 统计 Excel。

        返回 {total_pdfs, processed_pdfs, failed_pdfs, output_file, ng_count, fai_count, top_ng}
        """
        summary = {
            'total_pdfs': 0,
            'processed_pdfs': 0,
            'failed_pdfs': [],
            'output_file': None,
            'ng_count': 0,
            'fai_count': 0,
            'top_ng': [],
            'cancelled': False,
        }

        scan = self._scan_and_parse(pdf_folder, progress_callback)
        if scan is None:
            return summary

        summary['total_pdfs'] = scan['scanned_total']
        summary['processed_pdfs'] = len(scan['infos'])
        summary['failed_pdfs'] = scan['failed']
        if scan.get('cancelled'):
            summary['cancelled'] = True
            return summary

        if not scan['infos']:
            logger.warning('无有效 PDF 数据，未生成 NG 统计')
            return summary

        stats = collect_ng_stats(scan['infos'])
        summary['ng_count'] = stats['total_ng']
        summary['fai_count'] = stats['fai_count']
        summary['top_ng'] = [
            {
                'item_key': r.get('item_key', str(r['num'])),
                'label': r.get('label', f"FAI_{r['num']:02d}"),
                'num': r['num'],
                'desc': r['desc'],
                'ng_rate': r['ng_rate'],
                'ng_count': r['ng_count'],
            }
            for r in stats['summary'][:5] if r['ng_count'] > 0
        ]

        Path(output_folder).mkdir(parents=True, exist_ok=True)
        out_path = str(Path(output_folder) / f'NG统计_{time.strftime("%Y%m%d_%H%M")}.xlsx')
        export_ng_workbook(stats, out_path)
        summary['output_file'] = out_path

        logger.info(format_ng_summary_text(stats))
        return summary
