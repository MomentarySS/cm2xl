"""导出入口 — 统一走 PC-DMIS 列格式。"""


from __future__ import annotations


import warnings
from pathlib import Path


from ..core.models import FeatureRecord
from .pcdmis_style_report import export_pcdmis_excel


def export_report(
    features: list[FeatureRecord],
    output_path: Path,
    template_path: Path | None = None,
    part_name: str = "",
    program_path: str = "",
    tolerance=None,
    header=None,
) -> Path:
    """导出 Excel（PCDMIS 列格式）。

    Args:
        features: 特征记录列表
        output_path: 输出 Excel 路径
        template_path: **已废弃**，传入非 None 值会发出警告
        tolerance: **已废弃**，传入非 None 值会发出警告
        part_name: 件号/零件名称
        program_path: 程序路径
        header: 报告头信息

    Returns:
        生成的 Excel 文件路径
    """
    if template_path is not None:
        warnings.warn(
            "template_path 参数已废弃，Excel 导出不再支持模板模式，将忽略此参数。",
            DeprecationWarning,
            stacklevel=2,
        )
    if tolerance is not None:
        warnings.warn(
            "tolerance 参数已废弃，将忽略此参数。",
            DeprecationWarning,
            stacklevel=2,
        )

    return export_pcdmis_excel(
        features,
        output_path,
        header=header,
        part_name=part_name,
        program_path=program_path,
    )



