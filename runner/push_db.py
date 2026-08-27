#!/usr/bin/env python3
"""Push the local SQLite DB to prod via paramiko (password auth to LAN IP).

Pipeline:
  1. Stop api container (frees the SQLite file handle).
  2. Backup remote DB -> <remote_db>.bak-<timestamp>.
  3. SFTP upload local DB (+ -wal/-shm if present) to /tmp, then mv into place.
  4. Start api container.
  5. Health check.

Usage:
    python push_db.py --repo-root <path>
"""
from __future__ import annotations

import os
import sys
import time

# --- connection (LAN — verified working 2026-08-01) ------------------------
# PASS is only a fallback for callers without a console (e.g. the GUI runner,
# runner.py, spawns this with no console to type into). The standalone wrapper
# (push-db-prod.ps1) prompts for the kassir password and passes it via
# CTM_KASSIR_PASS, which takes priority.
HOST = "192.168.0.39"
USER = "kassir"
PASS = "7535789"
PORT = 22

REMOTE_DB = "/srv/ctm/data/construction-ctm2.db"
COMPOSE_DIR = "/srv/ctm/deploy"
LOCAL_DB_RELPATH = os.path.join("current", "construction.db")


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

    repo_root = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    if "--repo-root" in sys.argv:
        idx = sys.argv.index("--repo-root")
        if idx + 1 < len(sys.argv):
            repo_root = sys.argv[idx + 1]

    local_db = os.path.join(repo_root, LOCAL_DB_RELPATH)

    log("=== Push DB to prod ===")
    if not os.path.exists(local_db):
        log(f"[!] Local DB not found: {local_db}")
        sys.exit(1)

    size_kb = os.path.getsize(local_db) / 1024
    log(f"Local : {local_db}  ({size_kb:.0f} KB)")
    log(f"Prod  : {USER}@{HOST}:{REMOTE_DB}")
    log("")

    # 1. Connect
    passw = os.environ.get("CTM_KASSIR_PASS") or PASS
    log(f">>> Connecting to {USER}@{HOST}:{PORT} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=passw, timeout=15)
    log("[OK] Connected")

    # 2. Stop api container (frees the SQLite file handle)
    log("")
    log(">>> Stopping api container ...")
    rc = run_remote_stream(ssh, f"cd '{COMPOSE_DIR}' && sudo docker-compose stop api")
    if rc != 0:
        log(f"[!] docker-compose stop api returned {rc} — continuing anyway")

    # 3. Backup remote DB
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{REMOTE_DB}.bak-{ts}"
    log("")
    log(f">>> Backing up remote DB -> {backup_path} ...")
    rc = run_remote_stream(ssh, f"sudo cp -p '{REMOTE_DB}' '{backup_path}' && sudo ls -lh '{backup_path}'")
    if rc != 0:
        log(f"[!] Backup returned {rc} — continuing anyway")

    # 4. Upload DB files via SFTP
    sftp = ssh.open_sftp()
    files_to_send = [local_db]
    for ext in ("-wal", "-shm"):
        sidecar = local_db + ext
        if os.path.exists(sidecar):
            files_to_send.append(sidecar)

    main_leaf = os.path.basename(local_db)
    for fpath in files_to_send:
        leaf = os.path.basename(fpath)
        sz = os.path.getsize(fpath) / 1024
        log(f">>> Uploading {leaf} ({sz:.0f} KB) -> /tmp/{leaf} ...")
        sftp.put(fpath, f"/tmp/{leaf}")
    log("[OK] DB files uploaded")
    sftp.close()

    # 5. Move into place
    log("")
    log(">>> Installing DB ...")
    move_cmd = (
        f"sudo mv -f '/tmp/{main_leaf}' '{REMOTE_DB}'"
    )
    for ext in ("-wal", "-shm"):
        leaf = main_leaf + ext
        move_cmd += f"; if [ -f '/tmp/{leaf}' ]; then sudo mv -f '/tmp/{leaf}' '{REMOTE_DB}{ext}'; fi"
    move_cmd += f"; sudo chown 0:0 '{REMOTE_DB}' 2>/dev/null || true; sudo chmod 0644 '{REMOTE_DB}'"
    rc = run_remote_stream(ssh, move_cmd)
    if rc != 0:
        log(f"[!] DB install returned {rc}")

    # 6. Start api container
    log("")
    log(">>> Starting api container ...")
    rc = run_remote_stream(ssh, f"cd '{COMPOSE_DIR}' && sudo docker-compose start api")
    if rc != 0:
        log(f"[!] docker-compose start api returned {rc}")

    # 7. Health check (through caddy reverse-proxy, not localhost:8000)
    log("")
    log(">>> Health check ...")
    time.sleep(3)
    rc = run_remote_stream(
        ssh,
        "curl -fsS -o /dev/null -w 'GET /api/health -> HTTP %{http_code}\\n' "
        "http://localhost:18443/api/health || echo 'health check failed'",
    )

    log("")
    log("=" * 50)
    log("[OK] Push DB complete")
    log("=" * 50)

    ssh.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
