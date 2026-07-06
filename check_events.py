from app.database.session import SessionLocal
from sqlalchemy import text
s = SessionLocal()
rows = s.execute(text('SELECT name, effective_start FROM gold_nodes WHERE type = :t ORDER BY effective_start LIMIT 15'), {'t': 'event'}).all()
for r in rows:
    print((r.name or '')[:50], r.effective_start)
s.close()
