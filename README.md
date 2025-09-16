Legrand Progress Report

This progress report provides an update on the Legrand PCB project. Implementation has encountered a number of challenges due to unforeseen complexities from equipment and system limitations. The purpose of this report is to clarify customer requirements and assess whether the project remains feasible within the current budget.

Current Progress
•	A single robotic arm has been trialled for tray operation, PCB placement, and auxiliary tasks.
•	Fixed positioning has been implemented due to the absence of computer vision. The robot relies on fixed calibration within its coordinate frame.
•	Preliminary tray and gripper designs have been created for selected PCB types (Machine 1 & 5).
   
•	Integration testing has identified inconsistencies between machines, requiring individual adaptation(Difference between pull out trays and lever trays).
•	Evaluation of machine test cycles shows variability in timing (pass/fail durations), impacting synchronisation between the robot and test software.


Challenges Identified
1.	Machine Variability
o	Significant differences in PCB size and electrical components on board, open tray clearance (including protrusions), opening mechanisms, placement orientations, and distance between machines.
o	Each machine requires a tailored tray and handling solution.
 
2.	Positioning Constraints
o	Without computer vision, robot motion must remain absolute.
o	Any shift in robot position invalidates calibration and introduces collision risks.
3.	PCB Placement Variations
o	Orientation issues (e.g., inverted PCBs, panelised boards).
o	Issue with machine tray for PCB (easy to handle by human but introduces error for robot – protrusions, tray brackets, electrical components on PCB)
o	Clearance constraints differ per machine.
o	Tray designs and grippers must be customised accordingly.

 
 
 
 
4.	Lack of Feedback Systems
o	No built-in mechanism to confirm correct PCB insertion.
o	Incorrect placement could result in equipment damage.
o	Additional sensors must be integrated into machines to provide confirmation signals.
5.	Machine Software Dependency
o	Testing cycles vary in duration depending on pass/fail results.
o	Robot control must either adopt the longest cycle (cannot perform dynamic operations between machines) or establish communication with the test software for dynamic synchronisation.
6.	Sticker Printer Dependency
o	Sticker’s placement significantly complicate the gripper design – size restrictions from machines and sticker removal method (including size of stickers)
   

Outcomes
•	The robot arm’s operational functionality is limited by machine-specific requirements.
•	Multi-machine operation is not feasible across different categories. At most, similar tray-based machines can be grouped.
•	Sticker application is deprioritised to focus on critical tray handling and PCB placement tasks.
•	Full autonomy not possible with current limitations. Systems require physical overhauls and digital connection between testing machines and robot arm (Software)

Proposed Solutions
•	Motion Control Strategy:
Decide between a computer vision setup (higher flexibility, more development time and cost) or a fixed positioning setup (simpler but requires static calibrated fixtures and tables).


 

•	System Expansion:
Evaluate use of a second robotic arm / automated assembly  to manage auxiliary tasks such as stickers and PCB variants. (More complex 
•	Machine Adaptation:
1. Incorporate sensors into trays/machines to confirm correct PCB insertion and tray position. 
2. Modify Machine 1 & 5 PCB holding casing and protrusions

Resource Requirements
•	Labour: Increased complexity necessitates additional labour hours and personnel.
•	Testing Access: Overnight machine access is required, as daytime usage is constrained by production/repair schedules.
•	Hardware Modifications: Trays, tables, and machines will require physical modification and sensor integration depending on revised project expectations.




