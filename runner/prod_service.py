#!/usr/bin/env python3
"""Control the CTM Docker Compose stack on prod via the LAN.

Actions: status | logs | start | stop | restart | up.
Targets: api | frontend | reverse-proxy | stack.
Connects as kassir (root SSH is disabled) and runs Docker Compose commands
inside the CTM deployment directory.  `status` also shows relevant host ports;
`up stack` reconciles the complete CTM stack without rebuilding images.

Usage:
    python prod_service.py --action restart [--repo-root <path>]
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import prod_ssh

COMPOSE_DIR = "/srv/ctm/deploy"
# CTM is published on the host's LAN address.  Port 18443 belongs to the
# upstream WAN forwarding device, not this Linux host, so localhost:18443 is
# intentionally not used for an on-host health check.
HEALTH_URL = "https://192.168.0.39:8443/api/health"
SERVICES = ("api", "frontend", "reverse-proxy")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action", default="status",
        choices=("status", "logs", "start", "stop", "restart", "up"),
    )
    parser.add_argument(
        "--target", default="stack", choices=(*SERVICES, "stack"),
        help="Compose service to operate on, or the complete CTM stack.",
    )
    return parser.parse_args()


def main():
    import paramiko

    args = parse_args()
    action, target = args.action, args.target
    services = "" if target == "stack" else f" {target}"

    log("=== Prod service control ===")
    log(f"Target : {prod_ssh.USER}@{prod_ssh.HOST}:{prod_ssh.PORT} (LAN — root is disabled)")
    log(f"Compose: {COMPOSE_DIR}")
    log(f"Target : {target}")
    log(f"Action : {action}")
    log("")

    log(f">>> Connecting to {prod_ssh.USER}@{prod_ssh.HOST}:{prod_ssh.PORT} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    auth = prod_ssh.connect(ssh)
    log(f"[OK] Connected ({auth})")

    log("")
    if action == "status":
        cmd = (
            f"cd '{COMPOSE_DIR}' && sudo docker-compose ps; "
            "echo; echo '--- Host listeners ---'; "
            "sudo ss -ltnp | grep -E ':(8080|8443|18443)\\b' || true"
        )
        log(">>> docker-compose ps + host listeners")
    elif action == "logs":
        cmd = f"cd '{COMPOSE_DIR}' && sudo docker-compose logs --tail=200{services}"
        log(f">>> docker-compose logs --tail=200{services}")
    elif action == "up":
        cmd = f"cd '{COMPOSE_DIR}' && sudo docker-compose up -d{services}"
        log(f">>> docker-compose up -d{services}")
    else:
        cmd = f"cd '{COMPOSE_DIR}' && sudo docker-compose {action}{services}"
        log(f">>> docker-compose {action}{services}")
    rc = run_remote_stream(ssh, cmd)
    if rc != 0:
        log(f"[!] docker-compose {action} {target} returned {rc}")

    if action in ("start", "restart", "up") and target in ("api", "stack"):
        log("")
        log(">>> Health check ...")
        time.sleep(3)
        run_remote_stream(
            ssh,
            f"curl -kfsS -H 'Host: abitek.su' -o /dev/null "
            "-w 'GET /api/health -> HTTP %{http_code}\\n' "
            f"{HEALTH_URL} || echo 'health check failed'",
        )

    log("")
    log(f"=== Done ({action}) ===")
    ssh.close()
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
