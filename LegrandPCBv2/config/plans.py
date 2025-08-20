# Central registry of Elements plan names
# These must match exactly the names in your Flexiv controller plan list.

from dataclasses import dataclass

@dataclass(frozen=True)
class Plans:
	GripperModbus = "GripperModbus"
	davidt1 = "davidt1"
	Gripper_init = "Gripper_init"

# Optional: job-name → plan-name mapping used by the UI dropdown
PLAN_MAP = {
	"GripperModbus": Plans.GripperModbus,
	"davidt1": Plans.davidt1,
	"Gripper_init": Plans.Gripper_init,
}
