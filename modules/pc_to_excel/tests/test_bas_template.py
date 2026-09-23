"""BAS 脚本模板静态断言。

P1-5（BAS 字段常量撞引擎内置名）：部署的 export_current.bas 编译报
    Error on line: 9 - Duplicate definition: ID
根因：脚本第 9 行 `Const ID = 2` 与引擎预置的全局重名；那批字段常量
（ID/AXIS/NOMINAL/F_PLUS_TOL/...）与 PC-DMIS 字段常量同名同值，引擎只
报第一个冲突。改法：把字段常量统一加 FLD_ 前缀一次消除整类冲突。

本测试**不需要 PC-DMIS**，对模板文件做静态断言：

- 正向：模板里不存在裸的字段常量声明。
- 反向：COM 属性访问（cmd.ID / dimObj.ID / dimObj.NOMINAL / tolCmd.ID）
  原样保留 —— 防「图省事全局替换」再次撞坑。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 模板文件定位：模块目录下 scripts/export_current.bas.template
# ---------------------------------------------------------------------------


def _template_path() -> Path:
    """定位 export_current.bas.template。"""
    here = Path(__file__).resolve()
    # modules/pc_to_excel/tests/test_bas_template.py -> modules/pc_to_excel/scripts/
    return here.parent.parent / "scripts" / "export_current.bas.template"


# 这些常量在模板里**不应**作为 `Const X = <数字>` 出现：
# - 与 PC-DMIS 字段常量同名（AXIS=132 / F_PLUS_TOL=167 / F_MINUS_TOL=168 等）
# - 与引擎预置全局同名（ID / AXIS / NOMINAL）
# 注：行号（声明）保持文档可读性 —— 见 docs/CORE_DEFECT_PLAN.md P1-5 节。
RENAMED_FIELD_CONSTANTS = (
    "ID",
    "AXIS",
    "NOMINAL",
    "F_PLUS_TOL",
    "F_MINUS_TOL",
    "DIM_MEASURED",
    "DIM_LENGTH",
    "DIM_BONUS",
    "LINE1_FEATNAME",
    "LINE1_NOMINAL",
    "LINE1_MEAS",
    "LINE1_PLUSTOL",
    "LINE1_MINUSTOL",
    "LINE1_BONUS",
)

# 同拼写但**保留**作为 COM 属性访问的常量名 —— 反向守卫范围。
PRESERVED_PROPERTY_NAMES = (
    "ID",
    "NOMINAL",
)


# ---------------------------------------------------------------------------
# 正向：声明层（Const X = <int>）不应再出现裸字段常量
# ---------------------------------------------------------------------------


def test_no_bare_field_const_declarations():
    """模板的常量声明行不应再有裸字段常量。

    形式上匹配行首 `^\\s*Const\\s+X\\s*=\\s*\\d+\\s*$` —— X ∈ RENAMED_FIELD_CONSTANTS。
    全局正则（不锁行号）保证**任何位置**出现的裸声明都会被抓住。
    """
    import re

    text = _template_path().read_text(encoding="utf-8")
    pattern = re.compile(
        r"^\s*Const\s+("
        + "|".join(re.escape(n) for n in RENAMED_FIELD_CONSTANTS)
        + r")\s*=\s*\d+\s*$",
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    assert not matches, (
        "模板里仍存在裸字段常量声明，会与 PC-DMIS 引擎预置全局重名 ⇒ "
        "编译报 'Duplicate definition'。必须改名为 FLD_X 前缀。匹配到："
        + ", ".join(matches)
    )


# ---------------------------------------------------------------------------
# 正向：UNIT_TYPE 是死代码 —— 不应再出现
# ---------------------------------------------------------------------------


def test_unit_type_removed():
    """UNIT_TYPE 在修复前声明后零引用，是死代码。修复后应**完全删除**。

    不锁死「必须删除」也可以「改名 FLD_UNIT_TYPE」—— 本测试只断言
    「不存在裸 Const UNIT_TYPE =」这一契约，防止它再次以原名混入引擎预置全局
    命名。
    """
    import re

    text = _template_path().read_text(encoding="utf-8")
    pattern = re.compile(r"^\s*Const\s+UNIT_TYPE\s*=\s*\d+\s*$", re.MULTILINE)
    matches = pattern.findall(text)
    assert not matches, (
        "UNIT_TYPE 是死代码；若保留其声明则可能与引擎预置全局同名再次撞名。"
        "应删除或改名为 FLD_UNIT_TYPE。"
    )


# ---------------------------------------------------------------------------
# 反向守卫：COM 属性访问原样保留
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "com_access",
    [
        "cmd.ID",
        "dimObj.ID",
        "tolCmd.ID",
        "dimObj.NOMINAL",
    ],
)
def test_com_property_access_preserved(com_access: str):
    """**反向守卫** —— COM 属性访问**原样保留**。

    改常量名（ID → FLD_ID）若误用全局正则替换，会把这些属性访问也改坏。
    脚本就废了。这是「双假对照」策略：

    - 前面的正向测试断言「裸 Const 声明不存在」⇒ 修复动作有做。
    - 本测试断言「COM 属性访问原样存在」⇒ 修复**没做过头**。

    任何一条变红都意味着有人图省事做了全局替换 —— 立刻止损。
    """
    text = _template_path().read_text(encoding="utf-8")
    assert com_access in text, (
        f"COM 属性访问 '{com_access}' 已被误改 —— "
        "P1-5 修复不应触碰 cmd.ID / dimObj.ID / dimObj.NOMINAL / tolCmd.ID "
        "这类属性访问。"
    )


# ---------------------------------------------------------------------------
# 反向守卫：CSV 表头里的 'ID' 不被误伤（防止后续重构误改字符串）
# ---------------------------------------------------------------------------


def test_csv_header_id_preserved():
    """CSV 表头里 'ID,类型,...' 字面量不应被误改。

    `Const ID` 在第 9 行声明、与表头字符串里 'ID' 同拼写 —— 改名是声明行
    改名，表头字符串不应被改（字符串里的 'ID' 是列名，不是常量引用）。
    """
    text = _template_path().read_text(encoding="utf-8")
    assert '"ID,类型,理论值,' in text, (
        "CSV 表头里的 'ID' 是字面列名，不应被 P1-5 的改名动作误伤。"
    )


# ---------------------------------------------------------------------------
# 正向：声明层必须有 FLD_X 前缀
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", RENAMED_FIELD_CONSTANTS)
def test_field_const_declared_with_fld_prefix(name: str):
    """每个被改名的字段常量都必须以 FLD_<NAME> 形式声明。"""
    import re

    text = _template_path().read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^\s*Const\s+FLD_{re.escape(name)}\s*=\s*\d+\s*$",
        re.MULTILINE,
    )
    assert pattern.search(text), (
        f"字段常量 {name} 必须以 FLD_{name} 前缀重新声明 —— "
        "这是 P1-5 的核心改法。"
    )


# ---------------------------------------------------------------------------
# 正向：声明层不应有不属于字段常量集合的其它裸常量
# ---------------------------------------------------------------------------


# 修复后**保留**的常量（不是 PC-DMIS 字段常量，撞名风险低）
KEPT_CONSTANTS = (
    "CONFIG_PATH",
    "DATA_TYPE_DIMENSION",
    "DATA_TYPE_FCF",
    "DATA_TYPE_FCFDIM",
)


@pytest.mark.parametrize("name", KEPT_CONSTANTS)
def test_kept_consts_still_declared(name: str):
    """CONFIG_PATH / DATA_TYPE_* 不是 PC-DMIS 字段常量，保留裸名（撞名风险低）。

    本测试防止有人在批量改名时把不该改的也改了，缩窄 diff 范围（见文档）。
    """
    import re

    text = _template_path().read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^\s*Const\s+{re.escape(name)}\s*=",  # 不锁数值，只锁存在
        re.MULTILINE,
    )
    assert pattern.search(text), (
        f"非字段常量 {name} 不应被 P1-5 改名动作误伤。"
    )