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
  
- Integration testing has identified inconsistencies between machines, requiring individual adaptation (differences between pull-out trays and lever trays).  
- Evaluation of machine test cycles shows variability in timing (pass/fail durations), impacting synchronisation between the robot and test software.  

---

## Challenges Identified

1. **Machine Variability**
   - Significant differences in PCB size and electrical components on board, open tray clearance (including protrusions), opening mechanisms, placement orientations, and distance between machines.  
   - Each machine requires a tailored tray and handling solution.  

2. **Positioning Constraints**
   - Without computer vision, robot motion must remain absolute.  
   - Any shift in robot position invalidates calibration and introduces collision risks.  

3. **PCB Placement Variations**
   - Orientation issues (e.g., inverted PCBs, panelised boards).  
   - Issues with machine trays for PCBs (easy for humans but error-prone for robots due to protrusions, tray brackets, and electrical components).  
   - Clearance constraints differ per machine.  
   - Tray designs and grippers must be customised accordingly.  

4. **Lack of Feedback Systems**
   - No built-in mechanism to confirm correct PCB insertion.  
   - Incorrect placement could result in equipment damage.  
   - Additional sensors must be integrated into machines to provide confirmation signals.  

5. **Machine Software Dependency**
   - Testing cycles vary in duration depending on pass/fail results.  
   - Robot control must either adopt the longest cycle (limiting throughput) or establish communication with the test software for dynamic synchronisation.  

6. **Sticker Printer Dependency**
   - Sticker placement significantly complicates the gripper design due to size restrictions and removal method.  

---

## Outcomes
- The robot arm’s operational functionality is limited by machine-specific requirements.  
- Multi-machine operation is not feasible across different categories; at most, similar tray-based machines can be grouped.  
- Sticker application is deprioritised to focus on critical tray handling and PCB placement tasks.  
- Full autonomy is not possible with current limitations. Systems require **physical overhauls** and **digital connections** between testing machines and the robot arm.  

---

## Proposed Solutions

- **Motion Control Strategy**  
  Decide between:
  - A computer vision setup (higher flexibility, more development time and cost).  
  - A fixed positioning setup (simpler, but requires static calibrated fixtures and tables).  

- **System Expansion**  
  Evaluate the use of a second robotic arm / automated assembly to manage auxiliary tasks such as stickers and PCB variants.  

- **Machine Adaptation**  
  1. Incorporate sensors into trays/machines to confirm correct PCB insertion and tray position.  
  2. Modify Machine 1 & 5 PCB holding casings and protrusions.  

---

## Resource Requirements
- **Labour**: Increased complexity necessitates additional labour hours and personnel.  
- **Testing Access**: Overnight machine access is required, as daytime usage is constrained by production/repair schedules.  
