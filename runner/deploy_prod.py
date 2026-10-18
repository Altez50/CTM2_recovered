#!/usr/bin/env python3
"""CTM production deploy via paramiko (key auth to LAN IP, see prod_ssh.py).

No ControlMaster, no external .ps1 — just paramiko. Output goes to stdout
(one line per message); the runner's _pump routes tagged lines into the
Deploy tab.

Usage:
    python deploy_prod.py [--repo-root <path>]
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

import prod_ssh

REMOTE_CURRENT = "/srv/ctm/current"
REMOTE_DEPLOY  = "/srv/ctm/deploy"

# --- deploy script that runs ON prod ----------------------------------------
# Backs up, extracts, docker-compose up --build, verifies health + build stamps.
DEPLOY_SH = r"""#!/bin/bash
set -euo pipefail

REMOTE_CURRENT="/srv/ctm/current"
REMOTE_DEPLOY="/srv/ctm/deploy"
BUILD_VER="$(cat /tmp/ctm-build-version.txt)"
TS="$(date +%Y%m%d-%H%M%S)"

echo "=== CTM deploy (build $BUILD_VER) ==="

# 1. Backup
if [ -d "$REMOTE_CURRENT" ]; then
  echo ">>> Backing up current -> /srv/ctm/previous.$TS"
  cp -a "$REMOTE_CURRENT" "/srv/ctm/previous.$TS" 2>/dev/null || true
fi

# 2. Extract
echo ">>> Extracting current/ ..."
mkdir -p "$REMOTE_CURRENT"
tar -xzf /tmp/ctm-current.tar.gz -C "$REMOTE_CURRENT"
echo ">>> Extracting deploy/ ..."
mkdir -p "$REMOTE_DEPLOY"
tar -xzf /tmp/ctm-deploy.tar.gz -C "$REMOTE_DEPLOY"
echo "[OK] extracted"

# 3. Build + restart
echo ">>> docker-compose up -d --build ..."
cd "$REMOTE_DEPLOY"
set -a && . ./.deploy.kassir.env && set +a
# Fail fast if required secrets are missing (docker-compose 1.17 cannot
# enforce this via ${VAR:?...} interpolation).
for v in JWT_SECRET_KEY SYNC_TOKEN; do
  if [ -z "${!v}" ]; then
    echo "[!] $v is not set in .deploy.kassir.env"
    exit 1
  fi
done
(docker-compose up -d --build 2>&1) || \
  (echo "[!] docker-compose up failed, trying --no-cache rebuild ..." && \
   docker-compose build --no-cache api frontend && \
   docker-compose up -d --force-recreate)
echo "[OK] containers up"

# 4. Verify the API actually starts and is reachable through the proxy.
# A matching stamp in a restarting container does not mean a working deploy.
echo "=== Verifying ..."
HEALTH_URL="https://192.168.0.39:8443/api/health"
HEALTHY=false
for attempt in $(seq 1 30); do
  if HEALTH_JSON="$(curl -kfsS --connect-timeout 2 --max-time 3 -H 'Host: abitek.su' "$HEALTH_URL" 2>/dev/null)" && \
     python3 -c 'import json,sys; r=json.loads(sys.argv[1]).get("data", {}); sys.exit(0 if r.get("status") == "ok" and r.get("build") == sys.argv[2] else 1)' "$HEALTH_JSON" "$BUILD_VER"; then
    HEALTHY=true
    break
  fi
  sleep 2
done
if [ "$HEALTHY" != true ]; then
  echo "[!] API health check failed or returned the wrong build"
  docker-compose ps
  docker-compose logs --tail=60 api reverse-proxy
  exit 1
fi
echo "[OK] API healthy through reverse proxy (build $BUILD_VER)"

# 5. Verify build stamps inside both running containers.
API_BUILD="$(docker-compose exec -T api cat /app/api/BUILD_VERSION 2>/dev/null || echo MISSING)"
FRONT_BUILD="$(docker-compose exec -T frontend cat /usr/share/nginx/html/ctm/build-version.txt 2>/dev/null || echo MISSING)"
echo "expected : $BUILD_VER"
echo "api      : $API_BUILD"
echo "frontend : $FRONT_BUILD"
if [ "$API_BUILD" = "$BUILD_VER" ] && [ "$FRONT_BUILD" = "$BUILD_VER" ]; then
  echo "[OK] builds MATCH"
else
  echo "[!] MISMATCH — prod still serving old build"
  exit 1
fi

echo "=== Deploy complete ==="
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def stamp_build_version(repo_root: str) -> str:
    """Git-describe the repo and write the stamp into source files."""
    try:
        ver = subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=repo_root, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        ver = "build-" + time.strftime("%Y%m%d-%H%M%S")

    # Stamp into api/BUILD_VERSION + web-client/public/build-version.txt
    api_stamp = os.path.join(repo_root, "current", "api", "BUILD_VERSION")
    os.makedirs(os.path.dirname(api_stamp), exist_ok=True)
    with open(api_stamp, "w") as f:
        f.write(ver)

    pub_dir = os.path.join(repo_root, "current", "web-client", "public")
    os.makedirs(pub_dir, exist_ok=True)
    with open(os.path.join(pub_dir, "build-version.txt"), "w") as f:
        f.write(ver)

    return ver


def pack_tarballs(repo_root: str) -> tuple[str, str]:
    """Pack current/ and deploy/ into temp tar.gz files."""
    tmp = tempfile.gettempdir()
    current_tgz = os.path.join(tmp, "ctm-current.tar.gz")
    deploy_tgz  = os.path.join(tmp, "ctm-deploy.tar.gz")

    for path in (current_tgz, deploy_tgz):
        try:
            os.remove(path)
        except OSError:
            pass

    current_src = os.path.join(repo_root, "current")
    deploy_src  = os.path.join(repo_root, "deploy")

    log(f">>> Packing current/ ...")
    subprocess.check_call([
        "tar", "-czf", current_tgz,
        "-C", current_src,
        "--exclude=*/node_modules", "--exclude=*/node_modules/*",
        "--exclude=*/dist", "--exclude=*/dist/*",
        "--exclude=*/__pycache__", "--exclude=*/__pycache__/*",
        "--exclude=*.pyc", "--exclude=*.db",
        "--exclude=*.db-journal", "--exclude=*.db-wal", "--exclude=*.db-shm",
        ".",
    ])
    sz = os.path.getsize(current_tgz) / (1024 * 1024)
    log(f"[OK] current/ packed ({sz:.1f} MB)")

    log(f">>> Packing deploy/ ...")
    subprocess.check_call(["tar", "-czf", deploy_tgz, "-C", deploy_src, "."])
    log("[OK] deploy/ packed")

    return current_tgz, deploy_tgz


def main():
    import paramiko

    repo_root = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    if len(sys.argv) > 2 and sys.argv[1] == "--repo-root":
        repo_root = sys.argv[2]

    log("=== CTM production deploy ===")
    log(f"Target: {prod_ssh.USER}@{prod_ssh.HOST}:{prod_ssh.PORT}  (LAN)")
    log("")

    # 1. Stamp + pack
    build_ver = stamp_build_version(repo_root)
    log(f"Build version: {build_ver}")
    current_tgz, deploy_tgz = pack_tarballs(repo_root)

    # 2. Connect (dedicated key first, password fallback — see prod_ssh.py)
    log(f">>> Connecting to {prod_ssh.USER}@{prod_ssh.HOST}:{prod_ssh.PORT} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    auth = prod_ssh.connect(ssh)
    log(f"[OK] Connected ({auth})")

    # 3. Upload
    sftp = ssh.open_sftp()
    for local, remote in [(current_tgz, "/tmp/ctm-current.tar.gz"),
                          (deploy_tgz,  "/tmp/ctm-deploy.tar.gz")]:
        sz = os.path.getsize(local) / (1024 * 1024)
        log(f">>> Uploading {os.path.basename(local)} ({sz:.1f} MB) ...")
        sftp.put(local, remote)
    with sftp.open("/tmp/ctm-build-version.txt", "w") as f:
        f.write(build_ver)
    with sftp.open("/tmp/deploy-local.sh", "w") as f:
        f.write(DEPLOY_SH)
    sftp.chmod("/tmp/deploy-local.sh", 0o755)
    sftp.close()
    log("[OK] All files uploaded")

    # 4. Run deploy on prod with live streaming (docker build takes minutes)
    log("")
    log(">>> Running deploy on prod (sudo bash /tmp/deploy-local.sh) ...")
    log("")
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.get_pty()
    channel.exec_command("sudo bash /tmp/deploy-local.sh 2>&1")

    while True:
        if channel.recv_ready():
            data = channel.recv(4096).decode(errors="replace")
            if data:
                print(data, end="", flush=True)
        if channel.exit_status_ready():
            break
        time.sleep(0.1)

    # Drain remaining
    while channel.recv_ready():
        print(channel.recv(4096).decode(errors="replace"), end="", flush=True)

    rc = channel.recv_exit_status()
    log("")
    log(f"{'='*50}")
    if rc == 0:
        log(f"[OK] Deploy successful (build {build_ver})")
    else:
        log(f"[!] Deploy FAILED (exit code {rc})")
    log(f"{'='*50}")

    ssh.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
