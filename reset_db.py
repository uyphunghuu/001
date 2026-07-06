"""Drop and recreate all tables, handling the index issue."""
import sys
sys.path.insert(0, '.')
from silver.repositories import PostgresRepository
from silver.models.base import Base
from sqlalchemy import text

repo = PostgresRepository()
engine = repo._engine

# Drop indexes first if they exist
with engine.connect() as conn:
    conn.execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text("DROP INDEX IF EXISTS idx_attachments_email_id"))
    except Exception:
        pass
    try:
        conn.execute(text("DROP INDEX IF EXISTS idx_attachments_checksum"))
    except Exception:
        pass

# Now drop and recreate tables
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine, checkfirst=True)
print("Schema reset complete")
