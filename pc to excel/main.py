"""
PCDMIS 按需 Excel 测量报告 — 旧入口重定向（Phase 7）
====================================================

原 `pc to excel/main.py` 是 pc_to_excel 独立运行的入口。
Phase 6 迁移后，pc_to_excel 模块代码已迁移到 `pcdmis_toolbox/modules/pc_to_excel/`。
本文件保留作为兼容入口：被双击/命令行调用时，自动重定向到 Toolbox 的统一入口。

用法（保持原调用方式）：
  python "pc to excel/main.py"                  # 重定向到 pcdmis_toolbox

或者直接使用新入口（推荐）：
  python -m modules.pc_to_excel                 # 独立窗口模式
  python -m main                                # Toolbox 集成模式
"""
from __future__ import annotations

import sys
from pathlib import Path

# 把 pcdmis_toolbox 加入 sys.path
_TOOLBOX = Path(__file__).resolve().parent.parent / "pcdmis_toolbox"
if str(_TOOLBOX) not in sys.path:
    sys.path.insert(0, str(_TOOLBOX))

# 提示用户（仅 stderr，不弹窗避免阻塞旧脚本）
print(
    "[DEPRECATED] pc to excel/main.py 是旧入口，已重定向到 pcdmis_toolbox。\n"
    "         推荐改用：python -m modules.pc_to_excel（独立窗口模式）\n"
    "                  python -m main              （Toolbox 集成模式）\n",
    file=sys.stderr,
)

# 复用 pcdmis_toolbox/modules/pc_to_excel 的 main 入口
from modules.pc_to_excel.main import main  # noqa: E402

if __name__ == "__main__":
    main()