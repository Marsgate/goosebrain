#!/bin/bash
# Build all scene boards. usage: scenes.sh SCRATCH
cd $1/scene
NEW="case_tray.step case_cover.step case_diffuser.step@0.75 led_stick.step"
python3 ../scene.py $PWD/closed.kicad_pcb $NEW
python3 ../scene.py $PWD/clear.kicad_pcb case_tray.step@0.3 case_cover.step@0.3 case_diffuser.step@0.3 led_stick.step
python3 ../scene.py $PWD/robot_new.kicad_pcb $NEW kitbot.step@1@0,0,0.3
python3 ../scene.py $PWD/robot_old.kicad_pcb --bare kitbot.step@1@0,0,0.3 old_brain.step@1@0,0,0.3
python3 ../scene.py $PWD/brain_old.kicad_pcb --bare old_brain.step@1@0,0,0.3
