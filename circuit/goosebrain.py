"""goosebrain rev 2 circuit description (SKiDL).

This file is the source of truth for the schematic. Run it to regenerate the
netlist (and optionally a KiCad schematic), then import the netlist in KiCad's
PCB editor to pull changes into kicad/thegoose.kicad_pcb.

    .venv/bin/python circuit/goosebrain.py              # netlist + ERC
    .venv/bin/python circuit/goosebrain.py --schematic  # also a .kicad_sch

Board summary (rev 2): an RP2354A (RP2350A with 2 MB of in-package flash) runs
the robot. A 2.4 GHz game-controller dongle plugs into a USB-A host port driven
by PIO (Pico-PIO-USB); the RP2354's native USB goes to USB-C for UF2, Arduino
upload and serial. The same USB-C port charges an internal 3S pack through a
BQ25798, asking a USB-PD charger for 9 V. Three DRV8848 dual H-bridges drive six
motors from the pack, a 5 V buck feeds the IO ports and the dongle, and six
3-pin IO ports break out spare GPIOs. There is no radio on the board.

Each block is a @subcircuit. Reference designators are fixed so they stay
stable across regenerations. Part numbers and stock are in circuit/PARTS.md.
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

# Part fields. MPN is the primary ID; LCSC is optional (JLC assembly).
MPN = "MPN"
MFR = "Manufacturer"
LCSC = "LCSC Part #"

# Generic resistors and capacitors: (value, package) -> (MPN, manufacturer, LCSC)
UNIROYAL = "UNI-ROYAL"
SAMSUNG = "Samsung Electro-Mechanics"
FENGHUA = "FH (Guangdong Fenghua)"
PASSIVES = {
    ("22", "0402"): ("0402WGF220JTCE", UNIROYAL, "C25092"),
    ("27", "0402"): ("0402WGF270JTCE", UNIROYAL, "C25100"),
    ("33", "0402"): ("0402WGF330JTCE", UNIROYAL, "C25105"),
    ("100", "0402"): ("0402WGF1000TCE", UNIROYAL, "C25076"),
    ("330", "0402"): ("0402WGF3300TCE", UNIROYAL, "C25104"),
    ("1k", "0402"): ("0402WGF1001TCE", UNIROYAL, "C11702"),
    ("2.2k", "0402"): ("0402WGF2201TCE", UNIROYAL, "C25879"),
    ("5.23k", "0402"): ("0402WGF5231TCE", UNIROYAL, "C25907"),
    ("6.8k", "0402"): ("0402WGF6801TCE", UNIROYAL, "C25917"),
    ("10k", "0402"): ("0402WGF1002TCE", UNIROYAL, "C25744"),
    ("13.7k", "0402"): ("0402WGF1372TCE", UNIROYAL, "C25854"),
    ("15.8k", "0402"): ("0402WGF1582TCE", UNIROYAL, "C26956"),
    ("22.1k", "0402"): ("0402WGF2212TCE", UNIROYAL, "C43473"),
    ("27k", "0402"): ("0402WGF2702TCE", UNIROYAL, "C25771"),
    ("30.1k", "0402"): ("0402WGF3012TCE", UNIROYAL, "C29402"),
    ("33k", "0402"): ("0402WGF3302TCE", UNIROYAL, "C25779"),
    ("100k", "0402"): ("0402WGF1003TCE", UNIROYAL, "C25741"),
    ("115k", "0402"): ("0402WGF1153TCE", UNIROYAL, "C25747"),
    ("200k", "0402"): ("0402WGF2003TCE", UNIROYAL, "C25764"),
    ("15pF", "0402"): ("0402CG150J500NT", FENGHUA, "C1548"),
    ("1nF", "0402"): ("0402B102K500NT", FENGHUA, "C1523"),
    ("2.7nF", "0402"): ("0402B272K500NT", FENGHUA, "C45185"),
    ("47nF", "0402"): ("CL05B473KA5NNNC", SAMSUNG, "C318631"),
    ("100nF", "0402"): ("CL05B104KO5NNNC", SAMSUNG, "C1525"),
    ("1uF", "0402"): ("CL05A105KA5NQNC", SAMSUNG, "C52923"),  # 25 V
    ("4.7uF", "0402"): ("CL05A475MP5NRNC", SAMSUNG, "C23733"),  # 10 V
    ("1uF", "0603"): ("CL10A105KA8NNNC", SAMSUNG, "C5673"),  # 25 V
    ("4.7uF", "0603"): ("CL10A475KO8NNNC", SAMSUNG, "C19666"),  # 16 V
    ("10uF", "0603"): ("CL10A106KP8NNNC", SAMSUNG, "C19702"),  # 10 V
    ("100nF", "0805"): ("CC0805KRX7R9BB104", "YAGEO", "C49678"),  # 50 V
    ("2.2uF", "0805"): ("CL21A225KBQNNNE", SAMSUNG, "C377773"),  # 50 V
    ("10uF", "0805"): ("CL21A106KAYNNNE", SAMSUNG, "C15850"),  # 25 V
    ("22uF", "0805"): ("CL21A226MAQNNNE", SAMSUNG, "C45783"),  # 25 V
}
R_FP = "Resistor_SMD:R_{0}_{1}Metric"
C_FP = "Capacitor_SMD:C_{0}_{1}Metric"
METRIC = {"0402": "1005", "0603": "1608", "0805": "2012"}


def part(lib, name, ref, footprint, mpn, mfr, lcsc="", value=None):
    """Create a part with a fixed reference, footprint and part-number fields.

    The tag is set to the reference so regenerated netlists keep stable
    timestamps.
    """
    p = Part(lib, name, ref=ref, footprint=footprint, tag=ref)
    if value is not None:
        p.value = value
    p.fields[MPN] = mpn
    p.fields[MFR] = mfr
    if lcsc:
        p.fields[LCSC] = lcsc
    return p


def _passive(kind, ref, value, pkg, a, b):
    mpn, mfr, lcsc = PASSIVES[(value, pkg)]
    fp = (R_FP if kind == "R" else C_FP).format(pkg, METRIC[pkg])
    p = part("Device", kind, ref, fp, mpn, mfr, lcsc, value)
    p[1] += a
    p[2] += b
    return p


def cap(ref, value, pkg, a, b):
    """Capacitor with pin 1 on net a and pin 2 on net b."""
    return _passive("C", ref, value, pkg, a, b)


def res(ref, value, pkg, a, b):
    """Resistor with pin 1 on net a and pin 2 on net b."""
    return _passive("R", ref, value, pkg, a, b)


class Refs:
    """Hands out sequential reference designators per prefix."""

    def __init__(self, **start):
        self.next = dict(start)

    def __call__(self, prefix):
        n = self.next[prefix]
        self.next[prefix] = n + 1
        return f"{prefix}{n}"


# Rev 1 used C1-C16, R25-R28, U1-U4, L1, M1-M6; new parts continue from there.
ref = Refs(C=17, R=29, U=5, L=2, D=1, Q=1, F=1, J=1, SW=1, LED=1, TP=1, Y=1)


# Blocks ----------------------------------------------------------------------


@subcircuit
def usb_c_port(vbus, usb_dp, usb_dm, v3v3, gnd):
    """USB-C: data to the RP2354, power to the charger, PD sink asks for 9 V.

    The CH224A presents the sink's Rd on CC and negotiates 9 V; a source
    without PD stays at 5 V. Its own DP/DM pins (BC1.2/QC) are left open so
    they stay off the RP2354's USB lines.
    """
    j = part(
        "Connector", "USB_C_Receptacle_USB2.0_16P", ref("J"),
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        "TYPE-C-31-M-12", "Korean Hroparts Elec", "C165948",
    )
    j["A4", "A9", "B4", "B9"] += vbus
    j["A1", "A12", "B1", "B12", "SH"] += gnd
    j["A6", "B6"] += usb_dp
    j["A7", "B7"] += usb_dm
    j["A8", "B8"] += NC  # SBU
    cc1, cc2 = Net("CC1"), Net("CC2")
    j["A5"] += cc1
    j["B5"] += cc2

    # The KiCad CH224K symbol matches the CH224A pinout; pin 1 is VHV on the
    # CH224A and takes VBUS directly (up to 30 V).
    pd = part(
        "Interface_USB", "CH224K", ref("U"),
        "Package_SO:SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm",
        "CH224A", "WCH", "C42459160", "CH224A",
    )
    pd["VDD", "VBUS"] += vbus
    pd["CC1"] += cc1
    pd["CC2"] += cc2
    pd["GND"] += gnd
    cfg1 = Net("PD_CFG1")
    pd["CFG1"] += cfg1
    res(ref("R"), "6.8k", "0402", cfg1, gnd)  # 6.8 kOhm requests 9 V
    pd["CFG2", "CFG3", "DP", "DM", "PG"] += NC
    cap(ref("C"), "1uF", "0603", vbus, gnd)  # VHV decoupling

    tvs = part(
        "Device", "D_TVS", ref("D"), "Diode_SMD:D_SMB",
        "SMBJ20A", "MDD", "C364296", "SMBJ20A",
    )
    tvs["A1"] += vbus
    tvs["A2"] += gnd

    esd = part(
        "Power_Protection", "USBLC6-2SC6", ref("U"), "Package_TO_SOT_SMD:SOT-23-6",
        "USBLC6-2SC6", "STMicroelectronics", "C7519",
    )
    esd[1, 6] += usb_dp
    esd[3, 4] += usb_dm
    esd["VBUS"] += v3v3  # rated 6 V: never tie to PD VBUS
    esd["GND"] += gnd


@subcircuit
def charger_3s(vbus, vbat, regn, i2c_scl, i2c_sda, chg_int, v3v3, gnd):
    """BQ25798 buck-boost charger for the internal 3S pack.

    Safe with no firmware: PROG selects 3S (12.6 V) at 750 kHz, the TS divider
    plus the pack NTC gives JEITA temperature limits, and the ILIM_HIZ divider
    caps input current at about 0.30 A, so charge current stays near 0.45C of a
    500 mAh pack from 9 V (and lower from 5 V) even though the power-on charge
    current default is 1 A. The robot's loads run from the pack, not from SYS,
    because the internal BATFET is only rated 6 A continuous.
    """
    u = part(
        "Battery_Management", "BQ25798", ref("U"),
        "Package_DFN_QFN:Texas_RQM0029A_VQFN-29_4x4mm_P0.4mm",
        "BQ25798RQMR", "Texas Instruments", "C2876593",
    )
    pmid, sys_, sw1, sw2 = Net("CHG_PMID"), Net("CHG_SYS"), Net("CHG_SW1"), Net("CHG_SW2")
    u["VBUS", "VAC1", "VAC2"] += vbus  # single input: VAC1/VAC2 tied to VBUS
    u["ACDRV1", "ACDRV2"] += gnd  # no input FETs
    u["PMID"] += pmid
    u["SYS"] += sys_
    u["SW1"] += sw1
    u["SW2"] += sw2
    u["BAT"] += vbat
    u["REGN"] += regn
    u["GND"] += gnd
    u["~{CE}"] += gnd  # charging always enabled
    u["~{QON}", "D+", "D-"] += NC  # ILIM_HIZ overrides BC1.2 detection
    u["SCL"] += i2c_scl
    u["SDA"] += i2c_sda
    u["~{INT}"] += chg_int

    inductor = part(
        "Device", "L", ref("L"), "Inductor_SMD:L_Sunlord_MWSA0402S",
        "MWSA0402S-2R2MT", "Sunlord", "C408335", "2.2uH",
    )
    inductor[1] += sw1
    inductor[2] += sw2
    btst1, btst2 = Net("CHG_BTST1"), Net("CHG_BTST2")
    u["BTST1"] += btst1
    u["BTST2"] += btst2
    cap(ref("C"), "47nF", "0402", btst1, sw1)
    cap(ref("C"), "47nF", "0402", btst2, sw2)

    for _ in range(2):
        cap(ref("C"), "10uF", "0805", vbus, gnd)
    cap(ref("C"), "100nF", "0402", vbus, gnd)
    for _ in range(3):
        cap(ref("C"), "10uF", "0805", pmid, gnd)
    cap(ref("C"), "100nF", "0402", pmid, gnd)
    for _ in range(5):
        cap(ref("C"), "10uF", "0805", sys_, gnd)
    cap(ref("C"), "100nF", "0402", sys_, gnd)
    for _ in range(2):
        cap(ref("C"), "10uF", "0805", vbat, gnd)
    cap(ref("C"), "4.7uF", "0603", regn, gnd)

    batp = Net("CHG_BATP")
    u["BATP"] += batp
    res(ref("R"), "100", "0402", batp, vbat)  # battery voltage sense
    sdrv = Net("CHG_SDRV")
    u["SDRV"] += sdrv
    cap(ref("C"), "1nF", "0402", sdrv, gnd)  # no ship FET fitted

    prog = Net("CHG_PROG")
    u["PROG"] += prog
    res(ref("R"), "13.7k", "0402", prog, gnd)  # 3S, 750 kHz

    ilim = Net("CHG_ILIM")
    u["ILIM_HIZ"] += ilim
    res(ref("R"), "100k", "0402", regn, ilim)  # 1.24 V -> ~0.30 A input limit
    res(ref("R"), "33k", "0402", ilim, gnd)

    ts = Net("CHG_TS")
    u["TS"] += ts
    res(ref("R"), "5.23k", "0402", regn, ts)
    res(ref("R"), "30.1k", "0402", ts, gnd)
    ntc = part(
        "Connector_Generic", "Conn_01x02", ref("J"),
        "Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal",
        "S2B-PH-K-S(LF)(SN)", "JST", "C173752", "Pack NTC",
    )
    ntc[1] += ts  # 10 kOhm 103AT NTC in the pack, TS to GND
    ntc[2] += gnd

    # Charge LED on STAT: lit while charging, with no firmware involved.
    stat, stat_led = Net("CHG_STAT"), Net("CHG_STAT_LED")
    u["STAT"] += stat
    res(ref("R"), "2.2k", "0402", regn, stat_led)
    led = part(
        "Device", "LED", ref("LED"), "LED_SMD:LED_0603_1608Metric",
        "KT-0603G", "Hubei KENTO Elec", "C12624", "green",
    )
    led["A"] += stat_led
    led["K"] += stat

    for line in (i2c_scl, i2c_sda, chg_int):
        res(ref("R"), "10k", "0402", v3v3, line)


@subcircuit
def battery_and_switch(vbat, vsys, gnd):
    """Pack connector, fuse and the main power switch.

    The slide switch only drives the P-FET gate; motor current flows through
    the FET. Charging works with the switch off, since the charger connects to
    VBAT ahead of it.
    """
    j = part(
        "Connector_Generic", "Conn_01x02", ref("J"),
        "Connector_AMASS:AMASS_XT30PW-M_1x02_P2.50mm_Horizontal",
        "XT30PW-M", "Changzhou Amass", "C431092", "XT30 pack",
    )
    pack = Net("PACK+")
    j[1] += pack
    j[2] += gnd

    fuse = part(
        "Device", "Fuse", ref("F"), "Fuse:Fuse_Littelfuse-NANO2-451_453",
        "0453015.MR", "Littelfuse", "C178997", "15A slow",
    )
    fuse[1] += pack
    fuse[2] += vbat

    fet = part(
        "Transistor_FET", "IRF7404", ref("Q"), "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "AO4407A", "UMW", "C2841482", "AO4407A",
    )
    gate = Net("PWR_GATE")
    fet["S"] += vbat
    fet["D"] += vsys
    fet["G"] += gate
    res(ref("R"), "100k", "0402", vbat, gate)  # off by default

    switch = part(
        "Switch", "SW_SPDT", ref("SW"), "Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02",
        "MSK12C02", "SHOU HAN", "C431540", "Power",
    )
    sw_on = Net("PWR_SW_ON")
    switch["B"] += gate  # common
    switch["A"] += sw_on  # on: gate pulled to GND
    switch["C"] += NC  # off
    res(ref("R"), "1k", "0402", sw_on, gnd)


@subcircuit
def buck_5v(vin, vcc, gnd):
    """AP64500 buck converter, pack to 5 V (rev 1 values).

    Vout = 0.8 V * (1 + R26 / R27) = 0.8 * (1 + 115k / 22.1k) = 4.96 V
    """
    u = part(
        "hexyhustle", "AP64500-13", "U4", "Package_SO:Diodes_SO-8EP",
        "AP64500SP-13", "Diodes Incorporated", "C2070920", "AP64500SP-13",
    )
    sw, fb, comp, comp_rc = Net("SW"), Net("FB"), Net("COMP"), Net("COMP_RC")

    u["VIN"] += vin
    u["EN"] += vin  # always on
    u["GND", "EP"] += gnd
    u["SW"] += sw
    u["FB"] += fb
    u["COMP"] += comp

    cap("C15", "10uF", "0805", gnd, vin)  # input bulk
    cap("C14", "100nF", "0805", sw, u["BST"])  # bootstrap
    inductor = part(
        "Device", "L", "L1", "Inductor_SMD:L_Wuerth_WE-LQSH-4020",
        "CR4030-3R6M", "Ceaiya", "C7588667", "3.6uH",
    )
    inductor[1] += sw
    inductor[2] += vcc

    res("R25", "200k", "0402", gnd, u["RT/CLK"])  # switching frequency
    res("R26", "115k", "0402", fb, vcc)  # feedback divider, top
    res("R27", "22.1k", "0402", gnd, fb)  # feedback divider, bottom
    res("R28", "15.8k", "0402", comp_rc, comp)  # loop compensation
    cap("C16", "2.7nF", "0402", gnd, comp_rc)

    # 22 uF 0805/25 V: the rev 1 0603 parts lost most of their capacitance
    # to DC bias at 5 V.
    for r in ("C5", "C8", "C12"):
        cap(r, "22uF", "0805", vcc, gnd)


@subcircuit
def rail_3v3(vbus, vcc, v3v3, gnd):
    """3.3 V for the RP2354, from the 5 V buck or from USB alone.

    The USB-only path lets an end user program the board with the battery flat
    or the power switch off. HT7550 takes PD VBUS (up to 30 V in); keep its
    load small (MCU only, about 50 mA).
    """
    v5_usb, v5_or = Net("5V_USB"), Net("5V_OR")
    v5_or.drive = POWER  # fed through the OR diodes
    usb_reg = part(
        "Regulator_Linear", "HT75xx-1-SOT89", ref("U"), "Package_TO_SOT_SMD:SOT-89-3",
        "HT7550-1", "Holtek Semicon", "C16106", "HT7550-1",
    )
    usb_reg["VIN"] += vbus
    usb_reg["VOUT"] += v5_usb
    usb_reg["GND"] += gnd
    cap(ref("C"), "1uF", "0603", vbus, gnd)
    cap(ref("C"), "10uF", "0603", v5_usb, gnd)

    for src in (v5_usb, vcc):
        d = part(
            "Device", "D_Schottky", ref("D"), "Diode_SMD:D_SOD-123",
            "B5819W", "MDD", "C64885", "B5819W",
        )
        d["A"] += src
        d["K"] += v5_or

    ldo = part(
        "Regulator_Linear", "AP2112K-3.3", ref("U"), "Package_TO_SOT_SMD:SOT-23-5",
        "AP2112K-3.3TRG1", "Diodes Incorporated", "C51118", "AP2112K-3.3",
    )
    ldo["VIN", "EN"] += v5_or
    ldo["VOUT"] += v3v3
    ldo["GND"] += gnd
    ldo["NC"] += NC
    cap(ref("C"), "1uF", "0402", v5_or, gnd)
    cap(ref("C"), "10uF", "0603", v3v3, gnd)


@subcircuit
def mcu(v3v3, gnd, usb_dp, usb_dm, gpio):
    """RP2354A with the Raspberry Pi minimal-design support parts.

    gpio maps GPIO number -> net for every GPIO this board uses. The RP2354A
    has 2 MB of flash in the package, so the QSPI pins stay unconnected apart
    from QSPI_SS (BOOTSEL).
    """
    u = part(
        "MCU_RaspberryPi", "RP2354A", ref("U"),
        "Package_DFN_QFN:QFN-60-1EP_7x7mm_P0.4mm_EP3.4x3.4mm",
        "RP2354A", "Raspberry Pi", "C41378174",
    )
    v1v1, vreg_avdd, vreg_lx = Net("+1V1"), Net("VREG_AVDD"), Net("VREG_LX")
    v1v1.drive = vreg_avdd.drive = POWER  # fed through the inductor / RC filter

    u["IOVDD", "QSPI_IOVDD", "USB_OTP_VDD", "ADC_AVDD", "VREG_VIN"] += v3v3
    u["GND", "VREG_PGND"] += gnd  # PGND joins GND at one point (layout)
    for _ in range(6):  # one per IOVDD pin
        cap(ref("C"), "100nF", "0402", v3v3, gnd)
    cap(ref("C"), "100nF", "0402", v3v3, gnd)  # QSPI_IOVDD
    cap(ref("C"), "100nF", "0402", v3v3, gnd)  # USB_OTP_VDD
    cap(ref("C"), "100nF", "0402", v3v3, gnd)  # ADC_AVDD
    cap(ref("C"), "4.7uF", "0402", v3v3, gnd)  # VREG_VIN (CIN)

    # Core regulator: 3.3 uH polarity-marked inductor from VREG_LX to 1.1 V.
    u["VREG_AVDD"] += vreg_avdd
    res(ref("R"), "33", "0402", v3v3, vreg_avdd)
    cap(ref("C"), "4.7uF", "0402", vreg_avdd, gnd)
    u["VREG_LX"] += vreg_lx
    core_l = part(
        "Device", "L", ref("L"), "hexy:L_Abracon_AOTA-B201610",
        "AOTA-B201610S3R3-101-T", "Abracon", "C42411119", "3.3uH",
    )
    core_l[1] += v1v1
    core_l[2] += vreg_lx
    u["VREG_FB", "DVDD"] += v1v1
    cap(ref("C"), "4.7uF", "0402", v1v1, gnd)  # COUT, at DVDD pin 23
    for _ in range(3):  # one per DVDD pin
        cap(ref("C"), "100nF", "0402", v1v1, gnd)

    # 12 MHz crystal.
    xin, xout, xout_r = Net("XIN"), Net("XOUT"), Net("XOUT_R")
    u["XIN"] += xin
    u["XOUT"] += xout
    xtal = part(
        "Device", "Crystal_GND24", ref("Y"), "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        "ABM8-272-T3", "Abracon", "C20625731", "12MHz",
    )
    xtal[1] += xin
    xtal[3] += xout_r
    xtal[2, 4] += gnd
    res(ref("R"), "1k", "0402", xout, xout_r)
    cap(ref("C"), "15pF", "0402", xin, gnd)
    cap(ref("C"), "15pF", "0402", xout_r, gnd)

    # Native USB to USB-C.
    u["USB_DP"] += (dp_mcu := Net("USB_DP_MCU"))
    u["USB_DM"] += (dm_mcu := Net("USB_DM_MCU"))
    res(ref("R"), "27", "0402", dp_mcu, usb_dp)
    res(ref("R"), "27", "0402", dm_mcu, usb_dm)

    # BOOTSEL on QSPI_SS, RESET on RUN (each with 1 kOhm, per the RPi design).
    qspi_ss, boot_r = Net("QSPI_SS"), Net("BOOTSEL_R")
    u["~{QSPI_SS}"] += qspi_ss
    u["QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3", "QSPI_SCLK"] += NC
    res(ref("R"), "1k", "0402", qspi_ss, boot_r)
    run, run_r = Net("RUN"), Net("RUN_R")
    u["RUN"] += run
    res(ref("R"), "1k", "0402", run_r, gnd)
    for label, a, b in (("BOOT", boot_r, gnd), ("RESET", run, run_r)):
        sw = part(
            "Switch", "SW_Push", ref("SW"), "Button_Switch_SMD:SW_SPST_TS-1088-xR020",
            "TS-1088-AR02016", "XUNPU", "C720477", label,
        )
        sw[1] += a
        sw[2] += b

    # SWD test pads for factory programming and debugging.
    for name in ("SWCLK", "SWDIO"):
        net = Net(name)
        u[name] += net
        tp = part(
            "Connector", "TestPoint", ref("TP"), "TestPoint:TestPoint_Pad_D1.0mm",
            "", "", "", name,
        )
        tp[1] += net

    for n in range(30):
        pin = f"GPIO{n}" if n < 26 else f"GPIO{n}/ADC{n - 26}"
        u[pin] += gpio.get(n, NC)


@subcircuit
def usb_a_host(dp_gpio, dm_gpio, vbus_en, vcc, gnd):
    """USB-A host port for the controller dongle (Pico-PIO-USB on two GPIOs).

    22 Ohm series resistors as in Adafruit's Feather RP2040 USB Host; the PIO
    host enables the RP2354's internal pull-downs. VBUS comes from the 5 V rail
    through a 0.5 A current-limited switch, off until firmware enables it.
    """
    usba_dp, usba_dm, usba_vbus = Net("USBA_DP"), Net("USBA_DM"), Net("USBA_VBUS")
    res(ref("R"), "22", "0402", dp_gpio, usba_dp)
    res(ref("R"), "22", "0402", dm_gpio, usba_dm)

    esd = part(
        "Power_Protection", "USBLC6-2SC6", ref("U"), "Package_TO_SOT_SMD:SOT-23-6",
        "USBLC6-2SC6", "STMicroelectronics", "C7519",
    )
    esd[1, 6] += usba_dp
    esd[3, 4] += usba_dm
    esd["VBUS"] += vcc
    esd["GND"] += gnd

    switch = part(
        "Power_Management", "TPS2051CDBV", ref("U"), "Package_TO_SOT_SMD:SOT-23-5",
        "TPS2051CDBVR", "Texas Instruments", "C129581", "TPS2051C",
    )
    switch["IN"] += vcc
    switch["EN"] += vbus_en
    switch["OUT"] += usba_vbus
    switch["GND"] += gnd
    switch["~{FLT}"] += NC
    res(ref("R"), "100k", "0402", vbus_en, gnd)  # off while the MCU boots
    cap(ref("C"), "1uF", "0402", vcc, gnd)
    cap(ref("C"), "22uF", "0805", usba_vbus, gnd)
    cap(ref("C"), "100nF", "0402", usba_vbus, gnd)

    j = part(
        "Connector", "USB_A", ref("J"), "hexy:USB_A_Amphenol_87520-0010BLF",
        "87520-0010BLF", "Amphenol ICC", "C599115", "USB-A host",
    )
    j["VBUS"] += usba_vbus
    j["D+"] += usba_dp
    j["D-"] += usba_dm
    j["GND", "Shield"] += gnd


@subcircuit
def motor_driver(ref_, sleep, fault, ain1, ain2, bin1, bin2, vm, gnd, motors, caps):
    """DRV8848 dual H-bridge driving two motors (rev 1 circuit).

    motors is (motor A ref, motor B ref); caps is (VINT, VM bulk, VM bypass).
    """
    vint_cap, bulk_cap, bypass_cap = caps
    drv = part(
        "Driver_Motor", "DRV8848", ref_,
        "Package_SO:TSSOP-16-1EP_4.4x5mm_P0.65mm",
        "DRV8848PWPR", "Texas Instruments", "C131079",
    )
    drv["~{SLEEP}"] += sleep
    drv["~{FAULT}"] += fault  # open drain, wired-OR across all drivers
    drv["AIN1"] += ain1
    drv["AIN2"] += ain2
    drv["BIN1"] += bin1
    drv["BIN2"] += bin2

    drv["VM"] += vm
    drv["GND"] += gnd  # pin 13 and the exposed pad (17)
    # No current limiting, so the sense pins go straight to GND (data sheet).
    drv["AISEN", "BISEN"] += gnd

    vint = Net("VINT")
    drv["VINT", "VREF"] += vint  # VREF tied to VINT
    cap(vint_cap, "2.2uF", "0805", vint, gnd)
    cap(bulk_cap, "10uF", "0805", gnd, vm)
    cap(bypass_cap, "100nF", "0805", vm, gnd)

    # The B motor is wired reversed (OUT1 to BOUT2), as in rev 1, so the
    # firmware's direction handling depends on it.
    motor_a_ref, motor_b_ref = motors
    for motor_ref, out1, out2 in (
        (motor_a_ref, "AOUT1", "AOUT2"),
        (motor_b_ref, "BOUT2", "BOUT1"),
    ):
        motor = part(
            "hexyhustle", "motor", motor_ref,
            "Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal",
            "S2B-XH-A(LF)(SN)", "JST", "C157931", "~",
        )
        motor["OUT1"] += drv[out1]
        motor["OUT2"] += drv[out2]


@subcircuit
def io_ports(ios, vcc, gnd):
    """Six 3-pin IO ports, one 1x3 header each: pin 1 IO, 2 VCC (5 V), 3 GND.

    330 Ohm series resistors protect the GPIOs from shorts and hot-plugging.
    GPIO22-25 are 5 V tolerant; GPIO26-27 (ADC) are not, so IO5/IO6 must stay
    at 3.3 V logic.
    """
    for n, io in enumerate(ios, start=1):
        pin_net = Net(f"IO{n}")
        res(ref("R"), "330", "0402", io, pin_net)
        j = part(
            "Connector_Generic", "Conn_01x03", ref("J"),
            "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Horizontal",
            "HX PZ2.54-1x3P WZ", "hanxia", "C32713262", f"IO{n}",
        )
        j[1] += pin_net
        j[2] += vcc
        j[3] += gnd


@subcircuit
def status_led(gpio_net, gnd):
    led_a = Net("STATUS_LED_A")
    res(ref("R"), "1k", "0402", gpio_net, led_a)
    led = part(
        "Device", "LED", ref("LED"), "LED_SMD:LED_0603_1608Metric",
        "KT-0603R", "Hubei KENTO Elec", "C2286", "red",
    )
    led["A"] += led_a
    led["K"] += gnd


@subcircuit
def battery_sense(vsys, sense, gnd):
    """VSYS / 4.7 into an ADC pin: 12.6 V reads as about 2.68 V."""
    res(ref("R"), "100k", "0402", vsys, sense)
    res(ref("R"), "27k", "0402", sense, gnd)
    cap(ref("C"), "100nF", "0402", sense, gnd)


# Top level -------------------------------------------------------------------

vbus = Net("VBUS")  # USB-C, 5 V or 9 V (PD)
vbat = Net("VBAT")  # pack, after the fuse
vsys = Net("VSYS")  # pack, after the power switch: motors and buck
vcc = Net("VCC")  # 5 V from the buck
v3v3 = Net("+3V3")
regn = Net("REGN")  # charger's internal 5 V, present while USB is powered
gnd = Net("GND")
for rail in (vbus, vbat, vsys, vcc, v3v3, regn, gnd):
    rail.drive = POWER

# GPIO map (RP2354A, GPIO0-29). Motors sit on GPIO0-11 so each motor's two
# inputs share one PWM slice (slices 0-5). Servos on IO ports use the free
# third PIO block, since GPIO22-27 share PWM slices 3-5 with the motors.
#
#   GPIO0-1   M1 (U1 AIN1/AIN2)      GPIO12  I2C0 SDA (charger)
#   GPIO2-3   M2 (U1 BIN1/BIN2)      GPIO13  I2C0 SCL (charger)
#   GPIO4-5   M3 (U2 AIN1/AIN2)      GPIO14  charger /INT
#   GPIO6-7   M4 (U2 BIN1/BIN2)      GPIO15  driver nSLEEP (all three)
#   GPIO8-9   M5 (U3 AIN1/AIN2)      GPIO16  USB-A D+ (PIO-USB)
#   GPIO10-11 M6 (U3 BIN1/BIN2)      GPIO17  USB-A D- (PIO-USB, D+ + 1)
#   GPIO18    USB-A VBUS enable      GPIO19  driver nFAULT (wired-OR)
#   GPIO20    status LED             GPIO21  spare
#   GPIO22-25 IO1-IO4 (5 V tolerant) GPIO26-27 IO5-IO6 (ADC0-1, 3.3 V only)
#   GPIO28    battery sense (ADC2)   GPIO29  spare (ADC3)
GPIO_NETS = {
    12: "I2C_SDA", 13: "I2C_SCL", 14: "CHG_INT", 15: "DRV_SLEEP",
    16: "USBA_DP_GPIO", 17: "USBA_DM_GPIO", 18: "USBA_VBUS_EN", 19: "DRV_FAULT",
    20: "STATUS_LED", 22: "IO1_GPIO", 23: "IO2_GPIO", 24: "IO3_GPIO",
    25: "IO4_GPIO", 26: "IO5_GPIO", 27: "IO6_GPIO", 28: "BAT_SENSE",
}
gpio = {n: Net(f"GPIO{n}_M{n // 2 + 1}{'AB'[n % 2]}") for n in range(12)}
gpio.update({n: Net(name) for n, name in GPIO_NETS.items()})
for n in (14, 19):  # open-drain outputs into GPIO inputs, with pull-ups
    gpio[n].do_erc = False

usb_dp, usb_dm = Net("USB_DP"), Net("USB_DM")

usb_c_port(vbus, usb_dp, usb_dm, v3v3, gnd)
charger_3s(vbus, vbat, regn, gpio[13], gpio[12], gpio[14], v3v3, gnd)
battery_and_switch(vbat, vsys, gnd)
buck_5v(vsys, vcc, gnd)
rail_3v3(vbus, vcc, v3v3, gnd)
mcu(v3v3, gnd, usb_dp, usb_dm, gpio)
usb_a_host(gpio[16], gpio[17], gpio[18], vcc, gnd)
status_led(gpio[20], gnd)
battery_sense(vsys, gpio[28], gnd)
res(ref("R"), "10k", "0402", v3v3, gpio[19])  # nFAULT pull-up

for drv_ref, base, motors, caps in (
    ("U1", 0, ("M1", "M2"), ("C2", "C3", "C4")),
    ("U2", 4, ("M3", "M4"), ("C9", "C6", "C7")),
    ("U3", 8, ("M5", "M6"), ("C13", "C10", "C11")),
):
    motor_driver(drv_ref, gpio[15], gpio[19], *(gpio[base + i] for i in range(4)),
                 vsys, gnd, motors=motors, caps=caps)

io_ports([gpio[n] for n in (22, 23, 24, 25, 26, 27)], vcc, gnd)


if __name__ == "__main__":
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
