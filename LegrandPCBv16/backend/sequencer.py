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
    total_slots: int = 1
    # Micro-plan names (original naming the user wants to keep)
    plan_open_machine: str = "OpenMachine"
    plan_close_machine: str = "CloseMachine"
    plan_pick_fmt: str = "PickFromTray_{slot}"       # used in Insert phase
    plan_place_pass_fmt: str = "PlaceToOutputPass"     # used in Extract phase
    plan_place_fail_fmt: str = "PlaceToOutputFail"  
    # Timeouts
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
        self._fault = False
        self._plan_done_evt = threading.Event()
        self._fault_evt = threading.Event()
        self._stop_flag = False
        self._user_pause = False
        self._th: Optional[threading.Thread] = None
        self.test_done_evt = threading.Event()
        self.test_result = None  # "PASS"/"FAIL"/"DONE" etc.



        # ---- step plan (minimal flow using original field names) ----
        # Preamble (once)
        self.preamble = [
            lambda slot: self.cfg.plan_open_machine,
        ]

        # Insert phase (per slot): pick from tray -> (your plan should place into machine)
        self.insert_steps = [
            lambda slot: self.cfg.plan_pick_fmt.format(slot=slot),
        ]

        # Mid-cycle: close machine after inserts, then reopen before extracts
        self.mid_close = [lambda slot: self.cfg.plan_close_machine]
        self.mid_open  = [lambda slot: self.cfg.plan_open_machine]

        # Extract phase (per slot): remove from machine -> place to output
        self.extract_steps = [
            lambda slot: self.cfg.plan_place_fmt.format(slot=slot),
        ]

        # Postamble (once)
        self.postamble = [
            lambda slot: self.cfg.plan_close_machine,
        ]

    # -------- public API --------
    def start_tray(self, total_slots: Optional[int] = None):
        if total_slots is not None:
            self.cfg.total_slots = int(total_slots)
        if self._th and self._th.is_alive():
            self.log("Sequencer already running")
            return
        self._stop_flag = False
        self._th = threading.Thread(target=self._worker, daemon=True)
        self._th.start()
        self.log(f"Started (slot {self.current_slot}, step {self.current_step})")

    def stop(self):
        """Immediate: prevent new steps and break out of waits; reset will happen when worker exits."""
        self._stop_flag = True
        # Wake any waiters so _run_micro_plan loop can exit immediately
        self._plan_done_evt.set()
        self._fault_evt.set()
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
        """Logical reset only: rewind indices to start. No robot commands."""
        # refuse if worker still running (use Stop first)
        self.log("RESET SEQUENCER CALLED")

        # clear internal state
        self._fault = False
        self._plan_done_evt.clear()
        self._fault_evt.clear()
        self._user_pause = False
        self._stop_flag = False

        # rewind progress
        self.current_slot = 1
        self.current_step = 0
        self._preamble_done = False
        self.log("Sequencer reset: ready at slot 1 (CLOSE TRAY FIRST BEFORE CONTINUING)")

    # -------- internals --------
    def _worker(self):
        self.log(f"[SEQ] Worker alive: slot={self.current_slot}, step={self.current_step}, stop={self._stop_flag}")
        try:    
            # --- PREAMBLE ---
            if not self._preamble_done and not self._stop_flag:
                for step_fn in self.preamble:
                    if self._stop_flag:
                        self.log("Stop/Abort: requested during preamble")
                        break
                    self._wait_if_user_paused()
                    if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                        if self._stop_flag:
                            self.log("Stop/Abort during preamble; exiting")
                            return
                        if not self._recover():
                            self.log("Recovery failed during preamble; stopping")
                            return
                        if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                            self.log("Retry failed during preamble; giving up")
                            return
                self._preamble_done = True
            if self._stop_flag:
                self.log("Stop before slot loop; exiting")
                self._th = None
                return
            # --- PER-SLOT LOOP ---
            self.current_slot = 1
            while self.current_slot <= self.cfg.total_slots and not self._stop_flag:
                self._wait_if_user_paused()
                self.test_done_evt.clear()
                self.test_result = None

                # Pick
                for step_fn in self.insert_steps:
                    if self._stop_flag:
                        self.log("Stop/Abort during pick phase")
                        break
                    if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                        if self._stop_flag:
                            self.log("Stop/Abort during pick; exiting")
                            return
                        if not self._recover():
                            self.log("Recovery failed during pick; stopping")
                            return
                        if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                            self.log("Retry failed during pick; giving up")
                            return

                if self._stop_flag:
                    break
                # Close machine
                for step_fn in self.mid_close:
                    if self._stop_flag:
                        break
                    self._wait_if_user_paused()
                    if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                        if self._stop_flag: return
                        if not self._recover(): return
                        if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                            return
                
                
                if self._stop_flag:
                    break

                # ---- WAIT FOR TESTER RESULT HERE ----
                TEST_TIMEOUT_S = getattr(self.cfg, "test_timeout_s", 900.0)  # 15 min default
                self.log("Waiting for external tester result (PASS/FAIL/DONE)…")
                ok = self._wait_for_test_done(timeout_s=TEST_TIMEOUT_S)
                if not ok:
                    self.log("Tester did not signal completion within timeout → stopping")
                    self._stop_flag = True
                    break

                # Optional: log/use the verdict if you want to branch later
                self.log(f"Tester verdict: {self.test_result or 'UNKNOWN'}")

                # Per your spec: wait 2 seconds after result before opening the machine
                time.sleep(2.0)

                # Re-open machine
                for step_fn in self.mid_open:
                    if self._stop_flag:
                        break
                    self._wait_if_user_paused()
                    if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                        if self._stop_flag: return
                        if not self._recover(): return
                        if not self._run_micro_plan(step_fn(self.current_slot), self.cfg.plan_timeout_s):
                            return

                if self._stop_flag:
                    break

                # --- PLACE (STRICT PASS/FAIL) ---
                verdict = (self.test_result or "").upper()
                if verdict not in ("PASS", "FAIL"):
                    self.log(f"Invalid tester verdict '{self.test_result}'. Expected PASS or FAIL only.")
                    self._stop_flag = True
                    break

                plan_name = (
                    self.cfg.plan_place_pass_fmt if verdict == "PASS"
                    else self.cfg.plan_place_fail_fmt
                )

                if not isinstance(plan_name, str) or not plan_name.strip():
                    self.log(f"Place plan not configured for verdict {verdict} "
                            f"(check plan_place_pass_fmt / plan_place_fail_fmt in settings.py)")
                    self._stop_flag = True
                    break

                if not self._run_micro_plan(plan_name, self.cfg.plan_timeout_s):
                    if self._stop_flag:
                        self.log("Stop/Abort during place; exiting")
                        return
                    if not self._recover():
                        self.log("Recovery failed during place; stopping")
                        return
                    if not self._run_micro_plan(plan_name, self.cfg.plan_timeout_s):
                        self.log("Retry failed during place; giving up")
                        return

                self.current_slot += 1
            if self._stop_flag:
                self._th = None
                return

            # --- POSTAMBLE ---
            for step_fn in self.postamble:
                if self._stop_flag:
                    break
                self._wait_if_user_paused()
                if not self._run_micro_plan(step_fn(self.cfg.total_slots), self.cfg.plan_timeout_s):
                    if self._stop_flag: return
                    if not self._recover(): return
                    if not self._run_micro_plan(step_fn(self.cfg.total_slots), self.cfg.plan_timeout_s):
                        return
        finally:
            # Finished
            self.log("Sequencer HAS ENDED")
            self.reset()
            self._th = None




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
    

    def external_test_complete(self, verdict: str):
        self.test_result = (verdict or "").strip().upper()
        self.test_done_evt.set()
        self.log(f"External test result received: {self.test_result}")

    def _wait_for_test_done(self, timeout_s: float) -> bool:
        t0 = time.time()
        while not self._stop_flag:
            # honor pause button
            self._wait_if_user_paused()
            # event-based wait (non-busy)
            if self.test_done_evt.wait(timeout=0.1):
                return True
            if time.time() - t0 > timeout_s:
                return False
        return False