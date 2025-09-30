
from ..backend.sequencer import SequencerConfig

SEQUENCER_PROFILES = {
    "MachineA": SequencerConfig(
        total_slots=1,
        plan_open_machine="OpenMachine",
        plan_close_machine="CloseMachine",
        plan_pick_fmt="PickFromTray_{slot}",
        plan_place_pass_fmt="A_PlaceToPass",    # FIXED
        plan_place_fail_fmt="A_PlaceToFail",    # FIXED
    ),
    "MachineB": SequencerConfig(
        total_slots=1,
        plan_open_machine="B_OpenMachine",
        plan_close_machine="B_CloseMachine",
        plan_pick_fmt="B_PickFromTray_{slot}",
        plan_place_pass_fmt="B_PlaceToPass",      # ADDED
        plan_place_fail_fmt="B_PlaceToFail",      # ADDED
    ),
}

DEFAULT_SERIAL = "Rizon4-062691"

DEFAULT_IFACE = ""  # e.g., "192.168.2.50" or "eth0"

DEFAULT_JOB = "Gripper_init"
DEFAULT_SPEED = 100

DEFAULT_TRAYSIZE: int = 1


# --- Serial link to tester ---
SERIAL_PORT = "/dev/ttyUSB0"      # e.g. "COM5" on Windows, "/dev/ttyUSB0" on Linux
SERIAL_BAUD = 9600

