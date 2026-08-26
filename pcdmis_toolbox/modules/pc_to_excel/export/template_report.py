"""导出入口 — 统一走 PC-DMIS 列格式。"""


from __future__ import annotations



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

    """导出 Excel。template_path 已废弃，保留参数以兼容旧调用。"""

    _ = template_path, tolerance

    return export_pcdmis_excel(

        features,

        output_path,

        header=header,

        part_name=part_name,

        program_path=program_path,

    )


