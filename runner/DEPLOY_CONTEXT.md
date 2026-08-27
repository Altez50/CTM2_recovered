# CTM Deploy-to-Prod — Context & Handoff

> Session: 2026-08-01. Captures the broken deploy-to-prod investigation,
> fixes applied, environment, and what remains. Read this first in a new session.

## Original problem
`runner.py` "Deploy to prod" leaves the **old version** running on production.

## Root cause #1 — the real blocker (verified 2026-08-01, second session)
The deploy **never reached Docker**. It died at the first `scp` with:
`command-line: line 0: Bad configuration option: controlsocket`.

- **Windows OpenSSH (Win32-OpenSSH 9.5p1 on this box) does NOT implement
  connection multiplexing.** The three options every script passed via
  `$sshBase` — `ControlMaster`, `ControlPersist`, `ControlSocket` — are
  rejected. Confirmed: `ssh -G -o ControlSocket=none localhost` → exit 255.
  So `$sshBase` poisoned **every** `ssh`/`scp` call; the deploy had *never*
  succeeded from this workstation (this is why prod stayed on the old image).
- The key `~\.ssh\id_rsa` is **passphrase-protected**; without multiplexing,
  each of the ~10 `ssh`/`scp` calls would re-prompt.
- `ssh-agent` was **Stopped + Disabled**.

### Fix applied
1. Removed `ControlMaster`/`ControlPersist`/`ControlSocket` from `$sshBase` in
   all three scripts (deploy-prod.ps1, push-db-prod.ps1, prod-service.ps1), and
   dropped the now-meaningless `ssh -O exit` cleanup in the `finally` blocks.
2. Enabled `ssh-agent` (service now **Running / Automatic**, one-time, elevated).
3. Each script now self-loads the key into the agent once
   (`ssh-add` prompts in the deploy **console window** the first time it's
   empty), then all later `ssh`/`scp` calls in that session use the cached key.
   **First deploy after a reboot = one passphrase prompt in the console.**
   After reboot the agent restarts empty → the script re-prompts once.
- Verified: `ssh -G -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15
  root@abitek.su` → exit 0 (no "Bad configuration option").

## Root cause #2 — docker compose v1 (still real, separate from #1)
Prod has `docker-compose 1.17` only (NO `docker compose` v2 plugin). The
hardened `Confirm-Deploy`/`Get-ContainerFile` previously called the v2 form
with no fallback, so verification would always fail. Fixed: every
`docker compose …` now falls back to `docker-compose …`, and `Confirm-Deploy`
uses plain `ps` (no `--format`, unsupported in 1.17).
Both prod containers also serve a stale build — i.e. `docker compose up -d --build`
failed or was skipped during the last deploy:

| Element | Prod returns | Current code returns | Verdict |
|---|---|---|---|
| Backend `GET /api/health` | `{"status":"ok"}` only | `{"status":"ok","build":...,"schema":"2026-07-tmc-settlements-v1"}` | OLD image |
| Frontend `/ctm/build-version.txt` | SPA `index.html` (fallback) | stamped version string | OLD image |

- Backend proof: [system.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/system.py#L56-L62)
  returns `build` + `schema`; prod omits both → old `api/` code in the container.
- Frontend proof: `build-version.txt` is absent from served dist → nginx
  `try_files` falls back to `/ctm/index.html` ([nginx.conf:66-72](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/nginx.conf#L66-L72)).
- **Additionally**, the TLS cert was expired (notAfter Jul 11 2026) → HTTPS
  clients got `SEC_E_CERT_EXPIRED`. This is now FIXED (see below).

## Fixes already applied in this session

### 1. `deploy-prod.ps1` hardened ([deploy-prod.ps1](file:///f:/2026f/ctm3/CTM2_recovered/runner/deploy-prod.ps1))
- Added `Get-ContainerFile` + `Confirm-Deploy`: reads the build stamp baked
  into each **running** container (`api` → `/app/api/BUILD_VERSION`,
  `frontend` → `/usr/share/nginx/html/ctm/build-version.txt`), asserts both
  equal the just-stamped version, and that `docker compose ps` shows both `Up`.
- On mismatch: auto-forces `docker compose build --no-cache api frontend &&
  up -d --force-recreate`, then re-verifies; **throws loudly** if still wrong.
- Added TLS cert-expiry check (probes public HTTPS endpoint, warns red if expired).
- Replaced the swallow-on-failure `curl` health check.

### 2. `runner.py` tabbed log view ([runner.py](file:///f:/2026f/ctm3/CTM2_recovered/runner/runner.py))
- Single log → `ttk.Notebook` with tabs: All / Server / Frontend / Rebuild /
  Deploy / Push DB / Prod. Lines routed by `[tag]`. Auto-selects tab on start.
- **Gotcha (recurring):** the IDE auto-formatter strips "unused" imports
  (`re`, `shutil`, `ttk`) before the using-code lands, causing
  `NameError: name 're' is not defined` / `AttributeError: ...no attribute 'Notebook'`.
  All three imports + `_TAG_RE = re.compile(...)` + `ttk.Notebook` are required.
  If it breaks again, verify lines 44-56 and 91-92.

### 3. TLS certificate renewed (DONE, verified end-to-end)
- New cert: `notAfter=Oct 29 21:12:46 2026 GMT`, served correctly on
  `https://abitek.su:18443` (verified with strict validation from workstation).
- Method: acme.sh + reg.ru DNS-01 (see "Cert renewal" section below).

## What remains (NOT yet done)
1. **The prod app images are STILL the old build.** The cert is fixed, but the
   CTM app version on prod has NOT been redeployed with the hardened script yet.
   → **Next step: re-run "Deploy to Prod" from the runner** and confirm the new
   `Confirm-Deploy` verification passes (both stamps = `$buildVer`, both Up).
   Then `curl https://abitek.su:18443/api/health` should include `build`+`schema`.
2. If the hardened deploy still fails, inspect `docker-compose logs api frontend`
   on prod for the build error.

## Environment

### Prod box (abis)
- LAN: `192.168.0.39`, user `kassir`, password `7535789`, Ubuntu 18.04.
- External: `abitek.su` → `62.183.112.16`.
- SSH guide: `D:\sqldata\ObsidianFedorov\Доступы\SSH_CONNECTION_GUIDE.md`.
- **Python with paramiko on this workstation: `D:\ptn313\python.exe`**
  (the portable `f:\2026f\ctm3\.python` does NOT have paramiko).
  Write scripts to a file and run them — inline `-c` breaks on D:\ptn313.

### Port routing (critical)
- External `:80`  → **Windows Apache** (`Apache/2.4.48 Win64 PHP/8.4.3`) — NOT this box.
- External `:443` → dead / garbage.
- External `:18443` → docker caddy (reverse-proxy) on this box → CTM app.
- Host-level Caddy on `*:80` (pid 1013) is a separate gateway (frps vhosts), unrelated to CTM.

### CTM app on prod
- `/srv/ctm/current` (symlink to a release), `/srv/ctm/deploy` (compose),
  `/srv/ctm/data/construction-ctm2.db`, `/srv/ctm/certs`.
- **Docker compose v1** (`docker-compose 1.17.1`), NOT `docker compose` v2.
  deploy-prod.ps1 handles this via `docker compose ... || docker-compose ...`.
- Services: `api` (python:3.11-slim), `frontend` (nginx), `reverse-proxy` (caddy:2.8-alpine).
- Caddy reads `TLS_CERT_FILE=/certs/abitek.su-chain.pem`,
  `TLS_KEY_FILE=/certs/abitek.su-key.pem` (from `.deploy.kassir.env`).

### Cert renewal (fully automated now)
- Tool: **acme.sh v3.1.5** at `/home/kassir/.acme.sh`, CA = Let's Encrypt.
- Method: **DNS-01 via reg.ru** (`dns_regru` plugin), TXT at `_acme-challenge.abitek.su`.
- reg.ru account: `v781345@ya.ru` / `qw12+QW12`. DNS hosted at ns1/ns2.reg.ru.
- **IP `62.183.112.16` is allowlisted** in reg.ru API settings (was the first blocker).
- **Password gotcha:** acme.sh `dns_regru` does NOT URL-encode credentials, so the
  `+` in the password becomes a space. Must pass it pre-encoded as `qw12%2BQW12`.
- Cert paths: `/srv/ctm/certs/abitek.su-chain.pem` + `abitek.su-key.pem`
  (now owned by `kassir` so acme.sh can write on renewal).
- Auto-renew cron: `14 1,7,13,19 * * * acme.sh --cron`.
- install-cert hook reloadcmd: `cd /srv/ctm/deploy && docker-compose restart reverse-proxy`.
- Old certs backed up at `/srv/ctm/certs.bak-20260801-020317`.

## Key files
- [deploy-prod.ps1](file:///f:/2026f/ctm3/CTM2_recovered/runner/deploy-prod.ps1) — deploy pipeline (hardened).
- [runner.py](file:///f:/2026f/ctm3/CTM2_recovered/runner/runner.py) — desktop control panel (tabbed logs).
- [system.py](file:///f:/2026f/ctm3/CTM2_recovered/current/api/routers/system.py) — `/api/health` + `_build_version()`.
- [Dockerfile](file:///f:/2026f/ctm3/CTM2_recovered/current/Dockerfile) — api image.
- [web-client/Dockerfile](file:///f:/2026f/ctm3/CTM2_recovered/current/web-client/Dockerfile) — frontend image.
- [docker-compose.yml](file:///f:/2026f/ctm3/CTM2_recovered/deploy/docker-compose.yml) — prod compose.
- [Caddyfile.kassir](file:///f:/2026f/ctm3/CTM2_recovered/current/reverse-proxy/Caddyfile.kassir) — prod reverse proxy.

## Deploy verification one-liners (from workstation)
```powershell
# Backend should include build + schema after a good deploy:
f:\2026f\ctm3\.python\python.exe -c "import ssl,urllib.request; ctx=ssl.create_default_context(); print(urllib.request.urlopen(urllib.request.Request('https://abitek.su:18443/api/health'),timeout=12,context=ctx).read().decode())"
# Frontend should return the version string, not HTML:
f:\2026f\ctm3\.python\python.exe -c "import ssl,urllib.request; ctx=ssl.create_default_context(); print(urllib.request.urlopen(urllib.request.Request('https://abitek.su:18443/ctm/build-version.txt'),timeout=12,context=ctx).read().decode()[:60])"
```
