"""Delete all Silver data from PostgreSQL."""
import sys
sys.path.insert(0, '.')
from silver.repositories import PostgresRepository
from silver.models.base import Base
from sqlalchemy import text

repo = PostgresRepository()
engine = repo._engine

with engine.connect() as conn:
    conn.execution_options(isolation_level="AUTOCOMMIT")
    conn.execute(text("TRUNCATE TABLE documents, emails, calendar_events, attachments, raw_metadata, pipeline_runs RESTART IDENTITY CASCADE"))
    print("All Silver data cleared")
