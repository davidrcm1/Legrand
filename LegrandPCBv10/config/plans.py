# Central registry of Elements plan names
# These must match exactly the names in your Flexiv controller plan list.

from dataclasses import dataclass

@dataclass(frozen=True)
class Plans:
	trayopen = "trayopen"
	Placedowntest = "Placedowntest"
	Gripper_init = "Gripper_init"
	

# Optional: job-name → plan-name mapping used by the UI dropdown
PLAN_MAP = {
	"trayopen": Plans.trayopen,
	"Placedowntest": Plans.Placedowntest,
	"Gripper_init": Plans.Gripper_init,
	
}
