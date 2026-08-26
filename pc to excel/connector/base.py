"""测量软件连接器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.models import FeatureRecord


@dataclass
class ConnectionInfo:
    connected: bool
    source: str
    version: str = ""
    message: str = ""


class MeasurementConnector(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def connect(self) -> ConnectionInfo:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def extract_features(self) -> list[FeatureRecord]:
        ...
