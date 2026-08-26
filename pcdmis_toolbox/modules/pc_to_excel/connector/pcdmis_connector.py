"""PCDMIS COM 连接器。"""

from __future__ import annotations

import traceback
from typing import Callable

from .base import ConnectionInfo, MeasurementConnector
from .com_detector import (
    check_elevation_match,
    com_apartment,
    discover_install_dirs,
    dispatch_pcdmis,
    get_connect_candidates,
    quick_connect,
)
from ..core.models import FeatureRecord

ProgressCallback = Callable[[int, int, str], None]


class PcdmisConnector(MeasurementConnector):
    def __init__(self, prog_id: str | None = None) -> None:
        self._preferred_prog_id = prog_id
        self._connected = False
        self._active_prog_id = ""
        self._version = ""
        self._last_features: list[FeatureRecord] = []

    @property
    def name(self) -> str:
        return "PCDMIS COM"

    @property
    def version(self) -> str:
        return self._version

    @property
    def prog_id(self) -> str:
        return self._active_prog_id

    def _bind_app(self):
        if not self._active_prog_id:
            raise RuntimeError("未连接 PCDMIS")
        return dispatch_pcdmis(self._active_prog_id)

    def connect(self) -> ConnectionInfo:
        ok_elev, elev_msg = check_elevation_match()
        if not ok_elev:
            return ConnectionInfo(connected=False, source=self.name, message=elev_msg)

        candidates = get_connect_candidates()
        if self._preferred_prog_id:
            candidates = [self._preferred_prog_id] + [
                p for p in candidates if p != self._preferred_prog_id
            ]

        ok, prog_id, version, error, _app = quick_connect(candidates)
        if ok and prog_id:
            self._connected = True
            self._active_prog_id = prog_id
            self._version = version
            return ConnectionInfo(
                connected=True,
                source=self.name,
                version=version,
                message=f"已连接 ({prog_id})",
            )

        hint = ""
        if not discover_install_dirs():
            hint = "\n\n提示：未检测到 PCDMIS 安装目录。"

        return ConnectionInfo(
            connected=False,
            source=self.name,
            message=f"无法连接 PCDMIS COM: {error}{hint}",
        )

    def disconnect(self) -> None:
        self._connected = False
        self._active_prog_id = ""
        self._version = ""
        self._last_features = []

    def is_connected(self) -> bool:
        return self._connected

    def session_alive(self) -> bool:
        """探测 COM 会话是否仍可用（测第二件时常见会话失效）。"""
        if not self._connected or not self._active_prog_id:
            return False
        try:
            with com_apartment():
                app = self._bind_app()
                _ = app.ActivePartProgram
                return True
        except Exception:
            return False

    def ensure_session(self) -> ConnectionInfo:
        """保证可用会话：已活着则复用；否则自动重连（多件导出不必手点连接）。"""
        if self.session_alive():
            return ConnectionInfo(
                connected=True,
                source=self.name,
                version=self._version,
                message=f"会话有效 ({self._active_prog_id})",
            )
        # 旧标记作废，重新附着当前 PCDMIS
        self._connected = False
        return self.connect()

    def get_active_part_name(self) -> str:
        info = self.ensure_session()
        if not info.connected:
            return ""
        with com_apartment():
            try:
                app = self._bind_app()
                part = app.ActivePartProgram
                if part is None:
                    return ""
                return str(part.Name or "")
            except Exception:
                return ""

    def get_report_header_info(self) -> "ReportHeaderInfo":
        from ..core.models import ReportHeaderInfo

        info = self.ensure_session()
        if not info.connected:
            return ReportHeaderInfo()
        with com_apartment():
            from datetime import datetime
            from pathlib import Path

            app = self._bind_app()
            part = app.ActivePartProgram
            if part is None:
                return ReportHeaderInfo()

            program_name = ""
            part_name = ""
            serial = ""
            try:
                program_name = str(part.Name or "").strip()
            except Exception:
                pass
            if program_name and not program_name.upper().endswith(".PRG"):
                program_name = f"{program_name}.PRG"

            try:
                part_name = str(part.PartName or "").strip()
            except Exception:
                pass
            if not part_name:
                try:
                    part_name = str(part.Name or "").strip()
                except Exception:
                    pass
                if part_name.upper().endswith(".PRG"):
                    part_name = Path(part_name).stem

            try:
                serial = str(part.SerialNumber or "").strip()
            except Exception:
                serial = ""
            if serial in ("0", "None", "False"):
                serial = ""
            if not serial:
                for var_name in ("SN", "V_SN", "SERNO"):
                    try:
                        var_obj = part.GetVariableValue(var_name)
                        val = str(getattr(var_obj, "StringValue", var_obj) or "").strip()
                        if val and val not in ("0", "None", "False"):
                            serial = val
                            break
                    except Exception:
                        continue

            now = datetime.now()
            return ReportHeaderInfo(
                program_name=program_name,
                part_name=part_name,
                serial_number=serial,
                report_date=now.strftime("%Y/%m/%d"),
                report_time=now.strftime("%H:%M:%S"),
            )

    def extract_features(
        self,
        progress_cb: ProgressCallback | None = None,
        scope: str = "report",
        require_marked: bool = True,
    ) -> list[FeatureRecord]:
        info = self.ensure_session()
        if not info.connected:
            raise RuntimeError(info.message)

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                with com_apartment():
                    from ..core.data_extractor import extract_from_application

                    records = extract_from_application(
                        self._bind_app(),
                        progress_cb=progress_cb,
                        scope=scope,
                        require_marked=require_marked,
                    )
                break
            except Exception as exc:
                last_exc = exc
                # 第一件导出后会话偶发失效：清标记重连再试一次
                self._connected = False
                retry = self.connect()
                if not retry.connected or attempt >= 1:
                    raise RuntimeError(str(exc)) from exc
        else:
            raise RuntimeError(str(last_exc) if last_exc else "提取失败")

        if not records:
            scope_hint = (
                "未找到报告窗口中的已评价尺寸。\n"
                "请确认相关尺寸已 Mark（输出到报告），且含实测值。"
                if scope == "report"
                else "未提取到任何特征/尺寸数据。"
            )
            raise RuntimeError(
                f"{scope_hint}\n请确认 PCDMIS 中已打开含实测数据的测量程序。"
            )
        self._last_features = records
        return list(records)

    @staticmethod
    def format_error(exc: Exception) -> str:
        return f"{exc}\n\n详细:\n{traceback.format_exc()}"
