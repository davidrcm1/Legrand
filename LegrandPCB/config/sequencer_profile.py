from ..backend.sequencer import SequencerConfig

SEQUENCER_PROFILES = {
    # Machine a + b
    "Setup 1": SequencerConfig(
        #machine 1
        total_slots1=3,
        plan_open_machine1="OpenMachine",
        plan_close_machine1="CloseMachine",
        plan_pick_fmt1="PickFromTray_{slot}",
        plan_scan_machine1="ScanMachine1",
        plan_insert_machine1="InsertMachine1",
        plan_place_pass_fmt1="A_PlaceToPass",    
        plan_place_fail_fmt1="A_PlaceToFail", 

        # Machine 2
        total_slots2=1,
        plan_open_machine2="B_OpenMachine",
        plan_close_machine2="B_CloseMachine",
        plan_pick_fmt2="B_PickFromTray_{slot}",
        plan_scan_machine2="ScanMachine2",
        plan_insert_machine2="InsertMachine2",
        plan_place_pass_fmt2="B_PlaceToPass",      
        plan_place_fail_fmt2="B_PlaceToFail",
    ),
    "MachineB": SequencerConfig(
        total_slots1=1,
        plan_open_machine1="B_OpenMachine",
        plan_close_machine1="B_CloseMachine",
        plan_pick_fmt1="B_PickFromTray_{slot}",
        plan_place_pass_fmt1="B_PlaceToPass",      
        plan_place_fail_fmt1="B_PlaceToFail",      
    ),
}