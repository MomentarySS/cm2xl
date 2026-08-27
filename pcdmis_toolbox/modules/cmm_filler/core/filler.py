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

import fitz
import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

from ..ocr.engine import OCREngine, PaddleOCREngine
from utils.file_io import glob_pdfs, fitz_open_context
from utils.paths import paths
from utils.settings import save_settings_json_atomic

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
    """保存 GUI 路径记忆（原子写，避免中断留下半截文件）"""
    try:
        Path(APP_DATA_DIR).mkdir(parents=True, exist_ok=True)
        save_settings_json_atomic(Path(SETTINGS_PATH), data)
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
    def __init__(self, template_path, dpi=300, ocr_engine=None):
        self.template_path = template_path
        self.dpi = dpi
        self.ocr = ocr_engine or PaddleOCREngine()
        self.cache = self._load_cache()
        self._cleanup_cache()

        # 取消检查回调（由 GUI 注入，如 CancellableWorker.is_cancelled）：
        # 循环内检测到 True 时提前退出，返回结构带 cancelled=True
        self.cancel_check = None

        # 加载配置后智能合并（自动检测模板结构补全缺失项）
        raw_config = self._load_config()
        self.config = self._smart_config(raw_config)
        self._sheet_name_cache = None  # 缓存 sheet 名，避免重复打开工作簿

    def invalidate_sheet_cache(self):
        """模板切换后调用，清除缓存的 sheet 名"""
        self._sheet_name_cache = None

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
        config_locs = self.config.get('field_locations', {})
        if field in config_locs:
            return config_locs[field]
        return DEFAULT_FIELD_LOCATIONS.get(field, 'A3')

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
                lines = self.ocr.recognize(img_path)
                self.cache[os.path.basename(img_path)] = lines
                self._save_cache()
                return lines
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
        logger.info(f'  [预览] {Path(pdf_path).name}: 零件={part}, 日期={date}, {len(measures)} 项测量')
        for m in measures:
            ng = ' [NG!]' if m.get('ng') else ''
            logger.info(f'    FAI_{m["num"]:02d}: {m["desc"]} | {m["nominal"]} +{m["upper_tol"]}/-{abs(m["lower_tol"]):.3f} => {m["measured"]}{ng}')

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

    def _get_main_sample_count(self):
        """主表样品位数（1#-N# 写主 Sheet，超出溢出到 Sheet B）。
        可通过配置 main_sample_count 调整（1-20），默认 5。"""
        n = self.config.get('main_sample_count', DEFAULT_MAIN_SAMPLE_COUNT)
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = DEFAULT_MAIN_SAMPLE_COUNT
        return max(1, min(n, 20))

    def _get_sample_col_slots(self):
        """主表全部样品位的列号列表（支持非连续列，如 H,K,N）"""
        return [self._get_sample_col(f'{i}#') for i in range(1, self._get_main_sample_count() + 1)]

    def _get_data_start_row(self):
        return self.config.get('data_start_row', DEFAULT_DATA_START_ROW)

    def _get_sample_row(self):
        return self.config.get('sample_row', DEFAULT_SAMPLE_ROW)

    def _get_max_data_row(self):
        """数据区最后一行：优先配置 max_data_row，否则扫描模板规格列连续数据的末尾
        （加 50 行缓冲，兼容新增测量项），扫描不到时回退默认值。"""
        configured = self.config.get('max_data_row')
        if configured:
            return int(configured)

        default_max = self._get_data_start_row() + 28  # 历史行为：起始行 + 28 行数据
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

    def _compute_required_max_row(self, items):
        """根据所有 PDF 解析出的最大测量编号，计算写入所需的最大行号。
        用于 batch_process_by_date 动态扩展上限，避免固定 buffer 截断有效数据。"""
        max_num = 0
        for item in items:
            for m in item['data'].get('measurements', []):
                if m['num'] > max_num:
                    max_num = m['num']
        if max_num == 0:
            return None
        return self._get_data_start_row() - 1 + max_num

    def pdf_to_image(self, pdf_path):
        with fitz_open_context(pdf_path) as doc:
            page = doc[0]
            pix = page.get_pixmap(dpi=self.dpi)
            img_name = f'{Path(pdf_path).stem}.png'
            img_path = str(CACHE_DIR / img_name)
            pix.save(img_path)
        return img_path

    def _cache_key(self, img_path: str) -> str:
        """生成缓存 key：完整路径的 MD5（避免同名 PDF 不同路径冲突）"""
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

    def parse_from_text(self, ocr_lines):
        text = '\n'.join(ocr_lines)
        data = {'part_name': '', 'date': '', 'measurements': []}
        warnings = []

        # 零件名
        m = re.search(r'零件名[：:]\s*\n?\s*(\S+)', text)
        if m:
            data['part_name'] = m.group(1).strip()
        else:
            warnings.append('未识别到零件名')

        # 日期（支持多种常见格式，按优先级尝试匹配）
        date_parsed = False
        # 格式1：ISO / 分隔符（2024-01-02、2024/01/02、2024.01.02）
        for sep in ('-', '/', '.'):
            m = re.search(rf'(\d{{4}})\{sep}(\d{{1,2}})\{sep}(\d{{1,2}})', text)
            if m:
                data['date'] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
                date_parsed = True
                break
        # 格式2：中文年/月/日（2024年1月2日）
        if not date_parsed:
            m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
            if m:
                data['date'] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
                date_parsed = True
        # 格式3：中文月份名（十二月 2, 2024）
        if not date_parsed:
            m = re.search(r'(一月|二月|三月|四月|五月|六月|七月|八月|九月|十月|十一月|十二月)\s*(\d{1,2}),?\s*(\d{4})', text)
            if m:
                month_num = month_cn_to_num(m.group(1))
                data['date'] = f"{m.group(3)}-{month_num}-{m.group(2).zfill(2)}"
                date_parsed = True
        if not date_parsed:
            warnings.append('未识别到日期')

        # 测量项
        current = None
        numbers = []
        prefix_pattern = '|'.join(re.escape(p) for p in ITEM_PREFIXES)
        for line in ocr_lines:
            line = line.strip()
            if not line:
                continue
            m = re.match(rf'(?:{prefix_pattern})[_\s]*(\d+)[-\s]*(.+)', line, re.IGNORECASE)
            if m:
                if current and len(numbers) >= 4:
                    upper = numbers[1]
                    lower = numbers[2]
                    if upper > 0 and lower > 0 and upper == lower:
                        logger.info(f'  [公差对称] FAI_{current["num"]:02d} 上下公差均为 {upper}，假设为对称公差（下公差设为 -{upper}）')
                        lower = -upper
                    data['measurements'].append({
                        'num': current['num'],
                        'desc': current['desc'],
                        'nominal': numbers[0],
                        'upper_tol': upper,
                        'lower_tol': lower,
                        'measured': numbers[3],
                        'ng': self._is_ng(numbers[0], upper, lower, numbers[3]),
                    })
                elif current and len(numbers) > 0 and len(numbers) < 4:
                    warnings.append(f'FAI_{current["num"]:02d} 数据不完整（只识别到 {len(numbers)} 个数字）')
                current = {'num': int(m.group(1)), 'desc': m.group(2).strip()}
                numbers = []
            else:
                if line in OCR_SKIP_LINES:
                    continue
                n = re.search(r'[-+]?\d+\.?\d*', line)
                if n:
                    token = n.group()
                    # 测量项行头后紧跟的纯整数是表格行号伪影（如 FAI_12 后的 '1'），
                    # 会把 理论值/公差/实测 4 数窗口整体错位，跳过。
                    # 本报告格式的测量值总带小数点；已对 52 份缓存样本回归验证零误伤。
                    if '.' not in token and not numbers:
                        continue
                    try:
                        numbers.append(float(token))
                    except (ValueError, TypeError) as e:
                        logger.debug(f'[OCR 解析] 无法将 "{token}" 转为浮点数: {e}')

        if current and len(numbers) >= 4:
            upper = numbers[1]
            lower = numbers[2]
            if upper > 0 and lower > 0 and upper == lower:
                logger.info(f'  [公差对称] FAI_{current["num"]:02d} 上下公差均为 {upper}，假设为对称公差（下公差设为 -{upper}）')
                lower = -upper
            data['measurements'].append({
                'num': current['num'],
                'desc': current['desc'],
                'nominal': numbers[0],
                'upper_tol': upper,
                'lower_tol': lower,
                'measured': numbers[3],
                'ng': self._is_ng(numbers[0], upper, lower, numbers[3]),
            })
        elif current and len(numbers) > 0:
            warnings.append(f'FAI_{current["num"]:02d} 数据不完整（只识别到 {len(numbers)} 个数字）')

        for w in warnings:
            logger.warning(w)

        return data

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
                img_path = self.pdf_to_image(str(pdf))
                ocr_lines = self.ocr_image(img_path)
                data = self.parse_from_text(ocr_lines)
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
                'error': None,
            })
        for f in result['failed']:
            items.append({
                'stem': None, 'name': f['file'], 'date': '', 'part_name': '',
                'ng_count': 0, 'measurements': [], 'error': f['error'],
            })
        return items

    def batch_process_by_date(self, pdf_folder, output_folder, progress_callback=None, excluded_measures=None):
        """
        按日期批量处理：
        - Sheet A: 样品1#-5#（001-005）
        - Sheet B: 样品6#+ 溢出样品（006-010），基于原始模板创建，保持格式一致
        - 忽略误操作文件（如 003-1.PDF）
        - excluded_measures: {pdf_stem: {measure_num, ...}}，这些 PDF 的对应测量项
          不写入实测值（用于预览时剔除误识别项）

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

        # 动态扩展上限：若所有 PDF 的测量编号所需行数超过模板扫描值，使用较大者
        required_max = self._compute_required_max_row(pdf_info)
        if required_max is not None and required_max > max_data_row:
            logger.info(f'[数据区扩展] {max_data_row} → {required_max}（根据测量编号自动扩展）')
            max_data_row = required_max

        excluded_measures = excluded_measures or {}
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

            # 按文件名排序，顺序分配样品编号
            items.sort(key=lambda x: x['path'].name)
            for idx, item in enumerate(items, start=1):
                item['sample_num'] = idx

            # 使用该日期组所有PDF的测量项合并后初始化标准模板
            # 先收集所有测量项，去重并按编号排序
            all_measurements = []
            seen_keys = set()
            for item in items:
                for m in item['data'].get('measurements', []):
                    key = (m['num'], m['nominal'], m['upper_tol'], m['lower_tol'])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_measurements.append(m)
            all_measurements.sort(key=lambda x: x['num'])

            # 生成标准模板（基于原始模板，填入完整的规格/公差）
            std_template = str(Path(self.template_path).with_name(f'标准模板_{date}_已填描述.xlsx'))
            wb = openpyxl.load_workbook(self.template_path)
            ws = wb[self._get_sheet_name()]

            # 基本信息（取第一个有零件名的PDF）
            part_name = ''
            date_str = date
            for item in items:
                if item['data'].get('part_name'):
                    part_name = item['data']['part_name']
                    break
            _write_cell(ws, self._get_field_location('part_name'), part_name)
            _write_cell(ws, self._get_field_location('date'), date_str)

            # 填入所有测量项的名义值、上公差、下公差
            filled = 0
            spec_col = column_index_from_string(self._get_column_letter("spec"))
            upper_col = column_index_from_string(self._get_column_letter("upper_tol"))
            lower_col = column_index_from_string(self._get_column_letter("lower_tol"))
            for item in all_measurements:
                row = data_start_row - 1 + item['num']
                if row > max_data_row:
                    logger.warning(f'[超出数据区] FAI_{item["num"]:02d} 落在行 {row}（数据区上限 {max_data_row}），已跳过')
                    continue
                ws.cell(row=row, column=spec_col, value=item['nominal'])
                ws.cell(row=row, column=upper_col, value=item['upper_tol'])
                ws.cell(row=row, column=lower_col, value=item['lower_tol'])
                filled += 1

            logger.info(f'[初始化完成] 已填入 {filled} 项规格/公差（来自 {len(items)} 个PDF）')

            # 4. 分离主样品(1#-N#)和溢出样品(N+1#+)；
            #    N = main_sample_count（可配置），Sheet B 与主表样品位数相同
            main_count = self._get_main_sample_count()
            sample_col_slots = self._get_sample_col_slots()
            main_samples = [item for item in items if 1 <= item['sample_num'] <= main_count]
            overflow_samples = [item for item in items if item['sample_num'] > main_count]

            # 溢出超过 Sheet B 容量时截断（每组最多 2×N 个样品），并明确告警
            overflow_capacity = main_count
            dropped_overflow = overflow_samples[overflow_capacity:]
            overflow_samples = overflow_samples[:overflow_capacity]
            for item in dropped_overflow:
                logger.warning(f'[样品位不足] {item["path"].name}（{item["sample_num"]}#）超出 Sheet B 容量，已跳过')
                summary['skipped_pdfs'].append(item['path'].name)

            logger.info(f'  主样品(1#-{main_count}#): {len(main_samples)} 个')
            logger.info(f'  溢出样品({main_count + 1}#+): {len(overflow_samples)} 个')

            # 5. 处理主样品（Sheet A），直接在内存中操作
            out_wb = wb
            out_ws = out_wb[self._get_sheet_name()]
            sample_row = self._get_sample_row()

            # 填入样品序号行
            for item in main_samples:
                sample_num = item['sample_num']
                sample_col = sample_col_slots[sample_num - 1]
                _write_cell(out_ws, f'{get_column_letter(sample_col)}{sample_row}', f'{sample_num:03d}')
                logger.info(f'  Sheet A: {item["path"].name} -> {sample_num}# (列{sample_col}, 序号{sample_num:03d})')

            # 填入实测值
            for item in main_samples:
                sample_num = item['sample_num']
                sample_col = sample_col_slots[sample_num - 1]
                for measure in item['data'].get('measurements', []):
                    if measure['num'] in excluded_measures.get(item['stem'], set()):
                        continue
                    row = data_start_row - 1 + measure['num']
                    if row > max_data_row:
                        logger.warning(f'[超出数据区] FAI_{measure["num"]:02d} 落在行 {row}（数据区上限 {max_data_row}），已跳过')
                        continue
                    out_ws.cell(row=row, column=sample_col, value=measure['measured'])

            # 6. 处理溢出样品（Sheet B，放在 Sheet A 后面，保持格式一致）
            if overflow_samples:
                # 使用 copy_worksheet 从 Sheet A 复制到 Sheet B，保持格式一致
                sheet_b = out_wb.copy_worksheet(out_wb[self._get_sheet_name()])
                sheet_b_name = self._get_sheet_b_name()
                sheet_b.title = sheet_b_name

                # 调整 Sheet 顺序为 A, B, CPK（B 在 A 后面，CPK 最后）
                # CPK 不是必须的，只在存在时调整顺序
                sheets = out_wb._sheets
                b_sheet = next(s for s in sheets if s.title == sheet_b_name)
                b_idx = sheets.index(b_sheet)
                cpk_sheets = [s for s in sheets if s.title == 'CPK']
                if cpk_sheets:
                    cpk_idx = sheets.index(cpk_sheets[0])
                    if b_idx > cpk_idx:
                        sheets[b_idx], sheets[cpk_idx] = sheets[cpk_idx], sheets[b_idx]

                # 彻底清空样品序号行（按样品位列遍历，支持非连续列）
                for col in sample_col_slots:
                    _write_cell(sheet_b, f'{get_column_letter(col)}{sample_row}', None)

                # 清空所有实测值列（样品位列，数据区范围）
                for row in range(self._get_data_start_row(), max_data_row + 1):
                    for col in sample_col_slots:
                        cell = sheet_b.cell(row=row, column=col)
                        cell.value = None

                # 填入溢出样品：按顺序占用样品位（第1个溢出→1#位，第2个→2#位…）
                for slot_idx, item in enumerate(overflow_samples):
                    sample_num = item['sample_num']
                    sample_col = sample_col_slots[slot_idx]
                    _write_cell(sheet_b, f'{get_column_letter(sample_col)}{sample_row}', f'{sample_num:03d}')
                    logger.info(f'  Sheet B: {item["path"].name} -> {sample_num}# (列{sample_col}, 序号{sample_num:03d})')

                # 填入实测值（同样按样品位映射，避免覆盖）
                for slot_idx, item in enumerate(overflow_samples):
                    sample_col = sample_col_slots[slot_idx]
                    for measure in item['data'].get('measurements', []):
                        if measure['num'] in excluded_measures.get(item['stem'], set()):
                            continue
                        row = data_start_row - 1 + measure['num']
                        if row > max_data_row:
                            logger.warning(f'[超出数据区] FAI_{measure["num"]:02d} 落在行 {row}（数据区上限 {max_data_row}），已跳过')
                            continue
                        sheet_b.cell(row=row, column=sample_col, value=measure['measured'])

            # 保存
            out_path = str(Path(output_folder) / f'{date}_项目汇总.xlsx')
            self._safe_save(out_wb, out_path)
            wb.close()
            summary['output_files'].append(out_path)
            logger.info(f'  [完成] {out_path}')

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
                img_path = self.pdf_to_image(str(pdf))
                ocr_lines = self.ocr_image(img_path)
                data = self.parse_from_text(ocr_lines)
                for m in data.get('measurements', []):
                    key = (m['num'], m['nominal'], m['upper_tol'], m['lower_tol'])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_measurements.append(m)
                summary['processed_pdfs'] += 1
            except Exception as e:
                logger.error(f'[导出失败] {pdf.name}: {e}')
                summary['failed_pdfs'].append({'file': pdf.name, 'error': str(e)})

        _report(total, total, '写入标准模板...')

        all_measurements.sort(key=lambda x: x['num'])

        wb = openpyxl.load_workbook(self.template_path)
        ws = wb[self._get_sheet_name()]

        spec_col = column_index_from_string(self._get_column_letter("spec"))
        upper_col = column_index_from_string(self._get_column_letter("upper_tol"))
        lower_col = column_index_from_string(self._get_column_letter("lower_tol"))

        filled = 0
        for item in all_measurements:
            row = data_start_row - 1 + item['num']
            if row > max_data_row:
                logger.warning(f'[超出数据区] FAI_{item["num"]:02d} 落在行 {row}（数据区上限 {max_data_row}），已跳过')
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
                img_path = self.pdf_to_image(str(pdf))
                ocr_lines = self.ocr_image(img_path)
                data = self.parse_from_text(ocr_lines)
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
            measures = sorted(data.get('measurements', []), key=lambda m: m['num'])
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
