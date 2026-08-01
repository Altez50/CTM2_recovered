#!/usr/bin/env python3
"""CTM Runner — desktop control panel for the CTM project.

A tkinter window plus a system-tray icon (rendered text "CTM") with
**independent** controls for server and frontend, so you can run both
simultaneously (the normal case for full-stack dev):

  * Start / Stop Server    — uvicorn (API backend)
  * Start / Stop Frontend  — Vite dev server
  * Rebuild                — `npm run build` (production bundle)
  * Deploy to prod         — paramiko upload of current/ + deploy/ to prod
                             (192.168.0.39), then docker-compose up -d --build
                             (deploy_prod.py)
  * Push DB to prod        — overwrite the prod SQLite DB with the local one
                             (remote backup + api restart; push-db-prod.ps1)

Run:      python runner.py
Install:  pip install -r requirements.txt   (pystray, Pillow)
"""

from __future__ import annotations

# --- Interpreter bootstrap ---------------------------------------------------
import os
import subprocess
import sys

_SCRIPT = os.path.realpath(__file__)
_RUNNER_DIR = os.path.dirname(_SCRIPT)
_PORTABLE_PY = os.path.normpath(
    os.path.join(_RUNNER_DIR, "..", "..", ".python", "python.exe")
)


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
        os.path.realpath(b)
    )


if not _same_path(sys.executable, _PORTABLE_PY) and os.path.exists(_PORTABLE_PY):
    sys.exit(subprocess.call([_PORTABLE_PY, _SCRIPT, *sys.argv[1:]]))
# --- End bootstrap -----------------------------------------------------------

import locale
import queue
import re
import shutil
import ssl
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
from pathlib import Path
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.stderr.write(
        "Missing dependencies.\n"
        "Install them with one of:\n"
        f"  {_PORTABLE_PY} -m pip install pystray Pillow\n"
        f"  {_PORTABLE_PY} -m pip install -r requirements.txt\n"
    )
    sys.exit(1)


# -----------------------------------------------------------------------------
# Paths & helpers
# -----------------------------------------------------------------------------
TITLE = "CTM Runner"
BASE_DIR = Path(_SCRIPT).resolve().parent.parent
CURRENT_DIR = BASE_DIR / "current"
WEBCLIENT_DIR = CURRENT_DIR / "web-client"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = "8000"
FRONTEND_URL = "http://localhost:5173/ctm/"
PROD_URL = "https://abitek.su:18443/ctm/"
# Prod endpoints derived from PROD_URL (origin + /ctm/ base).
_PROD_ORIGIN = PROD_URL.rstrip("/").rsplit("/ctm", 1)[0]
PROD_API_HEALTH = _PROD_ORIGIN + "/api/health"
PROD_FRONT_VERSION = PROD_URL + "build-version.txt"
LOCAL_API_HEALTH = f"http://{SERVER_HOST}:{SERVER_PORT}/api/health"
# Local SQLite DB (default DATABASE_PATH from config.py = current/construction.db)
LOCAL_DB_PATH = CURRENT_DIR / "construction.db"
REMOTE_DB_PATH = "/srv/ctm/data/construction-ctm2.db"

# Python interpreter that has paramiko (the portable .python does NOT).
# Used for deploy_prod.py (SSH password auth to prod LAN IP).
PROD_PARAMIKO_PY = r"D:\ptn313\python.exe"
MAX_LOG_LINES = 2000
_TAG_RE = re.compile(r"^\[([^\]]+)\]")
# Start-Transcript session header/footer lines to drop from deploy/push/prod tabs.
_TRANSCRIPT_NOISE_RE = re.compile(
    r"^\*+$|"
    r"transcript\s+(start|started|end|ended)|"
    r"^(start|end)\s+time\b|^machine\b|^user\b|^command\s+line\b|"
    r"windows\s+powershell\s+transcript|consolehost",
    re.IGNORECASE,
)

CLR_OFF = "#95a5a6"
CLR_ON = "#27ae60"


def _npm_cmd() -> str | None:
    return shutil.which("npm.cmd") or shutil.which("npm")


def _cmd_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", locale.getpreferredencoding(False), "cp866", "cp1251"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _kill_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Main application
# -----------------------------------------------------------------------------
class RunnerApp:
    def __init__(self) -> None:
        self.server_proc: subprocess.Popen | None = None
        self.frontend_proc: subprocess.Popen | None = None
        self.rebuild_proc: subprocess.Popen | None = None
        self.deploy_proc: subprocess.Popen | None = None
        self.pushdb_proc: subprocess.Popen | None = None
        self.prodsvc_proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._exiting = False
        self._prod_checking = False
        self._local_build = self._git_describe()

        self._build_ui()
        self._build_tray()
        self._poll_log()
        self._refresh_state()

    # ---- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.geometry("560x680")
        self.root.minsize(460, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.font_b = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.font_sm = tkfont.Font(family="Segoe UI", size=9)
        self.font_link = tkfont.Font(
            family="Segoe UI", size=9, underline=True,
        )

        top = tk.Frame(self.root, padx=14, pady=10)
        top.pack(side=tk.TOP, fill=tk.X)

        # --- Build & Prod status ---
        st_frame = tk.LabelFrame(top, text=" Build & Prod status ", padx=10, pady=6)
        st_frame.pack(fill=tk.X, pady=(0, 6))
        st_frame.config(font=self.font_b)

        local_row = tk.Frame(st_frame)
        local_row.pack(fill=tk.X)
        self.local_build_lbl = tk.Label(
            local_row, text=f"Local build: {self._local_build}", anchor="w", fg="#2c3e50",
        )
        self.local_build_lbl.config(font=self.font_sm)
        self.local_build_lbl.pack(side=tk.LEFT)
        self.prod_check_btn = tk.Button(
            local_row, text="Check prod", width=12, command=self.check_prod,
        )
        self.prod_check_btn.pack(side=tk.RIGHT)

        self.prod_back_lbl = tk.Label(
            st_frame, text="Prod backend: ?", anchor="w", fg="#7f8c8d",
        )
        self.prod_back_lbl.config(font=self.font_sm)
        self.prod_back_lbl.pack(fill=tk.X, pady=(2, 0))

        self.prod_front_lbl = tk.Label(
            st_frame, text="Prod frontend: ?", anchor="w", fg="#7f8c8d",
        )
        self.prod_front_lbl.config(font=self.font_sm)
        self.prod_front_lbl.pack(fill=tk.X)

        # --- Server panel ---
        srv_frame = tk.LabelFrame(top, text=" Server (API backend) ", padx=10, pady=8)
        srv_frame.pack(fill=tk.X, pady=(0, 6))
        srv_frame.config(font=self.font_b)

        srv_row = tk.Frame(srv_frame)
        srv_row.pack(fill=tk.X)
        self.srv_dot = tk.Label(srv_row, text="  ", bg=CLR_OFF, width=2, relief="flat")
        self.srv_dot.pack(side=tk.LEFT)
        self.srv_status = tk.Label(srv_row, text="Stopped", anchor="w", width=14)
        self.srv_status.config(font=self.font)
        self.srv_status.pack(side=tk.LEFT, padx=(6, 0))
        self.srv_url = self._make_link(
            srv_row, f"http://{SERVER_HOST}:{SERVER_PORT}",
            f"http://{SERVER_HOST}:{SERVER_PORT}",
        )
        self.srv_url.pack(side=tk.LEFT, padx=(8, 0))
        self.srv_btn = tk.Button(
            srv_row, text="Start Server", width=14, command=self.toggle_server,
        )
        self.srv_btn.pack(side=tk.RIGHT)

        # --- Frontend panel ---
        fe_frame = tk.LabelFrame(top, text=" Frontend (Vite dev) ", padx=10, pady=8)
        fe_frame.pack(fill=tk.X, pady=(0, 6))
        fe_frame.config(font=self.font_b)

        fe_row = tk.Frame(fe_frame)
        fe_row.pack(fill=tk.X)
        self.fe_dot = tk.Label(fe_row, text="  ", bg=CLR_OFF, width=2, relief="flat")
        self.fe_dot.pack(side=tk.LEFT)
        self.fe_status = tk.Label(fe_row, text="Stopped", anchor="w", width=14)
        self.fe_status.config(font=self.font)
        self.fe_status.pack(side=tk.LEFT, padx=(6, 0))
        fe_desc = tk.Label(fe_row, text="npm run dev", anchor="w", fg="#7f8c8d")
        fe_desc.config(font=self.font_sm)
        fe_desc.pack(side=tk.LEFT, padx=(8, 0))
        self.fe_btn = tk.Button(
            fe_row, text="Start Frontend", width=14, command=self.toggle_frontend,
        )
        self.fe_btn.pack(side=tk.RIGHT)

        fe_links = tk.Frame(fe_frame)
        fe_links.pack(fill=tk.X, pady=(4, 0))
        self.dev_link = self._make_link(
            fe_links, "Open dev frontend: " + FRONTEND_URL, FRONTEND_URL,
        )
        self.dev_link.pack(side=tk.LEFT, padx=(16, 12))
        self.prod_link = self._make_link(
            fe_links, "Open prod: " + PROD_URL, PROD_URL,
        )
        self.prod_link.pack(side=tk.LEFT)

        # --- Rebuild + Deploy ---
        aux_row = tk.Frame(top)
        aux_row.pack(fill=tk.X, pady=(6, 0))
        self.rebuild_btn = tk.Button(
            aux_row, text="Rebuild frontend", command=self.rebuild,
        )
        self.rebuild_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.deploy_btn = tk.Button(
            aux_row, text="Deploy to Prod", command=self.deploy,
        )
        self.deploy_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # --- Database transfer ---
        db_frame = tk.LabelFrame(top, text=" Database ", padx=10, pady=8)
        db_frame.pack(fill=tk.X, pady=(0, 6))
        db_frame.config(font=self.font_b)

        db_row = tk.Frame(db_frame)
        db_row.pack(fill=tk.X)
        db_desc = tk.Label(
            db_row,
            text=f"Local: {LOCAL_DB_PATH.name}  ->  Prod: {REMOTE_DB_PATH}",
            anchor="w", fg="#7f8c8d",
        )
        db_desc.config(font=self.font_sm)
        db_desc.pack(side=tk.LEFT)
        self.pushdb_btn = tk.Button(
            db_row, text="Push DB to Prod", width=18, command=self.push_db,
        )
        self.pushdb_btn.pack(side=tk.RIGHT)

        # --- Prod service (remote api container) ---
        prod_frame = tk.LabelFrame(top, text=" Prod service (remote) ", padx=10, pady=8)
        prod_frame.pack(fill=tk.X, pady=(0, 6))
        prod_frame.config(font=self.font_b)

        prod_row = tk.Frame(prod_frame)
        prod_row.pack(fill=tk.X)
        prod_desc = tk.Label(
            prod_row,
            text="docker compose start/stop/restart api @ " + PROD_URL.split("/")[2],
            anchor="w", fg="#7f8c8d",
        )
        prod_desc.config(font=self.font_sm)
        prod_desc.pack(side=tk.LEFT)
        self.prod_start_btn = tk.Button(
            prod_row, text="Start", width=8, command=self.start_prod_api,
        )
        self.prod_start_btn.pack(side=tk.RIGHT)
        self.prod_stop_btn = tk.Button(
            prod_row, text="Stop", width=8, command=self.stop_prod_api,
        )
        self.prod_stop_btn.pack(side=tk.RIGHT, padx=(0, 4))
        self.prod_restart_btn = tk.Button(
            prod_row, text="Restart", width=9, command=self.restart_prod_api,
        )
        self.prod_restart_btn.pack(side=tk.RIGHT, padx=(0, 4))

        # --- Log (tabbed: one tab per operation + a combined "All") ---
        log_lbl = tk.Label(self.root, text="Output", anchor="w")
        log_lbl.config(font=self.font)
        log_lbl.pack(fill=tk.X, padx=14)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 4))

        def _make_log_tab(parent, title: str) -> scrolledtext.ScrolledText:
            w = scrolledtext.ScrolledText(
                parent, height=12, state=tk.DISABLED, wrap=tk.NONE,
                bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc",
            )
            w.config(font=tkfont.Font(family="Consolas", size=9))
            parent.add(w, text=title)
            return w

        self.all_log = _make_log_tab(self.nb, "All")
        self.log_tabs: dict[str, scrolledtext.ScrolledText] = {}
        for _key, _title in (
            ("server", "Server"),
            ("frontend", "Frontend"),
            ("rebuild", "Rebuild"),
            ("deploy", "Deploy"),
            ("pushdb", "Push DB"),
            ("prod", "Prod"),
        ):
            self.log_tabs[_key] = _make_log_tab(self.nb, _title)

        clr = tk.Button(self.root, text="Clear log", command=self.clear_log)
        clr.pack(side=tk.RIGHT, padx=14, pady=(0, 8))

    # ---- process spawning ---------------------------------------------------
    def _make_link(self, parent, text: str, url: str) -> tk.Label:
        lbl = tk.Label(parent, text=text, fg="#2c6fbb", cursor="hand2")
        lbl.config(font=self.font_link)
        lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
        return lbl

    @staticmethod
    def _git_describe() -> str:
        """Local build identifier: `git describe` of current/, else a stamped file."""
        try:
            out = subprocess.run(
                ["git", "-C", str(CURRENT_DIR), "describe", "--tags", "--always", "--dirty"],
                capture_output=True, text=True, timeout=2,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        for p in (CURRENT_DIR / "api" / "BUILD_VERSION", CURRENT_DIR / "BUILD_VERSION"):
            try:
                if p.exists():
                    val = p.read_text(encoding="utf-8").strip()
                    if val:
                        return val
            except OSError:
                continue
        return "unknown"

    @staticmethod
    def _fetch_url(url: str, timeout: float = 6.0) -> tuple[int | None, str]:
        """Return (http_code, body). Tolerant of SSL verification issues."""
        def _open(ctx):
            req = urllib.request.Request(url, headers={"User-Agent": "ctm-runner"})
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)

        try:
            with _open(None) as resp:
                return resp.getcode(), resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            reason = e.reason
            # Retry without cert verification if the cert chain is untrusted.
            if isinstance(reason, ssl.SSLCertVerificationError):
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    with _open(ctx) as resp:
                        return resp.getcode(), resp.read().decode("utf-8", errors="replace")
                except Exception as e2:  # noqa: BLE001
                    return None, f"{type(e2).__name__}: {e2}"
            return None, f"{type(e).__name__}: {reason}"
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {e}"

    def check_prod(self) -> None:
        """Probe prod backend (/api/health) and frontend (/ctm/build-version.txt)."""
        if self._prod_checking:
            return
        self._prod_checking = True
        self.prod_check_btn.config(state=tk.DISABLED)
        self.prod_back_lbl.config(text="Prod backend: checking…", fg="#7f8c8d")
        self.prod_front_lbl.config(text="Prod frontend: checking…", fg="#7f8c8d")
        threading.Thread(target=self._check_prod_worker, daemon=True).start()

    def _check_prod_worker(self) -> None:
        import json as _json

        bcode, bbody = self._fetch_url(PROD_API_HEALTH)
        fcode, fbody = self._fetch_url(PROD_FRONT_VERSION)

        if bcode == 200:
            try:
                data = (_json.loads(bbody) or {}).get("data", {})
                build = str(data.get("build") or "?")
                schema = str(data.get("schema") or "?")
                back_txt = f"Prod backend: UP  build={build}  schema={schema}"
                back_fg = CLR_ON
            except (ValueError, TypeError):
                back_txt = "Prod backend: UP (unparsable body)"
                back_fg = CLR_ON
        else:
            back_txt = f"Prod backend: DOWN (HTTP {bcode})" if bcode else f"Prod backend: DOWN — {bbody}"
            back_fg = "#c0392b"

        if fcode == 200:
            front_txt = f"Prod frontend: UP  build={fbody.strip()[:40]}"
            front_fg = CLR_ON
        else:
            front_txt = f"Prod frontend: DOWN (HTTP {fcode})" if fcode else f"Prod frontend: DOWN — {fbody}"
            front_fg = "#c0392b"

        match = "builds MATCH" if (
            bcode == 200 and fcode == 200 and back_txt.split("build=")[-1].split()[0] == fbody.strip()
        ) else ""
        self.root.after(0, self._apply_prod_result, back_txt, back_fg, front_txt, front_fg, match)

    def _apply_prod_result(self, back_txt, back_fg, front_txt, front_fg, match) -> None:
        self._prod_checking = False
        self.prod_check_btn.config(state=tk.NORMAL)
        self.prod_back_lbl.config(text=back_txt, fg=back_fg)
        self.prod_front_lbl.config(text=front_txt, fg=front_fg)
        if match:
            self._log(f"[prod] {match}")
        self._log(f"[prod] {back_txt}  |  {front_txt}")
        # Schedule the next automatic recheck.
        self.root.after(90000, self._auto_check_prod)

    def _auto_check_prod(self) -> None:
        if not self._exiting:
            self.check_prod()

    def _spawn(self, cwd: Path, args: list[str],
               tag: str, on_exit=None) -> subprocess.Popen | None:
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=_cmd_env(),
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                               if os.name == "nt" else 0),
                start_new_session=(os.name != "nt"),
                bufsize=1,
            )
        except FileNotFoundError:
            self._log(f"[{tag}] Command not found: {args[0]}")
            if on_exit:
                self.root.after(0, on_exit, -1)
            return None

        threading.Thread(
            target=self._pump, args=(proc, tag, on_exit), daemon=True
        ).start()
        return proc

    def _pump(self, proc: subprocess.Popen, tag: str, on_exit) -> None:
        try:
            assert proc.stdout
            for raw in iter(proc.stdout.readline, b""):
                self.log_queue.put(("out", f"[{tag}] {_decode(raw).rstrip()}"))
        finally:
            rc = proc.wait()
            self.log_queue.put(("out", f"[{tag}] process exited (code {rc})"))
            if on_exit:
                self.root.after(0, on_exit, rc)

    # ---- console-script spawning (deploy / push-db / prod-service) ---------
    def _spawn_console_script(
        self,
        script: Path,
        tag: str,
        extra_args: list[str] | None = None,
        on_done=None,
    ) -> subprocess.Popen | None:
        """Run a .ps1 in its own console (so SSH can still prompt for the key
        passphrase interactively) while mirroring its output via Start-Transcript
        into a temp file this panel tails live into the <tag> tab. The script
        skips its trailing 'Press Enter' pause when -LogFile is passed, so the
        process exits on its own and the tailer finishes. Returns Popen or None.
        """
        if not script.exists():
            messagebox.showerror(TITLE, f"Not found:\n{script}")
            return None
        log_path = os.path.join(tempfile.gettempdir(), f"ctm-{tag}.log")
        try:
            os.remove(log_path)
        except OSError:
            pass
        ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        args = [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-LogFile", log_path]
        if extra_args:
            args += extra_args
        self._show_tab(tag)
        try:
            proc = subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except OSError as e:
            messagebox.showerror(TITLE, f"Failed to open console:\n{e}")
            return None
        threading.Thread(
            target=self._tail_log, args=(proc, log_path, tag, on_done), daemon=True
        ).start()
        return proc

    @staticmethod
    def _log_is_noise(line: str) -> bool:
        """Transcript session header/footer lines (filtered from tabs)."""
        s = line.strip()
        if not s:
            return True
        return bool(_TRANSCRIPT_NOISE_RE.search(s))

    @staticmethod
    def _read_log_lines(path: str) -> list[str]:
        """Read a Start-Transcript log (UTF-16LE on PS 5.1, UTF-8 on pwsh)."""
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            return []
        if not raw:
            return []
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = raw.decode("utf-16", errors="replace")
        elif raw[:3] == b"\xef\xbb\xbf":
            text = raw[3:].decode("utf-8", errors="replace")
        else:
            text = raw.decode("utf-8", errors="replace")
        return text.splitlines()

    def _tail_log(self, proc: subprocess.Popen, log_path: str,
                  tag: str, on_done) -> None:
        shown = 0
        # Wait (up to ~10s) for the transcript file to appear.
        for _ in range(50):
            if os.path.exists(log_path) or proc.poll() is not None:
                break
            time.sleep(0.2)
        while True:
            lines = self._read_log_lines(log_path)
            if len(lines) > shown:
                for ln in lines[shown:]:
                    if not self._log_is_noise(ln):
                        self.log_queue.put(("out", f"[{tag}] {ln}"))
                shown = len(lines)
            if proc.poll() is not None:
                # Drain any final lines flushed between the last poll and exit.
                lines = self._read_log_lines(log_path)
                if len(lines) > shown:
                    for ln in lines[shown:]:
                        if not self._log_is_noise(ln):
                            self.log_queue.put(("out", f"[{tag}] {ln}"))
                    shown = len(lines)
                break
            time.sleep(0.25)
        self.log_queue.put(("out", f"[{tag}] console finished (exit code {proc.returncode})"))
        if on_done:
            try:
                on_done(proc.returncode)
            except Exception:  # noqa: BLE001
                pass

    # ---- Server -------------------------------------------------------------
    def is_server_running(self) -> bool:
        return self.server_proc is not None and self.server_proc.poll() is None

    def toggle_server(self) -> None:
        if self.is_server_running():
            self._log("[server] Stopping ...")
            _kill_tree(self.server_proc)
        else:
            if not CURRENT_DIR.exists():
                messagebox.showerror(TITLE, f"Directory not found:\n{CURRENT_DIR}")
                return
            self._log("[server] Starting uvicorn ...")
            self.server_proc = self._spawn(
                CURRENT_DIR,
                [sys.executable, "-m", "uvicorn", "api.main:app",
                 "--reload", "--host", SERVER_HOST, "--port", SERVER_PORT],
                tag="server",
                on_exit=self._server_exited,
            )
            self._refresh_state()

    def _server_exited(self, rc: int) -> None:
        self.server_proc = None
        self._refresh_state()

    # ---- Frontend -----------------------------------------------------------
    def is_frontend_running(self) -> bool:
        return self.frontend_proc is not None and self.frontend_proc.poll() is None

    def toggle_frontend(self) -> None:
        if self.is_frontend_running():
            self._log("[frontend] Stopping ...")
            _kill_tree(self.frontend_proc)
        else:
            npm = _npm_cmd()
            if not npm:
                messagebox.showerror(TITLE, "npm was not found on PATH.")
                return
            if not WEBCLIENT_DIR.exists():
                messagebox.showerror(TITLE, f"Directory not found:\n{WEBCLIENT_DIR}")
                return
            self._log("[frontend] Starting Vite dev server ...")
            self.frontend_proc = self._spawn(
                WEBCLIENT_DIR, [npm, "run", "dev"],
                tag="frontend",
                on_exit=self._frontend_exited,
            )
            self._refresh_state()

    def _frontend_exited(self, rc: int) -> None:
        self.frontend_proc = None
        self._refresh_state()

    # ---- Rebuild ------------------------------------------------------------
    def rebuild(self) -> None:
        if self.rebuild_proc and self.rebuild_proc.poll() is None:
            messagebox.showinfo(TITLE, "A rebuild is already running.")
            return
        npm = _npm_cmd()
        if not npm:
            messagebox.showerror(TITLE, "npm was not found on PATH.")
            return
        if not WEBCLIENT_DIR.exists():
            messagebox.showerror(TITLE, f"Directory not found:\n{WEBCLIENT_DIR}")
            return
        self._log("[rebuild] npm run build ...")
        self.rebuild_proc = self._spawn(
            WEBCLIENT_DIR, [npm, "run", "build"],
            tag="rebuild",
            on_exit=lambda rc: self._log(f"[rebuild] finished (code {rc})"),
        )

    # ---- Deploy --------------------------------------------------------------
    def deploy(self) -> None:
        if self.deploy_proc and self.deploy_proc.poll() is None:
            messagebox.showinfo(TITLE, "A deploy is already running.")
            return
        if not os.path.exists(PROD_PARAMIKO_PY):
            messagebox.showerror(
                TITLE,
                f"Python with paramiko not found:\n{PROD_PARAMIKO_PY}\n\n"
                "Install paramiko there:\n  "
                f'"{PROD_PARAMIKO_PY}" -m pip install paramiko',
            )
            return
        script = Path(_RUNNER_DIR) / "deploy_prod.py"
        if not script.exists():
            messagebox.showerror(TITLE, f"Not found:\n{script}")
            return
        self._show_tab("deploy")
        self._log("[deploy] Starting paramiko deploy to prod ...")
        self.deploy_btn.config(state=tk.DISABLED)

        def _done(rc: int) -> None:
            self.deploy_btn.config(state=tk.NORMAL)
            if rc == 0:
                self.check_prod()

        self.deploy_proc = self._spawn(
            Path(_RUNNER_DIR),
            [PROD_PARAMIKO_PY, str(script), "--repo-root", str(BASE_DIR)],
            tag="deploy",
            on_exit=_done,
        )
        if self.deploy_proc is None:
            self.deploy_btn.config(state=tk.NORMAL)

    # ---- Push DB to Prod ----------------------------------------------------
    def push_db(self) -> None:
        """Upload the local SQLite DB to prod (overwrites prod data)."""
        if self.pushdb_proc and self.pushdb_proc.poll() is None:
            messagebox.showinfo(TITLE, "A DB push is already running.")
            return
        if not os.path.exists(PROD_PARAMIKO_PY):
            messagebox.showerror(
                TITLE,
                f"Python with paramiko not found:\n{PROD_PARAMIKO_PY}\n\n"
                "Install paramiko there:\n  "
                f'"{PROD_PARAMIKO_PY}" -m pip install paramiko',
            )
            return
        script = Path(_RUNNER_DIR) / "push_db.py"
        if not script.exists():
            messagebox.showerror(TITLE, f"Not found:\n{script}")
            return
        if not LOCAL_DB_PATH.exists():
            messagebox.showerror(
                TITLE,
                f"Local DB not found:\n{LOCAL_DB_PATH}\n\n"
                "Start the server once to initialize it, or seed test data via\n"
                "python -m api.scripts.seed_cost_test_scenario",
            )
            return
        size_kb = LOCAL_DB_PATH.stat().st_size / 1024
        confirmed = messagebox.askyesno(
            TITLE,
            "Push the local database to PROD?\n\n"
            f"Local : {LOCAL_DB_PATH}  ({size_kb:.0f} KB)\n"
            f"Prod  : {REMOTE_DB_PATH}\n\n"
            "This OVERWRITES the production database. A backup of the remote DB "
            "and an api container restart are performed. The local server should "
            "be stopped (or idle) for a consistent snapshot.",
            icon="warning",
        )
        if not confirmed:
            return
        self._show_tab("pushdb")
        self._log(f"[pushdb] {LOCAL_DB_PATH.name} -> prod:{REMOTE_DB_PATH} "
                  "(backup + api restart)")
        self.pushdb_btn.config(state=tk.DISABLED)

        def _done(rc: int) -> None:
            self.pushdb_btn.config(state=tk.NORMAL)
            if rc == 0:
                self.check_prod()

        self.pushdb_proc = self._spawn(
            Path(_RUNNER_DIR),
            [PROD_PARAMIKO_PY, str(script), "--repo-root", str(BASE_DIR)],
            tag="pushdb",
            on_exit=_done,
        )
        if self.pushdb_proc is None:
            self.pushdb_btn.config(state=tk.NORMAL)

    # ---- Prod service control ----------------------------------------------
    def _run_prod_service(self, action: str, label: str) -> None:
        """Spawn prod-service.ps1 <action> in a console window (SSH to prod)."""
        if self.prodsvc_proc and self.prodsvc_proc.poll() is None:
            messagebox.showinfo(TITLE, "A prod service operation is already running.")
            return
        script = Path(_RUNNER_DIR) / "prod-service.ps1"
        self._log(f"[prod] {label} api container on prod ...")
        on_done = None
        if action in ("start", "restart"):
            on_done = lambda rc: self.root.after(0, self.check_prod)
        self.prodsvc_proc = self._spawn_console_script(
            script, "prod", extra_args=["-Action", action], on_done=on_done,
        )

    def start_prod_api(self) -> None:
        self._run_prod_service("start", "start")

    def stop_prod_api(self) -> None:
        self._run_prod_service("stop", "stop")

    def restart_prod_api(self) -> None:
        self._run_prod_service("restart", "restart")

    # ---- log ----------------------------------------------------------------
    def _log(self, line: str) -> None:
        self.log_queue.put(("out", line))

    def _append_log(self, line: str) -> None:
        self._append_to(self.all_log, line)
        tag = self._tag_of(line)
        if tag and tag in self.log_tabs:
            self._append_to(self.log_tabs[tag], line)

    @staticmethod
    def _tag_of(line: str) -> str | None:
        m = _TAG_RE.match(line)
        return m.group(1).lower() if m else None

    @staticmethod
    def _append_to(widget: tk.Widget, line: str) -> None:
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, line + "\n")
        line_count = int(widget.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            widget.delete(1.0, f"{line_count - MAX_LOG_LINES}.0")
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)

    def _show_tab(self, tag: str) -> None:
        widget = self.log_tabs.get(tag)
        if widget is not None:
            self.nb.select(widget)

    def clear_log(self) -> None:
        for w in (self.all_log, *self.log_tabs.values()):
            w.config(state=tk.NORMAL)
            w.delete(1.0, tk.END)
            w.config(state=tk.DISABLED)

    def _poll_log(self) -> None:
        try:
            while True:
                _tag, line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    # ---- state sync ---------------------------------------------------------
    def _refresh_state(self) -> None:
        srv_on = self.is_server_running()
        fe_on = self.is_frontend_running()

        self.srv_btn.config(text="Stop Server" if srv_on else "Start Server")
        self.srv_dot.config(bg=CLR_ON if srv_on else CLR_OFF)
        self.srv_status.config(text="Running" if srv_on else "Stopped")

        self.fe_btn.config(text="Stop Frontend" if fe_on else "Start Frontend")
        self.fe_dot.config(bg=CLR_ON if fe_on else CLR_OFF)
        self.fe_status.config(text="Running" if fe_on else "Stopped")

        try:
            self.tray.update_menu()
        except Exception:
            pass

    # ---- system tray --------------------------------------------------------
    def _make_icon_image(self):
        size = 64
        img = Image.new("RGBA", (size, size), (44, 62, 80, 255))
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        text = "CTM"
        bbox = d.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(
            ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]),
            text, fill=(255, 255, 255, 255), font=font,
        )
        return img

    def _build_tray(self) -> None:
        self.tray = pystray.Icon(
            "ctm-runner", self._make_icon_image(), TITLE, self._tray_menu()
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _tray_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Show window", self._tray_show, default=True),
            pystray.MenuItem(
                lambda *a: "Stop server" if self.is_server_running() else "Start server",
                self._tray_toggle_server),
            pystray.MenuItem(
                lambda *a: "Stop frontend" if self.is_frontend_running() else "Start frontend",
                self._tray_toggle_frontend),
            pystray.MenuItem("Rebuild frontend", self._tray_rebuild),
            pystray.MenuItem("Deploy to prod", self._tray_deploy),
            pystray.MenuItem("Push DB to prod", self._tray_push_db),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start prod API", self._tray_start_prod),
            pystray.MenuItem("Stop prod API", self._tray_stop_prod),
            pystray.MenuItem("Restart prod API", self._tray_restart_prod),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open dev frontend", self._tray_open_dev),
            pystray.MenuItem("Open prod frontend", self._tray_open_prod),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._tray_exit),
        )

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self._show_window)

    def _tray_toggle_server(self, icon=None, item=None):
        self.root.after(0, self.toggle_server)

    def _tray_toggle_frontend(self, icon=None, item=None):
        self.root.after(0, self.toggle_frontend)

    def _tray_rebuild(self, icon=None, item=None):
        self.root.after(0, self.rebuild)

    def _tray_deploy(self, icon=None, item=None):
        self.root.after(0, self.deploy)

    def _tray_push_db(self, icon=None, item=None):
        self.root.after(0, self.push_db)

    def _tray_start_prod(self, icon=None, item=None):
        self.root.after(0, self.start_prod_api)

    def _tray_stop_prod(self, icon=None, item=None):
        self.root.after(0, self.stop_prod_api)

    def _tray_restart_prod(self, icon=None, item=None):
        self.root.after(0, self.restart_prod_api)

    def _tray_open_dev(self, icon=None, item=None):
        webbrowser.open(FRONTEND_URL)

    def _tray_open_prod(self, icon=None, item=None):
        webbrowser.open(PROD_URL)

    def _tray_exit(self, icon=None, item=None):
        self.root.after(0, self._quit)

    # ---- lifecycle ----------------------------------------------------------
    def _hide_to_tray(self) -> None:
        self.root.withdraw()

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        _kill_tree(self.server_proc)
        _kill_tree(self.frontend_proc)
        _kill_tree(self.rebuild_proc)
        _kill_tree(self.deploy_proc)
        _kill_tree(self.pushdb_proc)
        try:
            self.tray.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    if not CURRENT_DIR.exists():
        sys.stderr.write(
            f"Could not locate project 'current' dir:\n  {CURRENT_DIR}\n"
            "Expected layout: <repo>/CTM2_recovered/current/api ...\n"
        )
        sys.exit(1)
    RunnerApp().run()


if __name__ == "__main__":
    main()
