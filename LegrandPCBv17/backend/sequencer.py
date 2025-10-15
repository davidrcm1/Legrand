# backend/sequencer.py
from __future__ import annotations
import threading
import time
from dataclasses import dataclass
from typing import Optional, Any, Callable

try:
    from .events import BackendEvents
except Exception:
    class BackendEvents:
        RUNNING = "RUNNING"
        STOPPED = "STOPPED"
        FAULT = "FAULT"
        LOG = "LOG"


@dataclass
class SequencerConfig:
    total_slots1: int = 1
    # Micro-plan names (original naming the user wants to keep)
    plan_open_machine1: str = "OpenMachine"
    plan_close_machine1: str = "CloseMachine"
    plan_pick_fmt1: str = "PickFromTray_{slot}"       # used in Insert phase
    plan_place_pass_fmt1: str = "PlaceToOutputPass"     # used in Extract phase
    plan_place_fail_fmt1: str = "PlaceToOutputFail"  

    #machine 2
    total_slots2: int = 1
    plan_open_machine2: str = "OpenMachine"
    plan_close_machine2: str = "CloseMachine"
    plan_pick_fmt2: str = "PickFromTray_{slot}"       # used in Insert phase
    plan_place_pass_fmt2: str = "PlaceToOutputPass"     # used in Extract phase
    plan_place_fail_fmt2: str = "PlaceToOutputFail"   
    
    # Timeouts (global for all testers)
    plan_timeout_s: float = 120.0
    recover_timeout_s: float = 45.0
    test_timeout_s: float = 900.0


class Sequencer:


    """
    Minimal step sequencer:
    - One-time preamble (OpenMachine), then per-slot steps: Pick → Insert → Close → Open → Remove → Place
    - On FAULT or timeout: Clear → Enable → (optional) SafeRetreat → (optional) OpenGripper, then retry SAME step
    - No sensors/reconciliation; progress only advances on clean finish
    """
    def __init__(
        self,
        backend,
        config: SequencerConfig = SequencerConfig(),
        log_cb: Optional[Callable[[str], None]] = None,
        speed_fn: Optional[Callable[[], int]] = None,  # <- use UI slider
    ):
        self.backend = backend
        self.cfg = config
        self.log_cb = log_cb
        self.speed_fn = speed_fn

        # progress tracking
        self.current_slot = 1
        self.current_step = 0
        self._preamble_done = False

        # control/events
        self._th = None
        self._fault = False
        self._plan_done_evt = threading.Event()
        self._fault_evt = threading.Event()
        self._stop_flag = False
        self._user_pause = False    
        

        # Thread and variable for each machine
        self.tester_done_evt1 = threading.Event()
        self._serial1_th = None
        self._halt_serial1 = None
        self.tester_commready1 = False
        self.tester_result1 = None  # "PASS"/"FAIL"/"DONE" etc.
        self.tester_operating1 = False # True if tester has pcb inserted and running tests
        self.tester_loaded1 = False # true if pcb is currently in machine.
        self.awaiting_result1 = False

        self.tester_done_evt2 = threading.Event()
        self._serial2_th = None
        self._halt_serial2 = None
        self.tester_commready2 = False
        self.tester_result2 = None  # "PASS"/"FAIL"/"DONE" etc.
        self.tester_operating2 = False # True if tester has pcb inserted and running tests
        self.tester_loaded2 = False
        self.awaiting_result2 = False
        




        # ---- step plan (minimal flow using original field names) ----
        # — Picks (slot-indexed) —
        self.plan_pick1 = lambda slot: self.cfg.plan_pick_fmt1.format(slot=slot)
        self.plan_pick2 = lambda slot: self.cfg.plan_pick_fmt2.format(slot=slot)

        # — Fixed actions (no indexing) —
        self.plan_close1 = self.cfg.plan_close_machine1
        self.plan_open1  = self.cfg.plan_open_machine1
        self.plan_close2 = self.cfg.plan_close_machine2
        self.plan_open2  = self.cfg.plan_open_machine2

        self.plan_place_pass1 = self.cfg.plan_place_pass_fmt1
        self.plan_place_fail1 = self.cfg.plan_place_fail_fmt1
        self.plan_place_pass2 = self.cfg.plan_place_pass_fmt2
        self.plan_place_fail2 = self.cfg.plan_place_fail_fmt2



        # --- Start threads for machines ---
        try:
            self._serial1_th = threading.Thread(
                target=self._serial_worker, args=(1,), daemon=True
            )
            self._serial1_th.start()
            self.log("[M1] listener started")
        except Exception as e:
            self.log(f"[M1] listener start error: {e}")

        try:
            self._serial2_th = threading.Thread(
                target=self._serial_worker, args=(2,), daemon=True
            )
            self._serial2_th.start()
            self.log("[M2] listener started")
        except Exception as e:
            self.log(f"[M2] listener start error: {e}")



    # -------- public API --------
    def start_seq_worker(self, total_slots: Optional[int] = None):
        if total_slots is not None:
            self.cfg.total_slots1 = int(total_slots)
            self.cfg.total_slots2 = int(total_slots)
        if self._th and self._th.is_alive():
            self.log("Sequencer already running")
            return
        self._stop_flag = False
        self._th = threading.Thread(target=self._worker, daemon=True)
        self._th.start()

        try:
            self.start_listener(1)
        except Exception as _e:
            self.log(f"[M1] listener start error: {_e}")
        try:
            self.start_listener(2)
        except Exception as _e:
            self.log(f"[M2] listener start error: {_e}")

        self.log(f"Started (slot {self.current_slot}, step {self.current_step})")

    def stop(self):
        """Immediate: prevent new steps and break out of waits; reset will happen when worker exits."""
        self._stop_flag = True
        # Wake any waiters so _run_micro_plan loop can exit immediately
        self._plan_done_evt.set()
        self._fault_evt.set()
        try: self.stop_listener(1)
        except Exception: pass
        try: self.stop_listener(2)
        except Exception: pass
 
        self.log("Sequencer Stop requested - breaking out")
        
        
    def log(self, msg: str):
        """Safe logger wrapper for sequencer"""
        if self.log_cb:
            self.log_cb(msg)
        else:
            print(msg, flush=True)

    def pause(self):
        self._user_pause = True

    def resume(self):
        self._user_pause = False

    def on_backend_event(self, ev: str, payload: Any):
        if ev == BackendEvents.FAULT:
            self._fault = bool(payload)
            if self._fault:
                self._fault_evt.set()
            else:
                self._fault_evt.clear()
        elif ev == BackendEvents.STOPPED:
            self._plan_done_evt.set()

    def get_state(self):
        return {
            "slot": self.current_slot,
            "step": self.current_step,
            "running": self._th.is_alive() if self._th else False,
            "preamble_done": self._preamble_done,
        }

    def reset(self):
        self.log("RESET SEQUENCER CALLED")

        self._fault = False
        self._plan_done_evt.clear()
        self._fault_evt.clear()
        self._user_pause = False
        self._stop_flag = False

        # per-machine state
        self.tester_done_evt1.clear()
        self.tester_done_evt2.clear()
        self.tester_result1 = None
        self.tester_result2 = None
        self.tester_operating1 = False
        self.tester_operating2 = False
        self.tester_loaded1 = False
        self.tester_loaded2 = False
        self.current_slot1 = 1
        self.current_slot2 = 1

        # legacy single-machine counters (kept for get_state())
        self.current_slot = 1
        self.current_step = 0
        self._preamble_done = False

        self.log("Sequencer reset: Reload Trays and Open Machines")


    # -------- internals --------
    def _worker(self):
        self.log(f"[SEQ] Worker alive: stop={self._stop_flag}")

        self._test_comms()
        self.log(f"[SEQ] Comm Ready Status → M1: {self.tester_commready1}, M2: {self.tester_commready2}")
        self.log(f"[SEQ] Tray Sizes → M1: {self.cfg.total_slots1}, M2: {self.cfg.total_slots2}")
        
        # Persist per-machine slot indices across the loop
        self.current_slot1 = getattr(self, "current_slot1", 1)
        self.current_slot2 = getattr(self, "current_slot2", 1)



        
        try:
            while not self._stop_flag:
                # honor pause
                self._wait_if_user_paused()
                if self._stop_flag:
                    break

                progressed = False  

                # ---------- absorb tester completions (non-blocking) ----------
                # If external listeners set "done", clear and mark operating False.
                if self.tester_done_evt1.is_set():
                    self.tester_done_evt1.clear()
                    self.tester_operating1 = False  # test finished; result should already be set
                if self.tester_done_evt2.is_set():
                    self.tester_done_evt2.clear()
                    self.tester_operating2 = False

                # ---------- MACHINE 1: UNLOAD on result ----------
                if (self.tester_commready1 and
                    not progressed and
                    not self.tester_operating1 and
                    self.tester_loaded1 and
                    isinstance(self.tester_result1, str)):

                    #OPEN MACHINE
                    if not self._run_micro_plan(self.plan_open1, self.cfg.plan_timeout_s):
                        break

                    verdict = self.tester_result1.strip().upper()
                    if verdict == "PASS":
                        plan = self.plan_place_pass1
                    elif verdict == "FAIL":
                        plan = self.plan_place_fail1
                    else:
                        self.log(f"[M1] Invalid test result: {self.tester_result1}")
                        break

                    if not self._run_micro_plan(plan, self.cfg.plan_timeout_s):
                        # stop/fault/timeout -> exit worker
                        break

                    # After placing to pass/fail bins, clear load & result
                    self.tester_loaded1 = False
                    self.tester_result1 = None
                    progressed = True

                # ---------- MACHINE 1: LOAD next PCB if idle & slots remain ----------
                if (self.tester_commready1 and ## use comm ready as a condition to action plans....
                    not progressed and
                    not self.tester_operating1 and
                    not self.tester_loaded1 and
                    self.current_slot1 <= self.cfg.total_slots1):

                    plan = self.plan_pick1(self.current_slot1)
                    if not self._run_micro_plan(plan, self.cfg.plan_timeout_s):
                        break


                    #  Close tester to start the test
                    if not self._run_micro_plan(self.plan_close1, self.cfg.plan_timeout_s):
                        break
                    
                    # start waiting for tester results
                    self.awaiting_result1 = True

                    self.current_slot1 += 1
                    self.tester_operating1 = True
                    self.tester_loaded1 = True
                    progressed = True

                # ---------- MACHINE 2: UNLOAD on result ----------
                if (self.tester_commready2 and
                    not progressed and
                    not self.tester_operating2 and
                    self.tester_loaded2 and
                    isinstance(self.tester_result2, str)):

                    if not self._run_micro_plan(self.plan_open2, self.cfg.plan_timeout_s):
                        break

                    verdict = self.tester_result2.strip().upper()
                    if verdict == "PASS":
                        plan = self.plan_place_pass2
                    elif verdict == "FAIL":
                        plan = self.plan_place_fail2
                    else:
                        self.log(f"[M2] Invalid test result: {self.tester_result2}")
                        break

                    if not self._run_micro_plan(plan, self.cfg.plan_timeout_s):
                        break

                    self.tester_loaded2 = False
                    self.tester_result2 = None
                    progressed = True

                # ---------- MACHINE 2: LOAD next PCB if idle & slots remain ----------
                if (self.tester_commready2 and
                    not progressed and
                    not self.tester_operating2 and
                    not self.tester_loaded2 and
                    self.current_slot2 <= self.cfg.total_slots2):

                    plan = self.plan_pick2(self.current_slot2)
                    if not self._run_micro_plan(plan, self.cfg.plan_timeout_s):
                        break

                    #  Close tester to start the test
                    if not self._run_micro_plan(self.plan_close2, self.cfg.plan_timeout_s):
                        break
                    

                    #start waiting for results
                    self.awaiting_result2 = True

                    self.current_slot2 += 1
                    self.tester_operating2 = True
                    self.tester_loaded2 = True
                    progressed = True

                # ---------- Exit when both machines are fully done ----------
                m1_done = (self.current_slot1 > self.cfg.total_slots1) and (not self.tester_loaded1) and (not self.tester_operating1)
                m2_done = (self.current_slot2 > self.cfg.total_slots2) and (not self.tester_loaded2) and (not self.tester_operating2)
                if m1_done and m2_done:
                    self.log("[SEQ] All slots processed for both machines — exiting.")
                    break

                # If nothing to do this tick, idle briefly
                if not progressed:
                    time.sleep(0.02)

        finally:
            self.log("Sequencer HAS ENDED")
            try: self.stop_listener(1)
            except Exception: pass
            try: self.stop_listener(2)
            except Exception: pass
            self.reset()
            self._th = None


    #thread for listening for both machines simulmatenously? or do we need seperate threads
    def external_test_complete(self, machine_id: int, verdict: str):
        v = (verdict or "").strip().upper()
        v = "PASS" if "PASS" in v else ("FAIL" if "FAIL" in v else v)

        if machine_id == 1:
            if not self.awaiting_result1:
                self.log("[M1] Ignored result (not awaiting)")
                return
            self.awaiting_result1 = False
            self.tester_result1 = v
            self.tester_done_evt1.set()
            self.tester_operating1 = False
            self.log(f"[M1] External test result: {v}")
        elif machine_id == 2:
            if not self.awaiting_result2:
                self.log("[M2] Ignored result (not awaiting)")
                return
            self.awaiting_result2 = False
            self.tester_result2 = v
            self.tester_done_evt2.set()
            self.tester_operating2 = False
            self.log(f"[M2] External test result: {v}")


    def _wait_if_user_paused(self):
        while self._user_pause and not self._stop_flag:
            time.sleep(0.05)

    def _run_micro_plan(self, plan_name: str, timeout_s: float) -> bool:

        self.log(f"→ Start plan: {plan_name}")
        self._plan_done_evt.clear()
        self._fault_evt.clear()
        try:
            speed = int(self.speed_fn())
            self.backend.start_plan(plan_name, speed)  # <-- pass speed
        except Exception as e:
            self.log(f"start_plan error: {e}")
            return False

        t0 = time.time()
        while True:
            if self._fault_evt.is_set():
                self.log(f"Plan '{plan_name}' interrupted by FAULT")
                return False
            if self._plan_done_evt.is_set():
                if self._stop_flag:
                    self.log(f"<- Plan finished (Stop Requested): {plan_name}")
                    return False
                self.log(f"← Plan finished: {plan_name}")
                return True
            if time.time() - t0 > timeout_s:
                self.log(f"Plan '{plan_name}' timeout ({timeout_s:.0f}s)")
                try:
                    self.backend.stop()
                except Exception:
                    pass
                return False
            if self._stop_flag:
                # graceful stop: let backend.stop() be called by on_stop or caller
                return False
            time.sleep(0.05)

    def _recover(self) -> bool:
        # No automatic actions: do NOT clear faults, do NOT enable, do NOT move.
        self.log("Recovery blocked: requires human intervention (no auto clear / no auto enable).")
        return False
    


    def start_listener(self, machine_id: int):
        import threading, queue
        if machine_id == 1:
            if not (self._serial1_th and self._serial1_th.is_alive()):
                import threading
                self._halt_serial1 = threading.Event()
                self._serial1_th = threading.Thread(target=self._serial_worker, args=(1,), daemon=True)
                self._serial1_th.start()
                self.log("[M1] Serial listener started")
        else:
            if not (self._serial2_th and self._serial2_th.is_alive()):
                self._halt_serial2 = threading.Event()
                self._serial2_th = threading.Thread(target=self._serial_worker, args=(2,), daemon=True)
                self._serial2_th.start()
                self.log("[M2] Serial listener started")

    def stop_listener(self, machine_id: int):
        if machine_id == 1:
            if self._halt_serial1: self._halt_serial1.set()
            self.log("[M1] Serial listener stopped")
        else:
            if self._halt_serial2: self._halt_serial2.set()
            self.log("[M2] Serial listener stopped")


    def _serial_worker(self, machine_id: int):
        try:
            import serial
            from ..config.settings import SERIAL_PORT1, SERIAL_PORT2, SERIAL_BAUD

            port = SERIAL_PORT1 if machine_id == 1 else SERIAL_PORT2
            halt_evt = self._halt_serial1 if machine_id == 1 else self._halt_serial2

            self.log(f"[serial M{machine_id}] opening {port} @ {SERIAL_BAUD}…")
            ser = serial.Serial(port=port, baudrate=SERIAL_BAUD, timeout=0.2)
            if machine_id == 1:
                self._serial1_handle = ser
            else:
                self._serial2_handle = ser

            # listener loop
            while halt_evt and not halt_evt.is_set():
                ...
                # TODO: set msg from serial input
                # e.g., line = ser.readline().decode(errors="ignore").strip()
                # msg = line
                if 'msg' in locals():
                    self.external_test_complete(machine_id, msg)

        except Exception as e:
            self.log(f"[serial M{machine_id}] open/loop error: {e}")

        finally:
            try:
                if 'ser' in locals() and ser:
                    ser.close()
            except Exception:
                pass
            if machine_id == 1:
                self._serial1_handle = None
            else:
                self._serial2_handle = None

    def _test_comms(self):
        """Ping each tester to verify serial connectivity."""
        import serial
        def ping_serial(mid: int, ser: serial.Serial) -> bool:
            """Return True if ping successful, False otherwise."""
            try:
                if ser is None or not ser.is_open:
                    return False
                ser.write(b"PING\n")      # small harmless message
                ser.flush()
                return True
            except (OSError, serial.SerialException) as e:
                self.log(f"[M{mid}] ping failed: {e}")
                return False

        # Machine 1
        ser1 = getattr(self, "_serial1_handle", None)
        ok1  = ping_serial(1, ser1)
        self.tester_commready1 = ok1

        # Machine 2
        ser2 = getattr(self, "_serial2_handle", None)
        ok2  = ping_serial(2, ser2)
        self.tester_commready2 = ok2

        self.log(f"[SEQ] Comm check → M1: {ok1}, M2: {ok2}")