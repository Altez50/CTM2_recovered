#!/usr/bin/env python3
"""Control the api container on prod via paramiko (password auth to LAN IP).

Actions: start | stop | restart | status.
Connects as kassir (root SSH is disabled), runs `sudo docker-compose <action>
api`. For start/restart also runs a health check on GET /api/health.

Usage:
    python prod_service.py --action restart [--repo-root <path>]
"""
from __future__ import annotations

import os
import sys
import time

# --- connection (LAN — verified working 2026-08-01) ------------------------
# PASS is only a fallback for callers without a console (none today). The
# PowerShell wrapper (prod-service.ps1) prompts for the kassir password and
# passes it via CTM_KASSIR_PASS, which takes priority.
HOST = "192.168.0.39"
USER = "kassir"
PASS = "7535789"
PORT = 22

COMPOSE_DIR = "/srv/ctm/deploy"
SERVICE = "api"
HEALTH_URL = "http://localhost:18443/api/health"


def log(msg: str) -> None:
    print(msg, flush=True)


def run_remote_stream(ssh, cmd: str) -> int:
    """Run a command on prod, streaming stdout+stderr live."""
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.get_pty()
    channel.exec_command(cmd + " 2>&1")
    while True:
        if channel.recv_ready():
            data = channel.recv(4096).decode(errors="replace")
            if data:
                print(data, end="", flush=True)
        if channel.exit_status_ready():
            break
        time.sleep(0.05)
    while channel.recv_ready():
        print(channel.recv(4096).decode(errors="replace"), end="", flush=True)
    return channel.recv_exit_status()


def main():
    import paramiko

    action = "status"
    if "--action" in sys.argv:
        idx = sys.argv.index("--action")
        if idx + 1 < len(sys.argv):
            action = sys.argv[idx + 1].lower()
    if action not in ("start", "stop", "restart", "status"):
        log(f"[!] Unknown action: {action}")
        sys.exit(2)

    log("=== Prod service control ===")
    log(f"Target : {USER}@{HOST}:{PORT} (LAN, password auth — root is disabled)")
    log(f"Compose: {COMPOSE_DIR}")
    log(f"Service: {SERVICE}")
    log(f"Action : {action}")
    log("")

    passw = os.environ.get("CTM_KASSIR_PASS") or PASS
    log(f">>> Connecting to {USER}@{HOST}:{PORT} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=passw, timeout=15)
    log("[OK] Connected")

    cmd = f"cd '{COMPOSE_DIR}' && sudo docker-compose {action} {SERVICE}"
    log("")
    log(f">>> docker-compose {action} {SERVICE}")
    rc = run_remote_stream(ssh, cmd)
    if rc != 0:
        log(f"[!] docker-compose {action} {SERVICE} returned {rc}")

    if action in ("start", "restart"):
        log("")
        log(">>> Health check ...")
        time.sleep(3)
        run_remote_stream(
            ssh,
            f"curl -fsS -o /dev/null -w 'GET /api/health -> HTTP %{{http_code}}\\n' "
            f"{HEALTH_URL} || echo 'health check failed'",
        )

    log("")
    log(f"=== Done ({action}) ===")
    ssh.close()
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
