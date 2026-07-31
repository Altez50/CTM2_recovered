#!/usr/bin/env python3
"""CTM Runner — desktop control panel for the CTM project.

A tkinter window plus a system-tray icon (rendered text "CTM") with
**independent** controls for server and frontend, so you can run both
simultaneously (the normal case for full-stack dev):

  * Start / Stop Server    — uvicorn (API backend)
  * Start / Stop Frontend  — Vite dev server
  * Rebuild                — `npm run build` (production bundle)
  * Deploy to prod         — STUB (needs research)

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
import shutil
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
import webbrowser
from tkinter import messagebox, scrolledtext

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
MAX_LOG_LINES = 2000

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
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._exiting = False

        self._build_ui()
        self._build_tray()
        self._poll_log()
        self._refresh_state()

    # ---- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.geometry("560x460")
        self.root.minsize(460, 360)
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.font_b = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.font_sm = tkfont.Font(family="Segoe UI", size=9)
        self.font_link = tkfont.Font(
            family="Segoe UI", size=9, underline=True,
        )

        top = tk.Frame(self.root, padx=14, pady=10)
        top.pack(side=tk.TOP, fill=tk.X)

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
            aux_row, text="Deploy to Prod (stub)", command=self.deploy, fg="#b7791f",
        )
        self.deploy_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # --- Log ---
        log_lbl = tk.Label(self.root, text="Output", anchor="w")
        log_lbl.config(font=self.font)
        log_lbl.pack(fill=tk.X, padx=14)
        self.log = scrolledtext.ScrolledText(
            self.root, height=12, state=tk.DISABLED, wrap=tk.NONE,
            bg="#1e1e1e", fg="#dcdcdc", insertbackground="#dcdcdc",
        )
        self.log.config(font=tkfont.Font(family="Consolas", size=9))
        self.log.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 4))

        clr = tk.Button(self.root, text="Clear log", command=self.clear_log)
        clr.pack(side=tk.RIGHT, padx=14, pady=(0, 8))

    # ---- process spawning ---------------------------------------------------
    def _make_link(self, parent, text: str, url: str) -> tk.Label:
        lbl = tk.Label(parent, text=text, fg="#2c6fbb", cursor="hand2")
        lbl.config(font=self.font_link)
        lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
        return lbl

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

    # ---- Deploy (stub) ------------------------------------------------------
    def deploy(self) -> None:
        self._log("[deploy] STUB — not implemented yet (needs research).")
        messagebox.showinfo(
            TITLE,
            "Deploy to production is a stub.\n\n"
            "Production uses docker-compose under deploy/ against a remote "
            "host (abitek.su). Wiring this needs research (remote access, "
            "secrets, build/push flow) and is intentionally left as a stub.",
        )

    # ---- log ----------------------------------------------------------------
    def _log(self, line: str) -> None:
        self.log_queue.put(("out", line))

    def _append_log(self, line: str) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n")
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.log.delete(1.0, f"{line_count - MAX_LOG_LINES}.0")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def clear_log(self) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.delete(1.0, tk.END)
        self.log.config(state=tk.DISABLED)

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
            pystray.MenuItem("Deploy to prod (stub)", self._tray_deploy),
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
