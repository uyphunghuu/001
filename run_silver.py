#!/usr/bin/env python3
"""
Silver Pipeline Entry Point — with full observability.

Usage:
    python run_silver.py                          # Auto: try MinIO + local
    python run_silver.py --source minio           # Read from MinIO
    python run_silver.py --source local           # Read from local files
    python run_silver.py --bucket gmail-raw       # Specific bucket
    python run_silver.py --init-db                # Initialize DB schema only
    python run_silver.py --health                 # Health check
    python run_silver.py --observe                # Start Prometheus HTTP endpoint
"""
import os
import sys
import time

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data")
sys.path.insert(0, DATA)

from data.silver.repositories.base import BaseRepository
from data.silver.services import SilverPipeline, MinioHelper
from data.observability import metrics, logger, lineage


def print_header(text):
    print()
    print("=" * 70)
    print("  %s" % text)
    print("=" * 70)


def health_check():
    """Run health checks on all infrastructure components."""
    print_header("Health Check")
    results = {}

    # PostgreSQL
    print("\n  Checking PostgreSQL...")
    repo = BaseRepository()
    pg_health = repo.health_check()
    results["postgresql"] = pg_health
    print("    Status: %s (latency: %dms, pgvector: %s)" % (
        pg_health.get("status"), pg_health.get("latency_ms", 0), pg_health.get("has_pgvector", False)))

    # MinIO
    print("\n  Checking MinIO...")
    try:
        m = MinioHelper()
        m_health = m.health_check()
        results["minio"] = m_health
        print("    Status: %s (latency: %dms, buckets: %s)" % (
            m_health.get("status"), m_health.get("latency_ms", 0), m_health.get("buckets")))
    except Exception as e:
        results["minio"] = {"status": "unhealthy", "error": str(e)}
        print("    Status: unhealthy — %s" % e)

    # Gold connection check
    print("\n  Checking Gold DB...")
    try:
        from data.gold.repositories.base import BaseRepository as GoldRepo
        gr = GoldRepo()
        g_health = gr.health_check()
        results["gold_postgresql"] = g_health
    except Exception as e:
        results["gold_postgresql"] = {"status": "unhealthy", "error": str(e)}

    # Overall
    all_ok = all(r.get("status") == "healthy" for r in results.values() if isinstance(r, dict))
    all_text = "ALL HEALTHY" if all_ok else "SOME COMPONENTS UNHEALTHY"
    print("\n  Overall: %s" % all_text)
    return results


def run_from_minio(bucket: str = "gmail-raw", prefix: str = ""):
    print_header("Silver Pipeline — Reading from MinIO")
    print("  Bucket: %s" % bucket)
    print("  Prefix: %s" % (prefix or "(root)"))

    helper = MinioHelper()
    repo = BaseRepository()
    repo.init_schema()

    pipeline = SilverPipeline()

    print("\n  Listing objects...")
    objects = helper.list_objects(bucket, prefix)
    print("  Found %d objects" % len(objects))

    if not objects:
        print("\n  No objects to process.")
        return

    sources = []
    for obj in objects:
        fname = os.path.basename(obj["object_key"])
        ext = os.path.splitext(fname.lower())[1]

        source_type = "document"
        if ext == ".json":
            try:
                resp = helper._client.get_object(obj["bucket"], obj["object_key"])
                head = resp.read(262144)
                resp.close()
                resp.release_conn()
                import json as j
                preview = j.loads(head.decode("utf-8", errors="replace"))
                if "id" in preview or "threadId" in preview:
                    source_type = "email"
                elif "items" in preview or "summary" in preview:
                    source_type = "calendar"
            except Exception:
                pass

        source = helper.get_source(
            obj["bucket"], obj["object_key"],
            metadata={"source_type": source_type},
        )
        sources.append(source)

    print("  Queued %d sources for processing" % len(sources))
    result = pipeline.process_batch(sources)
    _print_result(result)


def run_from_local(directory: str = ""):
    if not directory:
        directory = os.path.join(BASE, "data", "documents")

    print_header("Silver Pipeline — Reading from Local Files")
    print("  Directory: %s" % directory)

    repo = BaseRepository()
    repo.init_schema()
    pipeline = SilverPipeline()

    if not os.path.exists(directory):
        print("\n  Directory not found: %s" % directory)
        return

    files = [f for f in os.listdir(directory)
             if os.path.isfile(os.path.join(directory, f))]
    print("  Found %d files" % len(files))

    sources = []
    for fname in files:
        fpath = os.path.join(directory, fname)
        ext = os.path.splitext(fname.lower())[1]
        source_type = "email" if ext == ".json" else "document"
        source = MinioHelper.read_from_disk(
            fpath, metadata={"source_type": source_type}
        )
        sources.append(source)

    print("  Queued %d sources for processing" % len(sources))
    result = pipeline.process_batch(sources)
    _print_result(result)


def _print_result(result: dict):
    def _safe_print(text: str):
        try:
            print(text)
        except UnicodeEncodeError:
            import sys as _sys
            _sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")

    print_header("Pipeline Complete")
    print("  Run ID:     %s" % result.get("run_id", "N/A"))
    print("  Total:      %d" % result.get("total", 0))
    print("  Processed:  %d" % result.get("processed", 0))
    print("  Failed:     %d" % result.get("failed", 0))
    print("  Skipped:    %d" % result.get("skipped", 0))
    print("  Duration:   %d ms" % result.get("batch_duration_ms", 0))

    if result.get("errors"):
        print("\n  Errors:")
        for err in result["errors"][:10]:
            _safe_print("    - %s" % err)

    print("\n  Details:")
    for r in result.get("results", []):
        status = r.get("status", "?")
        fname = r.get("filename", r.get("object_key", "?"))
        stype = r.get("source_type", "")

        if status == "processed":
            if stype == "document":
                _safe_print("    [OK] Document  %s (%d chars)" % (
                    fname, r.get("content_length", 0)))
            elif stype == "email":
                for c in r.get("communications", []):
                    _safe_print("    [OK] Comm     %s" % c.get("comm_id", "?"))
            elif stype == "calendar":
                for e in r.get("events", []):
                    _safe_print("    [OK] Event    %s" % e.get("event_id", "?"))
            else:
                _safe_print("    [OK] %s %s" % (stype.upper(), fname))
        elif status == "failed":
            _safe_print("    [FAIL] %s - %s" % (fname, r.get("error", "unknown")))
        else:
            _safe_print("    [SKIP] %s - %s" % (fname, r.get("reason", "")))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Silver Pipeline")
    parser.add_argument("--source", choices=["minio", "local", "auto"],
                        default="auto", help="Data source")
    parser.add_argument("--bucket", default="gmail-raw", help="MinIO bucket")
    parser.add_argument("--prefix", default="", help="MinIO object prefix")
    parser.add_argument("--dir", default="", help="Local directory path")
    parser.add_argument("--init-db", action="store_true", help="Only init schema")
    parser.add_argument("--health", action="store_true", help="Run health checks")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.health:
        health_check()
        sys.exit(0)

    if args.init_db:
        repo = BaseRepository()
        repo.init_schema()
        print("Database schema initialized.")
        sys.exit(0)

    logger.info("Silver pipeline started", component="cli", event="pipeline.start",
                 source=args.source, bucket=args.bucket)

    if args.source == "minio":
        run_from_minio(args.bucket, args.prefix)
    elif args.source == "local":
        run_from_local(args.dir)
    else:
        local_dir = args.dir or os.path.join(BASE, "data", "documents")
        if os.path.exists(local_dir) and any(os.path.isfile(os.path.join(local_dir, f)) for f in os.listdir(local_dir)):
            run_from_local(local_dir)
        else:
            run_from_minio(args.bucket, args.prefix)
