#!/usr/bin/env python3
"""Web viewer for Silver Layer — entity-based schema."""
import json
import os
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data")
sys.path.insert(0, DATA)

PORT = int(os.getenv("SILVER_WEB_PORT", "8080"))

from data.silver.repositories.base import BaseRepository
from sqlalchemy import text

repo = BaseRepository()


def query(sql, params=None):
    with repo.session as s:
        result = s.execute(text(sql), params or {})
        cols = list(result.keys()) if result.returns_rows else []
        rows = list(result.fetchall()) if result.returns_rows else []
        return cols, rows


HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Silver Layer - AI Platform</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#f0f2f5; color:#333; }}
.header {{ background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
          color:white; padding:20px 40px; }}
.header h1 {{ font-size:24px; }}
.header p {{ opacity:0.85; font-size:13px; margin-top:4px; }}
.nav {{ background:white; border-bottom:1px solid #ddd; padding:10px 40px; display:flex; gap:10px; }}
.nav a {{ padding:8px 20px; text-decoration:none; color:#555; border-radius:6px; font-size:14px; }}
.nav a:hover {{ background:#f0f0f0; }}
.nav a.active {{ background:#667eea; color:white; }}
.content {{ max-width:1200px; margin:20px auto; padding:0 20px; }}
.card {{ background:white; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.08);
        margin-bottom:20px; overflow:hidden; }}
.card-header {{ padding:15px 20px; border-bottom:1px solid #eee;
               font-weight:600; font-size:16px; display:flex; justify-content:space-between; }}
.card-body {{ padding:0; overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:#f8f9fa; text-align:left; padding:10px 15px;
     font-weight:600; white-space:nowrap; border-bottom:2px solid #dee2e6; }}
td {{ padding:8px 15px; border-bottom:1px solid #f0f0f0; vertical-align:top; }}
tr:hover td {{ background:#f8f9ff; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:500; }}
.badge-document {{ background:#e8f5e9; color:#2e7d32; }}
.badge-email {{ background:#e3f2fd; color:#1565c0; }}
.badge-calendar {{ background:#fff3e0; color:#e65100; }}
.badge-slack {{ background:#f3e5f5; color:#7b1fa2; }}
.hash {{ font-family:monospace; font-size:11px; color:#888; }}
.text-preview {{ font-family:monospace; font-size:12px; color:#444;
                white-space:pre-wrap; max-height:200px; overflow-y:auto; }}
.stats {{ font-size:13px; color:#666; padding:20px; display:flex; gap:30px; flex-wrap:wrap; }}
.stats-item {{ text-align:center; }}
.stats-num {{ font-size:28px; font-weight:700; color:#667eea; }}
.stats-label {{ font-size:11px; color:#999; }}
.empty {{ padding:40px; text-align:center; color:#999; }}
.metadata {{ font-size:12px; color:#666; }}
.metadata summary {{ cursor:pointer; padding:10px 15px; }}
.metadata .inner {{ padding:0 15px 15px; }}
.align-right {{ text-align:right; }}
</style>
</head>
<body>
<div class="header">
  <h1>Silver Layer</h1>
  <p>AI Platform — Entity-based Architecture | PostgreSQL 17</p>
</div>
<div class="nav">
  <a href="/" class="{active_dashboard}">Dashboard</a>
  <a href="/documents" class="{active_documents}">Documents</a>
  <a href="/communications" class="{active_communications}">Communications</a>
  <a href="/events" class="{active_events}">Events</a>
  <a href="/contacts" class="{active_contacts}">Contacts</a>
  <a href="/runs" class="{active_runs}">Pipeline Runs</a>
</div>
<div class="content">
{body}
</div>
</body>
</html>"""


def render_nav(active):
    return HTML.format(
        active_dashboard="active" if active == "dashboard" else "",
        active_documents="active" if active == "documents" else "",
        active_communications="active" if active == "communications" else "",
        active_events="active" if active == "events" else "",
        active_contacts="active" if active == "contacts" else "",
        active_runs="active" if active == "runs" else "",
        body="{body}",
    )


def page_dashboard():
    nav = render_nav("dashboard")
    try:
        doc_count = repo.execute_raw("SELECT COUNT(*) FROM documents")[0][0]
        comm_count = repo.execute_raw("SELECT COUNT(*) FROM communications")[0][0]
        event_count = repo.execute_raw("SELECT COUNT(*) FROM events")[0][0]
        contact_count = repo.execute_raw("SELECT COUNT(*) FROM contacts")[0][0]
        file_count = repo.execute_raw("SELECT COUNT(*) FROM files")[0][0]
        run_count = repo.execute_raw("SELECT COUNT(*) FROM processing_logs")[0][0]
    except Exception:
        doc_count = comm_count = event_count = contact_count = file_count = run_count = 0

    body = """
    <div class="stats">
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Documents</div></div>
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Communications</div></div>
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Events</div></div>
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Contacts</div></div>
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Files</div></div>
      <div class="stats-item"><div class="stats-num">%d</div><div class="stats-label">Pipeline Runs</div></div>
    </div>
    <div class="card">
      <div class="card-header">Recent Documents</div>
      <div class="card-body">
    """ % (doc_count, comm_count, event_count, contact_count, file_count, run_count)

    try:
        cols, rows = query("SELECT id, title, source, checksum, created_at FROM documents ORDER BY created_at DESC LIMIT 10")
        if rows:
            body += "<table><tr><th>ID</th><th>Title</th><th>Source</th><th>Checksum</th><th>Created</th></tr>"
            for r in rows:
                body += "<tr><td class='hash'>%s</td><td>%s</td><td>%s</td><td class='hash'>%s</td><td>%s</td></tr>" % (
                    _esc(str(r[0])[:8]), _esc(str(r[1] or "")[:60]), _esc(str(r[2])),
                    _esc(str(r[3] or "")[:16]), _esc(str(r[4])[:19] if r[4] else ""))
            body += "</table>"
    except Exception:
        pass
    body += """</div></div>"""
    return nav.replace("{body}", body)


def page_documents():
    nav = render_nav("documents")
    try:
        cols, rows = query("""
            SELECT id, title, source, source_type, content, checksum,
                   mime_type, size_bytes, processing_status, created_at
            FROM documents ORDER BY created_at DESC LIMIT 100
        """)
        rows_html = ""
        for r in rows:
            rows_html += "<tr>"
            rows_html += "<td class='hash'>%s</td>" % _esc(str(r[0])[:8])
            rows_html += "<td>%s</td>" % _esc(str(r[1] or "(no title)")[:80])
            rows_html += "<td>%s</td>" % _esc(str(r[2]))
            rows_html += "<td><span class='badge badge-document'>%s</span></td>" % _esc(str(r[3] or r[2]))
            rows_html += "<td class='hash'>%s</td>" % _esc(str(r[5])[:16] if r[5] else "")
            rows_html += "<td>%s</td>" % _esc(str(r[9])[:19] if r[9] else "")
            rows_html += "</tr>"
        total = len(rows)
    except Exception:
        rows_html = "<tr><td colspan='6' class='empty'>No documents</td></tr>"
        total = 0

    body = """
    <div class="card">
      <div class="card-header">Documents <span>%d total</span></div>
      <div class="card-body"><table>
        <tr><th>ID</th><th>Title</th><th>Source</th><th>Type</th><th>Checksum</th><th>Created</th></tr>
        %s
      </table></div>
    </div>
    """ % (total, rows_html)
    return nav.replace("{body}", body)


def page_communications():
    nav = render_nav("communications")
    try:
        cols, rows = query("""
            SELECT id, subject, sender_name, sender_email, source,
                   received_at, checksum, processing_status
            FROM communications ORDER BY received_at DESC LIMIT 100
        """)
        rows_html = ""
        for r in rows:
            rows_html += "<tr>"
            rows_html += "<td class='hash'>%s</td>" % _esc(str(r[0])[:8])
            rows_html += "<td>%s</td>" % _esc(str(r[1] or "(no subject)")[:80])
            rows_html += "<td>%s<br><small>%s</small></td>" % (_esc(str(r[2] or "")), _esc(str(r[3] or "")))
            rows_html += "<td>%s</td>" % _esc(str(r[4]))
            rows_html += "<td>%s</td>" % _esc(str(r[5])[:19] if r[5] else "")
            rows_html += "<td class='hash'>%s</td>" % _esc(str(r[6])[:16] if r[6] else "")
            rows_html += "</tr>"
        total = len(rows)
    except Exception:
        rows_html = "<tr><td colspan='6' class='empty'>No communications</td></tr>"
        total = 0

    body = """
    <div class="card">
      <div class="card-header">Communications <span>%d total</span></div>
      <div class="card-body"><table>
        <tr><th>ID</th><th>Subject</th><th>Sender</th><th>Source</th><th>Received</th><th>Checksum</th></tr>
        %s
      </table></div>
    </div>
    """ % (total, rows_html)
    return nav.replace("{body}", body)


def page_events():
    nav = render_nav("events")
    try:
        cols, rows = query("""
            SELECT id, title, start_time, end_time, location, status, source
            FROM events ORDER BY start_time DESC LIMIT 100
        """)
        rows_html = ""
        for r in rows:
            rows_html += "<tr>"
            rows_html += "<td class='hash'>%s</td>" % _esc(str(r[0])[:8])
            rows_html += "<td>%s</td>" % _esc(str(r[1] or ""))
            rows_html += "<td>%s</td>" % _esc(str(r[2])[:19] if r[2] else "")
            rows_html += "<td>%s</td>" % _esc(str(r[3])[:19] if r[3] else "")
            rows_html += "<td>%s</td>" % _esc(str(r[4] or ""))
            rows_html += "<td><span class='badge badge-calendar'>%s</span></td>" % _esc(str(r[5] or ""))
            rows_html += "<td>%s</td>" % _esc(str(r[6]))
            rows_html += "</tr>"
        total = len(rows)
    except Exception:
        rows_html = "<tr><td colspan='7' class='empty'>No events</td></tr>"
        total = 0

    body = """
    <div class="card">
      <div class="card-header">Events <span>%d total</span></div>
      <div class="card-body"><table>
        <tr><th>ID</th><th>Title</th><th>Start</th><th>End</th><th>Location</th><th>Status</th><th>Source</th></tr>
        %s
      </table></div>
    </div>
    """ % (total, rows_html)
    return nav.replace("{body}", body)


def page_contacts():
    nav = render_nav("contacts")
    try:
        cols, rows = query("""
            SELECT id, name, email, organization, role, source
            FROM contacts ORDER BY name LIMIT 100
        """)
        rows_html = ""
        for r in rows:
            rows_html += "<tr>"
            rows_html += "<td class='hash'>%s</td>" % _esc(str(r[0])[:8])
            rows_html += "<td>%s</td>" % _esc(str(r[1] or ""))
            rows_html += "<td>%s</td>" % _esc(str(r[2] or ""))
            rows_html += "<td>%s</td>" % _esc(str(r[3] or ""))
            rows_html += "<td>%s</td>" % _esc(str(r[4] or ""))
            rows_html += "<td>%s</td>" % _esc(str(r[5]))
            rows_html += "</tr>"
        total = len(rows)
    except Exception:
        rows_html = "<tr><td colspan='6' class='empty'>No contacts</td></tr>"
        total = 0

    body = """
    <div class="card">
      <div class="card-header">Contacts <span>%d total</span></div>
      <div class="card-body"><table>
        <tr><th>ID</th><th>Name</th><th>Email</th><th>Organization</th><th>Role</th><th>Source</th></tr>
        %s
      </table></div>
    </div>
    """ % (total, rows_html)
    return nav.replace("{body}", body)


def page_runs():
    nav = render_nav("runs")
    try:
        cols, rows = query("""
            SELECT id, pipeline_name, status, started_at, completed_at,
                   source_count, processed_count, failed_count, skipped_count, errors
            FROM processing_logs ORDER BY started_at DESC LIMIT 50
        """)
        rows_html = ""
        for r in rows:
            rows_html += "<tr>"
            rows_html += "<td class='hash'>%s</td>" % _esc(str(r[0])[:8])
            rows_html += "<td>%s</td>" % _esc(str(r[1]))
            rows_html += "<td>%s</td>" % _esc(str(r[2]))
            rows_html += "<td>%s</td>" % _esc(str(r[3])[:19] if r[3] else "")
            rows_html += "<td class='align-right'>%d</td>" % (r[5] or 0)
            rows_html += "<td class='align-right'>%d</td>" % (r[6] or 0)
            rows_html += "<td class='align-right'>%d</td>" % (r[7] or 0)
            rows_html += "<td class='align-right'>%d</td>" % (r[8] or 0)
            rows_html += "<td>%s</td>" % _esc(str(r[9] or "")[:60])
            rows_html += "</tr>"
        total = len(rows)
    except Exception:
        rows_html = "<tr><td colspan='10' class='empty'>No pipeline runs</td></tr>"
        total = 0

    body = """
    <div class="card">
      <div class="card-header">Pipeline Runs <span>%d total</span></div>
      <div class="card-body"><table>
        <tr><th>ID</th><th>Pipeline</th><th>Status</th><th>Started</th><th>Total</th><th>OK</th><th>Fail</th><th>Skip</th><th>Errors</th></tr>
        %s
      </table></div>
    </div>
    """ % (total, rows_html)
    return nav.replace("{body}", body)


def _esc(text):
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            path = self.path.rstrip("/") or "/"
            if path == "/" or path == "/dashboard":
                body = page_dashboard()
            elif path == "/documents":
                body = page_documents()
            elif path == "/communications":
                body = page_communications()
            elif path == "/events":
                body = page_events()
            elif path == "/contacts":
                body = page_contacts()
            elif path == "/runs":
                body = page_runs()
            else:
                body = render_nav("dashboard").replace("{body}",
                    "<div class='card'><div class='empty'>404</div></div>")

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        except Exception as e:
            import traceback
            self.send_response(500)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write((str(e) + "\n" + traceback.format_exc()).encode("utf-8"))

    def log_message(self, fmt, *args):
        print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), args[0]))


if __name__ == "__main__":
    print("=" * 50)
    print("  Silver Layer Web Viewer")
    print("  http://localhost:%d" % PORT)
    print("=" * 50)

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()
