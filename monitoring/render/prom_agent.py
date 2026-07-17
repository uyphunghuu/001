import os
import time
import json
import logging
import threading
from urllib.request import Request, urlopen
from urllib.error import URLError

APP_URL = os.getenv("APP_URL", "https://ai-platform.onrender.com")
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))
SCRAPE_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT", "10"))

metrics_cache = b"# no data yet"
metrics_updated = 0.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("prom-agent")

HEADER_ACCEPT = os.getenv("METRICS_HEADER_ACCEPT", "text/plain; version=0.0.4; charset=utf-8")


def scrape_metrics():
    global metrics_cache, metrics_updated
    targets = [("app", f"{APP_URL}/metrics")]

    # Also try additional targets from env
    extra = os.getenv("EXTRA_TARGETS", "")
    if extra:
        for t in extra.split(","):
            t = t.strip()
            if t:
                targets.append((t.split("/")[-1].split(".")[0], t))

    all_lines = []
    for name, url in targets:
        try:
            req = Request(url, headers={"Accept": HEADER_ACCEPT})
            resp = urlopen(req, timeout=SCRAPE_TIMEOUT)
            data = resp.read().decode("utf-8")
            all_lines.append(f"# scrape_target=\"{name}\"")
            all_lines.append(data)
            logger.info(f"Scraped {name} OK ({len(data)} bytes)")
        except Exception as e:
            logger.warning(f"Scrape {name} failed: {e}")

    if all_lines:
        metrics_cache = "\n".join(all_lines).encode("utf-8")
    metrics_updated = time.time()


def scrape_loop():
    while True:
        try:
            scrape_metrics()
        except Exception as e:
            logger.error(f"Scrape loop error: {e}")
        time.sleep(SCRAPE_INTERVAL)


threading.Thread(target=scrape_loop, daemon=True).start()
start_time = time.time()


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")

    if path == "/health":
        data = json.dumps({
            "status": "ok",
            "target": APP_URL,
            "scrape_interval": SCRAPE_INTERVAL,
            "uptime": int(time.time() - start_time),
        }).encode()
        start_response("200 OK", [("Content-Type", "application/json")])
        return [data]

    elif path == "/metrics":
        start_response("200 OK", [
            ("Content-Type", "text/plain; version=0.0.4; charset=utf-8"),
        ])
        return [metrics_cache]

    elif path == "/ready":
        if metrics_updated > 0:
            start_response("200 OK", [("Content-Type", "application/json")])
            return [b'{"status":"ready"}']
        else:
            start_response("503 Service Unavailable", [("Content-Type", "application/json")])
            return [b'{"status":"not_ready"}']
    else:
        start_response("404 Not Found", [("Content-Type", "application/json")])
        return [b'{"error":"not found"}']


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    from wsgiref.simple_server import make_server
    logger.info(f"Starting Prometheus Agent on port {port}")
    logger.info(f"  Target: {APP_URL}/metrics")
    logger.info(f"  Interval: {SCRAPE_INTERVAL}s")
    server = make_server("0.0.0.0", port, app)
    server.serve_forever()
