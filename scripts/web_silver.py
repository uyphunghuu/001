#!/usr/bin/env python3
"""
Web viewer for Silver layer (PostgreSQL).
Xem du lieu Silver tren trinh duyet: http://localhost:8080
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    print("Can't import http.server - use Python 3")
    sys.exit(1)


PORT = int(os.getenv("SILVER_WEB_PORT", "8080"))


def query(sql, params=None):
    from scripts.database_pg import get_conn, put_conn
    conn = get_conn()
    c = conn.cursor()
    if params:
        c.execute(sql, params)
    else:
        c.execute(sql)
    cols = [d.name for d in c.description] if c.description else []
    rows = c.fetchall() if c.description else []
    put_conn(conn)
    return cols, rows


HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Silver Layer - AI Platform</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f0f2f5; color: #333; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white; padding: 20px 40px; }}
.header h1 {{ font-size: 24px; }}
.header p {{ opacity: 0.85; font-size: 13px; margin-top: 4px; }}
.nav {{ background: white; border-bottom: 1px solid #ddd; padding: 10px 40px; display: flex; gap: 10px; }}
.nav a {{ padding: 8px 20px; text-decoration: none; color: #555; border-radius: 6px; font-size: 14px; }}
.nav a:hover {{ background: #f0f0f0; }}
.nav a.active {{ background: #667eea; color: white; }}
.content {{ max-width: 1200px; margin: 20px auto; padding: 0 20px; }}
.card {{ background: white; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 20px; overflow: hidden; }}
.card-header {{ padding: 15px 20px; border-bottom: 1px solid #eee;
               font-weight: 600; font-size: 16px; display: flex; justify-content: space-between; }}
.card-body {{ padding: 0; overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: #f8f9fa; text-align: left; padding: 10px 15px;
      font-weight: 600; white-space: nowrap; border-bottom: 2px solid #dee2e6; }}
td {{ padding: 8px 15px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
tr:hover td {{ background: #f8f9ff; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
          font-weight: 500; }}
.badge-vi {{ background: #e3f2fd; color: #1565c0; }}
.badge-en {{ background: #fff3e0; color: #e65100; }}
.badge-document {{ background: #e8f5e9; color: #2e7d32; }}
.badge-text {{ background: #f3e5f5; color: #7b1fa2; }}
.hash {{ font-family: monospace; font-size: 11px; color: #888; }}
.keywords {{ font-size: 12px; color: #666; }}
.text-preview {{ font-family: monospace; font-size: 12px; color: #444;
                white-space: pre-wrap; max-height: 120px; overflow-y: auto; }}
.stats {{ font-size: 13px; color: #666; padding: 20px; display: flex; gap: 30px; }}
.stats-item {{ text-align: center; }}
.stats-num {{ font-size: 28px; font-weight: 700; color: #667eea; }}
.stats-label {{ font-size: 11px; color: #999; }}
.empty {{ padding: 40px; text-align: center; color: #999; }}
.metadata {{ font-size: 12px; color: #666; }}
.metadata summary {{ cursor: pointer; padding: 10px 15px; }}
.metadata .inner {{ padding: 0 15px 15px; }}
.chunk-block {{ margin: 5px 0; padding: 8px 12px; background: #f8f9fa;
               border-radius: 6px; border-left: 3px solid #667eea; }}
.chunk-idx {{ font-size: 11px; color: #999; }}
.align-right {{ text-align: right; }}
</style>
</head>
<body>
<div class="header">
  <h1>Silver Layer</h1>
  <p>AI Platform - Data Pipeline | PostgreSQL</p>
</div>
<div class="nav">
  <a href="/" class="{active_records}">Records</a>
  <a href="/attachments" class="{active_attachments}">Attachments</a>
  <a href="/texts" class="{active_texts}">Text Content</a>
  <a href="/chunks" class="{active_chunks}">Chunks</a>
  <a href="/runs" class="{active_runs}">Pipeline Runs</a>
</div>
<div class="content">
{body}
</div>
</body>
</html>"""


def render_nav(active):
    return HTML.format(
        active_records="active" if active == "records" else "",
        active_attachments="active" if active == "attachments" else "",
        active_texts="active" if active == "texts" else "",
        active_chunks="active" if active == "chunks" else "",
        active_runs="active" if active == "runs" else "",
        body="{body}",
    )


def page_records():
    cols, rows = query("""
        SELECT email_id, subject, sender_name, sender_email,
               received_at, content_type, language,
               attachment_count, total_text_length, keyword_count,
               metadata, processed_at
        FROM silver_records ORDER BY received_at DESC
    """)
    nav = render_nav("records")
    rows_html = ""
    for r in rows:
        meta = r[10] or {}
        dates = meta.get("detected_dates", [])
        rows_html += "<tr><td>%s</td><td>%s</td><td>%s<br><small>%s</small></td><td>%s</td><td><span class='badge badge-%s'>%s</span> / <span class='badge badge-%s'>%s</span></td><td class='align-right'>%d / %d</td><td><details class='metadata'><summary>%d keys</summary><div class='inner'>%s</div></details></td></tr>" % (
            r[0], r[1], r[2], r[3],
            str(r[4])[:19] if r[4] else "",
            r[5], r[5], r[6], r[6],
            r[7], r[8],
            len(meta), json.dumps(meta, ensure_ascii=False)[:300],
        )
    body = """
    <div class="card">
      <div class="card-header">Silver Records <span>%d total</span></div>
      <div class="card-body">
        <table>
          <tr><th>Email ID</th><th>Subject</th><th>Sender</th><th>Received</th><th>Type / Lang</th><th>Attach / Chars</th><th>Metadata</th></tr>
          %s
        </table>
      </div>
    </div>
    """ % (len(rows), rows_html)
    return nav.replace("{body}", body)


def page_attachments():
    cols, rows = query("""
        SELECT email_id, filename, normalized_filename, file_category,
               size_kb, language, text_length, text_word_count,
               content_type, keywords, content_hash
        FROM silver_attachments ORDER BY email_id
    """)
    nav = render_nav("attachments")
    rows_html = ""
    for r in rows:
        kw = ", ".join(r[9][:5]) if r[9] else ""
        rows_html += "<tr><td>%s</td><td>%s</td><td><span class='badge badge-%s'>%s</span></td><td>%.2f</td><td><span class='badge badge-%s'>%s</span></td><td class='align-right'>%d / %d</td><td>%s</td><td class='keywords'>%s</td><td class='hash'>%s</td></tr>" % (
            r[0], r[1],
            r[3], r[3],
            r[4] if r[4] else 0,
            r[5], r[5],
            r[6], r[7],
            r[8],
            kw,
            r[10][:20] + "..." if r[10] else "",
        )
    body = """
    <div class="card">
      <div class="card-header">Silver Attachments <span>%d total</span></div>
      <div class="card-body">
        <table>
          <tr><th>Email ID</th><th>Filename</th><th>Category</th><th>Size KB</th><th>Lang</th><th>Chars / Words</th><th>Type</th><th>Keywords</th><th>Hash</th></tr>
          %s
        </table>
      </div>
    </div>
    """ % (len(rows), rows_html)
    return nav.replace("{body}", body)


def page_texts():
    cols, rows = query("""
        SELECT email_id, filename, normalized_text
        FROM silver_texts ORDER BY email_id
    """)
    nav = render_nav("texts")
    cards = ""
    for r in rows:
        cards += """
        <div class='card'>
          <div class='card-header'>%s / %s <span>%d chars</span></div>
          <div class='card-body'>
            <pre class='text-preview'>%s</pre>
          </div>
        </div>
        """ % (r[0], r[1], len(r[2]), _escape(r[2]))
    body = """
    <div class="stats">
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Texts</div></div>
    </div>
    %s
    """ % (len(rows), cards)
    return nav.replace("{body}", body)


def page_chunks():
    cols, rows = query("""
        SELECT email_id, chunk_index, text, length
        FROM silver_chunks ORDER BY email_id, chunk_index
    """)
    nav = render_nav("chunks")
    cards = ""
    current_email = None
    for r in rows:
        if current_email != r[0]:
            current_email = r[0]
        cards += "<div class='chunk-block'><span class='chunk-idx'>[%s chunk:%d] %d chars</span><br>%s</div>" % (
            r[0], r[1], r[3], _escape(r[2][:200]),
        )
    body = """
    <div class="stats">
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Chunks</div></div>
    </div>
    %s
    """ % (len(rows), cards)
    return nav.replace("{body}", body)


def page_runs():
    cols, rows = query("""
        SELECT id, run_at, status, processed, failed, errors
        FROM silver_processing ORDER BY id DESC
    """)
    nav = render_nav("runs")
    rows_html = ""
    for r in rows:
        rows_html += "<tr><td>%d</td><td>%s</td><td>%s</td><td class='align-right'>%d</td><td class='align-right'>%d</td><td>%s</td></tr>" % (
            r[0], str(r[1])[:19], r[2], r[3], r[4], r[5][:100] if r[5] else "[]",
        )
    body = """
    <div class="card">
      <div class="card-header">Pipeline Runs</div>
      <div class="card-body">
        <table>
          <tr><th>Run ID</th><th>Run At</th><th>Status</th><th>Processed</th><th>Failed</th><th>Errors</th></tr>
          %s
        </table>
      </div>
    </div>
    """ % rows_html
    return nav.replace("{body}", body)


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            path = self.path.rstrip("/") or "/"
            if path == "/" or path == "/records":
                body = page_records()
            elif path == "/attachments":
                body = page_attachments()
            elif path == "/texts":
                body = page_texts()
            elif path == "/chunks":
                body = page_chunks()
            elif path == "/runs":
                body = page_runs()
            else:
                body = render_nav("records").replace("{body}",
                    "<div class='card'><div class='empty'>404 - Page not found</div></div>")

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

    def log_message(self, fmt, *args):
        print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), args[0]))


if __name__ == "__main__":
    print("=" * 50)
    print("  Silver Layer Web Viewer")
    print("  http://localhost:%d" % PORT)
    print("=" * 50)

    try:
        from scripts.database_pg import init_db
        init_db()
    except Exception as e:
        print("PostgreSQL not available: %s" % e)
        print("Start Docker first: docker-compose up -d")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()
