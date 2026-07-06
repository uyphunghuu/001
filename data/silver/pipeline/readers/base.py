"""Base reader interface."""
from abc import ABC, abstractmethod

from data.silver.schemas.source import SourceData


class BaseReader(ABC):
    @abstractmethod
    def can_handle(self, source: SourceData) -> bool:
        pass

    @abstractmethod
    def read(self, source: SourceData) -> dict:
        pass

    @abstractmethod
    def extract_metadata(self, source: SourceData) -> dict:
        pass
