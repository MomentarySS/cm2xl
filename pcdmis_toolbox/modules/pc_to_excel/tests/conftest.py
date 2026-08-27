"""pc_to_excel tests — shared fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FakePathManager:
    """Minimal fake for utils.paths.PathManager, rooted at a tmp directory."""

    def __init__(self, root: Path):
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @property
    def config_dir(self) -> Path:
        return self._root / "config"

    @property
    def pc_excel_reports(self) -> Path:
        return self._root / "reports"

    @property
    def bas_deploy_dir(self) -> Path:
        return self._root / "scripts"

    @property
    def log_dir(self) -> Path:
        return self._root / "logs"

    @property
    def cache_dir(self) -> Path:
        return self._root / "cache"
