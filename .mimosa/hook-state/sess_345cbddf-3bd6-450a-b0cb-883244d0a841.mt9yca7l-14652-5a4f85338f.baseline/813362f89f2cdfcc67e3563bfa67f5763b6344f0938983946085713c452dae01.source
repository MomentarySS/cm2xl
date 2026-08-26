"""统一测量数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PassStatus(str, Enum):
    PASS = "合格"
    FAIL = "超差"
    NA = "—"


TOLERANCE_VALUE_KEYS: tuple[str, ...] = (
    "x", "y", "z", "d", "length", "width", "height", "angle", "minor_d"
)

EXTRA_VALUE_LABELS: dict[str, str] = {
    "length": "L",
    "width": "W",
    "height": "H",
    "angle": "A",
    "minor_d": "MD",
    "i": "I",
    "j": "J",
    "k": "K",
}


@dataclass
class AxisValues:
    x: float | None = None
    y: float | None = None
    z: float | None = None
    d: float | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None
    angle: float | None = None
    minor_d: float | None = None
    i: float | None = None
    j: float | None = None
    k: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AxisValues":
        if not data:
            return cls()
        return cls(
            x=data.get("x"),
            y=data.get("y"),
            z=data.get("z"),
            d=data.get("d"),
            length=data.get("length"),
            width=data.get("width"),
            height=data.get("height"),
            angle=data.get("angle"),
            minor_d=data.get("minor_d"),
            i=data.get("i"),
            j=data.get("j"),
            k=data.get("k"),
        )

    def to_dict(self) -> dict[str, float | None]:
        result: dict[str, float | None] = {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "d": self.d,
        }
        for key in EXTRA_VALUE_LABELS:
            val = getattr(self, key)
            if val is not None:
                result[key] = val
        return result

    def has_tolerance_data(self) -> bool:
        return any(getattr(self, key) is not None for key in TOLERANCE_VALUE_KEYS)

    def extra_field_keys(self) -> list[str]:
        return [key for key in EXTRA_VALUE_LABELS if getattr(self, key) is not None]


@dataclass
class ReportHeaderInfo:
    """PC-DMIS 报告窗口页眉 — 与内置 Excel 导出一致。"""

    program_name: str = ""
    part_name: str = ""
    serial_number: str = ""
    report_date: str = ""
    report_time: str = ""


@dataclass
class ToleranceConfig:
    x_upper: float = 0.02
    x_lower: float = -0.02
    y_upper: float = 0.02
    y_lower: float = -0.02
    z_upper: float = 0.02
    z_lower: float = -0.02
    d_upper: float = 0.05
    d_lower: float = -0.05

    def axis_limits(self, axis: str) -> tuple[float, float] | None:
        mapping = {
            "x": (self.x_lower, self.x_upper),
            "y": (self.y_lower, self.y_upper),
            "z": (self.z_lower, self.z_upper),
            "d": (self.d_lower, self.d_upper),
        }
        return mapping.get(axis)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToleranceConfig":
        return cls(
            x_lower=data.get("x_lower", -0.02),
            x_upper=data.get("x_upper", 0.02),
            y_lower=data.get("y_lower", -0.02),
            y_upper=data.get("y_upper", 0.02),
            z_lower=data.get("z_lower", -0.02),
            z_upper=data.get("z_upper", 0.02),
            d_lower=data.get("d_lower", -0.05),
            d_upper=data.get("d_upper", 0.05),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "x_lower": self.x_lower,
            "x_upper": self.x_upper,
            "y_lower": self.y_lower,
            "y_upper": self.y_upper,
            "z_lower": self.z_lower,
            "z_upper": self.z_upper,
            "d_lower": self.d_lower,
            "d_upper": self.d_upper,
        }


@dataclass
class FeatureRecord:
    name: str
    feature_type: str
    nominal: AxisValues = field(default_factory=AxisValues)
    measured: AxisValues = field(default_factory=AxisValues)
    deviation: AxisValues = field(default_factory=AxisValues)
    tolerance: AxisValues | None = None
    status: PassStatus = PassStatus.NA
    failed_axes: list[str] = field(default_factory=list)
    cmd_index: int = 0
    write_cmd_index: int = 0
    source_kind: str = ""
    write_axis: str = ""
    write_field: str = ""
    write_field_index: int = 0
    feat1: str = ""
    feat2: str = ""
    feat3: str = ""
    segment: str = ""
    plus_tol: float | None = None
    minus_tol: float | None = None
    bonus: float | None = None
    outtol: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureRecord":
        tol = data.get("tolerance")
        status_raw = data.get("status", PassStatus.NA)
        if isinstance(status_raw, PassStatus):
            status = status_raw
        else:
            try:
                status = PassStatus(str(status_raw))
            except ValueError:
                status = PassStatus.NA
        failed = data.get("failed_axes") or []
        if not isinstance(failed, list):
            failed = []
        return cls(
            name=data["name"],
            feature_type=data.get("type", "UNKNOWN"),
            nominal=AxisValues.from_dict(data.get("nominal")),
            measured=AxisValues.from_dict(data.get("measured")),
            deviation=AxisValues.from_dict(data.get("deviation")),
            tolerance=AxisValues.from_dict(tol) if tol else None,
            status=status,
            failed_axes=[str(a) for a in failed],
            cmd_index=int(data.get("cmd_index", 0) or 0),
            write_cmd_index=int(data.get("write_cmd_index", 0) or 0),
            source_kind=str(data.get("source_kind", "") or ""),
            write_axis=str(data.get("write_axis", "") or ""),
            write_field=str(data.get("write_field", "") or ""),
            write_field_index=int(data.get("write_field_index", 0) or 0),
            feat1=str(data.get("feat1", "") or ""),
            feat2=str(data.get("feat2", "") or ""),
            feat3=str(data.get("feat3", "") or ""),
            segment=str(data.get("segment", "") or ""),
            plus_tol=data.get("plus_tol"),
            minus_tol=data.get("minus_tol"),
            bonus=data.get("bonus"),
            outtol=data.get("outtol"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.feature_type,
            "nominal": self.nominal.to_dict(),
            "measured": self.measured.to_dict(),
            "deviation": self.deviation.to_dict(),
            "status": self.status.value,
            "failed_axes": self.failed_axes,
        }
        if self.cmd_index:
            result["cmd_index"] = self.cmd_index
        if self.write_cmd_index:
            result["write_cmd_index"] = self.write_cmd_index
        if self.source_kind:
            result["source_kind"] = self.source_kind
        if self.write_axis:
            result["write_axis"] = self.write_axis
        if self.write_field:
            result["write_field"] = self.write_field
        if self.write_field_index:
            result["write_field_index"] = self.write_field_index
        if self.feat1:
            result["feat1"] = self.feat1
        if self.feat2:
            result["feat2"] = self.feat2
        if self.feat3:
            result["feat3"] = self.feat3
        if self.segment:
            result["segment"] = self.segment
        if self.plus_tol is not None:
            result["plus_tol"] = self.plus_tol
        if self.minus_tol is not None:
            result["minus_tol"] = self.minus_tol
        if self.bonus is not None:
            result["bonus"] = self.bonus
        if self.outtol is not None:
            result["outtol"] = self.outtol
        if self.tolerance:
            result["tolerance"] = self.tolerance.to_dict()
        return result
