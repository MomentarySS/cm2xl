"""同机 cm2xl 实例之间的文件 IPC（测量房无网、无额外服务）。

第二进程（工具栏再次点击）写入命令后退出；正在运行的 Shell 轮询消费。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from utils.file_io import atomic_write_text
from utils.paths import paths

IPC_FILENAME = "ipc_command.json"
CMD_AUTO_EXPORT = "auto_export"
COMMAND_TTL_SEC = 20.0


def ipc_path() -> Path:
    return paths.data_dir / IPC_FILENAME


def clear_ipc_commands() -> None:
    path = ipc_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def write_auto_export_command() -> Path:
    payload = {"cmd": CMD_AUTO_EXPORT, "ts": time.time()}
    dest = ipc_path()
    atomic_write_text(dest, json.dumps(payload, ensure_ascii=False))
    return dest


def consume_command(*, now: float | None = None) -> dict[str, Any] | None:
    """读取并删除命令文件。过期或损坏则丢弃。"""
    path = ipc_path()
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    ts = data.get("ts")
    stamp = now if now is not None else time.time()
    try:
        age = stamp - float(ts)
    except (TypeError, ValueError):
        return None
    if age < 0 or age > COMMAND_TTL_SEC:
        return None
    cmd = str(data.get("cmd") or "")
    if not cmd:
        return None
    data["cmd"] = cmd
    return data
