"""Base normalizer interface."""
from abc import ABC, abstractmethod


class BaseNormalizer(ABC):
    @abstractmethod
    def normalize(self, data: dict, context: dict | None = None) -> dict:
        pass
