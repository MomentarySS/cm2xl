"""
cm2xl — 配置管理
原子写 + 文件锁 + 配置迁移 + 版本升级链。
"""

import json
import os
import shutil
import time
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Callable

# fcntl 仅 Unix 可用
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

logger = logging.getLogger(__name__)

from utils.error_codes import ErrorCode, ToolboxError

# 配置 schema 版本（与 toolbox.app_meta.APP_VERSION 独立；APP_VERSION 随发布递增）
CONFIG_SCHEMA_VERSION = "2.0.0"

# 迁移函数类型
Migration = Callable[[dict], dict]

# 迁移函数注册表：module_name -> {from_version: migration_fn}
# 约定：每个 from_version 的迁移函数一次性升级到 CONFIG_SCHEMA_VERSION。
_MIGRATIONS: dict[str, dict[str, Migration]] = {}

# 无 _version 字段的旧文件（file_version 视为 0.0.0）按模块默认旧版本走迁移
_LEGACY_DEFAULT_VERSION: dict[str, str] = {
    "cmm_filler": "1.0.0",
    "pc_to_excel": "1.4.5",
}


def register_migration(module: str, from_ver: str, to_ver: str | None = None):
    """
    装饰器：注册迁移函数。
    自动推断 to_ver（from_ver 去掉尾号 v，如 "1.0.0" → "1.0.1"）。
    """
    def deco(fn: Migration):
        _MIGRATIONS.setdefault(module, {})[from_ver] = fn
        return fn
    return deco


# ── 原子写 ─────────────────────────────────────────────────────────────────

def save_settings_json_atomic(path: Path, data: dict) -> None:
    """
    将 data 以原子方式写入 path（临时文件 + os.replace）。
    修复 json.dump 直接写、异常中断留半截文件的问题。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        logger.debug(f"settings saved (atomic): {path}")
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


# ── 文件锁 ─────────────────────────────────────────────────────────────────

class FileLock:
    """
    基于 O_EXCL 的跨进程文件锁（Windows + Linux 通用）。

    用法：
        with FileLock(lock_path, timeout=5.0) as locked:
            if locked:
                # 拿到了锁
                pass
            else:
                # 超时
    """

    def __init__(self, lock_path: Path, timeout: float = 5.0, retry_interval: float = 0.1):
        self._lock_path = lock_path
        self._timeout = timeout
        self._retry_interval = retry_interval
        self._fd = None

    def __enter__(self) -> bool:
        """尝试获取锁，返回 True 表示拿到，False 表示超时。"""
        start = time.monotonic()
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                self._fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                # 写入当前 PID
                os.write(self._fd, str(os.getpid()).encode())
                os.close(self._fd)
                self._fd = None
                return True
            except FileExistsError:
                # 检查是否死锁（进程已不存在）
                if self._is_stale():
                    try:
                        self._lock_path.unlink()
                        continue
                    except Exception:
                        pass
                if time.monotonic() - start >= self._timeout:
                    return False
                time.sleep(self._retry_interval)

    def __exit__(self, *args) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
        try:
            self._lock_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _is_stale(self) -> bool:
        """检查锁文件对应的进程是否还存活。"""
        try:
            pid_str = self._lock_path.read_text(encoding="utf-8").strip()
            pid = int(pid_str)
            if pid <= 0:
                return True
            if sys.platform == "win32":
                return not _pid_exists_windows(pid)
            os.kill(pid, 0)
            return False  # 进程存活
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            return True  # 进程已死


def _pid_exists_windows(pid: int) -> bool:
    """Windows 进程存活检测；避免 os.kill(pid, 0) 触发 WinError 87。"""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ERROR_ACCESS_DENIED = 5

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        exit_code = wintypes.DWORD()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return bool(ok) and exit_code.value == 259  # STILL_ACTIVE

    # Access denied means the PID exists but this user cannot query it.
    return ctypes.get_last_error() == ERROR_ACCESS_DENIED


# ── 配置迁移 ────────────────────────────────────────────────────────────────

def migrate_settings_if_needed(
    module_name: str,
    old_path: Path,
    new_path: Path,
) -> dict:
    """
    配置文件迁移：旧路径 → 新路径，复制后删除旧文件。
    适用于首次启动时的单向迁移（无版本升级链）。
    """
    if new_path.exists():
        return load_json(new_path)
    if not old_path.exists():
        return {}

    new_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old_path, new_path)
    bak_path = old_path.with_suffix(".bak")
    old_path.rename(bak_path)
    logger.info(f"[settings] migrated {old_path} → {new_path}, old backed up")
    return load_json(new_path)


def load_json(path: Path) -> dict:
    """读取 JSON 文件，失败返回空 dict。"""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"[settings] read error {path}: {e}, using defaults")
        corrupt = path.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}.bak")
        shutil.copy2(path, corrupt)
        return {}


def _next_version(ver: str) -> str:
    """简单版本递增（最后一段 +1）。"""
    parts = ver.rsplit(".", 1)
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def load_and_migrate_settings(module_name: str, config_path: Path) -> dict:
    """
    加载配置，执行版本升级链（如有），返回最终 settings dict。
    详见 ARCHITECTURE.md 3.9.1。
    """
    if not config_path.is_file():
        return _default_settings(module_name)

    data = load_json(config_path)
    file_version = data.get("_version", "0.0.0")

    if file_version == CONFIG_SCHEMA_VERSION:
        return data

    # 无版本字段的旧文件：按模块默认旧版本走迁移链
    if file_version == "0.0.0":
        file_version = _LEGACY_DEFAULT_VERSION.get(module_name, "0.0.0")

    if file_version == CONFIG_SCHEMA_VERSION:
        return data

    # 升级前先备份
    backup_path = config_path.with_suffix(f".v{file_version}.bak")
    if not backup_path.exists():
        shutil.copy2(config_path, backup_path)
        logger.info(f"[settings] backup {config_path} → {backup_path}")

    # 执行迁移（每个 from_version 的迁移函数一次性升到当前 schema）
    migrations = _MIGRATIONS.get(module_name, {})
    current = data
    current_version = file_version
    migrated = False

    while current_version != CONFIG_SCHEMA_VERSION:
        if current_version not in migrations:
            raise ToolboxError(
                ErrorCode.CONFIG_MIGRATION_FAIL,
                f"{module_name}: 没有从 v{current_version} 升级的迁移函数",
            )
        migration = migrations[current_version]
        try:
            current = migration(current)
            current["_version"] = CONFIG_SCHEMA_VERSION
            current["_updated_at"] = datetime.now().isoformat()
            current_version = current["_version"]
            migrated = True
            logger.info(f"[settings] {module_name} 升级 → v{current_version}")
        except Exception as e:
            logger.error(f"[settings] 迁移失败: {e}，从备份恢复")
            current = load_json(backup_path)
            break

    if migrated:
        save_settings_json_atomic(config_path, current)
    return current


def stamp_settings(data: dict, module_name: str) -> dict:
    """
    给配置字典盖上 schema 版本戳（_version / _schema / _updated_at）。

    各模块保存配置时**必须**调用本函数：文件里没有 _version 时，下次启动会被
    当成 0.0.0 走一遍迁移链（每次弹「配置已升级」并生成 .bak）。
    与 _default_settings() 共用同一套字段，避免两处各写一份。
    """
    stamped = dict(data)
    stamped["_version"] = CONFIG_SCHEMA_VERSION
    stamped["_schema"] = f"{module_name}.settings"
    stamped["_updated_at"] = datetime.now().isoformat()
    return stamped


def _default_settings(module_name: str) -> dict:
    """返回模块默认 settings（含 _version 和 _schema 字段）。"""
    return stamp_settings({}, module_name)


# ── 模块迁移函数（旧 1.x → 当前 schema）────────────────────────────────────

def migrate_cmm_filler_1_0_to_2_0(old: dict) -> dict:
    """CMMFiller 1.0.0 → 2.0.0：保留原有全部字段 + 补齐版本字段。

    这里**刻意不用白名单**：白名单会丢掉「新增、但忘记同步到本函数」的字段。
    历史上 report_profile / custom_item_prefixes / ocr_roi 就是这样每次启动被抹掉的
    —— 保存侧（gui._save_paths）写 6 个键，而本函数的白名单停在 3 个。
    改为保留未知键后，「忘记同步」这个失效模式变得无害。

    版本字段由 _default_settings() 覆盖写入（顺序：old 在前、默认值在后），
    因此旧的 _version / _schema / _updated_at 会被刷新为当前值。
    """
    return {**old, **_default_settings("cmm_filler")}


def migrate_pc_to_excel_1_4_to_2_0(old: dict) -> dict:
    """pc to excel 1.4.5 → 2.0.0：保留原有全部字段 + 补齐版本字段（同上）。"""
    return {**old, **_default_settings("pc_to_excel")}


_MIGRATIONS.update({
    "cmm_filler": {"1.0.0": migrate_cmm_filler_1_0_to_2_0},
    "pc_to_excel": {"1.4.5": migrate_pc_to_excel_1_4_to_2_0},
})


# ── 降级导出 ───────────────────────────────────────────────────────────────

# 各模块 2.0 schema 的「业务字段」白名单（不含 _ 前缀元数据），用于降级导出。
#
# 这里**必须**用白名单，方向与迁移函数相反：
#   - 迁移：必须保留未知键 —— 否则丢用户数据
#   - 降级导出：必须丢弃未知键 —— 目标是**冻结的** 1.x 格式，新字段旧工具不认识，
#     带出去只会让「导出给旧工具的配置」内容不再可控
_LEGACY_EXPORT_KEYS: dict[str, tuple[str, ...]] = {
    "cmm_filler": ("template_path", "pdf_folder", "output_folder"),
    "pc_to_excel": (
        "export_dir",
        "filename_pattern",
        "tolerance",
        "export_scope",
        "require_marked",
        "form_fill",
    ),
}


def export_legacy_settings(module_name: str, target_path: Path, current_data: dict) -> None:
    """
    把 2.0 配置降级导出为 1.x 格式，导出给旧工具使用。
    详见 ARCHITECTURE.md 3.9.2。
    """
    allowed = _LEGACY_EXPORT_KEYS.get(module_name, ())
    legacy = {k: v for k, v in current_data.items() if k in allowed}

    from utils.file_io import atomic_write_text

    atomic_write_text(target_path, json.dumps(legacy, ensure_ascii=False, indent=2))
    logger.info(f"[settings] exported legacy settings for {module_name} → {target_path}")


# ── Toolbox 全局设置 ───────────────────────────────────────────────────────

TOOLBOX_SETTINGS_VERSION = "1.0.0"

TOOLBOX_DEFAULT_SETTINGS: dict = {
    "_version": TOOLBOX_SETTINGS_VERSION,
    "_schema": "toolbox.settings",
    "appearance_mode": "system",   # "light" / "dark" / "system"
    "ocr_model_dir": "",           # 空 = 用内置；非空 = 用户自定义路径
    "ocr_model_tier": "server",    # "server" = 高精度(PP-OCRv4) / "mobile" = 轻量(Mobile v2.0)
    "log_level": "INFO",           # "DEBUG" / "INFO" / "WARNING"
    "nav_collapsed": False,        # 侧边栏默认展开；折叠后仅显示图标
}


def _toolbox_settings_path() -> Path:
    """toolbox 全局配置路径：config_dir/toolbox/settings.json"""
    from utils.paths import paths
    return paths.config_dir / "toolbox" / "settings.json"


def load_toolbox_settings() -> dict:
    """
    加载 toolbox 全局设置（外观模式 / OCR 模型目录 / 日志级别）。
    文件缺失或损坏 → 返回默认值。
    """
    path = _toolbox_settings_path()
    if not path.exists():
        return dict(TOOLBOX_DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 用默认值补缺失字段（向前兼容）
        merged = dict(TOOLBOX_DEFAULT_SETTINGS)
        merged.update({k: v for k, v in data.items() if k in TOOLBOX_DEFAULT_SETTINGS})
        return merged
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"[settings] toolbox settings 加载失败，使用默认值: {e}")
        return dict(TOOLBOX_DEFAULT_SETTINGS)


def save_toolbox_settings(data: dict) -> None:
    """
    原子写 toolbox 全局设置（外观模式 / OCR 模型目录 / 日志级别）。
    自动补全字段，确保 schema 完整。
    """
    path = _toolbox_settings_path()
    # 合并默认值（避免字段缺失）
    payload = dict(TOOLBOX_DEFAULT_SETTINGS)
    payload.update({k: v for k, v in data.items() if k in TOOLBOX_DEFAULT_SETTINGS})
    payload["_version"] = TOOLBOX_SETTINGS_VERSION
    save_settings_json_atomic(path, payload)
    logger.info(f"[settings] toolbox settings 已保存 → {path}")
