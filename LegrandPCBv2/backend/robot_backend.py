import queue
import threading
import time

from .events import BackendEvents


class RobotBackend:
    """
    Flexiv backend.
    - connect(): establishes RDK session (no enable/motion yet).
    - background monitor publishes FAULT/RUNNING and lightweight status logs.
    - start_plan(): executes a plan by NAME only.
    """
    def __init__(self, event_q: queue.Queue, serial_getter, iface_getter):
        self.q = event_q
        self.get_sn = serial_getter
        self.get_if = iface_getter
        self.robot = None
        self.connected = False

        # monitor thread
        self._mon_th = None
        self._halt_mon = threading.Event()

    def _emit(self, kind, msg=None):
        self.q.put((kind, msg))

    def connect(self):
        try:
            try:
                import flexivrdk
            except Exception as e:
                raise RuntimeError(f"flexivrdk not available: {e}")

            sn = (self.get_sn() or "").strip()
            if not sn:
                raise RuntimeError("Robot serial is empty (e.g., Rizon4-062691)")

            iface_txt = (self.get_if() or "").strip()
            ifaces = [s.strip() for s in iface_txt.split(",") if s.strip()] or None

            # Creating Robot establishes the session with the controller
            self.robot = flexivrdk.Robot(sn, ifaces) if ifaces else flexivrdk.Robot(sn)
            self.connected = True
            self._emit(
                BackendEvents.LOG,
                f"[rdk] Connected to robot {sn}" + (f" via {ifaces}" if ifaces else "")
            )

            # Optional lightweight probe (read-only, safe)
            try:
                _ = self.robot.plan_list()
                self._emit(BackendEvents.LOG, "[rdk] Link OK (plan list queried)")
            except Exception as e:
                self._emit(BackendEvents.LOG, f"[rdk] Link check warn: {e}")

            # start background monitor
            self._start_monitor()

        except Exception as e:
            self.connected = False
            self._emit(BackendEvents.LOG, f"[rdk] ERROR: {e}")
            self._emit(BackendEvents.FAULT, True)

    # ---- Background monitor (state/fault/running) ----
    def _start_monitor(self):
        if self._mon_th and self._mon_th.is_alive():
            return
        self._halt_mon.clear()
        self._mon_th = threading.Thread(target=self._monitor, daemon=True)
        self._mon_th.start()

    def _monitor(self):
        # Poll ~10 Hz. Keep it light: only cheap calls.
        while not self._halt_mon.is_set():
            try:
                if not self.connected or self.robot is None:
                    time.sleep(0.1)
                    continue

                # 1) Fault check
                try:
                    if self.robot.fault():
                        self._emit(BackendEvents.FAULT, True)
                        # Optional: fetch controller log text if available
                        try:
                            msg = self.robot.mu_log()
                            if msg:
                                self._emit(BackendEvents.LOG, f"[rdk] {msg}")
                        except Exception:
                            pass
                        time.sleep(0.2)
                        continue
                except Exception as e:
                    self._emit(BackendEvents.LOG, f"[rdk] fault() check error: {e}")

                # 2) Motion / running state
                running = False
                try:
                    info = self.robot.plan_info()
                    if info and getattr(info, "pt_name", None):
                        running = True
                except Exception:
                    pass

                try:
                    if hasattr(self.robot, "stopped"):
                        running = running or (not self.robot.stopped())
                except Exception:
                    pass

                self._emit(BackendEvents.RUNNING, running)

                # 3) (Optional) Operational status breadcrumbs (throttled ~1s)
                try:
                    status = self.robot.operational_status()
                    if int(time.time() * 10) % 10 == 0:
                        self._emit(BackendEvents.LOG, f"[rdk] status={status}")
                except Exception:
                    pass

            except Exception as e:
                self._emit(BackendEvents.LOG, f"[rdk] monitor error: {e}")

            time.sleep(0.1)

    # ---- Lifecycle ----
    def disconnect(self):
        # Stop monitor; add explicit RDK close calls here if needed.
        self._halt_mon.set()
        self._emit(BackendEvents.LOG, "[rdk] disconnect(): not implemented yet")

    # ---- Motion / Plans ----
    def start_plan(self, plan_name: str, speed: int):
        """
        Execute a plan by NAME only.

        Steps (mirrors tutorial):
          1) Clear fault (optional) and ensure robot is enabled & operational
          2) Switch to NRT_PLAN_EXECUTION
          3) Set velocity scale
          4) ExecutePlan(<plan_name>, True)
          5) Monitor busy() and emit plan_info
        """
        if not self.connected or self.robot is None:
            self._emit(BackendEvents.LOG, "[rdk] Not connected")
            self._emit(BackendEvents.FAULT, True)
            return

        if not isinstance(plan_name, str) or not plan_name.strip():
            self._emit(BackendEvents.LOG, "[rdk] start_plan(): plan_name must be a non-empty string")
            self._emit(BackendEvents.FAULT, True)
            return
        plan_name = plan_name.strip()

        try:
            import flexivrdk
            mode = flexivrdk.Mode
        except Exception as e:
            self._emit(BackendEvents.LOG, f"[rdk] flexivrdk import error: {e}")
            self._emit(BackendEvents.FAULT, True)
            return

        try:
            # Clear fault if present
            try:
                if self.robot.fault():
                    self._emit(BackendEvents.LOG, "[rdk] Fault present, attempting ClearFault() …")
                    if not self.robot.ClearFault():
                        self._emit(BackendEvents.LOG, "[rdk] Fault cannot be cleared")
                        self._emit(BackendEvents.FAULT, True)
                        return
                    self._emit(BackendEvents.LOG, "[rdk] Fault cleared")
            except Exception as e:
                self._emit(BackendEvents.LOG, f"[rdk] fault/ClearFault warn: {e}")

            # Enable and wait operational
            if not self.robot.operational():
                self._emit(BackendEvents.LOG, "[rdk] Enabling robot … (release E‑stop if needed)")
                self.robot.Enable()
                t0 = time.time()
                while not self.robot.operational():
                    if self.robot.fault():
                        self._emit(BackendEvents.LOG, "[rdk] Fault occurred while enabling")
                        self._emit(BackendEvents.FAULT, True)
                        return
                    if time.time() - t0 > 30.0:
                        self._emit(BackendEvents.LOG, "[rdk] Timeout waiting for operational()")
                        self._emit(BackendEvents.FAULT, True)
                        return
                    time.sleep(0.5)
                self._emit(BackendEvents.LOG, "[rdk] Robot is now operational")

            # Switch to plan execution mode
            try:
                self.robot.SwitchMode(mode.NRT_PLAN_EXECUTION)
                self._emit(BackendEvents.LOG, "[rdk] Switched to NRT_PLAN_EXECUTION")
            except Exception as e:
                self._emit(BackendEvents.LOG, f"[rdk] SwitchMode failed: {e}")
                self._emit(BackendEvents.FAULT, True)
                return

            # Velocity scaling (1..100)
            try:
                vel = max(1, min(100, int(speed)))
                self.robot.SetVelocityScale(vel)
                self._emit(BackendEvents.LOG, f"[rdk] Velocity scale set to {vel}%")
            except Exception as e:
                self._emit(BackendEvents.LOG, f"[rdk] SetVelocityScale warn: {e}")

            # Optional: validate plan name against controller list
            try:
                plans = list(self.robot.plan_list())
                self._emit(BackendEvents.LOG, f"[rdk] Plans: {plans}")
                if plans and plan_name not in plans:
                    self._emit(BackendEvents.LOG, f"[rdk] Plan '{plan_name}' not found in controller")
                    self._emit(BackendEvents.FAULT, True)
                    return
            except Exception as e:
                self._emit(BackendEvents.LOG, f"[rdk] plan_list() warn: {e}")
                # continue anyway; ExecutePlan by name may still succeed

            # Execute by NAME (allow continue if program exits)
            self.robot.ExecutePlan(plan_name, True)
            self._emit(BackendEvents.LOG, f"[rdk] Executing plan by name: '{plan_name}'")
            self._emit(BackendEvents.RUNNING, True)

            # Watch busy() and emit plan_info
            def _watch_busy():
                try:
                    while True:
                        if self.robot.fault():
                            self._emit(BackendEvents.LOG, "[rdk] Fault during plan execution")
                            self._emit(BackendEvents.FAULT, True)
                            self._emit(BackendEvents.RUNNING, False)
                            self._emit(BackendEvents.STOPPED, True)
                            return
                        if not self.robot.busy():
                            self._emit(BackendEvents.LOG, "[rdk] Plan completed")
                            self._emit(BackendEvents.RUNNING, False)
                            self._emit(BackendEvents.STOPPED, True)
                            return
                        try:
                            pi = self.robot.plan_info()
                            if pi:
                                self._emit(
                                    BackendEvents.LOG,
                                    f"[rdk] plan_info: assigned={getattr(pi,'assigned_plan_name',None)}, "
                                    f"pt={getattr(pi,'pt_name',None)}, node={getattr(pi,'node_name',None)}, "
                                    f"vel={getattr(pi,'velocity_scale',None)}, "
                                    f"wait_step={getattr(pi,'waiting_for_step',None)}"
                                )
                        except Exception:
                            pass
                        time.sleep(1.0)
                except Exception as e:
                    self._emit(BackendEvents.LOG, f"[rdk] busy() watcher error: {e}")
                finally:
                    self._emit(BackendEvents.RUNNING, False)

            threading.Thread(target=_watch_busy, daemon=True).start()

        except Exception as e:
            self._emit(BackendEvents.LOG, f"[rdk] Execute plan error: {e}")
            self._emit(BackendEvents.FAULT, True)

    def pause(self):
        if not self.connected or self.robot is None:
            self._emit(BackendEvents.LOG, "[rdk] pause(): not connected")
            return
        try:
            self.robot.PausePlan(True)
            self._emit(BackendEvents.PAUSED, True)
            self._emit(BackendEvents.LOG, "[rdk] Plan paused")
        except Exception as e:
            self._emit(BackendEvents.LOG, f"[rdk] PausePlan failed: {e}")
            self._emit(BackendEvents.FAULT, True)

    def resume(self):
        if not self.connected or self.robot is None:
            self._emit(BackendEvents.LOG, "[rdk] resume(): not connected")
            return
        try:
            self.robot.PausePlan(False)
            self._emit(BackendEvents.PAUSED, False)
            self._emit(BackendEvents.LOG, "[rdk] Plan resumed")
        except Exception as e:
            self._emit(BackendEvents.LOG, f"[rdk] Resume (PausePlan False) failed: {e}")
            self._emit(BackendEvents.FAULT, True)

    def stop(self):
        if not self.connected or self.robot is None:
            self._emit(BackendEvents.LOG, "[rdk] stop(): not connected")
            return
        try:
            self.robot.Stop()
            self._emit(BackendEvents.RUNNING, False)
            self._emit(BackendEvents.STOPPED, True)
            self._emit(BackendEvents.LOG, "[rdk] Stop requested")
        except Exception as e:
            self._emit(BackendEvents.LOG, f"[rdk] Stop failed: {e}")
            self._emit(BackendEvents.FAULT, True)

