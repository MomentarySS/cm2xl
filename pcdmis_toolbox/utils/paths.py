"""
cm2xl — 统一路径管理
区分开发模式、Frozen 打包模式、无网测量房环境。
"""

from pathlib import Path
import sys
import os

# BAS 脚本固定部署路径（不能含空格，不能在 Program Files）
BAS_DEPLOY_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "PCDMIS_ExcelExporter" / "scripts"


class PathManager:
    """
    统一管理各模块的路径，区分 frozen / dev 模式。

    - 开发模式：data/config/logs/cache 放在项目根目录下的 data/
    - 打包模式：data/config/logs/cache 放在 %LOCALAPPDATA%/cm2xl/（可写，无需 admin）
    - 资源文件（模型、模板等）：仍从 exe 所在目录或 _MEIPASS 加载
    """

    def __init__(self):
        self._frozen = getattr(sys, "frozen", False)
        if self._frozen:
            self._bundle = Path(sys._MEIPASS)
            self._root = Path(sys.executable).resolve().parent
            # 打包后用户数据放 LocalAppData，避免 Program Files 权限问题
            self._user_data = Path(os.environ.get("LOCALAPPDATA", "")) / "cm2xl"
        else:
            self._bundle = Path(__file__).resolve().parent.parent
            self._root = self._bundle
            self._user_data = self._root / "data"

    @property
    def root(self) -> Path:
        """项目根目录（exe 所在目录或开发根目录）"""
        return self._root

    @property
    def bundle(self) -> Path:
        """PyInstaller 打包资源目录（sys._MEIPASS）"""
        return self._bundle

    @property
    def data_dir(self) -> Path:
        """用户数据目录（可写），不存在则创建"""
        d = self._user_data
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def config_dir(self) -> Path:
        """配置文件目录"""
        d = self.data_dir / "config"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def log_dir(self) -> Path:
        """日志目录"""
        d = self.data_dir / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def cache_dir(self) -> Path:
        """缓存目录（OCR 缓存等）"""
        d = self.data_dir / "cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def bas_deploy_dir(self) -> Path:
        """BAS 脚本部署目录（LocalAppData）"""
        d = BAS_DEPLOY_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def cmm_filler_templates(self) -> Path:
        """CMMFiller 模板目录"""
        return self.bundle / "modules" / "cmm_filler" / "templates"

    @property
    def cmm_filler_models(self) -> Path:
        """CMMFiller PaddleOCR 模型目录"""
        return self.bundle / "modules" / "cmm_filler" / "models" / "paddleocr"

    @property
    def pc_excel_reports(self) -> Path:
        """PC to Excel 报告导出目录"""
        d = self.data_dir / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def docs_dir(self) -> Path:
        """用户文档目录（打包后在 exe 同级 docs/）。"""
        for candidate in (self._root / "docs", self._bundle / "docs"):
            if candidate.is_dir():
                return candidate
        return self._root / "docs"

    def user_data_location_hint(self) -> str:
        """面向用户的简短说明：日志/配置是否在安装目录。"""
        if self._frozen:
            return (
                "安装版：配置、日志、OCR 缓存写在当前 Windows 用户的 AppData 下"
                "（通常在 C 盘，路径见下），不在程序安装目录。"
                "这样无需管理员权限也能保存设置和日志。"
            )
        return (
            "开发模式：配置、日志、缓存在本项目 data/ 目录下"
            "（与安装包路径无关）。"
        )

    def is_frozen(self) -> bool:
        return self._frozen


# 全局单例
paths = PathManager()
