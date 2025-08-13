import threading
import time
import queue
import tkinter as tk
from tkinter import ttk

from ..backend.events import BackendEvents
from ..backend.robot_backend import RobotBackend
from ..config.settings import (
    DEFAULT_SERIAL, DEFAULT_IFACE, DEFAULT_JOB, DEFAULT_SPEED
)
from ..config.plans import PLAN_MAP


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.pack(fill="both", expand=True)
        self.event_q = queue.Queue()

        # State flags bound to UI
        self.program_request = tk.BooleanVar(value=False)
        self.running = tk.BooleanVar(value=False)
        self.paused = tk.BooleanVar(value=False)
        self.fault = tk.BooleanVar(value=False)
        self.progress = tk.IntVar(value=0)

        # Config (UI-bound)
        self.robot_sn = tk.StringVar(value=DEFAULT_SERIAL)
        self.iface = tk.StringVar(value=DEFAULT_IFACE)
        self.speed = tk.IntVar(value=DEFAULT_SPEED)
        self.speed_label = tk.StringVar(value=f"{DEFAULT_SPEED}%")
        self.job = tk.StringVar(value=DEFAULT_JOB)
        self.plan_id = tk.IntVar(value=PLAN_MAP.get(DEFAULT_JOB, 1))
        self.plan_map = PLAN_MAP

        # Backend
        self.backend = RobotBackend(self.event_q, self.robot_sn.get, self.iface.get)

        self._build_ui()
        self.after(50, self._pump_events)

    def _build_ui(self):
        self.master.title("PCB Handler – Flexiv Launcher")
        self.master.minsize(760, 540)
        try:
            self.master.tk.call("tk", "scaling", 1.25)
        except Exception:
            pass

        style = ttk.Style()
        style.configure("TButton", padding=6)
        style.configure("Header.TLabel", font=("Arial", 14, "bold"))

        ttk.Label(self, text="Flexiv Job Launcher", style="Header.TLabel") \
            .grid(row=0, column=0, columnspan=6, sticky="w")

        # Connection row
        ttk.Label(self, text="Robot SN:").grid(row=1, column=0, sticky="e", pady=4)
        ttk.Entry(self, textvariable=self.robot_sn, width=20).grid(row=1, column=1, sticky="w")
        ttk.Label(self, text="Iface (opt):").grid(row=1, column=2, sticky="e")
        ttk.Entry(self, textvariable=self.iface, width=16).grid(row=1, column=3, sticky="w")
        ttk.Button(self, text="Connect", command=self.on_connect).grid(row=1, column=4, sticky="w", padx=6)
        ttk.Label(
            self,
            text="RDK: Remote Mode must be enabled; Motion Bar: Auto (Remote)",
            foreground="#666",
        ).grid(row=2, column=0, columnspan=6, sticky="w")

        # Job row (Plan ID read-only)
        ttk.Label(self, text="Job:").grid(row=3, column=0, sticky="e", pady=4)
        cb = ttk.Combobox(
            self,
            textvariable=self.job,
            values=list(self.plan_map.keys()),
            state="readonly",
            width=14,
        )
        cb.grid(row=3, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", self.on_job_changed)
        ttk.Label(self, text="Plan ID:").grid(row=3, column=2, sticky="e")
        ttk.Label(self, textvariable=self.plan_id).grid(row=3, column=3, sticky="w")

        # Speed
        ttk.Label(self, text="Speed %:").grid(row=4, column=0, sticky="e", pady=6)
        sp = ttk.Scale(
            self,
            from_=1,
            to=100,
            variable=self.speed,
            orient="horizontal",
            command=lambda v: self.speed_label.set(f"{int(float(v))}%"),
        )
        sp.grid(row=4, column=1, columnspan=2, sticky="we")
        ttk.Label(self, textvariable=self.speed_label).grid(row=4, column=3, sticky="w")

        # Buttons (wired to backend shells)
        btns = ttk.Frame(self)
        btns.grid(row=5, column=0, columnspan=6, sticky="we", pady=8)
        self.btn_start = ttk.Button(btns, text="Start", command=self.on_start)
        self.btn_pause = ttk.Button(btns, text="Pause", command=self.on_pause, state="disabled")
        self.btn_resume = ttk.Button(btns, text="Resume", command=self.on_resume, state="disabled")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        for i, b in enumerate((self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop)):
            b.grid(row=0, column=i, padx=6)

        # Status indicators
        ind = ttk.Labelframe(self, text="Status")
        ind.grid(row=6, column=0, columnspan=6, sticky="we", pady=6)
        self._mk_indicator(ind, "Program Request", self.program_request, 0)
        self._mk_indicator(ind, "Running", self.running, 1)
        self._mk_indicator(ind, "Paused", self.paused, 2)
        self._mk_indicator(ind, "Fault", self.fault, 3)

        # Progress + Log
        self.pbar = ttk.Progressbar(self, maximum=10, variable=self.progress, mode="determinate")
        self.pbar.grid(row=7, column=0, columnspan=6, sticky="we", pady=6)

        logf = ttk.Labelframe(self, text="Log")
        logf.grid(row=8, column=0, columnspan=6, sticky="nsew", pady=6)
        self.txt = tk.Text(logf, height=12)
        self.txt.pack(fill="both", expand=True)

        # Layout stretch
        for c in (1, 2, 3, 4, 5):
            self.columnconfigure(c, weight=1)
        self.rowconfigure(8, weight=1)

        self.on_job_changed()

    def _mk_indicator(self, parent, label, var, col):
        f = ttk.Frame(parent, padding=(6, 4))
        f.grid(row=0, column=col, sticky="w")
        dot = tk.Canvas(f, width=12, height=12, highlightthickness=0)
        dot.grid(row=0, column=0, padx=(0, 6))
        ttk.Label(f, text=label).grid(row=0, column=1)

        def paint(*_):
            dot.delete("all")
            color = "#1abc9c" if var.get() else "#e0e0e0"
            if label == "Fault" and var.get():
                color = "#e74c3c"
            dot.create_oval(2, 2, 10, 10, fill=color, outline="")

        var.trace_add("write", paint)
        paint()

    # -------- Actions --------
    def on_connect(self):
        threading.Thread(target=self.backend.connect, daemon=True).start()

    def on_job_changed(self, *_):
        self.plan_id.set(self.plan_map.get(self.job.get(), 1))

    def on_start(self):
        self.progress.set(0)
        self.paused.set(False)
        self.fault.set(False)
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")
        threading.Thread(
            target=self.backend.start_plan,
            args=(self.plan_id.get(), self.speed.get()),
            daemon=True,
        ).start()

    def on_pause(self):
        self.backend.pause()
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="normal")

    def on_resume(self):
        self.backend.resume()
        self.btn_pause.configure(state="normal")
        self.btn_resume.configure(state="disabled")

    def on_stop(self):
        self.backend.stop()
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="disabled")
        self.btn_stop.configure(state="disabled")

    # -------- Event pump --------
    def _pump_events(self):
        try:
            while True:
                kind, msg = self.event_q.get_nowait()
                if kind == BackendEvents.PROGRAM_REQUEST:
                    self.program_request.set(bool(msg))
                elif kind == BackendEvents.RUNNING:
                    running = bool(msg)
                    self.running.set(running)
                    if running:
                        self.progress.set(0)
                    else:
                        self.btn_start.configure(state="normal")
                        self.btn_pause.configure(state="disabled")
                        self.btn_resume.configure(state="disabled")
                        self.btn_stop.configure(state="disabled")
                elif kind == BackendEvents.PAUSED:
                    self.paused.set(bool(msg))
                elif kind == BackendEvents.STOPPED:
                    self.running.set(False)
                elif kind == BackendEvents.FAULT:
                    self.fault.set(True)
                    self.running.set(False)
                    self.btn_start.configure(state="normal")
                    self.btn_pause.configure(state="disabled")
                    self.btn_resume.configure(state="disabled")
                    self.btn_stop.configure(state="disabled")
                elif kind == BackendEvents.LOG:
                    self._log(msg)
        except queue.Empty:
            pass
        self.after(50, self._pump_events)

    def _log(self, text):
        self.txt.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.txt.see("end")

