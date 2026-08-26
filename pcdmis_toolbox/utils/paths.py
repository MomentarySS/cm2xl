"""
PCDMIS Toolbox 2.0 — 统一路径管理
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
    """

    def __init__(self):
        self._frozen = getattr(sys, "frozen", False)
        if self._frozen:
            self._bundle = Path(sys._MEIPASS)
            self._root = Path(sys.executable).resolve().parent
        else:
            self._bundle = Path(__file__).resolve().parent.parent
            self._root = self._bundle

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
        d = self._root / "data"
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

    def is_frozen(self) -> bool:
        return self._frozen


# 全局单例
paths = PathManager()
