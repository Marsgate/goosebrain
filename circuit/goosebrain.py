"""goosebrain circuit description (SKiDL).

This file is the source of truth for the schematic. Run it to regenerate the
netlist (and optionally a KiCad schematic), then import the netlist in KiCad's
PCB editor to pull changes into kicad/thegoose.kicad_pcb.

    .venv/bin/python circuit/goosebrain.py              # netlist + ERC
    .venv/bin/python circuit/goosebrain.py --schematic  # also a .kicad_sch

Board summary: an ESP32 DevKit (30-pin) plugs into two 1x15 sockets. A 5 V
AP64500 buck converter runs it from the battery. Three DRV8848 dual H-bridges
drive six motors, and six 3-pin IO ports (IO, VCC, GND) break out spare GPIOs.

Each block is a @subcircuit so the generated schematic gets one tidy group
per block. Reference designators are fixed so they match the PCB.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KICAD_DIR = ROOT / "kicad"
BUILD_DIR = ROOT / "build"

# SKiDL writes its logs and ERC reports to the working directory, starting at
# import time, so keep them in build/.
BUILD_DIR.mkdir(exist_ok=True)
os.chdir(BUILD_DIR)

from skidl import (  # noqa: E402
    KICAD10,
    POWER,
    ERC,
    Net,
    Part,
    generate_netlist,
    generate_schematic,
    lib_search_paths,
    set_default_tool,
    subcircuit,
)

# NC (no connect) is a builtin that SKiDL installs on import.
KICAD_SYMBOLS = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
os.environ.setdefault("KICAD10_SYMBOL_DIR", KICAD_SYMBOLS)

set_default_tool(KICAD10)
lib_search_paths[KICAD10].extend([KICAD_SYMBOLS, str(KICAD_DIR)])

# Footprints used more than once.
C_0805 = "Capacitor_SMD:C_0805_2012Metric"
C_0603 = "Capacitor_SMD:C_0603_1608Metric"
R_0805 = "Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder"
LCSC = "LCSC Part #"


def part(lib, name, ref, footprint, lcsc, value=None):
    """Create a part with a fixed reference, footprint and LCSC number.

    The tag is set to the reference so regenerated netlists keep stable
    timestamps.
    """
    p = Part(lib, name, ref=ref, footprint=footprint, tag=ref)
    if value is not None:
        p.value = value
    p.fields[LCSC] = lcsc
    return p


def cap(ref, value, footprint, lcsc, a, b):
    """Capacitor with pin 1 on net a and pin 2 on net b."""
    c = part("Device", "C", ref, footprint, lcsc, value)
    c[1] += a
    c[2] += b
    return c


def res(ref, value, lcsc, a, b):
    """Resistor with pin 1 on net a and pin 2 on net b."""
    r = part("Device", "R", ref, R_0805, lcsc, value)
    r[1] += a
    r[2] += b
    return r


# Blocks ----------------------------------------------------------------------


@subcircuit
def battery_input(vbat, gnd):
    """XT60 battery connector. No fuse or reverse-polarity protection."""
    bt = part(
        "Connector_Generic", "Conn_01x02", "BT1",
        "hexy:AMASS_XT60PW-M_1x02_P7.20mm_Horizontal", "C98732", "XT60",
    )
    bt[1] += vbat
    bt[2] += gnd


@subcircuit
def buck_5v(vbat, vcc, gnd):
    """AP64500 buck converter, battery to 5 V.

    Vout = 0.8 V * (1 + R26 / R27) = 0.8 * (1 + 115k / 22.1k) = 4.96 V
    """
    u = part(
        "hexyhustle", "AP64500-13", "U4",
        "Package_SO:Diodes_SO-8EP", "C2070920", "AP64500SP-13",
    )
    sw, fb, comp, comp_rc = Net("SW"), Net("FB"), Net("COMP"), Net("COMP_RC")

    u["VIN"] += vbat
    u["EN"] += vbat  # always on
    u["GND", "EP"] += gnd
    u["SW"] += sw
    u["FB"] += fb
    u["COMP"] += comp

    cap("C15", "10uF", C_0805, "C15850", gnd, vbat)  # input bulk
    cap("C14", "100nF", C_0805, "C49678", sw, u["BST"])  # bootstrap
    inductor = part(
        "Device", "L", "L1",
        "Inductor_SMD_Wurth:L_Wurth_WE-LQSH-4020", "C7588667", "3.6uH",
    )
    inductor[1] += sw
    inductor[2] += vcc

    res("R25", "200k", "C844827", gnd, u["RT/CLK"])  # switching frequency
    res("R26", "115k", "C5200544", fb, vcc)  # feedback divider, top
    res("R27", "22.1k", "C228640", gnd, fb)  # feedback divider, bottom
    res("R28", "15.8k", "C47115540", comp_rc, comp)  # loop compensation
    cap("C16", "2.7nF", C_0603, "C302024", gnd, comp_rc)

    for ref in ("C5", "C8", "C12"):  # output bulk
        cap(ref, "22uF", C_0603, "C59461", vcc, gnd)


# 30-pin ESP32 DevKit pinout, socket pin 1 first. Ints are GPIO numbers.
ESP_LEFT = ["VIN", "GND", 13, 12, 14, 27, 26, 25, 33, 32, "D35", "D34", "VN", "VP", "EN"]
ESP_RIGHT = [23, 22, "TX0", "RX0", 21, 19, 18, 5, 17, 16, 4, 2, 15, "GND", "3V3"]


@subcircuit
def esp32_sockets(gpio, vcc, gnd):
    """Two 1x15 sockets for an ESP32 DevKit, powered from 5 V into VIN.

    gpio maps GPIO number -> net for every GPIO this board uses.
    """
    socket_fp = "Connector_PinSocket_2.54mm:PinSocket_1x15_P2.54mm_Vertical"
    left = part("Connector", "Conn_01x15_Socket", "ESP32_1", socket_fp, "C2932676")
    right = part("Connector", "Conn_01x15_Socket", "ESP32_2", socket_fp, "C2932676")

    for socket, pinout in ((left, ESP_LEFT), (right, ESP_RIGHT)):
        for pin_num, name in enumerate(pinout, start=1):
            if isinstance(name, int):
                socket[pin_num] += gpio[name]

    left[1] += vcc  # VIN
    left[2] += gnd
    right[14] += gnd

    en = Net("ESP_EN")
    left[15] += en
    cap("C1", "1uF", C_0805, "C28323", en, gnd)

    # Unused: D35, D34, VN, VP, TX0, RX0, 3V3.
    left[11, 12, 13, 14] += NC
    right[3, 4, 15] += NC


@subcircuit
def motor_driver(ref, sleep, ain1, ain2, bin1, bin2, vbat, gnd, motors, caps):
    """DRV8848 dual H-bridge driving two motors.

    motors is (motor A ref, motor B ref); caps is (VINT, VM bulk, VM bypass).
    """
    vint_cap, bulk_cap, bypass_cap = caps
    drv = part(
        "Driver_Motor", "DRV8848", ref,
        "Package_SO:TSSOP-16-1EP_4.4x5mm_P0.65mm", "C131079",
    )
    drv["~{SLEEP}"] += sleep
    drv["AIN1"] += ain1
    drv["AIN2"] += ain2
    drv["BIN1"] += bin1
    drv["BIN2"] += bin2

    drv["VM"] += vbat
    drv["GND"] += gnd  # pin 13 and the exposed pad (17)
    # No current limiting, so the sense pins go straight to GND (data sheet).
    # The original design left them open, which gave the H-bridges' low side
    # no return path.
    drv["AISEN", "BISEN"] += gnd

    vint = Net("VINT")
    drv["VINT", "VREF"] += vint  # VREF tied to VINT
    cap(vint_cap, "2.2uF", C_0805, "C377773", vint, gnd)
    cap(bulk_cap, "10uF", C_0805, "C15850", gnd, vbat)
    cap(bypass_cap, "100nF", C_0805, "C49678", vbat, gnd)

    drv["~{FAULT}"] += NC  # open-drain fault output, unused

    # The B motor is wired reversed (OUT1 to BOUT2), as in the original
    # design, so the firmware's direction handling depends on it.
    motor_a_ref, motor_b_ref = motors
    for motor_ref, out1, out2 in (
        (motor_a_ref, "AOUT1", "AOUT2"),
        (motor_b_ref, "BOUT2", "BOUT1"),
    ):
        motor = part(
            "hexyhustle", "motor", motor_ref,
            "hexy:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal", "C157931", "~",
        )
        motor["OUT1"] += drv[out1]
        motor["OUT2"] += drv[out2]


@subcircuit
def io_ports(ios, vcc, gnd):
    """One 3x6 right-angle header = six 3-pin ports (IO, VCC, GND).

    Port n (from 1) uses header pins 3n-2 (IO), 3n-1 (VCC) and 3n (GND).
    """
    header = part(
        "Connector", "Conn_01x18_Pin", "GPIO1",
        "hexy:PinHeader_3x06_P2.54mm_Horizontal", "C51953246", "Conn_06x3_Pin",
    )
    for port, io in enumerate(ios):
        pin = 3 * port + 1
        header[pin] += io
        header[pin + 1] += vcc
        header[pin + 2] += gnd


# Top level -------------------------------------------------------------------

vbat = Net("+BATT")  # battery, straight from the XT60
vcc = Net("VCC")  # 5 V from the buck converter
gnd = Net("GND")
for rail in (vbat, vcc, gnd):
    rail.drive = POWER

gpio = {
    n: Net(f"/ESP_D{n}")
    for n in [*ESP_LEFT, *ESP_RIGHT]
    if isinstance(n, int)
}

battery_input(vbat, gnd)
buck_5v(vbat, vcc, gnd)
esp32_sockets(gpio, vcc, gnd)

# All drivers share one SLEEP line (D2).
motor_driver("U1", gpio[2], gpio[13], gpio[12], gpio[15], gpio[4],
             vbat, gnd, motors=("M1", "M2"), caps=("C2", "C3", "C4"))
motor_driver("U2", gpio[2], gpio[16], gpio[17], gpio[18], gpio[5],
             vbat, gnd, motors=("M3", "M4"), caps=("C9", "C6", "C7"))
motor_driver("U3", gpio[2], gpio[19], gpio[21], gpio[23], gpio[22],
             vbat, gnd, motors=("M5", "M6"), caps=("C13", "C10", "C11"))

# IO_PORT_1 .. IO_PORT_6
io_ports([gpio[n] for n in (32, 33, 25, 26, 27, 14)], vcc, gnd)


if __name__ == "__main__":
    BUILD_DIR.mkdir(exist_ok=True)
    ERC()
    generate_netlist(file_=str(BUILD_DIR / "goosebrain.net"))
    if "--schematic" in sys.argv:
        sch_dir = BUILD_DIR / "schematic"
        sch_dir.mkdir(exist_ok=True)
        # Point the generated schematic at the project's own libraries.
        # KiCad only reads project library tables next to a .kicad_pro.
        (sch_dir / "goosebrain.kicad_pro").write_text("{}\n")
        for table in ("sym-lib-table", "fp-lib-table"):
            text = (KICAD_DIR / table).read_text()
            (sch_dir / table).write_text(
                text.replace("${KIPRJMOD}", "${KIPRJMOD}/../../kicad")
            )
        generate_schematic(
            filepath=str(sch_dir),
            top_name="goosebrain",
            title="goosebrain",
            auto_stub=True,
        )
