"""出货检测表按序号匹配填入 — 只写 CMM 行，不改动其它检具行。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from ..core.models import FeatureRecord
from .pcdmis_style_report import flatten_to_pcdmis_rows

_DEFAULT_PREFIXES = ("FAI_", "CC_", "尺寸_")
_DEFAULT_CMM_CODES = ("A", "CMM")
MANUAL_MAP_PLACEHOLDER = "示例：FAI_17A=17.1; POS_A=34（分号分隔，可按需改）"
_MAP_LINE_RE = re.compile(
    r"^\s*([^=:：>]+?)\s*(?:=|:|：|->|→)\s*([^=:：>]+?)\s*$"
)


@dataclass
class FormFillConfig:
    """出货表填入配置（均可自定义）。"""

    enabled: bool = True
    form_path: str = ""
    id_prefixes: list[str] = field(default_factory=lambda: list(_DEFAULT_PREFIXES))
    cmm_codes: list[str] = field(default_factory=lambda: list(_DEFAULT_CMM_CODES))
    serial_col: str = "A"
    instrument_col: str = "G"
    data_start_col: str = "H"
    spec_col: str = "B"
    target_col: str = "auto"  # "auto" | "H" | "I" | ...
    hyphen_to_dot: bool = True
    manual_map: dict[str, str] = field(default_factory=dict)
    manual_map_text: str = ""
    header_scan_row: int = 5
    data_start_row: int = 6
    chain_from_last: bool = True
    last_fill_output: str = ""
    write_piece_id: bool = True
    piece_id: str = ""
    nominal_check: bool = True
    nominal_tol: float = 0.05

    @classmethod
    def from_dict(cls, data: dict | None) -> "FormFillConfig":
        data = data or {}
        prefixes = data.get("id_prefixes")
        codes = data.get("cmm_codes")
        manual_text = str(data.get("manual_map_text", "") or "")
        manual = data.get("manual_map") or {}
        if manual_text.strip():
            manual = parse_manual_map_text(manual_text)
        elif manual:
            manual = {str(k): _normalize_serial(v) for k, v in dict(manual).items()}
        return cls(
            enabled=bool(data.get("enabled", True)),
            form_path=str(data.get("form_path", "") or ""),
            id_prefixes=[str(p) for p in prefixes] if prefixes else list(_DEFAULT_PREFIXES),
            cmm_codes=[str(c).strip().upper() for c in codes] if codes else list(_DEFAULT_CMM_CODES),
            serial_col=str(data.get("serial_col", "A") or "A").upper(),
            instrument_col=str(data.get("instrument_col", "G") or "G").upper(),
            data_start_col=str(data.get("data_start_col", "H") or "H").upper(),
            spec_col=str(data.get("spec_col", "B") or "B").upper(),
            target_col=str(data.get("target_col", "auto") or "auto").strip().lower(),
            hyphen_to_dot=bool(data.get("hyphen_to_dot", True)),
            manual_map=manual,
            manual_map_text=manual_text or format_manual_map_text(manual),
            header_scan_row=int(data.get("header_scan_row", 5) or 5),
            data_start_row=int(data.get("data_start_row", 6) or 6),
            chain_from_last=bool(data.get("chain_from_last", True)),
            last_fill_output=str(data.get("last_fill_output", "") or ""),
            write_piece_id=bool(data.get("write_piece_id", True)),
            piece_id=str(data.get("piece_id", "") or ""),
            nominal_check=bool(data.get("nominal_check", True)),
            nominal_tol=float(data.get("nominal_tol", 0.05) or 0.05),
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "form_path": self.form_path,
            "id_prefixes": list(self.id_prefixes),
            "cmm_codes": list(self.cmm_codes),
            "serial_col": self.serial_col,
            "instrument_col": self.instrument_col,
            "data_start_col": self.data_start_col,
            "spec_col": self.spec_col,
            "target_col": self.target_col,
            "hyphen_to_dot": self.hyphen_to_dot,
            "manual_map": dict(self.manual_map),
            "manual_map_text": self.manual_map_text,
            "header_scan_row": self.header_scan_row,
            "data_start_row": self.data_start_row,
            "chain_from_last": self.chain_from_last,
            "last_fill_output": self.last_fill_output,
            "write_piece_id": self.write_piece_id,
            "piece_id": self.piece_id,
            "nominal_check": self.nominal_check,
            "nominal_tol": self.nominal_tol,
        }

    def effective_manual_map(self) -> dict[str, str]:
        if self.manual_map_text.strip():
            return parse_manual_map_text(self.manual_map_text)
        return dict(self.manual_map)

    def resolve_input_form(self) -> tuple[Path | None, bool]:
        """返回 (输入表路径, 是否来自上次续填)。

        链式文件会验证扩展名（.xlsx/.xlsm）并在无法作为 Excel 打开时发出警告。
        """
        if self.chain_from_last and self.last_fill_output.strip():
            last = Path(self.last_fill_output)
            if last.is_file():
                # 验证扩展名，排除损坏或被替换为非 Excel 文件的情况
                if last.suffix.lower() not in (".xlsx", ".xlsm"):
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.warning(
                        "上次续填输出 %s 不是 Excel 文件（扩展名 %s），"
                        "将回退到 --form 指定路径。",
                        last,
                        last.suffix,
                    )
                else:
                    # 扩展名正确后，尝试用 openpyxl 加载验证文件完整性
                    try:
                        load_workbook(last, read_only=True, data_only=True)
                        return last, True
                    except Exception as exc:
                        import logging

                        logger = logging.getLogger(__name__)
                        logger.warning(
                            "上次续填输出 %s 无法作为 Excel 打开（%s），"
                            "将回退到 --form 指定路径。请确认文件未损坏，"
                            "或用 --reset-chain 重新开始。",
                            last,
                            exc,
                        )
        if self.form_path.strip():
            path = Path(self.form_path)
            if path.is_file():
                return path, False
        return None, False


def default_form_fill_config() -> FormFillConfig:
    """出货表常用默认（前缀 / CMM 代号 / auto 续列）。"""
    return FormFillConfig(
        enabled=True,
        id_prefixes=list(_DEFAULT_PREFIXES),
        cmm_codes=list(_DEFAULT_CMM_CODES),
        target_col="auto",
        hyphen_to_dot=True,
        manual_map={},
        manual_map_text="",
        chain_from_last=True,
        write_piece_id=True,
        nominal_check=True,
        nominal_tol=0.05,
    )


@dataclass
class FormFillResult:
    output_path: Path
    filled: int = 0
    skipped_not_cmm: int = 0
    unmatched_form: list[str] = field(default_factory=list)
    unmatched_pcdmis: list[str] = field(default_factory=list)
    nominal_warnings: list[str] = field(default_factory=list)
    target_col: str = ""
    source_path: Path | None = None
    chained: bool = False
    piece_id_written: str = ""


@dataclass
class FormFillPreview:
    """填入前预览（不写文件）。"""

    form_path: Path
    chained: bool = False
    target_col: str = ""
    cmm_rows: int = 0
    will_fill: int = 0
    extract_count: int = 0
    piece_id: str = ""
    write_piece_id: bool = False
    unmatched_form: list[str] = field(default_factory=list)
    unmatched_pcdmis: list[str] = field(default_factory=list)
    nominal_warnings: list[str] = field(default_factory=list)
    serial_conflicts: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        mode = "续填" if self.chained else "新开"
        lines = [
            f"模式：{mode}",
            f"底稿：{self.form_path.name}",
            f"写入列：{self.target_col or '?'}",
            f"CMM 行：{self.cmm_rows}　预计填入：{self.will_fill} / 提取 {self.extract_count}",
        ]
        if self.write_piece_id:
            lines.append(f"件号：{self.piece_id or '（空，将不写或用序列号）'}")
        if self.serial_conflicts:
            lines.append(f"序号冲突（后写覆盖）：{len(self.serial_conflicts)} 项")
            lines.extend(f"  - {x}" for x in self.serial_conflicts[:8])
        if self.unmatched_form:
            lines.append(f"表中暂无测量值：{len(self.unmatched_form)} 项")
            lines.extend(f"  - {x}" for x in self.unmatched_form[:12])
            if len(self.unmatched_form) > 12:
                lines.append("  - …")
        if self.unmatched_pcdmis:
            lines.append(f"测量多余序号：{len(self.unmatched_pcdmis)} 项")
            lines.extend(f"  - {x}" for x in self.unmatched_pcdmis[:8])
        if self.nominal_warnings:
            lines.append(f"规格/名义差异：{len(self.nominal_warnings)} 项")
            lines.extend(f"  - {x}" for x in self.nominal_warnings[:8])
        lines.append("")
        lines.append("确认后将另存副本（不覆盖底稿）。")
        return "\n".join(lines)


def parse_manual_map_text(text: str) -> dict[str, str]:
    """解析手工对照：每行或分号分隔 `FAI_17A=17.1` / `FAI_17A:17.1` / `FAI_17A->17.1`。"""
    result: dict[str, str] = {}
    if not text or not str(text).strip():
        return result
    chunks = re.split(r"[\n;；]+", str(text))
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or chunk.startswith("#"):
            continue
        match = _MAP_LINE_RE.match(chunk)
        if not match:
            continue
        key = match.group(1).strip()
        serial = _normalize_serial(match.group(2))
        if key and serial:
            result[key] = serial
    return result


def format_manual_map_text(mapping: dict[str, str]) -> str:
    if not mapping:
        return ""
    return "\n".join(f"{k}={v}" for k, v in mapping.items())


def _normalize_serial(value) -> str:
    """统一序号：1 / 1.0 / '12.1' / '12-1' → 可比对字符串。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return text
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("－", "-").replace("—", "-")
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def dim_name_to_serial(
    name: str,
    prefixes: list[str] | tuple[str, ...] | None = None,
    hyphen_to_dot: bool = True,
    manual_map: dict[str, str] | None = None,
) -> str:
    """PCDMIS 尺寸名 → 出货表序号。例：FAI_12-1 / CC_1 / 尺寸_1 → 12.1 / 1 / 1。"""
    raw = (name or "").strip()
    if not raw:
        return ""

    if manual_map:
        for key, serial in manual_map.items():
            if key and raw.upper() == str(key).upper():
                return _normalize_serial(serial)

    if "-" in raw:
        base, suffix = raw.rsplit("-", 1)
        if any("\u4e00" <= ch <= "\u9fff" for ch in suffix):
            raw = base.strip()

    body = raw
    prefs = list(prefixes) if prefixes is not None else list(_DEFAULT_PREFIXES)
    prefs = sorted((p for p in prefs if p), key=len, reverse=True)
    upper = body.upper()
    for pref in prefs:
        if upper.startswith(pref.upper()):
            body = body[len(pref) :]
            break

    body = body.strip()
    if hyphen_to_dot:
        body = re.sub(r"(?<=\d)-(?=\d)", ".", body)
    return _normalize_serial(body)


def _primary_measured(rec: FeatureRecord) -> float | None:
    rows = flatten_to_pcdmis_rows(rec)
    for row in rows:
        if row.measured is not None:
            return float(row.measured)
    return None


def _primary_nominal(rec: FeatureRecord) -> float | None:
    rows = flatten_to_pcdmis_rows(rec)
    for row in rows:
        if row.nominal is not None:
            return float(row.nominal)
    return None


def build_serial_value_maps(
    features: list[FeatureRecord],
    config: FormFillConfig,
) -> tuple[dict[str, float], dict[str, float], list[str]]:
    """返回 (序号→实测, 序号→名义, 冲突说明)。同序号多值时后写覆盖并记冲突。"""
    measured_map: dict[str, float] = {}
    nominal_map: dict[str, float] = {}
    owners: dict[str, str] = {}
    conflicts: list[str] = []
    manual = config.effective_manual_map()
    for rec in features:
        serial = dim_name_to_serial(
            rec.name,
            prefixes=config.id_prefixes,
            hyphen_to_dot=config.hyphen_to_dot,
            manual_map=manual,
        )
        if not serial:
            continue
        measured = _primary_measured(rec)
        if measured is not None:
            prev = measured_map.get(serial)
            if prev is not None and abs(prev - measured) > 1e-9:
                conflicts.append(
                    f"{serial}: {owners.get(serial, '?')}={prev} → {rec.name}={measured}"
                )
            measured_map[serial] = measured
            owners[serial] = rec.name
        nominal = _primary_nominal(rec)
        if nominal is not None:
            nominal_map[serial] = nominal
    return measured_map, nominal_map, conflicts


def build_serial_measured_map(
    features: list[FeatureRecord],
    config: FormFillConfig,
) -> dict[str, float]:
    measured, _, _ = build_serial_value_maps(features, config)
    return measured


def _col_index(letter: str) -> int:
    return column_index_from_string(letter.strip().upper())


def _is_cmm_code(value, codes: list[str]) -> bool:
    if value is None:
        return False
    text = str(value).strip().upper()
    if not text:
        return False
    allowed = {c.strip().upper() for c in codes if c and str(c).strip()}
    return text in allowed


def _as_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _column_has_cmm_data(ws, col: int, candidate_rows: list[int]) -> bool:
    for row in candidate_rows:
        val = ws.cell(row, col).value
        if val is not None and str(val).strip() != "":
            return True
    return False


def _resolve_target_col(ws, config: FormFillConfig, candidate_rows: list[int]) -> int:
    """返回 1-based 列号。auto：优先选全空列，其次半数空列，避免覆盖已有实测。"""
    start = _col_index(config.data_start_col)
    mode = (config.target_col or "auto").strip().lower()
    if mode and mode != "auto":
        return _col_index(mode)

    header_row = config.header_scan_row
    max_col = max(ws.max_column or start, start + 20)
    for col in range(start, max_col + 1):
        header_val = ws.cell(header_row, col).value
        header_empty = header_val is None or str(header_val).strip() == ""
        if header_empty and not _column_has_cmm_data(ws, col, candidate_rows):
            return col

    # 优先查找全空的 CMM 列（完全不动已有数据）
    for col in range(start, max_col + 8):
        empty = 0
        for row in candidate_rows:
            val = ws.cell(row, col).value
            if val is None or str(val).strip() == "":
                empty += 1
        if candidate_rows and empty == len(candidate_rows):
            return col

    # 全空列找不到时，退而求其次：选半数空（仍有空间）且无实测的列
    for col in range(start, max_col + 8):
        empty = 0
        for row in candidate_rows:
            val = ws.cell(row, col).value
            if val is None or str(val).strip() == "":
                empty += 1
        if (
            candidate_rows
            and empty >= max(1, len(candidate_rows) // 2)
            and not _column_has_cmm_data(ws, col, candidate_rows)
        ):
            return col

    # 全部有数据时追加新列，绝不覆盖
    return max_col + 1


def preview_form_fill(
    features: list[FeatureRecord],
    form_path: Path,
    config: FormFillConfig | None = None,
    *,
    piece_id: str = "",
    chained: bool = False,
) -> FormFillPreview:
    """扫描出货表与测量结果，生成填入预览（不写盘）。"""
    cfg = config or FormFillConfig()
    if not form_path.is_file():
        raise FileNotFoundError(f"出货检测表不存在: {form_path}")

    measured_map, nominal_map, serial_conflicts = build_serial_value_maps(features, cfg)
    unmatched_form: list[str] = []
    nominal_warnings: list[str] = []
    used: set[str] = set()
    cmm_rows_total = 0
    will_fill = 0
    target_letter = ""
    piece = (piece_id or cfg.piece_id or "").strip()

    # 与写入同一打开方式，避免 data_only 导致预览与实写不一致
    wb = load_workbook(form_path)
    try:
        for ws in wb.worksheets:
            serial_col = _col_index(cfg.serial_col)
            inst_col = _col_index(cfg.instrument_col)
            spec_col = _col_index(cfg.spec_col)
            cmm_rows: list[int] = []
            row_serials: dict[int, str] = {}
            row_specs: dict[int, float | None] = {}

            # 表头行关键字检测（仅 header_scan_row，不检查数据行）
            header_val = ws.cell(cfg.header_scan_row, serial_col).value
            if isinstance(header_val, str) and any(
                k in header_val for k in ("检验", "判定", "检具", "OK/NG")
            ):
                # 序号列表头包含关键字，说明第 5 列（如"检验员"）被误认为序号；
                # 这种情况极少见，按原逻辑跳过即可，不影响数据行
                pass

            for row in range(cfg.data_start_row, (ws.max_row or cfg.data_start_row) + 1):
                serial = _normalize_serial(ws.cell(row, serial_col).value)
                if not serial:
                    continue
                if not _is_cmm_code(ws.cell(row, inst_col).value, cfg.cmm_codes):
                    continue
                cmm_rows.append(row)
                row_serials[row] = serial
                row_specs[row] = _as_float(ws.cell(row, spec_col).value)

            if not cmm_rows:
                continue

            target_col = _resolve_target_col(ws, cfg, cmm_rows)
            target_letter = get_column_letter(target_col)
            cmm_rows_total += len(cmm_rows)

            for row in cmm_rows:
                serial = row_serials[row]
                if serial not in measured_map:
                    unmatched_form.append(f"{ws.title}:{serial}")
                    continue
                will_fill += 1
                used.add(serial)
                if cfg.nominal_check and serial in nominal_map:
                    form_nom = row_specs.get(row)
                    pcd_nom = nominal_map[serial]
                    if form_nom is not None and abs(form_nom - pcd_nom) > abs(cfg.nominal_tol):
                        nominal_warnings.append(
                            f"{ws.title}:{serial} 表规格={form_nom} / PCDMIS名义={pcd_nom}"
                        )
    finally:
        wb.close()

    unmatched_pcdmis = sorted(s for s in measured_map if s not in used)
    return FormFillPreview(
        form_path=form_path,
        chained=chained,
        target_col=target_letter,
        cmm_rows=cmm_rows_total,
        will_fill=will_fill,
        extract_count=len(features),
        piece_id=piece,
        write_piece_id=bool(cfg.write_piece_id and piece),
        unmatched_form=unmatched_form,
        unmatched_pcdmis=unmatched_pcdmis,
        nominal_warnings=nominal_warnings,
        serial_conflicts=serial_conflicts,
    )


def fill_inspection_form(
    features: list[FeatureRecord],
    form_path: Path,
    output_path: Path,
    config: FormFillConfig | None = None,
    piece_id: str | None = None,
) -> FormFillResult:
    """复制出货表并按序号填入 CMM 实测；非 CMM 行与未匹配行一律不动。"""
    cfg = config or FormFillConfig()
    if not form_path.is_file():
        raise FileNotFoundError(f"出货检测表不存在: {form_path}")
    if Path(output_path).resolve() == Path(form_path).resolve():
        raise ValueError(
            "输出路径与出货表底稿相同，拒绝覆盖。请另存副本（换输出目录或文件名）。"
        )

    measured_map, nominal_map, _conflicts = build_serial_value_maps(features, cfg)
    used_serials: set[str] = set()
    filled = 0
    skipped_not_cmm = 0
    unmatched_form: list[str] = []
    nominal_warnings: list[str] = []
    piece = (piece_id if piece_id is not None else cfg.piece_id).strip()
    piece_written = ""

    wb = load_workbook(form_path)
    target_letter = ""

    for ws in wb.worksheets:
        serial_col = _col_index(cfg.serial_col)
        inst_col = _col_index(cfg.instrument_col)
        spec_col = _col_index(cfg.spec_col)
        cmm_rows: list[int] = []
        row_serials: dict[int, str] = {}

        # 表头行关键字检测（仅 header_scan_row，不检查数据行）
        header_val = ws.cell(cfg.header_scan_row, serial_col).value
        if isinstance(header_val, str) and any(
            k in header_val for k in ("检验", "判定", "检具", "OK/NG")
        ):
            pass

        for row in range(cfg.data_start_row, (ws.max_row or cfg.data_start_row) + 1):
            serial = _normalize_serial(ws.cell(row, serial_col).value)
            if not serial:
                continue
            inst = ws.cell(row, inst_col).value
            if not _is_cmm_code(inst, cfg.cmm_codes):
                skipped_not_cmm += 1
                continue
            cmm_rows.append(row)
            row_serials[row] = serial

        if not cmm_rows:
            continue

        target_col = _resolve_target_col(ws, cfg, cmm_rows)
        target_letter = get_column_letter(target_col)

        if cfg.write_piece_id and piece and not piece_written:
            ws.cell(cfg.header_scan_row, target_col).value = piece
            piece_written = piece

        for row in cmm_rows:
            serial = row_serials[row]
            if serial not in measured_map:
                unmatched_form.append(f"{ws.title}:{serial}")
                continue
            value = measured_map[serial]
            ws.cell(row, target_col).value = round(float(value), 4)
            used_serials.add(serial)
            filled += 1

            if cfg.nominal_check and serial in nominal_map:
                form_nom = _as_float(ws.cell(row, spec_col).value)
                pcd_nom = nominal_map[serial]
                if form_nom is not None and abs(form_nom - pcd_nom) > abs(cfg.nominal_tol):
                    nominal_warnings.append(
                        f"{ws.title}:{serial} 表规格={form_nom} / PCDMIS名义={pcd_nom}"
                    )

    unmatched_pcdmis = sorted(s for s in measured_map if s not in used_serials)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return FormFillResult(
        output_path=output_path,
        filled=filled,
        skipped_not_cmm=skipped_not_cmm,
        unmatched_form=unmatched_form,
        unmatched_pcdmis=unmatched_pcdmis,
        nominal_warnings=nominal_warnings,
        target_col=target_letter,
        source_path=form_path,
        piece_id_written=piece_written,
    )


def default_fill_output_path(form_path: Path, export_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return export_dir / f"{form_path.stem}_CMM填入_{stamp}.xlsx"


def summarize_fill_result(result: FormFillResult, extract_count: int = 0) -> str:
    """生成可复制的填入结果摘要。"""
    src = result.source_path.name if result.source_path else "?"
    mode = "续填" if result.chained else "新开"
    lines = [
        f"模式：{mode}（底稿 {src}）",
        f"写入列：{result.target_col or '?'}",
        f"填入格数：{result.filled}",
    ]
    if extract_count:
        lines.insert(1, f"PCDMIS 提取：{extract_count} 条")
    if result.piece_id_written:
        lines.append(f"件号已写入表头行：{result.piece_id_written}")
    lines.append(f"输出：{result.output_path}")
    if result.unmatched_form:
        lines.append("")
        lines.append(f"表中未匹配（{len(result.unmatched_form)}）：")
        lines.extend(f"  - {x}" for x in result.unmatched_form)
    if result.unmatched_pcdmis:
        lines.append("")
        lines.append(f"测量多余序号（{len(result.unmatched_pcdmis)}）：")
        lines.extend(f"  - {x}" for x in result.unmatched_pcdmis)
    if result.nominal_warnings:
        lines.append("")
        lines.append(f"规格/名义差异警告（{len(result.nominal_warnings)}）：")
        lines.extend(f"  - {x}" for x in result.nominal_warnings)
    return "\n".join(lines)
