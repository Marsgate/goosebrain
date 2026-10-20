#!/bin/bash
# Render the case set. usage: render.sh SCRATCH OUTDIR
set -u
S=$1; O=$2; T=$S/try; mkdir -p $O $T; cd $S/scene
R(){ kicad-cli pcb render --quality high --background opaque --light-camera 0.4 --light-side 0.32 --light-top 0.5 --light-side-elevation 30 "$@" >/dev/null 2>&1 || echo "FAIL $*"; }
F="--perspective -w 1600 -h 1200"
R $F --rotate "-60,0,145" --zoom 0.9 -o $O/3_case_top_usb.png closed.kicad_pcb &
R $F --rotate "-60,0,55" --zoom 0.9 -o $O/4_case_left_io.png closed.kicad_pcb &
R $F --rotate "-60,0,-125" --zoom 0.9 -o $O/5_case_right_motors.png closed.kicad_pcb &
R $F --rotate "-55,0,-30" --zoom 0.9 -o $O/6_case_bottom_power.png closed.kicad_pcb &
R $F --rotate "-40,0,-25" --zoom 0.9 -o $O/7_clear_case.png clear.kicad_pcb &
R -w 1600 -h 1400 --rotate "-90,0,0" --zoom 0.95 -o $T/side_tall.png clear.kicad_pcb &
wait
P="--perspective -w 1600 -h 1200"
R $P --rotate "30,-35,0" --zoom 0.22 -o $O/1_on_robot.png robot_new.kicad_pcb &
R $P --rotate "20,-30,0" --zoom 0.7 -o $O/2_on_robot_closeup.png robot_new.kicad_pcb &
R $P --rotate "30,-35,0" --zoom 0.22 -o $T/old_robot.png robot_old.kicad_pcb &
R $P --rotate "20,-30,0" --zoom 0.7 -o $T/old_closeup.png robot_old.kicad_pcb &
wait
for b in brain_old closed; do
 R -w 1100 -h 800 --perspective --rotate "-50,0,25" --zoom 0.75 -o $T/${b}_iso.png $b.kicad_pcb &
 R -w 1100 -h 800 --rotate "0,0,0" --zoom 0.75 -o $T/${b}_top.png $b.kicad_pcb &
 R -w 1100 -h 800 --rotate "-90,0,0" --zoom 0.75 -o $T/${b}_side.png $b.kicad_pcb &
done; wait
