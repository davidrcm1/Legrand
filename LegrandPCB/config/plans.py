# Central registry of Elements plan IDs (Settings > Project ID Editor).
# Fill these with the actual IDs from your Elements project.

from dataclasses import dataclass

@dataclass(frozen=True)
class Plans:
    GripperModbus = 1
    davidt1 = 2
    Gripper_Init = 3
    

# Optional: job-name → plan-id mapping used by the UI dropdown
PLAN_MAP = {
    "GripperModbus": Plans.GripperModbus,
    "davidt1":  Plans.davidt1,
    "Gripper_Init":  Plans.Gripper_Init,
    
}


PROJECT_TO_PLAN_NAME = {
    1: "GripperModbus",
    2: "davidt1",
    3: "Gripper_Init",
}
