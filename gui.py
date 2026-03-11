#!/usr/bin/env python3
"""
ComfyUI Workflow Beautifier - GUI
Standalone desktop app. NOT a ComfyUI plugin.
"""

import os
import sys
import json
import queue
import threading
import subprocess
import urllib.request
import urllib.error
from tkinter import filedialog, messagebox
import tkinter as tk
import tkinter.ttk as ttk
from tkinter.scrolledtext import ScrolledText

try:
    from tkinterdnd2 import TkDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT, "outputs")
INPUTS_DIR  = os.path.join(ROOT, "inputs")
CONFIG_FILE = os.path.join(ROOT, ".gui_config.json")

# ── Colours ────────────────────────────────────────────────────────────────────
BG       = "#1e1e2e"
SURFACE  = "#2a2a3e"
BORDER   = "#3a3a5c"
ACCENT   = "#7c6af7"
ACCENT2  = "#1a6b2a"
RED      = "#8b1a1a"
FG       = "#cdd6f4"
FG_DIM   = "#6c7086"
FG_GREEN = "#a6e3a1"
FG_RED   = "#f38ba8"
FG_YELLOW= "#f9e2af"

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_config() -> dict:
    defaults = {
        "ollama_url":    "http://localhost:11434",
        "ollama_model":  "qwen3.5:9b",
        "searxng_container": "searxng",
        "provider":      "ollama",   # "ollama" | "minimax" | "kimi"
        "minimax_key":   "",
        "minimax_model": "MiniMax-M2.5",
        "kimi_key":      "",
        "kimi_model":    "kimi-k2-5-instruct",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return {**defaults, **json.load(f)}
        except Exception:
            pass
    return defaults


def _save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def _fetch_ollama_models(url: str) -> list[str]:
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _open_folder(path: str):
    os.makedirs(path, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _docker_cmd(action: str, container: str) -> bool:
    try:
        r = subprocess.run(
            ["docker", action, container],
            capture_output=True, timeout=15
        )
        return r.returncode == 0
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Log redirector
# ═══════════════════════════════════════════════════════════════════════════════

class QueueStream:
    """Redirect stdout/stderr into a queue for the GUI log widget."""
    def __init__(self, q: queue.Queue, tag: str = ""):
        self.q = q
        self.tag = tag

    def write(self, text: str):
        if text.strip():
            self.q.put((self.tag, text))

    def flush(self):
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# Main window
# ═══════════════════════════════════════════════════════════════════════════════

class App(TkDnD if HAS_DND else tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("ComfyUI Workflow Beautifier")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=BG)

        self.cfg = _load_config()
        self._log_q: queue.Queue = queue.Queue()
        self._workflow_files: list[str] = []   # JSON paths queued
        self._user_info_path: str = os.path.join(INPUTS_DIR, "user_info.md")
        self._running = False

        self._apply_theme()
        self._build_ui()
        self._start_services()
        self._refresh_models()
        self._poll_log()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Theme ──────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        for widget in ("TFrame", "TLabelFrame"):
            style.configure(widget, background=BG, bordercolor=BORDER, foreground=FG)
        style.configure("TLabel",       background=BG,      foreground=FG)
        style.configure("Dim.TLabel",   background=BG,      foreground=FG_DIM)
        style.configure("TEntry",       fieldbackground=SURFACE, foreground=FG,
                        insertcolor=FG, bordercolor=BORDER)
        style.configure("TCombobox",    fieldbackground=SURFACE, foreground=FG,
                        selectbackground=ACCENT, bordercolor=BORDER)
        style.map("TCombobox",          fieldbackground=[("readonly", SURFACE)])
        style.configure("Accent.TButton",  background=ACCENT,  foreground="#ffffff",
                        font=("Segoe UI", 10, "bold"), borderwidth=0, padding=8)
        style.map("Accent.TButton",
                  background=[("active", "#9b8df8"), ("disabled", BORDER)])
        style.configure("TButton",      background=SURFACE, foreground=FG,
                        borderwidth=1, relief="flat", padding=6)
        style.map("TButton",
                  background=[("active", BORDER)])
        style.configure("TScrollbar",   background=SURFACE, troughcolor=BG,
                        bordercolor=BG, arrowcolor=FG_DIM)

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=BG, pady=10, padx=16)
        top.pack(fill="x")
        tk.Label(top, text="✦ ComfyUI Workflow Beautifier",
                 font=("Segoe UI", 14, "bold"), bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(top, text="  standalone tool · not a ComfyUI plugin",
                 font=("Segoe UI", 9), bg=BG, fg=FG_DIM).pack(side="left", pady=4)

        # ── Status strip ──────────────────────────────────────────────────────
        self._status_bar = tk.Label(
            self, text="● Starting services…", font=("Segoe UI", 9),
            bg=SURFACE, fg=FG_YELLOW, anchor="w", padx=12, pady=4
        )
        self._status_bar.pack(fill="x")

        # ── Main body ─────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        left  = tk.Frame(body, bg=BG, width=340)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_right(right)

        # ── Bottom action bar ─────────────────────────────────────────────────
        bottom = tk.Frame(self, bg=SURFACE, pady=10, padx=16)
        bottom.pack(fill="x", side="bottom")

        self._run_btn = ttk.Button(
            bottom, text="▶  Run Beautifier", style="Accent.TButton",
            command=self._run
        )
        self._run_btn.pack(side="left")

        ttk.Button(bottom, text="📂 Open Outputs",
                   command=lambda: _open_folder(OUTPUTS_DIR)).pack(side="left", padx=8)
        ttk.Button(bottom, text="🗑 Clear Queue",
                   command=self._clear_queue).pack(side="left")

        self._progress = ttk.Progressbar(bottom, mode="indeterminate", length=180)
        self._progress.pack(side="right", padx=8)

    # ── Left panel ─────────────────────────────────────────────────────────────

    def _build_left(self, parent):
        # Settings section
        sf = tk.LabelFrame(parent, text=" ⚙ Settings ", bg=BG, fg=ACCENT,
                           font=("Segoe UI", 9, "bold"),
                           bd=1, relief="solid", highlightbackground=BORDER)
        sf.pack(fill="x", pady=(0, 10))

        # Provider radio buttons
        self._provider_var = tk.StringVar(value=self.cfg.get("provider", "ollama"))
        prow = tk.Frame(sf, bg=BG)
        prow.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8,4))
        for val, label in [("ollama", "🖥 Ollama"), ("minimax", "☁ MiniMax"), ("kimi", "🌙 Kimi")]:
            tk.Radiobutton(
                prow, text=label, variable=self._provider_var, value=val,
                bg=BG, fg=FG, selectcolor=SURFACE, activebackground=BG,
                activeforeground=ACCENT, font=("Segoe UI", 9),
                command=self._on_provider_change,
            ).pack(side="left", padx=(0, 8))

        # ── Ollama sub-panel ──
        self._ollama_frame = tk.Frame(sf, bg=BG)
        self._ollama_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        tk.Label(self._ollama_frame, text="Ollama URL", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", padx=8, pady=(0,2))
        self._url_var = tk.StringVar(value=self.cfg["ollama_url"])
        url_entry = ttk.Entry(self._ollama_frame, textvariable=self._url_var)
        url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0,4))
        url_entry.bind("<FocusOut>", lambda _: self._refresh_models())
        tk.Label(self._ollama_frame, text="Model", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", padx=8)
        self._model_var = tk.StringVar(value=self.cfg["ollama_model"])
        self._model_cb = ttk.Combobox(self._ollama_frame, textvariable=self._model_var, state="readonly")
        self._model_cb.grid(row=3, column=0, sticky="ew", padx=8, pady=(0,6))
        ttk.Button(self._ollama_frame, text="↺", width=3,
                   command=self._refresh_models).grid(row=3, column=1, padx=(0,8))
        self._ollama_frame.columnconfigure(0, weight=1)

        # ── MiniMax sub-panel ──
        self._minimax_frame = tk.Frame(sf, bg=BG)
        self._minimax_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        tk.Label(self._minimax_frame, text="MiniMax API Key", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", padx=8, pady=(0,2))
        self._minimax_key_var = tk.StringVar(value=self.cfg.get("minimax_key", ""))
        ttk.Entry(self._minimax_frame, textvariable=self._minimax_key_var, show="•").grid(
            row=1, column=0, sticky="ew", padx=8, pady=(0,4))
        tk.Label(self._minimax_frame, text="Model", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", padx=8)
        self._minimax_model_var = tk.StringVar(value=self.cfg.get("minimax_model", "MiniMax-M2.5"))
        ttk.Entry(self._minimax_frame, textvariable=self._minimax_model_var).grid(
            row=3, column=0, sticky="ew", padx=8, pady=(0,6))
        self._minimax_frame.columnconfigure(0, weight=1)

        # ── Kimi sub-panel ──
        self._kimi_frame = tk.Frame(sf, bg=BG)
        self._kimi_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        tk.Label(self._kimi_frame, text="Kimi API Key", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", padx=8, pady=(0,2))
        self._kimi_key_var = tk.StringVar(value=self.cfg.get("kimi_key", ""))
        ttk.Entry(self._kimi_frame, textvariable=self._kimi_key_var, show="•").grid(
            row=1, column=0, sticky="ew", padx=8, pady=(0,4))
        tk.Label(self._kimi_frame, text="Model", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", padx=8)
        self._kimi_model_var = tk.StringVar(value=self.cfg.get("kimi_model", "kimi-k2-5-instruct"))
        ttk.Entry(self._kimi_frame, textvariable=self._kimi_model_var).grid(
            row=3, column=0, sticky="ew", padx=8, pady=(0,6))
        self._kimi_frame.columnconfigure(0, weight=1)

        sf.columnconfigure(0, weight=1)
        self._on_provider_change()  # show correct sub-panel

        # User info file
        uif = tk.LabelFrame(parent, text=" 👤 User Info ", bg=BG, fg=ACCENT,
                            font=("Segoe UI", 9, "bold"),
                            bd=1, relief="solid", highlightbackground=BORDER)
        uif.pack(fill="x", pady=(0, 10))

        self._userinfo_lbl = tk.Label(
            uif, text=self._short_path(self._user_info_path),
            bg=BG, fg=FG_GREEN if os.path.exists(self._user_info_path) else FG_DIM,
            font=("Segoe UI", 8), wraplength=280, anchor="w", justify="left"
        )
        self._userinfo_lbl.pack(fill="x", padx=8, pady=6)
        btn_row = tk.Frame(uif, bg=BG)
        btn_row.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(btn_row, text="Browse…",
                   command=self._browse_userinfo).pack(side="left")
        ttk.Button(btn_row, text="Edit",
                   command=self._edit_userinfo).pack(side="left", padx=4)

        if HAS_DND:
            uif.drop_target_register(DND_FILES)
            uif.dnd_bind("<<Drop>>", lambda e: self._drop_userinfo(e.data))

        # Workflow queue
        wf = tk.LabelFrame(parent, text=" 📋 Workflow Queue ", bg=BG, fg=ACCENT,
                           font=("Segoe UI", 9, "bold"),
                           bd=1, relief="solid", highlightbackground=BORDER)
        wf.pack(fill="both", expand=True)

        hint = "Drag & drop JSON files here" if HAS_DND else "Click Add to select files"
        tk.Label(wf, text=hint, bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8, "italic")).pack(pady=(6,2))

        list_frame = tk.Frame(wf, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self._file_list = tk.Listbox(
            list_frame, bg=SURFACE, fg=FG, selectbackground=ACCENT,
            font=("Segoe UI", 9), bd=0, highlightthickness=0,
            yscrollcommand=scrollbar.set, activestyle="none"
        )
        self._file_list.pack(fill="both", expand=True)
        scrollbar.config(command=self._file_list.yview)

        if HAS_DND:
            self._file_list.drop_target_register(DND_FILES)
            self._file_list.dnd_bind("<<Drop>>", lambda e: self._drop_workflows(e.data))

        btn_row2 = tk.Frame(wf, bg=BG)
        btn_row2.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(btn_row2, text="＋ Add",
                   command=self._browse_workflows).pack(side="left")
        ttk.Button(btn_row2, text="✕ Remove",
                   command=self._remove_selected).pack(side="left", padx=4)
        ttk.Button(btn_row2, text="📁 inputs/",
                   command=self._add_from_inputs).pack(side="right")

    # ── Right panel (log) ──────────────────────────────────────────────────────

    def _build_right(self, parent):
        lf = tk.LabelFrame(parent, text=" 📜 Log ", bg=BG, fg=ACCENT,
                           font=("Segoe UI", 9, "bold"),
                           bd=1, relief="solid", highlightbackground=BORDER)
        lf.pack(fill="both", expand=True)

        self._log = ScrolledText(
            lf, bg="#0d0d1a", fg=FG, font=("Consolas", 9),
            state="disabled", bd=0, highlightthickness=0,
            wrap="word", insertbackground=FG
        )
        self._log.pack(fill="both", expand=True, padx=4, pady=4)

        self._log.tag_config("info",    foreground=FG)
        self._log.tag_config("success", foreground=FG_GREEN)
        self._log.tag_config("error",   foreground=FG_RED)
        self._log.tag_config("warn",    foreground=FG_YELLOW)
        self._log.tag_config("dim",     foreground=FG_DIM)
        self._log.tag_config("accent",  foreground=ACCENT)

        btn_row = tk.Frame(lf, bg=BG)
        btn_row.pack(fill="x", padx=8, pady=(0,6))
        ttk.Button(btn_row, text="Clear log",
                   command=self._clear_log).pack(side="right")

    # ── Provider switching ─────────────────────────────────────────────────────

    def _on_provider_change(self):
        p = self._provider_var.get()
        self._ollama_frame.grid_remove()
        self._minimax_frame.grid_remove()
        self._kimi_frame.grid_remove()
        if p == "ollama":
            self._ollama_frame.grid()
        elif p == "minimax":
            self._minimax_frame.grid()
        elif p == "kimi":
            self._kimi_frame.grid()

    # ── Services ───────────────────────────────────────────────────────────────

    def _start_services(self):
        def _start():
            container = self.cfg.get("searxng_container", "searxng")
            self._log_msg(f"Starting SearXNG container '{container}'…", "dim")
            ok = _docker_cmd("start", container)
            if ok:
                self._log_msg("✓ SearXNG started", "success")
                self._set_status("● Services ready", FG_GREEN)
            else:
                self._log_msg("⚠ SearXNG start failed (Docker unavailable or container missing)", "warn")
                self._set_status("⚠ SearXNG unavailable — web search disabled", FG_YELLOW)
        threading.Thread(target=_start, daemon=True).start()

    def _stop_services(self):
        container = self.cfg.get("searxng_container", "searxng")
        self._log_msg(f"Stopping SearXNG container '{container}'…", "dim")
        _docker_cmd("stop", container)

    # ── Model refresh ──────────────────────────────────────────────────────────

    def _refresh_models(self):
        url = self._url_var.get().strip()
        def _fetch():
            models = _fetch_ollama_models(url)
            if models:
                self.after(0, lambda: self._model_cb.configure(values=models))
                if self._model_var.get() not in models:
                    self.after(0, lambda: self._model_var.set(models[0]))
                self._log_msg(f"✓ Ollama connected — {len(models)} model(s) found", "success")
            else:
                self._log_msg("⚠ Cannot reach Ollama at " + url, "warn")
        threading.Thread(target=_fetch, daemon=True).start()

    # ── File management ────────────────────────────────────────────────────────

    def _add_files(self, paths: list[str]):
        for p in paths:
            p = p.strip().strip("{}")
            if p.lower().endswith(".json") and p not in self._workflow_files:
                self._workflow_files.append(p)
                self._file_list.insert("end", os.path.basename(p))

    def _browse_workflows(self):
        paths = filedialog.askopenfilenames(
            title="Select workflow JSON files",
            filetypes=[("JSON", "*.json"), ("All", "*.*")]
        )
        self._add_files(list(paths))

    def _add_from_inputs(self):
        if os.path.isdir(INPUTS_DIR):
            paths = [
                os.path.join(INPUTS_DIR, f)
                for f in os.listdir(INPUTS_DIR)
                if f.endswith(".json")
            ]
            self._add_files(paths)
        else:
            messagebox.showinfo("Not found", f"inputs/ folder not found at:\n{INPUTS_DIR}")

    def _drop_workflows(self, data: str):
        # tkinterdnd2 wraps paths with {} on Windows for paths with spaces
        import re
        paths = re.findall(r'\{([^}]+)\}|(\S+)', data)
        flat = [a or b for a, b in paths]
        self._add_files(flat)

    def _remove_selected(self):
        for idx in reversed(self._file_list.curselection()):
            self._file_list.delete(idx)
            self._workflow_files.pop(idx)

    def _clear_queue(self):
        self._file_list.delete(0, "end")
        self._workflow_files.clear()

    def _browse_userinfo(self):
        path = filedialog.askopenfilename(
            title="Select user_info.md",
            filetypes=[("Markdown", "*.md"), ("All", "*.*")]
        )
        if path:
            self._set_userinfo(path)

    def _drop_userinfo(self, data: str):
        path = data.strip().strip("{}")
        if path.endswith(".md"):
            self._set_userinfo(path)

    def _set_userinfo(self, path: str):
        self._user_info_path = path
        self._userinfo_lbl.config(
            text=self._short_path(path),
            fg=FG_GREEN if os.path.exists(path) else FG_RED
        )

    def _edit_userinfo(self):
        if os.path.exists(self._user_info_path):
            os.startfile(self._user_info_path)
        else:
            messagebox.showinfo("Not found", f"File not found:\n{self._user_info_path}")

    # ── Run ────────────────────────────────────────────────────────────────────

    def _run(self):
        if self._running:
            return
        if not self._workflow_files:
            messagebox.showwarning("No files", "Add at least one workflow JSON to the queue.")
            return

        # Save current settings
        provider = self._provider_var.get()
        self.cfg["provider"]       = provider
        self.cfg["ollama_url"]     = self._url_var.get().strip()
        self.cfg["ollama_model"]   = self._model_var.get().strip()
        self.cfg["minimax_key"]    = self._minimax_key_var.get().strip()
        self.cfg["minimax_model"]  = self._minimax_model_var.get().strip()
        self.cfg["kimi_key"]       = self._kimi_key_var.get().strip()
        self.cfg["kimi_model"]     = self._kimi_model_var.get().strip()
        _save_config(self.cfg)

        # Patch config module at runtime
        import config as cfg_mod
        cfg_mod.OLLAMA_BASE_URL  = self.cfg["ollama_url"]
        cfg_mod.OLLAMA_MODELS    = [self.cfg["ollama_model"]]
        cfg_mod.ACTIVE_PROVIDER  = provider
        if provider == "minimax":
            cfg_mod.ACTIVE_API_KEY   = self.cfg["minimax_key"]
            cfg_mod.ACTIVE_API_MODEL = self.cfg["minimax_model"]
        elif provider == "kimi":
            cfg_mod.ACTIVE_API_KEY   = self.cfg["kimi_key"]
            cfg_mod.ACTIVE_API_MODEL = self.cfg["kimi_model"]
        else:
            cfg_mod.ACTIVE_API_KEY   = ""
            cfg_mod.ACTIVE_API_MODEL = ""

        self._running = True
        self._run_btn.state(["disabled"])
        self._progress.start(12)
        self._set_status("⚙ Processing…", FG_YELLOW)

        files = list(self._workflow_files)
        threading.Thread(target=self._worker, args=(files,), daemon=True).start()

    def _worker(self, files: list[str]):
        # Redirect stdout/stderr into the log queue
        import beautify as bmod
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = QueueStream(self._log_q, "info")
        sys.stderr = QueueStream(self._log_q, "error")

        success, failed = [], []
        try:
            for path in files:
                self._log_msg(f"\n{'─'*50}", "dim")
                self._log_msg(f"Processing: {os.path.basename(path)}", "accent")
                try:
                    # For cloud providers, model is set via cfg_mod.ACTIVE_API_MODEL;
                    # pass None so analyze_workflow picks it up from config.
                    ollama_model = self.cfg["ollama_model"] if self.cfg["provider"] == "ollama" else None
                    out = bmod.process_workflow(
                        path,
                        model=ollama_model,
                        user_info_override=self._user_info_path,
                    )
                    success.append((path, out))
                    self._log_msg(f"✓ Saved → {os.path.basename(out)}", "success")
                except Exception as e:
                    failed.append((path, str(e)))
                    self._log_msg(f"✗ Failed: {e}", "error")
        finally:
            sys.stdout, sys.stderr = old_out, old_err

        self.after(0, lambda: self._on_done(success, failed))

    def _on_done(self, success, failed):
        self._running = False
        self._run_btn.state(["!disabled"])
        self._progress.stop()

        total = len(success) + len(failed)
        if failed:
            self._set_status(
                f"⚠ {len(success)}/{total} succeeded, {len(failed)} failed", FG_YELLOW
            )
        else:
            self._set_status(f"✓ {len(success)}/{total} workflows beautified", FG_GREEN)
            _open_folder(OUTPUTS_DIR)

    # ── Log helpers ────────────────────────────────────────────────────────────

    def _log_msg(self, msg: str, tag: str = "info"):
        self._log_q.put((tag, msg + "\n"))

    def _poll_log(self):
        try:
            while True:
                tag, text = self._log_q.get_nowait()
                self._log.configure(state="normal")
                self._log.insert("end", text, tag)
                self._log.see("end")
                self._log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(80, self._poll_log)

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _set_status(self, msg: str, color: str = FG):
        self._status_bar.config(text=msg, fg=color)

    # ── Misc ───────────────────────────────────────────────────────────────────

    def _short_path(self, path: str) -> str:
        try:
            return os.path.relpath(path, ROOT)
        except ValueError:
            return path

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("Running", "Processing is still running. Quit anyway?"):
                return
        self._stop_services()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# beautify.py shim — expose user_info_override parameter
# ═══════════════════════════════════════════════════════════════════════════════

def _patch_beautify():
    """
    Monkey-patch beautify.process_workflow to accept user_info_override kwarg
    so the GUI can pass the user-selected user_info.md path.
    """
    import beautify as bmod
    import notes as nmod
    _orig = bmod.process_workflow

    def _patched(input_path, output_path=None, model=None, user_info_override=None):
        # Temporarily replace load_user_info to return our file
        if user_info_override:
            _orig_load = nmod.load_user_info
            nmod.load_user_info = lambda _: _orig_load(user_info_override)
            try:
                return _orig(input_path, output_path, model)
            finally:
                nmod.load_user_info = _orig_load
        return _orig(input_path, output_path, model)

    bmod.process_workflow = _patched


# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.chdir(ROOT)  # ensure relative imports work
    _patch_beautify()
    app = App()
    app.mainloop()
