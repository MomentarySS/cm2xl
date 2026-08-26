"""PC-DMIS COM 枚举常量 — 优先动态加载，失败时使用回退值。

参考:
- https://blog.iyatt.com/?p=18363
- https://docs.hexagonmi.com/pcdmis/2024.1/en/helpcenter/mergedProjects/automationobjects/webframe.html
"""

from __future__ import annotations

PCDLRN_TYPELIB = "{10C96EB9-ED97-492D-BC67-700C7F18E394}"


class _FallbackConstants:
    """常用 ENUM_FIELD_TYPES 回退值（2019–2024 各版本基本一致）。"""

    AXIS = 132
    NOMINAL = 166
    F_PLUS_TOL = 167
    F_MINUS_TOL = 168
    DIM_MEASURED = 328
    DIM_DEVIATION = 340
    DIM_OUTTOL = 344
    DIM_LENGTH = 173
    DIM_LENGTH2 = 754
    DIM_HALF_ANGLE = 880
    DIM_ID = 304
    DIM_TEXT = 177
    ID = 2
    DISPLAY_ID = 184
    REF_ID = 3
    DIM_BONUS = 324
    UNIT_TYPE = 49
    THEO_DIAM = 34
    MEAS_DIAM = 29
    MEAS_D = 88
    THEO_LENGTH = 36
    THEO_WIDTH = 35
    THEO_HEIGHT = 37
    THEO_ANGLE = 38
    THEO_MINOR_DIAMETER = 920
    THEO_I = 16
    THEO_J = 17
    THEO_K = 18
    MEAS_LENGTH = 28
    MEAS_WIDTH = 316
    MEAS_HEIGHT = 306
    MEAS_ANGLE = 30
    MEAS_MINOR_DIAMETER = 921
    MEAS_I = 25
    MEAS_J = 26
    MEAS_K = 27
    FPOINT_CENTROID = 0
    FDATA_THEO = 0
    FDATA_MEAS = 1
    FDATA_TARG = 2
    # Legacy 形位公差 (IsFcfCommand) — LINE1/2/3 表格
    GDT_SYMBOL = 708
    FCF_RUNOUT_TYPE = 867
    LINE1_TBLHDR = 642
    LINE1_FEATNAME = 645
    LINE1_NOMINAL = 646
    LINE1_MEAS = 647
    LINE1_PLUSTOL = 648
    LINE1_MINUSTOL = 649
    LINE1_DEV = 650
    LINE1_OUTTOL = 765
    LINE1_BONUS = 782
    LINE2_TBLHDR = 654
    LINE2_FEATNAME = 657
    LINE2_TOL = 659
    LINE2_AXIS = 686
    LINE2_NOMINAL = 687
    LINE2_MEAS = 688
    LINE2_PLUSTOL = 693
    LINE2_MINUSTOL = 694
    LINE2_DEV = 662
    LINE2_OUTTOL = 766
    LINE2_BONUS = 658
    LINE3_TBLHDR = 665
    LINE3_FEATNAME = 668
    LINE3_TOL = 670
    LINE3_NOMINAL = 770
    LINE3_MEAS = 771
    LINE3_PLUSTOL = 772
    LINE3_MINUSTOL = 773
    LINE3_DEV = 673
    LINE3_OUTTOL = 767
    LINE3_BONUS = 669
    # BASIC Script 命令字段
    BASIC_SCRIPT = 12346
    FILE_NAME = 1
    SUB_NAME = 4
    SHOW_DETAILS = 5


def load_pcdlrn_constants():
    """尝试从本机 PCDLRN.tlb 加载常量，失败则返回回退对象（模块级缓存）。"""
    global _CONSTANTS_SINGLETON
    if _CONSTANTS_SINGLETON is not None:
        return _CONSTANTS_SINGLETON
    try:
        import win32com.client.gencache as gencache
        from win32com.client import constants

        for major, minor in (
            (19, 1), (19, 0), (18, 2), (18, 1), (18, 0),
            (17, 1), (17, 0), (16, 0), (15, 0), (14, 2),
        ):
            try:
                gencache.EnsureModule(PCDLRN_TYPELIB, 0, major, minor)
                _CONSTANTS_SINGLETON = constants
                return _CONSTANTS_SINGLETON
            except Exception:
                continue
    except Exception:
        pass
    _CONSTANTS_SINGLETON = _FallbackConstants()
    return _CONSTANTS_SINGLETON


_CONSTANTS_SINGLETON = None
_CONST_VALUE_CACHE: dict[str, int] = {}


def get_const(name: str, default: int | None = None) -> int:
    """按名称读取常量，不存在时返回 default 或回退值（名称级缓存）。"""
    cached = _CONST_VALUE_CACHE.get(name)
    if cached is not None:
        return cached
    c = load_pcdlrn_constants()
    if hasattr(c, name):
        val = int(getattr(c, name))
    else:
        fb = _FallbackConstants()
        if hasattr(fb, name):
            val = int(getattr(fb, name))
        elif default is not None:
            val = default
        else:
            raise AttributeError(f"未知 PCDLRN 常量: {name}")
    _CONST_VALUE_CACHE[name] = val
    return val
