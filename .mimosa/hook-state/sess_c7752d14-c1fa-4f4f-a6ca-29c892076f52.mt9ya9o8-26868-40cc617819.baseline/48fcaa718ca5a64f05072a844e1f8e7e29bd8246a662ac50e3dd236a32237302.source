# -*- coding: utf-8 -*-
"""对比工具导出与 PCDMIS 原生 Excel。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import openpyxl


def load_rows(path: Path) -> list[tuple]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = [tuple(row) for row in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def extract_dims(rows: list[tuple]) -> list[dict]:
    dims: list[dict] = []
    in_data = False
    for row in rows:
        vals = [str(c).strip() if c is not None else "" for c in row[:10]]
        if not vals or not vals[0]:
            continue
        header_join = "".join(vals)
        if vals[0] == "尺寸" and "NOMINAL" in header_join:
            in_data = True
            continue
        if not in_data:
            continue
        if vals[0] in ("统计",):
            break
        if vals[0] == "尺寸" and vals[1] == "描述" and "NOMINAL" in header_join:
            continue
        dims.append(
            {
                "id": vals[0],
                "desc": vals[1] if len(vals) > 1 else "",
                "axis": vals[2] if len(vals) > 2 else "",
                "nom": vals[3] if len(vals) > 3 else "",
                "meas": vals[4] if len(vals) > 4 else "",
                "plus": vals[5] if len(vals) > 5 else "",
                "minus": vals[6] if len(vals) > 6 else "",
                "dev": vals[7] if len(vals) > 7 else "",
                "outtol": vals[8] if len(vals) > 8 else "",
            }
        )
    return dims


def group_by_id(dims: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for d in dims:
        out[d["id"]].append(d)
    return dict(out)


def is_orphan_name(name: str) -> bool:
    prefixes = ("X轴位置_", "Y轴位置_", "Z轴位置_", "长度位置_", "直径位置_", "X 轴位置_", "半径位置_")
    return any(name.startswith(p) for p in prefixes)


def main() -> None:
    tool_path = Path(r"c:\Users\terence\Desktop\本体I_20260725_170847.xlsx")
    native_path = Path(r"c:\Users\terence\Desktop\PCDMIS原生读取.XLSX")

    tool = extract_dims(load_rows(tool_path))
    native = extract_dims(load_rows(native_path))
    tool_g = group_by_id(tool)
    native_g = group_by_id(native)

    print("=" * 70)
    print(f"工具导出: {len(tool)} 行, {len(tool_g)} 个尺寸 ID")
    print(f"PCDMIS原生: {len(native)} 行, {len(native_g)} 个尺寸 ID")
    print()

    print("【1】工具中错误的系统命名行（应对应头行 ID）")
    for d in tool:
        if is_orphan_name(d["id"]):
            match = native_g.get("基准") if d["axis"] in ("X", "Y", "Z") else None
            hint = ""
            if d["axis"] == "L":
                for cand in ("FAI_17A", "FAI_17"):
                    if cand not in tool_g and cand in native_g:
                        hint = f" → 应为 {cand}"
            if match and d["axis"] in ("X", "Y", "Z"):
                hint = f" → 应为 基准/{d['axis']}"
            print(f"  {d['id']:20} axis={d['axis']:3} meas={d['meas']}{hint}")
    print()

    print("【2】原生有、工具缺失的尺寸 ID")
    for nid in sorted(native_g.keys()):
        if nid not in tool_g:
            rows = native_g[nid]
            print(f"  {nid}: {len(rows)} 行 — {rows[0]['desc']}")
    print()

    print("【3】工具多出的尺寸 ID（原生没有）")
    for tid in sorted(tool_g.keys()):
        if tid not in native_g:
            print(f"  {tid}: {tool_g[tid][0]['desc']}")
    print()

    print("【4】同名尺寸数值差异（FAI / 基准）")
    for nid in sorted(native_g.keys()):
        if nid not in tool_g:
            continue
        for tr in tool_g[nid]:
            nr = next((r for r in native_g[nid] if r["axis"] == tr["axis"]), None)
            if nr is None:
                print(f"  {nid} axis={tr['axis']}: 工具有多出行")
                continue
            issues = []
            for key in ("nom", "meas", "dev"):
                try:
                    tv = float(tr[key]) if tr[key] != "" else None
                    nv = float(nr[key]) if nr[key] != "" else None
                    if tv is not None and nv is not None and abs(tv - nv) > 0.0005:
                        issues.append(f"{key} 工具={tv} 原生={nv}")
                except (TypeError, ValueError):
                    if tr[key] != nr[key]:
                        issues.append(f"{key} 工具={tr[key]} 原生={nr[key]}")
            if issues:
                print(f"  {nid} axis={tr['axis']}: " + "; ".join(issues))
    print()

    print("【5】关键案例对照")
    for key in ("基准", "FAI_6", "FAI_10", "FAI_17A", "FAI_17", "FAI_12A", "FAI_12"):
        print(f"--- {key} ---")
        print("  工具:", tool_g.get(key, "缺失"))
        print("  原生:", native_g.get(key, "缺失"))
        print()


if __name__ == "__main__":
    main()
