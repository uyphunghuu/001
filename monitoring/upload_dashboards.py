"""
Usage: python monitoring/upload_dashboards.py

Upload 9 Grafana dashboards to Grafana Cloud via API.

Prerequisites:
  1. .env.grafana-cloud file with GC_INSTANCE_ID and GC_API_KEY
  2. Grafana Cloud API Key with role "Admin" (not MetricsPublisher)
     Create at: https://grafana.com/org/access-policies
"""
import json
import os
import re
from pathlib import Path

import urllib.request


def load_env(path: str) -> dict:
    env = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def main():
    env = load_env(Path(__file__).parent / ".env.grafana-cloud")

    instance_id = env.get("GC_INSTANCE_ID") or os.getenv("GC_INSTANCE_ID")
    api_key = env.get("GC_API_KEY") or os.getenv("GC_API_KEY")

    if not instance_id or not api_key:
        print("ERROR: Thieu GC_INSTANCE_ID va GC_API_KEY")
        print("  Tao file .env.grafana-cloud hoac set environment variables")
        return

    dashboards_dir = Path(__file__).parent / "grafana" / "dashboards"
    if not dashboards_dir.exists():
        print(f"ERROR: Khong tim thay {dashboards_dir}")
        return

    base_url = f"https://{instance_id}.grafana.net"
    auth_header = f"Bearer {api_key}"

    for dash_file in sorted(dashboards_dir.glob("*.json")):
        # Skip the old overview dashboard
        if dash_file.name == "ai_platform_overview.json":
            continue

        print(f"Uploading {dash_file.name}... ", end="")

        try:
            raw = json.loads(dash_file.read_text(encoding="utf-8"))
            payload = {
                "dashboard": raw,
                "overwrite": True,
                "message": f"Deploy {dash_file.stem}",
                "folderUid": "",
            }

            req = urllib.request.Request(
                url=f"{base_url}/api/dashboards/db",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("status") == "success":
                print(f"OK -> {result.get('url', 'N/A')}")
            else:
                print(f"FAIL: {result}")

        except Exception as e:
            print(f"ERROR: {e}")

    print("\nDone! Mo https://{instance_id}.grafana.net xem dashboards.")


if __name__ == "__main__":
    main()
