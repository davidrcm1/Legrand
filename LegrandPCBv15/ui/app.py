import threading
import time
import queue
import tkinter as tk
from tkinter import ttk

from ..backend.events import BackendEvents
from ..backend.robot_backend import RobotBackend
from ..backend.sequencer import Sequencer, SequencerConfig
from ..config.settings import (
    DEFAULT_SERIAL, DEFAULT_IFACE, DEFAULT_JOB, DEFAULT_SPEED
)
from ..config.settings import DEFAULT_TRAYSIZE, SEQUENCER_PROFILES
from ..config.settings import DEFAULT_TRAYSIZE


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
        self.job = tk.StringVar(value=list(SEQUENCER_PROFILES.keys())[0])
        self.plan_name = tk.StringVar(value=f"Sequencer: {list(SEQUENCER_PROFILES.keys())[0]}")

        # Backend
        self.backend = RobotBackend(
            self.event_q, self.robot_sn.get, self.iface.get
        )

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

        ttk.Label(
            self,
            text="Flexiv Job Launcher",
            style="Header.TLabel"
        ).grid(row=0, column=0, columnspan=6, sticky="w")

        # Connection row
        ttk.Label(self, text="Robot SN:").grid(row=1, column=0, sticky="e", pady=4)
        ttk.Entry(
            self, textvariable=self.robot_sn, width=20
        ).grid(row=1, column=1, sticky="w")
        ttk.Label(self, text="Iface (opt):").grid(row=1, column=2, sticky="e")
        ttk.Entry(
            self, textvariable=self.iface, width=16
        ).grid(row=1, column=3, sticky="w")
        ttk.Button(
            self, text="Connect", command=self.on_connect
        ).grid(row=1, column=4, sticky="w", padx=6)
        ttk.Label(
            self,
            text="RDK: Remote Mode must be enabled; Motion Bar: Auto (Remote)",
            foreground="#666",
        ).grid(row=2, column=0, columnspan=6, sticky="w")
        ttk.Button(
            self, text="Disconnect", command=self.on_disconnect
        ).grid(row=1, column=5, sticky="w")

        # Job row (Plan ID read-only)
        ttk.Label(self, text="Job:").grid(row=3, column=0, sticky="e", pady=4)
        cb = ttk.Combobox(
            self,
            textvariable=self.job,
            values=list(SEQUENCER_PROFILES.keys()),
            state="readonly",
            width=14,
        )
        cb.grid(row=3, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", self.on_job_changed)
        ttk.Label(self, text="Mode:").grid(row=3, column=2, sticky="e")
        ttk.Label(
            self, textvariable=self.plan_name
        ).grid(row=3, column=3, sticky="w")

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
        ttk.Label(
            self, textvariable=self.speed_label
        ).grid(row=4, column=3, sticky="w")

        # Buttons (wired to backend shells)
        btns = ttk.Frame(self)
        btns.grid(row=5, column=0, columnspan=6, sticky="we", pady=8)
        self.btn_start = ttk.Button(btns, text="Start", command=self.on_start)
        self.btn_pause = ttk.Button(btns, text="Pause", command=self.on_pause, state="disabled")
        self.btn_resume = ttk.Button(btns, text="Resume", command=self.on_resume, state="disabled")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.btn_enable = ttk.Button(btns, text="Enable", command=self.on_enable)
        self.btn_clearfault = ttk.Button(btns, text="Clear Fault", command=self.on_clearfault)
        self.btn_enablegripper = ttk.Button(btns, text="Enable Gripper", command=self.on_enablegripper,state ="disabled")

        for i, b in enumerate((self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop, self.btn_enable, self.btn_clearfault, self.btn_enablegripper)):
                    b.grid(row=0, column=i, padx=6)

        # Status indicators
        ind = ttk.Labelframe(self, text="Status")
        ind.grid(row=6, column=0, columnspan=6, sticky="we", pady=6)
        self._mk_indicator(ind, "Program Request", self.program_request, 0)
        self._mk_indicator(ind, "Running", self.running, 1)
        self._mk_indicator(ind, "Paused", self.paused, 2)
        self._mk_indicator(ind, "Fault", self.fault, 3)

        # Progress + Log
        self.pbar = ttk.Progressbar(
            self, maximum=10, variable=self.progress, mode="determinate"
        )
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

        # STATUS log
        statusf = ttk.Labelframe(self, text="Status")
        statusf.grid(row=9, column=0, columnspan=6, sticky="nsew", pady=6)
        self.txt_status = tk.Text(statusf, height=8)
        self.txt_status.pack(fill="both", expand=True)

        # Stretch layout
        self.rowconfigure(9, weight=1)

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
        self.plan_name.set(f"Sequencer: {self.job.get()}")

    def on_start(self):
        self.progress.set(0)
        self.paused.set(False)
        self.fault.set(False)
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")

        # Create sequencer if not already
        if not hasattr(self, "sequencer"):
            print("no sequencer active -creating new one",flush = True)
            self.sequencer = Sequencer(
                backend=self.backend,
                config=SEQUENCER_PROFILES[self.job.get()],  # MachineA or MachineB
                log_cb=self._log,
                speed_fn=self.speed.get,
            )
        else:
            # Update to the selected machine profile dynamically
            print("Sequencer active, changing machine type",flush = True)
            self.sequencer.cfg = SEQUENCER_PROFILES[self.job.get()]

        # Start the tray sequence
        self.sequencer.start_tray()

    def on_pause(self):
        
        if hasattr(self, "sequencer"):
            self.sequencer.pause()

        self.backend.pause()
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="normal")        
        self.btn_stop.configure(state="normal")

    def on_resume(self):
        self.backend.resume()
        if hasattr(self, "sequencer"):
            self.sequencer.resume()


        self.btn_pause.configure(state="normal")
        self.btn_resume.configure(state="disabled")

    def on_stop(self):      

        if hasattr(self, 'sequencer'):
            threading.Thread(target=self.sequencer.stop, daemon=True).start()

        print("BACKEND STOP CALLED FROM APP ui",flush = True)
        threading.Thread(target=self.backend.stop, daemon=True).start()
        
        # existing UI state updates…
        self.paused.set(False)
        self.running.set(False)
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="disabled")        
        self.btn_start.configure(state="normal")        
        self.event_q.put((BackendEvents.LOG, " STOP pressed: motion stopped (software stop)"))

    def on_enable(self):
        threading.Thread(target=self.backend.enable, daemon=True).start()
        

    def on_clearfault(self):
        threading.Thread(target=self.backend.clear_fault, daemon=True).start()
        
    def on_disconnect(self):
        threading.Thread(target=self.backend.disconnect, daemon=True).start()

    def on_enablegripper(self):
        self._log("[ui] Enable Gripper pressed (backend wiring TBD)")
        threading.Thread(target=self.backend.enable_gripper, daemon=True).start()
    # -------- Event pump --------
    def _pump_events(self):
        try:
            while True:
                kind, msg = self.event_q.get_nowait()
                if hasattr(self, "sequencer"):
                    self.sequencer.on_backend_event(kind, msg)
                if kind == BackendEvents.PROGRAM_REQUEST:
                    self.program_request.set(bool(msg))
                elif kind == BackendEvents.RUNNING:
                    running = bool(msg)
                    self.running.set(running)
                    if running:
                        self.progress.set(0)
                    else:
                        # UI idle between plans or finished. If finished → auto-reset from UI level.
                        if hasattr(self, "sequencer"):
                            st = self.sequencer.get_state()  # {'slot': ..., 'step': ..., 'running': ...}
                            # Finished condition: thread not alive AND we've stepped past the last slot
                            if not st.get("running") and st.get("slot", 0) > self.sequencer.cfg.total_slots:
                                try:
                                    self.sequencer.reset()   # safe: worker thread is already dead
                                except Exception:
                                    pass

                        # (your existing button enable/disable logic below)
                        self.btn_start.configure(state="normal")
                
                elif kind == BackendEvents.STOPPED:
                    print("pump event * STOPPED",flush = True)
                    self.running.set(False)
                            
                elif kind == BackendEvents.PAUSED:
                    print("pump event * PAUSED",flush = True)
                    self.paused.set(bool(msg))
                    self.btn_stop.configure(state="normal") 
                
                elif kind == BackendEvents.FAULT:
                    is_fault = bool(msg)
                    self.fault.set(is_fault)
                    self.btn_stop.configure(state="normal")  # keep STOP available
                    if is_fault:
                        # Faulted: freeze motion controls (no auto actions)
                        self.running.set(False)
                        self.btn_start.configure(state="disabled")
                        self.btn_pause.configure(state="disabled")
                        self.btn_resume.configure(state="disabled")
                          
                    else:
                        # Not faulted: make Pause/Resume available as requested
                        self.btn_pause.configure(state="normal")
                        self.btn_resume.configure(state="normal")
                        
                        self.btn_start.configure(state="normal")
                        
                    
                elif kind == BackendEvents.LOG:
                    self._log(msg)
                
                elif kind == BackendEvents.STATUS:
                    self._log_status(msg)

                self.btn_enablegripper.configure(
                    state=("normal" if (not self.running.get() and not self.fault.get()) else "disabled")
                )       

                

        except queue.Empty:
            pass
        self.after(50, self._pump_events)

    def _log(self, text):
        self.txt.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")

        # Check if scrollbar is already at bottom
        if float(self.txt.yview()[1]) == 1.0:
            self.txt.see("end")

    def _log_status(self, text):
        self.txt_status.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.txt_status.see("end")
