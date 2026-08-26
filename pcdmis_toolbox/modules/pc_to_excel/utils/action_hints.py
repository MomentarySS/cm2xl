"""面向用户的操作提示 — 把技术错误转成可执行说明。"""

from __future__ import annotations

import traceback

from ....utils.error_codes import ToolboxError


def hint_for_message(text: str) -> str:
    """根据错误原文给出处理建议。"""
    raw = text or ""
    low = raw.lower()

    if "权限" in raw or "elevation" in low or "管理员" in raw:
        return (
            "处理建议：\n"
            "• 工具与 PCDMIS 须同级运行（都普通，或都管理员）\n"
            "• PCDMIS 若是管理员启动，请用 run_as_admin.bat 开本工具"
        )

    if "无法连接" in raw or ("connect" in low and "pcd" in low) or "dispatch" in low:
        return (
            "处理建议：\n"
            "• 先启动 PCDMIS，并打开含实测数据的 .PRG\n"
            "• 确认权限一致（都普通或都管理员）\n"
            "• 导出/填入会自动重连；仍失败再点「连接 PCDMIS」\n"
            "• ProgID 由工具扫描注册表（如 2024.1→.19.1）"
        )

    if "未打开" in raw or "没有打开" in raw or "无活动" in raw or "part program" in low:
        return (
            "处理建议：\n"
            "• 在 PCDMIS 中打开测量程序（.PRG）\n"
            "• 确认程序里已有实测尺寸后再导出/填入"
        )

    if "未提取" in raw or "0 条" in raw or "没有可导出" in raw or "无数据" in raw:
        return (
            "处理建议：\n"
            "• 确认尺寸命令已 Mark，且已评价/有实测值\n"
            "• 若仍为空：临时取消勾选「仅 Mark 命令」再试\n"
            "• 或取消「仅报告窗口数据」扩大提取范围"
        )

    if ("出货" in raw or "检测表" in raw) and (
        "不存在" in raw or "缺少" in raw or "not found" in low
    ):
        return (
            "处理建议：\n"
            "• 点「选出货表…」选择你复制好的 xlsx 底稿\n"
            "• 续填时若上次结果被移动/删除，请重新选表或点「清除续填」"
        )

    if "模板" in raw and ("不存在" in raw or "缺少" in raw):
        return (
            "处理建议：\n"
            "• 本工具已取消自定义 xlsx 模板导出，请用「一键导出」生成 PC-DMIS 列格式\n"
            "• 厂内表格请用「出货检测表填入」按序号写入"
        )

    if "拒绝访问" in raw or "permission" in low or "access is denied" in low:
        return (
            "处理建议：\n"
            "• 输出文件可能正被 Excel 打开 — 先关闭再试\n"
            "• 或换一个有写权限的输出目录"
        )

    if "未找到脚本" in raw or ("script" in low and "not found" in low):
        return (
            "处理建议：\n"
            "• 先点「部署 BAS 脚本」，再「植入/更新导出命令」\n"
            "• 然后在 PCDMIS 中 Ctrl+S 保存 PRG"
        )

    return ""


def format_user_error(title: str, exc: BaseException | str | ToolboxError, *, with_trace: bool = False) -> str:
    """组装弹窗正文：原因 + 建议 +（可选）技术细节。

    接入 ToolboxError：错误码直接显示，便于用户报障时提供代码。
    """
    if isinstance(exc, ToolboxError):
        body = f"[{exc.code}] {exc.message}"
        hint = exc.hint or hint_for_message(exc.message)
        detail = traceback.format_exc() if with_trace else ""
        parts = [f"【{title}】", body]
        if hint:
            parts.extend(["", hint])
        if with_trace and detail and detail.strip() != "NoneType: None":
            parts.extend(["", "—— 技术细节 ——", detail.strip()])
        return "\n".join(parts)

    if isinstance(exc, BaseException):
        body = str(exc).strip() or exc.__class__.__name__
        detail = traceback.format_exc() if with_trace else ""
    else:
        body = str(exc).strip()
        detail = ""

    hint = hint_for_message(body)
    parts = [f"【{title}】", body]
    if hint:
        parts.extend(["", hint])
    if with_trace and detail and detail.strip() != "NoneType: None":
        parts.extend(["", "—— 技术细节 ——", detail.strip()])
    return "\n".join(parts)
