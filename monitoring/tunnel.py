"""
Expose local monitoring stack to the internet.
Usage: python monitoring/tunnel.py
"""
import subprocess
import sys
import threading
import time


def run_tunnel(name, local_port, subdomain=None):
    print(f"  {name}: http://localhost:{local_port} -> ", end="")
    cmd = [
        sys.executable, "-m", "pyngrok", "ngrok",
        "http", str(local_port),
        "--log", "stdout",
    ]
    if subdomain:
        cmd.extend(["--subdomain", subdomain])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    # Read a few lines to get the URL
    for _ in range(20):
        line = proc.stdout.readline()
        if "url=" in line:
            url = line.split("url=")[-1].strip()
            print(f"{url}")
            return proc, url
        if "started" in line.lower():
            continue
    print("(could not get URL)")
    return proc, None


if __name__ == "__main__":
    print("=== Starting tunnels ===")
    print("(Ctrl+C to stop)")
    print()

    tunnels = [
        ("Grafana", 3000),
        ("Prometheus", 9090),
    ]

    procs = []
    for name, port in tunnels:
        proc, url = run_tunnel(name, port)
        procs.append(proc)

    print()
    print("=== URLs ===")
    print("  Grafana:     http://localhost:3000")
    if procs:
        print("  Ctrl+C to stop all tunnels")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping tunnels...")
        for p in procs:
            p.terminate()
