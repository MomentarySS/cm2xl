"""
PCDMIS Toolbox 2.0 — 错误码体系
所有业务异常必须用 ToolboxError(code, message) 抛出，不用裸 RuntimeError。
"""

from typing import Optional


class ErrorCode:
    """错误码枚举，字母前缀表示类别。"""

    # 通用错误（E1xxx）
    UNKNOWN = "E0000"
    ELEVATION_MISMATCH = "E1001"
    PYTHON_BITNESS_WRONG = "E1002"
    MODEL_MISSING = "E1003"

    # PCDMIS 连接错误（E2xxx）
    PCDMIS_NOT_RUNNING = "E2001"
    PCDMIS_CONNECT_FAIL = "E2002"
    PCDMIS_PART_NOT_OPEN = "E2003"
    PCDMIS_NO_DATA = "E2004"
    PCDMIS_SAVE_FAIL = "E2005"

    # CMMFiller / PDF / OCR 错误（E3xxx）
    PDF_NOT_FOUND = "E3001"
    TEMPLATE_INVALID = "E3002"
    OCR_FAIL = "E3003"

    # 文件 / 路径错误（E4xxx）
    OUTPUT_DIR_INVALID = "E4001"
    OUTPUT_FILE_LOCKED = "E4002"

    # BAS / 命令注入错误（E5xxx）
    BAS_NOT_DEPLOYED = "E5001"
    INJECT_FAIL = "E5002"

    # 配置错误（E6xxx）
    CONFIG_INVALID = "E6001"
    CONFIG_MIGRATION_FAIL = "E6002"


# 错误码 → (消息模板, 提示)
_ERROR_HINTS = {
    ErrorCode.ELEVATION_MISMATCH: (
        "权限级别不一致",
        "PCDMIS 与 Toolbox 必须以相同权限级别启动（同时管理员或同时普通用户）。"
    ),
    ErrorCode.PYTHON_BITNESS_WRONG: (
        "Python 位数错误",
        "PC-DMIS 2022+（64-bit）需要 64 位 Python。请使用 64 位 Python 运行本工具。"
    ),
    ErrorCode.MODEL_MISSING: (
        "OCR 模型未找到",
        "OCR 模型文件缺失。请检查 models/paddleocr/ 目录是否完整。"
    ),
    ErrorCode.PCDMIS_NOT_RUNNING: (
        "PC-DMIS 未运行",
        "请先启动 PCDMIS，再点击连接。"
    ),
    ErrorCode.PCDMIS_CONNECT_FAIL: (
        "PC-DMIS 连接失败",
        "请确认 PCDMIS 已完全启动，且当前用户有权限访问 COM 接口。"
    ),
    ErrorCode.PCDMIS_PART_NOT_OPEN: (
        "PC-DMIS 中没有打开的零件程序",
        "请先在 PCDMIS 中打开要导出的 .prg 文件。"
    ),
    ErrorCode.PCDMIS_NO_DATA: (
        "PC-DMIS 中没有测量数据",
        "请先执行一次测量，再尝试导出。"
    ),
    ErrorCode.PDF_NOT_FOUND: (
        "PDF 文件未找到",
        "请确认 PDF 文件路径正确。"
    ),
    ErrorCode.TEMPLATE_INVALID: (
        "Excel 模板无效",
        "请重新选择有效的模板文件。"
    ),
    ErrorCode.OCR_FAIL: (
        "OCR 识别失败",
        "请检查 PDF 是否清晰，或尝试手动输入。"
    ),
    ErrorCode.OUTPUT_DIR_INVALID: (
        "输出目录无效",
        "请在设置中选择有效的输出目录。"
    ),
    ErrorCode.OUTPUT_FILE_LOCKED: (
        "输出文件被占用",
        "请关闭 Excel 文件后重试。"
    ),
    ErrorCode.BAS_NOT_DEPLOYED: (
        "BAS 脚本未部署",
        "请点击「部署 BAS 脚本」后再试。"
    ),
    ErrorCode.INJECT_FAIL: (
        "命令植入失败",
        "请确认 PRG 有写入权限，且文件未被其他程序占用。"
    ),
}


class ToolboxError(Exception):
    """
    所有业务异常的基类。
    属性：
        code: ErrorCode 枚举值
        message: 中文人类可读消息
        hint: 用户操作提示
    """

    def __init__(self, code: str, message: str, *, hint: str = ""):
        self.code = code
        self.message = message
        self.hint = hint
        super().__init__(f"[{code}] {message}")

    @classmethod
    def from_code(cls, code: str, **fmt_fields) -> "ToolboxError":
        """通过错误码构造 ToolboxError，自动填充消息和 hint。"""
        entry = _ERROR_HINTS.get(code)
        if entry:
            msg_tpl, hint = entry
            message = msg_tpl if not fmt_fields else msg_tpl.format(**fmt_fields)
        else:
            message = f"未知错误 ({code})"
            hint = ""
        return cls(code, message, hint=hint)

    def with_hint(self, hint: str) -> "ToolboxError":
        """返回带自定义 hint 的新实例（不改原对象）。"""
        return ToolboxError(self.code, self.message, hint=hint)


def format_user_error(exc: BaseException) -> tuple[str, str]:
    """
    将异常格式化为 (标题消息, 操作提示)。
    先尝试 ToolboxError.code → 再 fall back 到关键字匹配 → 最后用未知错误。
    """
    if isinstance(exc, ToolboxError):
        title = f"[{exc.code}] {exc.message}"
        hint = exc.hint
    else:
        title = str(exc)
        hint = ""

    return title, hint
