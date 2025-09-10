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
    total_slots: int = 6
    # Micro-plan names
    plan_open_machine: str = "OpenMachine"
    plan_close_machine: str = "CloseMachine"
    plan_insert: str = "InsertIntoFixture"
    plan_remove: str = "RemoveFromFixture"
    plan_pick_fmt: str = "PickFromTray_{slot}"
    plan_place_fmt: str = "PlaceToOutput_{slot}"
    # Optional recovery helpers
    plan_safe_retreat: Optional[str] = None
    plan_open_gripper: Optional[str] = None
    # Timeouts
    plan_timeout_s: float = 120.0
    recover_timeout_s: float = 45.0


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
        self.log = log_cb or (lambda msg: print(f"[Sequencer] {msg}"))
        self._speed_fn = speed_fn or (lambda: 50)

        # progress
        self.current_slot = 1
        self.current_step = 0  # index into per_slot_steps
        self._preamble_done = False

        # control/events
        self._fault = False
        self._plan_done_evt = threading.Event()
        self._fault_evt = threading.Event()
        self._stop_flag = False
        self._user_pause = False
        self._th: Optional[threading.Thread] = None

        # steps
        self.preamble = [
            lambda slot: self.cfg.plan_open_machine,  # run ONCE at the very start
        ]
        self.per_slot_steps = [
            lambda slot: self.cfg.plan_pick_fmt.format(slot=slot),
            lambda slot: self.cfg.plan_insert,
            lambda slot: self.cfg.plan_close_machine,
            # (External test happens here if any)
            lambda slot: self.cfg.plan_open_machine,
            lambda slot: self.cfg.plan_remove,
            lambda slot: self.cfg.plan_place_fmt.format(slot=slot),
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
        self.log("Stop requested - breaking out")


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
        if self._th and self._th.is_alive():
            self.log("Reset refused: sequencer is running. Press STOP first.")
            return

        # clear internal state
        self._th = None
        self._fault = False
        self._plan_done_evt.clear()
        self._fault_evt.clear()
        self._user_pause = False
        self._stop_flag = False

        # rewind progress
        self.current_slot = 1
        self.current_step = 0
        self._preamble_done = False
        self.log("Sequencer reset: ready at slot 1 (preamble not done)")

    # -------- internals --------
    def _worker(self):
        # 1) Preamble once
        if not self._preamble_done and not self._stop_flag:
            for step_fn in self.preamble:
                if self._stop_flag:
                    self.log("Stop/Abort: Requested (during preamble)")
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
                        self.log("Preamble step failed again; stopping")
                        return
            self._preamble_done = True

        # 2) Per-slot loop
        while not self._stop_flag and self.current_slot <= self.cfg.total_slots:
            self._wait_if_user_paused()
            plan_name = self.per_slot_steps[self.current_step](self.current_slot)
            ok = self._run_micro_plan(plan_name, self.cfg.plan_timeout_s)

            # If stop was requested at any time, leave immediately
            if self._stop_flag:
                self.log("Stop/Abort: Requested")
                break

            if ok:
                # NEW: honour stop right after clean finish (before advancing)
                if self._stop_flag:
                    self.log("Stop requested after plan finish; exiting")
                    break

                self.current_step += 1
                if self.current_step >= len(self.per_slot_steps):
                    self.current_step = 0
                    self.log(f"Completed slot {self.current_slot}")
                    self.current_slot += 1
                continue
            else:
                if self._stop_flag:
                    self.log("Stop/Abort requested; exiting")
                    break
                if not self._recover():
                    self.log("Recovery failed; stopping")
                    break

        self.log("Sequencer finished")

        # Reset only *after* the worker exits, iff stop was requested
        if self._stop_flag:
            self.reset()

    def _wait_if_user_paused(self):
        while self._user_pause and not self._stop_flag:
            time.sleep(0.05)

    def _run_micro_plan(self, plan_name: str, timeout_s: float) -> bool:
        self.log(f"→ Start plan: {plan_name}")
        self._plan_done_evt.clear()
        self._fault_evt.clear()
        try:
            speed = int(self._speed_fn())
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

