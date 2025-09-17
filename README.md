# Legrand PCB Project – Progress Report

This progress report provides an update on the Legrand PCB project. Implementation has encountered a number of challenges due to unforeseen complexities from equipment and system limitations.  
The purpose of this report is to clarify customer requirements and assess whether the project remains feasible within the current budget.

---

## Current Progress
- A single robotic arm has been trialled for tray operation, PCB placement, and auxiliary tasks.  
- Fixed positioning has been implemented due to the absence of computer vision. The robot relies on fixed calibration within its coordinate frame.  
- Preliminary tray and gripper designs have been created for selected PCB types (Machine 1 & 5).
<img width="320" height="248" alt="image" src="https://github.com/user-attachments/assets/fd798b17-d4a5-47fd-891b-cdd1733e45d4" />
<img width="450" height="277" alt="image" src="https://github.com/user-attachments/assets/e2743bd1-e576-4c82-873a-49fdc355c364" /> 
- Integration testing has identified inconsistencies between machines, requiring individual adaptation (pull-out trays vs. lever trays).  
- Evaluation of machine test cycles shows variability in timing (pass/fail durations), impacting synchronisation between the robot and test software.  

---

## Challenges Identified

1. **Machine Variability**  
   - Large differences in PCB size, tray clearance (with protrusions), opening mechanisms, placement orientations, and distance between machines.  
   - Each machine requires a tailored tray and handling solution.  

2. **Positioning Constraints**  
   - Without computer vision, robot motion must remain absolute.  
   - Any shift in robot position invalidates calibration and increases collision risk.  

3. **PCB Placement Variations**  
   - Orientation issues (inverted PCBs, panelised boards).  
   - Trays designed for human handling introduce errors for robots (brackets, protrusions, electrical components).  
   - Clearance constraints differ per machine.  
  <img width="262" height="329" alt="image" src="https://github.com/user-attachments/assets/060c466b-0f77-4d9e-a743-6cb07453416c" />
  <img width="388" height="329" alt="image" src="https://github.com/user-attachments/assets/74182512-f5ce-4965-a49d-391b60c87dec" />
  <img width="397" height="338" alt="image" src="https://github.com/user-attachments/assets/42045a67-e457-4d0a-94e6-7ae3dcb5773e" />
  <img width="398" height="500" alt="image" src="https://github.com/user-attachments/assets/e8120d8c-cdb6-4286-b1f9-1b14d450adec" />
4. **Lack of Feedback Systems**  
   - No built-in mechanism to confirm PCB insertion.  
   - Incorrect placement could damage equipment.  
   - Requires additional sensors for confirmation signals.  

5. **Machine Software Dependency**  
   - Testing cycle durations vary depending on pass/fail results.  
   - Robot must either adopt longest cycle or integrate with test software for dynamic synchronisation.  

6. **Sticker Printer Dependency**  
   - Sticker placement complicates gripper design due to size restrictions and removal method.
    <img width="519" height="280" alt="image" src="https://github.com/user-attachments/assets/d9e5e85d-e8b7-48f0-bbff-ad40ebf8c8e3" />

---

## Outcomes

- Initial expectations that a single robotic arm could fully automate PCB handling and testing have proven unrealistic. Variability between machines, reliance on human adaptability, and lack of integrated feedback limit automation potential.  
- The robot’s functionality is constrained by machine-specific requirements. At best, only machines with similar tray systems can be grouped into a shared workflow.  
- Full autonomy would require redesigned trays, fixtures, and test machine interfaces. Commercial PCB assembly lines (e.g. [Minitec Automated Lines](https://www.minitec.si/automated-line-for-pcb-assemblies)) show that true automation depends on multiple subsystems (conveyors, feeders, sensors, and multiple robots), not a single manipulator.  
- With the current setup, multi-machine operation is not feasible. Sticker application and auxiliary tasks have been deprioritised in favour of safe tray handling and PCB placement.  
- A robust solution requires both physical overhauls (custom trays, sensors, fixtures) and digital integration between robot and test machines. Without these, safe operation and throughput cannot be guaranteed.  

---

## Proposed Solutions

### 1. Motion Control Strategy
**Option A: Computer Vision Integration**  
- Advantages: Flexible positioning, adapts across machines, can detect inverted/misaligned boards.  
- Drawbacks: PCBs must be placed individually (not stacked), angled boards affect pickup/placement, high cost and development time.  

**Option B: Fixed Positioning with Calibrated Fixtures**  
- Advantages: Simple, low cost, no extra hardware, reliable if fixtures stay static.  
- Drawbacks: Sensitive to any shifts, requires standardised trays, low adaptability.  

---

### 2. Machine Adaptation
- **Sensor Integration**  
  - Advantages: Confirms PCB insertion and tray position, reduces risk of damage.  
  - Drawbacks: Requires wiring changes, may cause downtime.  

- **Hardware Modifications (Trays/Fixtures)**  
  - Advantages: Removes clearance issues, makes trays easier for robots.  
  - Drawbacks: Custom machining adds cost, may affect warranties.  

---

### 3. System Expansion
- **Additional Robotic Arm / Automation**  
  - Advantages: Splits workload (stickers vs. PCB handling), increases throughput and reliability.  
  - Drawbacks: Expensive, needs more space and safety controls.  

---

### 4. Digital Integration
- **Communication with Test Software**  
  - Advantages: Syncs with actual test times, avoids waiting for longest cycle, improves efficiency.  
  - Drawbacks: Depends on machine APIs or test software modifications, complexity varies.  

---

### 5. Phased Implementation
- **Short Term**: Focus on tray handling and PCB placement.  
  - Risk: Requires operator supervision, not fully autonomous.  
- **Medium Term**: Add sensors and standardised trays.  
  - Risk: Extra cost and downtime during adaptation.  
- **Long Term**: Expand with vision systems and auxiliary automation.  
  - Risk: High investment, may still not match full PCB assembly line flexibility.  

---

## Resource Requirements
- **Testing Access**: Overnight access needed, daytime availability is limited by production schedules.  
- **Hardware Modifications**: Trays, tables, and machines will require redesign and integration of sensors.  

---
