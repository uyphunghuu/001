"""FastAPI dependencies."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data"))

from data.silver.repositories.base import BaseRepository

repo = BaseRepository()


def get_repo() -> BaseRepository:
    return repo
