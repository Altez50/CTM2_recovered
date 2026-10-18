#!/usr/bin/env python3
"""Shared SSH auth to the CTM prod box (kassir@192.168.0.39).

Auth order (first that works wins):
  1. $CTM_DEPLOY_KEY          — explicit key-file override
  2. ~/.ssh/ctm_prod_ed25519  — dedicated no-passphrase deploy key
                                (installed on prod 2026-09-02; kassir has
                                passwordless sudo, so deploys need no secrets)
  3. CTM_KASSIR_PASS           — legacy password path (wrapper prompts)

Credentials must never be stored in the repository.
"""
from __future__ import annotations

import os

HOST = "192.168.0.39"
USER = "kassir"
PORT = 22

DEFAULT_KEY = os.path.join(os.path.expanduser("~"), ".ssh", "ctm_prod_ed25519")


def connect(ssh) -> str:
    """Connect a prepared paramiko.SSHClient; returns the auth method used.

    Raises SystemExit with setup instructions when nothing works.
    """
    import paramiko

    keys = []
    override = os.environ.get("CTM_DEPLOY_KEY", "").strip()
    if override:
        keys.append(override)
    if os.path.exists(DEFAULT_KEY):
        keys.append(DEFAULT_KEY)

    for key in keys:
        if not os.path.exists(key):
            continue
        try:
            ssh.connect(HOST, port=PORT, username=USER, key_filename=key,
                        timeout=15, allow_agent=False, look_for_keys=False)
            return f"key {os.path.basename(key)}"
        except paramiko.SSHException as e:
            if not isinstance(e, paramiko.AuthenticationException):
                raise  # network/host problems are not "try the next key"
        except FileNotFoundError:
            continue

    passw = os.environ.get("CTM_KASSIR_PASS", "").strip()
    if passw:
        ssh.connect(HOST, port=PORT, username=USER, password=passw, timeout=15,
                    allow_agent=False, look_for_keys=False)
        return "password"

    raise SystemExit(
        f"Cannot authenticate to {USER}@{HOST}: no usable deploy key and "
        "CTM_KASSIR_PASS is not set.\n"
        f"Install the dedicated key (no passphrase, one-time):\n"
        f"  ssh-keygen -t ed25519 -N \"\" -f {DEFAULT_KEY}\n"
        f"  type {DEFAULT_KEY}.pub | ssh {USER}@{HOST} \"mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys\"\n"
        "or set CTM_KASSIR_PASS for the legacy password path."
    )
