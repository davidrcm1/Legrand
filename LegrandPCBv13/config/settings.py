
from ..backend.sequencer import SequencerConfig

SEQUENCER_PROFILES = {
    "MachineA": SequencerConfig(
        total_slots=1,
        plan_open_machine="OpenMachine",
        plan_close_machine="CloseMachine",
        plan_pick_fmt="PickFromTray_{slot}",
        plan_place_fmt="PlaceToOutput_{slot}",
        plan_timeout_s=120.0,
        recover_timeout_s=45.0,
    ),
    "MachineB": SequencerConfig(
        total_slots=1,
        plan_open_machine="B_OpenMachine",
        plan_close_machine="B_CloseMachine",
        plan_pick_fmt="B_PickFromTray_{slot}",
        plan_place_fmt="B_PlaceToOutput_{slot}",
        plan_timeout_s=150.0,
        recover_timeout_s=60.0,
    ),
}

DEFAULT_SERIAL = "Rizon4-062691"

DEFAULT_IFACE = ""  # e.g., "192.168.2.50" or "eth0"

DEFAULT_JOB = "Gripper_init"
DEFAULT_SPEED = 100


DEFAULT_TRAYSIZE: int = 1