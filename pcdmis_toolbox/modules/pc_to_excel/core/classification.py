"""拆分自 data_extractor.py — 记录分类与统计。"""

from __future__ import annotations

from enum import Enum

from .models import FeatureRecord


# 用户关心的 11 类元素 — 顺序从具体到一般（避免「圆柱」被「圆」抢先匹配）
_FEATURE_ELEMENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("圆柱", ("圆柱", "CYLINDER")),
    ("圆锥", ("圆锥", "CONE")),
    ("圆槽", ("圆槽", "ROUND SLOT", "ROUND_SLOT")),
    ("方槽", ("方槽", "SQUARE SLOT", "SQUARE_SLOT")),
    ("凹口槽", ("凹口", "开槽", "OPEN SLOT", "NOTCH")),
    ("椭圆", ("椭圆", "ELLIPSE")),
    ("多边形", ("多边形", "POLYGON")),
    ("球", ("球", "SPHERE")),
    ("直线", ("直线", "LINE")),
    ("平面", ("平面", "PLANE")),
    ("圆", ("圆", "CIRCLE")),
)


def normalize_feature_element(type_name: str) -> str | None:
    """将 PCDMIS FeatType 归一化为 11 类元素名，无法识别时返回 None。

    使用逐 token 精确匹配（大小写不敏感），避免子串误匹配导致
    "CIRCLE" 匹配到 "AUTOCIRCLE"、"SLOT" 匹配到 "KEY_SLOT" 等问题。
    """
    type_name = type_name or ""
    # 将类型名按常见分隔符拆分为 token，支持 "ROUND_SLOT" / "ROUND SLOT" 等格式
    tokens = type_name.replace("/", " ").replace("_", " ").replace("-", " ").split()
    upper_tokens = {t.upper() for t in tokens}
    for label, keywords in _FEATURE_ELEMENT_KEYWORDS:
        for kw in keywords:
            if kw.upper() in upper_tokens:
                return label
    return None


def summarize_extraction(records: list[FeatureRecord]) -> dict[str, int]:
    """按 feature_type 统计提取结果。"""
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec.feature_type] = counts.get(rec.feature_type, 0) + 1
    return counts


def summarize_dimension_records(records: list[FeatureRecord]) -> dict[str, int]:
    """统计评价尺寸（含 2D 距离 / 位置 / 半径位置等）。"""
    counts: dict[str, int] = {}
    for rec in records:
        if not is_dimension_record(rec):
            continue
        counts[rec.feature_type] = counts.get(rec.feature_type, 0) + 1
    return counts


def is_dimension_record(rec: FeatureRecord) -> bool:
    """判断是否为 Legacy 评价尺寸（非特征、非 ToleranceCommand）。"""
    ftype = rec.feature_type or ""
    if rec.source_kind in ("assign", "datum", "prg_offline"):
        return False
    if ftype.startswith("TOLERANCE_") or ftype == "DATUM" or ftype.startswith("FCF_"):
        return False
    if ftype in ("终止尺寸", "基准定义", "尺寸格式"):
        return False
    keywords = (
        "尺寸",
        "距离",
        "位置",
        "半径",
        "半角",
        "直径",
        "角度",  # 尺寸3D 角度 / 圆锥角度
        "DIMENSION",
    )
    return any(k in ftype for k in keywords)


class RecordCategory(str, Enum):
    """GUI / 导出用业务分类。"""

    FEATURE = "特征"
    EVALUATED_DIM = "已评价尺寸"
    GDT = "形位公差"
    SIZE_DIM = "大小尺寸"
    DATUM = "基准"
    CALCULATED = "计算尺寸"


RECORD_CATEGORY_ORDER: tuple[str, ...] = (
    "全部",
    RecordCategory.FEATURE.value,
    RecordCategory.EVALUATED_DIM.value,
    RecordCategory.GDT.value,
    RecordCategory.SIZE_DIM.value,
    RecordCategory.DATUM.value,
    RecordCategory.CALCULATED.value,
)


def classify_record(rec: FeatureRecord) -> RecordCategory:
    """将单条记录归入业务分类。"""
    ftype = rec.feature_type or ""
    if rec.source_kind == "datum" or ftype == "DATUM":
        return RecordCategory.DATUM
    if rec.source_kind == "assign" or "计算" in ftype or "ASSIGN" in ftype.upper():
        return RecordCategory.CALCULATED
    if ftype in ("FCF_SIZE", "TOLERANCE_SIZE"):
        return RecordCategory.SIZE_DIM
    if ftype.startswith("TOLERANCE_") or (
        ftype.startswith("FCF_") and ftype not in ("FCF_SIZE", "FCF_OFFLINE")
    ):
        return RecordCategory.GDT
    if is_dimension_record(rec):
        return RecordCategory.EVALUATED_DIM
    return RecordCategory.FEATURE


def summarize_by_category(records: list[FeatureRecord]) -> dict[str, int]:
    """按业务分类统计条数。"""
    counts: dict[str, int] = {}
    for rec in records:
        key = classify_record(rec).value
        counts[key] = counts.get(key, 0) + 1
    return counts


def parse_category_filter(label: str) -> str:
    """从「已评价尺寸 (11)」解析出分类名。"""
    text = (label or "全部").strip()
    if text == "全部":
        return "全部"
    for name in RECORD_CATEGORY_ORDER[1:]:
        if text == name or text.startswith(f"{name} ("):
            return name
    return "全部"


def category_filter_options(records: list[FeatureRecord]) -> list[str]:
    """生成分类下拉选项（含条数）。"""
    counts = summarize_by_category(records)
    total = len(records)
    options = [f"全部 ({total})" if total else "全部"]
    for name in RECORD_CATEGORY_ORDER[1:]:
        n = counts.get(name, 0)
        options.append(f"{name} ({n})" if n else name)
    return options


def matches_evaluated_dim_group(feature_type: str, group: str) -> bool:
    """已评价尺寸子类：距离 / 位置 / 半径 / 夹角。"""
    ftype = feature_type or ""
    if group == "距离":
        return "距离" in ftype
    if group == "位置":
        return ftype == "尺寸位置"
    if group == "半径":
        return "半径" in ftype
    if group == "夹角":
        return "半角" in ftype or "夹角" in ftype
    return ftype == group


def summarize_feature_elements(records: list[FeatureRecord]) -> dict[str, int]:
    """统计 11 类基础元素覆盖（仅 IsFeature 类记录）。"""
    counts: dict[str, int] = {}
    for rec in records:
        element = normalize_feature_element(rec.feature_type)
        if element is None:
            continue
        counts[element] = counts.get(element, 0) + 1
    return counts
