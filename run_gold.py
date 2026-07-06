#!/usr/bin/env python3
"""
Gold Pipeline Entry Point — with full observability.

Commands:
    python run_gold.py                        # Run pipeline
    python run_gold.py --show                 # Stats with quality metrics
    python run_gold.py --detail               # All nodes + edges
    python run_gold.py --query "keyword"      # Full-text search
    python run_gold.py --semantic "query"     # Semantic vector search
    python run_gold.py --health               # Health check
    python run_gold.py --validate-embeddings  # Validate all embeddings
    python run_gold.py --lineage-stats        # Show lineage events
"""
import os
import sys
import json

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data")
sys.path.insert(0, DATA)

from data.observability import metrics, logger, lineage


def print_header(text):
    print()
    print("=" * 70)
    print("  %s" % text)
    print("=" * 70)


def init_db():
    print_header("Gold Layer — Initialize Schema")
    from data.gold.repositories.base import BaseRepository
    repo = BaseRepository()
    repo.init_schema()
    print("  Gold tables created: gold_nodes, gold_edges, gold_timeline")
    print("  Indexes: 15 indexes created")


def run_migration():
    print_header("Gold Layer — Run Migration")
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config(os.path.join(DATA, "gold", "migrations", "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    print("  Migration complete")


def show_stats():
    print_header("Gold Layer — Stats & Quality")
    from data.gold.repositories.node_repository import NodeRepository
    from data.gold.repositories.edge_repository import EdgeRepository
    from data.gold.repositories.base import BaseRepository
    from sqlalchemy import text
    nr = NodeRepository()
    er = EdgeRepository()
    nc = nr.count()
    ec = er.count()
    print("  Nodes: %d" % nc)
    print("  Edges: %d" % ec)

    if nc > 0:
        print("\n  Nodes by type:")
        by_type = nr.count_by_type()
        for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
            print("    %-20s: %d" % (t, c))

        # Quality: embedding status
        with nr.session as s:
            embed_null = s.execute(text("""
                SELECT COUNT(*) FROM gold_nodes WHERE embedding_vector IS NULL
            """)).scalar()
            print("\n  Embedding quality:")
            print("    With embedding:  %d (%.1f%%)" % (nc - embed_null, (nc - embed_null) / nc * 100))
            print("    Without:         %d (%.1f%%)" % (embed_null, embed_null / nc * 100))

            # Quality: nodes with empty content
            empty_content = s.execute(text("""
                SELECT COUNT(*) FROM gold_nodes WHERE content IS NULL OR content = ''
            """)).scalar()
            print("\n  Content quality:")
            print("    Empty content:   %d (%.1f%%)" % (empty_content, empty_content / nc * 100))

            # Quality: constraint violations
            orphan = s.execute(text("""
                SELECT COUNT(*) FROM gold_nodes g
                WHERE g.source_ref->>'table' = 'communications'
                AND NOT EXISTS (
                    SELECT 1 FROM communications c WHERE c.id::text = g.source_ref->>'id'
                )
            """)).scalar()
            print("    Orphan refs:     %d" % orphan)

    if ec > 0:
        print("\n  Edges by predicate:")
        by_pred = er.count_by_predicate()
        for p, c in sorted(by_pred.items(), key=lambda x: -x[1]):
            print("    %-20s: %d" % (p, c))

    # Check pgvector
    print("\n  pgvector:")
    with nr.session as s:
        has_hnsw = s.execute(text("""
            SELECT COUNT(*) FROM pg_indexes WHERE indexdef LIKE '%hnsw%'
        """)).scalar()
        print("    HNSW index:      %s" % ("present" if has_hnsw else "missing"))


def show_detail():
    print_header("Gold Layer — All Nodes")
    from data.gold.repositories.node_repository import NodeRepository
    from data.gold.repositories.edge_repository import EdgeRepository
    nr = NodeRepository()
    er = EdgeRepository()
    with nr.session as s:
        from sqlalchemy import text
        nodes = s.execute(text("""
            SELECT id, type, subtype, name,
                   substr(properties::text, 1, 200) as props,
                   status, importance,
                   embedding_vector IS NOT NULL as has_embedding
            FROM gold_nodes ORDER BY type, subtype, name
        """)).fetchall()
        for n in nodes:
            stype = f"[{n.subtype}]" if n.subtype else ""
            embed_mark = " [EMB]" if n.has_embedding else ""
            print(f'  {n.type:20s} {stype:15s} {n.name[:50]:50s}  imp={n.importance}{embed_mark}')
            print(f'  {"":20s} ID: {n.id}')

    print()
    print_header("Gold Layer — All Edges")
    with nr.session as s:
        edges = s.execute(text("""
            SELECT e.predicate,
                   src.name as source_name, src.type as source_type,
                   tgt.name as target_name, tgt.type as target_type
            FROM gold_edges e
            JOIN gold_nodes src ON src.id = e.source_node_id
            JOIN gold_nodes tgt ON tgt.id = e.target_node_id
            ORDER BY e.predicate
        """)).fetchall()
        for e in edges:
            print(f'  {e.predicate:20s}  [{e.source_type}] {e.source_name[:30]:30s}  -->  [{e.target_type}] {e.target_name[:30]:30s}')


def show_query(q: str):
    print_header("Gold Layer — Search: %s" % q)
    from data.gold.repositories.node_repository import NodeRepository
    nr = NodeRepository()
    with nr.session as s:
        from sqlalchemy import text
        nodes = s.execute(text("""
            SELECT id, type, subtype, name,
                   substr(properties::text, 1, 200) as props,
                   status, importance, substr(content, 1, 300) as content_snip
            FROM gold_nodes
            WHERE name ILIKE :q OR content ILIKE :q
            ORDER BY importance DESC, name
            LIMIT 20
        """), {"q": f"%{q}%"}).fetchall()
        if not nodes:
            print("  No results")
            return
        for n in nodes:
            stype = f"[{n.subtype}]" if n.subtype else ""
            print(f'  {n.type:20s} {stype:15s} {n.name[:60]}')
            print(f'  {"":20s} ID: {n.id}  |  imp={n.importance}')
            if n.content_snip:
                print(f'  {"":20s} Content: {n.content_snip[:150]}...')
            print()


def show_semantic(q: str):
    print_header("Gold Layer — Semantic Search: %s" % q)
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        vec = model.encode(q, normalize_embeddings=True)
    except ImportError:
        print("  sentence-transformers not installed.")
        return

    from data.gold.repositories.base import BaseRepository
    repo = BaseRepository()
    with repo.session as s:
        from sqlalchemy import text
        rows = s.execute(text("""
            SELECT id, type, subtype, name,
                   substr(content, 1, 200) as content_snip, importance,
                   1 - (embedding_vector <=> CAST(:vec AS vector)) as score
            FROM gold_nodes
            WHERE embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> CAST(:vec AS vector)
            LIMIT 10
        """), {"vec": vec.tolist()}).fetchall()
        if not rows:
            print("  No results (try running pipeline first, or --validate-embeddings)")
            return
        for r in rows:
            stype = f"[{r.subtype}]" if r.subtype else ""
            print(f'  {r.type:20s} {stype:15s} {r.name[:55]:55s}  score={r.score:.4f}')
            print(f'  {"":20s} ID: {r.id}')
            if r.content_snip:
                print(f'  {"":20s} Content: {r.content_snip[:120]}...')
            print()


def validate_embeddings():
    """Validate all embeddings in the database."""
    print_header("Embedding Validation")
    from data.gold.pipeline.embedding_generator import EmbeddingGenerator
    emb = EmbeddingGenerator()
    result = emb.validate_embeddings()
    print("  Total nodes:      %d" % result["total"])
    print("  Valid embeddings: %d" % result["valid"])
    print("  Invalid dim:      %d" % result["invalid_dim"])
    print("  Corrupt:          %d" % result["corrupt"])
    print("  Null:             %d" % result["null"])
    print("  Health:           %s" % result["health"])
    if result["invalid_dim"] > 0 or result["corrupt"] > 0:
        print("\n  ⚠️  Issues found — run pipeline to regenerate embeddings")


def lineage_stats():
    """Show lineage event statistics."""
    print_header("Lineage Stats")
    lineage_file = os.environ.get("LINEAGE_FILE", "data/observability/lineage_events.jsonl")
    if not os.path.exists(lineage_file):
        print("  No lineage events found (run pipeline first)")
        return
    with open(lineage_file, "r") as f:
        events = [json.loads(line) for line in f if line.strip()]
    print("  Total events:     %d" % len(events))
    transforms = {}
    for ev in events:
        t = ev.get("job", {}).get("name", "unknown")
        transforms[t] = transforms.get(t, 0) + 1
    print("\n  By transform:")
    for t, c in sorted(transforms.items(), key=lambda x: -x[1]):
        print("    %-30s: %d" % (t, c))


def health_check():
    """Run health checks on all Gold infrastructure."""
    print_header("Gold Health Check")
    from data.gold.repositories.base import BaseRepository
    from data.gold.pipeline.embedding_generator import EmbeddingGenerator

    # DB
    repo = BaseRepository()
    pg = repo.health_check()
    print("  PostgreSQL:       %s (%.1fms)" % (pg.get("status"), pg.get("latency_ms", 0)))

    # Embedding model
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("all-MiniLM-L6-v2")
        print("  Embedding model:  [LOADED] (%s, %d dim)" % (m._modules.get('0', {}).__class__.__name__ if hasattr(m, '_modules') else "OK", 384))
    except Exception as e:
        print("  Embedding model:  [FAIL] %s" % e)

    # Vector count
    if pg.get("status") == "healthy":
        from sqlalchemy import text
        with repo.session as s:
            n_count = s.execute(text("SELECT COUNT(*) FROM gold_nodes")).scalar()
            e_count = s.execute(text("SELECT COUNT(*) FROM gold_edges")).scalar()
            v_count = s.execute(text("SELECT COUNT(*) FROM gold_nodes WHERE embedding_vector IS NOT NULL")).scalar()
            has_hnsw = s.execute(text("SELECT COUNT(*) FROM pg_indexes WHERE indexdef LIKE '%hnsw%'")).scalar()
        print("  Nodes:            %d" % n_count)
        print("  Edges:            %d" % e_count)
        print("  With embeddings:  %d" % v_count)
        print("  HNSW index:       %s" % ("present" if has_hnsw else "missing"))


def run_pipeline():
    print_header("Gold Pipeline — Processing")
    print("  Reading from Silver (documents, communications, events)")
    print("  Classifying into Gold (nodes + edges)")

    from data.gold.repositories.base import BaseRepository
    from data.gold.pipeline import GoldPipeline

    repo = BaseRepository()
    repo.init_schema()

    pipeline = GoldPipeline()
    result = pipeline.process_all()

    print("\n  Results:")
    print("    Nodes created:     %d" % result.get("nodes_created", 0))
    print("    Edges created:     %d" % result.get("edges_created", 0))
    print("    Agents created:    %d" % result.get("agents_created", 0))
    print("    Documents:         %d" % result.get("documents", 0))
    print("    Communications:    %d" % result.get("communications", 0))
    print("    Events:            %d" % result.get("events", 0))
    print("    Embeddings updated:%d" % result.get("embeddings_updated", 0))
    print("    Timeline entries:  %d" % result.get("timeline_entries", 0))
    print("    Discovered edges:  %d" % result.get("discovered_edges", 0))
    print("    Total duration:    %d ms" % result.get("total_duration_ms", 0))

    if result.get("phase_times_ms"):
        print("\n  Phase times:")
        for phase, ms in result["phase_times_ms"].items():
            print("    %-20s: %d ms" % (phase, ms))

    errors = result.get("errors", [])
    if errors:
        print("\n  Errors (%d):" % len(errors))
        for e in errors[:10]:
            print("    - %s" % e)
    else:
        print("\n  => No errors")

    # Validate embeddings after pipeline
    print("\n  Post-run validation:")
    validate_embeddings()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gold Pipeline")
    parser.add_argument("--init-db", action="store_true", help="Create Gold schema only")
    parser.add_argument("--migrate", action="store_true", help="Run Alembic migration")
    parser.add_argument("--show", action="store_true", help="Show Gold stats + quality")
    parser.add_argument("--detail", action="store_true", help="Show all nodes and edges")
    parser.add_argument("--query", type=str, default="", help="Search nodes by name/content")
    parser.add_argument("--semantic", type=str, default="", help="Semantic vector search")
    parser.add_argument("--install-pgvector", action="store_true", help="Install pgvector + migrate embeddings")
    parser.add_argument("--health", action="store_true", help="Health check")
    parser.add_argument("--validate-embeddings", action="store_true", help="Validate all embeddings")
    parser.add_argument("--lineage-stats", action="store_true", help="Show lineage event stats")
    args = parser.parse_args()

    if args.health:
        health_check()
    elif args.init_db:
        init_db()
    elif args.migrate:
        run_migration()
    elif args.show:
        show_stats()
    elif args.detail:
        show_detail()
    elif args.install_pgvector:
        from scripts.install_pgvector import run as install_pgvector
        install_pgvector()
    elif args.semantic:
        show_semantic(args.semantic)
    elif args.query:
        show_query(args.query)
    elif args.validate_embeddings:
        validate_embeddings()
    elif args.lineage_stats:
        lineage_stats()
    else:
        run_pipeline()
