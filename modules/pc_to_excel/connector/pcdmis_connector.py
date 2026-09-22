"""PCDMIS COM 连接器。"""

from __future__ import annotations

import logging
import traceback
from typing import Callable

from .base import ConnectionInfo, MeasurementConnector
from .pcdlrn_constants import set_active_prog_id
from .com_detector import (
    check_elevation_match,
    com_apartment,
    com_call_lock,
    discover_install_dirs,
    dispatch_pcdmis,
    get_connect_candidates,
    quick_connect,
)
from ..core.models import FeatureRecord
from utils.error_codes import ErrorCode, ToolboxError

logger = logging.getLogger("pc_to_excel")

ProgressCallback = Callable[[int, int, str], None]


def _is_com_session_error(exc: BaseException) -> bool:
    """是否为 COM 会话失效（可重连），而非 UI/业务错误。"""
    name = type(exc).__name__
    if name in ("com_error", "COMError"):
        return True
    msg = str(exc).lower()
    needles = (
        "rpc",
        "0x800706ba",
        "0x800706be",
        "0x80010108",
        "0x800401e3",
        "notinitialized",
        "co_e_notinitialized",
        "被调用的对象已与其客户端断开",
        "server is unavailable",
    )
    return any(n in msg for n in needles)


class PcdmisConnector(MeasurementConnector):
    def __init__(self, prog_id: str | None = None) -> None:
        self._preferred_prog_id = prog_id
        self._connected = False
        self._active_prog_id = ""
        self._version = ""
        self._last_features: list[FeatureRecord] = []
        self._last_part_name: str = ""

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
            raise ToolboxError(ErrorCode.PCDMIS_NOT_RUNNING, "未连接 PCDMIS")
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
            set_active_prog_id(prog_id)
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
        set_active_prog_id("")
        self._version = ""
        self._last_features = []
        self._last_part_name = ""

    def is_connected(self) -> bool:
        return self._connected

    def session_alive(self) -> bool:
        """探测 COM 会话是否仍可用。其它线程正在抽数时不抢锁，避免和界面互锁。"""
        if not self._connected or not self._active_prog_id:
            return False
        if not com_call_lock.acquire(blocking=False):
            return True
        try:
            with com_apartment():
                app = self._bind_app()
                _ = app.ActivePartProgram
                return True
        except Exception:
            return False
        finally:
            com_call_lock.release()

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
        """界面用：抽数中不抢 COM，返回上次缓存的程序名。

        刻意**不**调 ensure_session()：调用方（_refresh_connection_ui /
        _status_watcher_tick）均已先确认过连接状态，再在这里做一次完整会话
        自愈会多付一次 dispatch + ActivePartProgram 探测（实测 ~192ms），
        且自愈失败时会走 connect() 全量重连——那不是界面刷新该付的代价。

        这里只做轻量读取：未连接直接返回缓存；已连接则尝试读一次
        ActivePartProgram.Name，任何失败都回退到 _last_part_name。
        导出前的会话自愈在 _ensure_connected() → ensure_session()，不受影响。
        """
        if not self._connected or not self._active_prog_id:
            return self._last_part_name
        if not com_call_lock.acquire(blocking=False):
            return self._last_part_name
        try:
            with com_apartment():
                app = self._bind_app()
                part = app.ActivePartProgram
                if part is None:
                    return self._last_part_name
                name = str(part.Name or "")
                self._last_part_name = name
                return name
        except Exception:
            return self._last_part_name
        finally:
            com_call_lock.release()

    def get_report_header_info(self) -> "ReportHeaderInfo":
        """读取报告表头（程序名 / 零件名 / 序号 / 日期时间）。

        整个 COM 段必须在 com_call_lock 内 —— 与 session_alive /
        get_active_part_name / extract_features 保持一致。这里读的**不是**一个属性：
        _bind_app() + ActivePartProgram + PartName / SerialNumber / GetVariableValue
        是多次 COM 往返，漏锁时会与主线程探测交错（本方法历史上就漏了这把锁）。

        用**阻塞**锁、而不是 get_active_part_name 那种非阻塞回退：本方法的调用方
        全是「要结果」的场景（CLI 主线程、GUI 的两个工作线程），拿不到锁就返回空
        表头会让导出文件名与出货表件号静默变空。调用方里没有 GUI 主线程，
        因此不存在卡界面的风险。

        ensure_session() 刻意留在锁**外**：它内部的 session_alive() 用的是非阻塞
        抢锁，若在外层持锁会让那次探测退化（与 extract_features 的写法一致）。
        """
        from ..core.models import ReportHeaderInfo

        info = self.ensure_session()
        if not info.connected:
            return ReportHeaderInfo()
        with com_call_lock:
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
                header = ReportHeaderInfo(
                    program_name=program_name,
                    part_name=part_name,
                    serial_number=serial,
                    report_date=now.strftime("%Y/%m/%d"),
                    report_time=now.strftime("%H:%M:%S"),
                )
                self._last_part_name = part_name or program_name
                return header

    def extract_features(
        self,
        progress_cb: ProgressCallback | None = None,
        scope: str = "report",
        require_marked: bool = True,
    ) -> list[FeatureRecord]:
        info = self.ensure_session()
        if not info.connected:
            raise ToolboxError(ErrorCode.PCDMIS_CONNECT_FAIL, info.message)

        last_exc: Exception | None = None
        records: list[FeatureRecord] = []
        for attempt in range(2):
            try:
                with com_call_lock:
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
                if isinstance(exc, ToolboxError) or not _is_com_session_error(exc):
                    raise
                logger.warning("COM 会话失效，重连后重试 (%s)", exc)
                self._connected = False
                retry = self.connect()
                if not retry.connected or attempt >= 1:
                    raise ToolboxError(
                        ErrorCode.PCDMIS_CONNECT_FAIL, str(exc)
                    ) from exc
        else:
            raise ToolboxError(
                ErrorCode.PCDMIS_CONNECT_FAIL,
                str(last_exc) if last_exc else "提取失败",
            )

        if not records:
            scope_hint = (
                "未找到报告窗口中的已评价尺寸。\n"
                "请确认相关尺寸已 Mark（输出到报告），且含实测值。"
                if scope == "report"
                else "未提取到任何特征/尺寸数据。"
            )
            raise ToolboxError(
                ErrorCode.PCDMIS_NO_DATA,
                f"{scope_hint}\n请确认 PCDMIS 中已打开含实测数据的测量程序。",
            )
        self._last_features = records
        return list(records)

    @staticmethod
    def format_error(exc: Exception) -> str:
        return f"{exc}\n\n详细:\n{traceback.format_exc()}"
