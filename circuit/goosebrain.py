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
    ("27", "0603"): ("0603WAF270JT5E", UNIROYAL, "C25190"),  # Preferred
    ("33", "0402"): ("0402WGF330JTCE", UNIROYAL, "C25105"),
    ("100", "0402"): ("0402WGF1000TCE", UNIROYAL, "C25076"),
    ("330", "0402"): ("0402WGF3300TCE", UNIROYAL, "C25104"),
    ("1k", "0402"): ("0402WGF1001TCE", UNIROYAL, "C11702"),
    ("2.2k", "0402"): ("0402WGF2201TCE", UNIROYAL, "C25879"),
    ("4.7k", "0402"): ("0402WGF4701TCE", UNIROYAL, "C25900"),
    ("5.1k", "0402"): ("0402WGF5101TCE", UNIROYAL, "C25905"),
    ("5.23k", "0402"): ("0402WGF5231TCE", UNIROYAL, "C25907"),
    ("6.8k", "0402"): ("0402WGF6801TCE", UNIROYAL, "C25917"),
    ("10k", "0402"): ("0402WGF1002TCE", UNIROYAL, "C25744"),
    ("7.5k", "0402"): ("0402WGF7501TCE", UNIROYAL, "C25918"),  # Preferred
    ("15k", "0402"): ("0402WGF1502TCE", UNIROYAL, "C25756"),
    ("27k", "0402"): ("0402WGF2702TCE", UNIROYAL, "C25771"),
    ("30.1k", "0402"): ("0402WGF3012TCE", UNIROYAL, "C29402"),
    ("39k", "0402"): ("0402WGF3902TCE", UNIROYAL, "C25783"),  # Preferred
    ("33k", "0402"): ("0402WGF3302TCE", UNIROYAL, "C25779"),
    ("100k", "0402"): ("0402WGF1003TCE", UNIROYAL, "C25741"),
    ("200k", "0402"): ("0402WGF2003TCE", UNIROYAL, "C25764"),
    ("470k", "0402"): ("0402WGF4703TCE", UNIROYAL, "C25790"),
    ("1M", "0402"): ("0402WGF1004TCE", UNIROYAL, "C26083"),
    ("15pF", "0402"): ("0402CG150J500NT", FENGHUA, "C1548"),
    ("1nF", "0402"): ("0402B102K500NT", FENGHUA, "C1523"),
    ("4.7nF", "0402"): ("0402B472K500NT", FENGHUA, "C1538"),
    ("100nF", "0402"): ("CL05B104KO5NNNC", SAMSUNG, "C1525"),
    ("1uF", "0402"): ("CL05A105KA5NQNC", SAMSUNG, "C52923"),  # 25 V
    ("4.7uF", "0402"): ("CL05A475MP5NRNC", SAMSUNG, "C23733"),  # 10 V
    ("47nF", "0603"): ("0603B473K500NT", FENGHUA, "C1622"),  # 50 V
    ("1uF", "0603"): ("CL10A105KB8NNNC", SAMSUNG, "C15849"),  # 50 V (basic)
    ("2.2uF", "0603"): ("CL10A225KO8NNNC", SAMSUNG, "C23630"),  # 16 V
    ("4.7uF", "0603"): ("CL10A475KO8NNNC", SAMSUNG, "C19666"),  # 16 V
    ("10uF", "0603"): ("CL10A106KP8NNNC", SAMSUNG, "C19702"),  # 10 V
    ("100nF", "0805"): ("CC0805KRX7R9BB104", "YAGEO", "C49678"),  # 50 V
    ("10uF", "0805"): ("CL21A106KAYNNNE", SAMSUNG, "C15850"),  # 25 V
    ("22uF", "1206"): ("CL31A226KPHNNNE", SAMSUNG, "C5672"),  # 10 V, Preferred
}
# BOOT switch (side push, top edge); set from the parts search
# Alps SKRTLAE010: Ø2 mm actuator 1.7 mm above the board, 0.2 mm travel, 1.6 N, 100k cycles; the case pinhole
# (3.0-3.2 mm, for the end of a 2.5 mm hex key) is centred on the actuator.
BOOT_SW = {"fp": "hexy:SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010_JLC", "mpn": "SKRTLAE010",
           "mfr": "ALPS Electric", "lcsc": "C110293"}
R_FP = "Resistor_SMD:R_{0}_{1}Metric"
C_FP = "Capacitor_SMD:C_{0}_{1}Metric"
METRIC = {"0402": "1005", "0603": "1608", "0805": "2012", "1206": "3216"}


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
ref = Refs(C=17, R=29, U=5, L=2, D=1, Q=1, F=1, J=1, SW=1, LED=1, TP=1, Y=1, TH=1, FID=1)


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
        # SHOU HAN TYPE-C16PIN: same pegs, tabs and mouth as the HRO part; its
        # 1.15 mm pads match the GCT USB4105 land pattern (outer GND pads
        # trimmed 0.1 mm for hole clearance to the pegs).
        "hexy:USB_C_Receptacle_ShouHan_TYPE-C16PIN",
        "TYPE-C16PIN", "SHOU HAN", "C393939",
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
        "SMBJ20A", "hongjiacheng", "C19077575", "SMBJ20A",  # unidirectional, Preferred
    )
    tvs["A1"] += vbus
    tvs["A2"] += gnd

    # SRV05-4: four steering-diode channels, two per line, on the USBLC6-2SC6
    # pinout (1/6 and 3/4 paired, 5 VP, 2 VN). About 2 pF per line.
    esd = part(
        "hexyhustle", "SRV05-4", ref("U"), "Package_TO_SOT_SMD:SOT-23-6",
        "SRV05-4", "hongjiacheng", "C7420376", "SRV05-4",
    )
    esd["IO1", "IO4"] += usb_dp
    esd["IO2", "IO3"] += usb_dm
    esd["VP"] += v3v3  # 5 V working voltage: never tie to PD VBUS
    esd["VN"] += gnd


@subcircuit
def charger_3s(vbus, vbat, regn, i2c_scl, i2c_sda, chg_int, v3v3, gnd):
    """BQ25798 buck-boost charger for the internal 3S pack.

    Safe with no firmware: PROG selects 3S (12.6 V) at 750 kHz, the TS divider
    holds TS at the 25 C point (fixed 10k, no pack NTC), and the ILIM_HIZ divider
    caps input current at about 0.30 A, so charge current stays near 0.2 A, about
    0.45C of the 450 mAh pack, from 9 V (and lower from 5 V) even though the power-on charge
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
        # 2.2 uH for 750 kHz; Isat 4.9 A, Irms 2.95 A, DCR 39 mOhm max
        "Device", "L", ref("L"), "Inductor_SMD:L_Changjiang_FNR4030S",
        "FNR4030S2R2MT", "Changjiang Microelectronics", "C167869", "2.2uH",
    )
    inductor[1] += sw1
    inductor[2] += sw2
    btst1, btst2 = Net("CHG_BTST1"), Net("CHG_BTST2")
    u["BTST1"] += btst1
    u["BTST2"] += btst2
    cap(ref("C"), "47nF", "0603", btst1, sw1)  # 0603: the 0402 47 nF is low-stock and extended
    cap(ref("C"), "47nF", "0603", btst2, sw2)

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
    # 3S, 750 kHz needs 13.7k (datasheet Table 7-1). Two Preferred 6.8k in series give 13.6k,
    # 13.46-13.74k worst case: inside the +/-2% TI allows, and far from the 10.5k and 17.4k
    # settings either side (TI publishes no decode windows). Read REG0x0A CELL on the first
    # board (must be 3S).
    prog_mid = Net("CHG_PROG_MID")
    res(ref("R"), "6.8k", "0402", prog, prog_mid)
    res("R78", "6.8k", "0402", prog_mid, gnd)  # added part: fresh ref, so later refs don't shift

    ilim = Net("CHG_ILIM")
    u["ILIM_HIZ"] += ilim
    res(ref("R"), "100k", "0402", regn, ilim)  # 1.24 V -> ~0.30 A input limit
    res(ref("R"), "33k", "0402", ilim, gnd)

    ts = Net("CHG_TS")
    u["TS"] += ts
    # TI's 0/60 C divider for a 103AT (5.23k REGN-TS, 30.1k TS-GND). There is
    # no pack thermistor (user decision: packs are used indoors at low stress),
    # so a fixed 10k (R81) sits where the NTC was, i.e. the NTC at 25 C:
    #   TS = 30.1k || 10k = 7.506k;  7.506 / (5.23 + 7.506) = 58.9 % of REGN.
    # That is between T3 (warm, 44.8 %) and T2 (cool, 68.4 %), so the charger
    # always sees the normal zone: full charge current and voltage, JEITA never
    # steps in, no firmware needed. The pack is still protected by the
    # BQ7791501 (OV/UV/OC/SC) and TH1 keeps watching the protector's FETs.
    res(ref("R"), "5.23k", "0402", regn, ts)
    res(ref("R"), "30.1k", "0402", ts, gnd)
    ref("J")  # J2 burned: the NTC bead pads were removed
    res("R81", "10k", "0402", ts, gnd)  # fixed "25 C" in place of the NTC

    # Charge LED on STAT: lit while charging, with no firmware involved. A
    # side-view LED on the top edge, shining out through a small hole in the
    # wall (no side-view LED at JLC is basic). 2.2k from REGN gives about 1.3 mA.
    stat, stat_led = Net("CHG_STAT"), Net("CHG_STAT_LED")
    u["STAT"] += stat
    res(ref("R"), "2.2k", "0402", regn, stat_led)
    led = part(
        "Device", "LED", ref("LED"), "hexy:LED_Everlight_27-21_SideView",
        "27-21SYGC/S530-E3/TR8", "Everlight Elec", "C74270", "green",
    )
    led["A"] += stat_led
    led["K"] += stat

    for line in (i2c_scl, i2c_sda, chg_int):
        res(ref("R"), "10k", "0402", v3v3, line)


@subcircuit
def battery_and_switch(vbat, vsys, bat_n, gnd):
    """Pack connector, fuse and the main power switch.

    The slide switch only drives the P-FET gate; motor current flows through
    the FET. Charging works with the switch off, since the charger connects to
    VBAT ahead of it.
    """
    # Pack connector: a vertical male XT30 (Amass XT30UPB-M) on top beside the
    # pack's lead end; the pack's female XT30U-F plugs straight in. Pin 1 is
    # "-" at the keyed (chamfered) end: the pack's negative, which goes to the
    # protector's low side (BAT_N), not board GND. Pin 2 is "+" (PACK+).
    # Mated with the lead bent toward the pack it stands about 22-24 mm, close
    # to the face (23.4 mm): see PARTS.md.
    j = part(
        "Connector_Generic", "Conn_01x02", ref("J"),
        "hexy:AMASS_XT30UPB-M_1x02_P5.0mm_Vertical_EasyEDA3D",
        "XT30UPB-M", "Changzhou Amass Elec", "C428721", "XT30UPB-M",
    )
    pack = Net("PACK+")
    j[2] += pack
    j[1] += bat_n

    fuse = part(
        "Device", "Fuse", ref("F"), "Fuse:Fuse_Littelfuse-NANO2-451_453",
        # Very fast-acting. The cheaper JFC2410-2150TS (C136393) was rejected:
        # it is time-lag, about 7-15x slower at 30-50 A, with 2.4x the I2t.
        "0453015.MR", "Littelfuse", "C178997", "15A fast",
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
        # THT, rated 50 V (the SMD MSK12C02 was rated 12 V and sees 12.6 V).
        # The lever reaches 4 mm past the board edge: the box needs a slot.
        "Switch", "SW_SPDT", ref("SW"), "hexy:SW_SPDT_ShouHan_SK12D07VG4",
        "SK12D07VG4", "SHOU HAN", "C393937", "Power",
    )
    sw_on = Net("PWR_SW_ON")
    switch["B"] += gate  # common
    switch["A"] += sw_on  # on: gate pulled to GND
    switch["C"] += NC  # off
    res(ref("R"), "1k", "0402", sw_on, gnd)


@subcircuit
def buck_5v(vin, vcc, gnd):
    """AP64500 buck converter, pack to 5 V (datasheet DS41979 equations).

    Vout = 0.8 V * (1 + R26 / R27) = 0.8 * (1 + 39k / 7.5k) = 4.960 V,
    the same as rev 1's 115k / 22.1k (4.963 V); worst case with VFB +/-1% and
    1% resistors is 4.83-5.09 V. The divider now draws 107 uA instead of 36.

    Compensation (Eq. 17/18, gm = 0.15 mS, current sense 0.089 V/A):
    fc = R28 / (4660 * Vout * Cout). With R28 = 15k and 30-45 uF effective
    Cout (3 x 22 uF 10 V at 5 V bias; not measured) fc is 14-22 kHz, under
    fsw / 10 = 45 kHz at the 450 kHz minimum; it stays under that limit
    while Cout > 14.4 uF. The zero 1 / (2 pi R28 C16) is at 2.26 kHz, below
    the full-load output pole (3.6 kHz at 45 uF): about 5 degrees more phase
    margin than rev 1's 15.8k / 2.7 nF, with a slower settling tail
    (R28 * C16 = 70 us) after load steps. The Eq. 18 value for 15k would be
    2-3 nF; 4.7 nF is the basic part. No Cc2 (Eq. 19) is fitted.
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
        "Device", "L", "L1", "Inductor_SMD_Wurth:L_Wurth_WE-LQSH-4020",
        "CR4030-3R6M", "Ceaiya", "C7588667", "3.6uH",
    )
    inductor[1] += sw
    inductor[2] += vcc

    res("R25", "200k", "0402", gnd, u["RT/CLK"])  # switching frequency
    res("R26", "39k", "0402", fb, vcc)  # feedback divider, top
    res("R27", "7.5k", "0402", gnd, fb)  # feedback divider, bottom
    res("R28", "15k", "0402", comp_rc, comp)  # loop compensation
    cap("C16", "4.7nF", "0402", gnd, comp_rc)

    # 22 uF 1206/10 V (5 V is 50% of rating). The rev 1 0603 parts lost most
    # of their capacitance to DC bias at 5 V; Samsung publishes no 5 V curve
    # for this part, so check the output ripple (about 14 mV expected) on
    # the first board.
    for r in ("C5", "C8", "C12"):
        cap(r, "22uF", "1206", vcc, gnd)


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

    # XC6206: 200 mA, 6 V max input, no enable (always on), 250 mV dropout
    # at 100 mA; the RP2354 and its I/O draw well under 100 mA.
    ldo = part(
        "hexyhustle", "XC6206P332MR", ref("U"), "Package_TO_SOT_SMD:SOT-23-3",
        "XC6206P332MR-G", "Torex Semicon", "C5446", "XC6206P332MR",
    )
    ldo["VIN"] += v5_or
    ldo["VOUT"] += v3v3
    ldo["GND"] += gnd
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

    # Core regulator: 3.3 uH polarity-marked inductor between VREG_LX and 1.1 V.
    # The dot (pin 1) goes to +1V1 and pin 2 to VREG_LX, as in Figure 4 of
    # "Hardware design with RP2350".
    u["VREG_AVDD"] += vreg_avdd
    res(ref("R"), "33", "0402", v3v3, vreg_avdd)
    cap(ref("C"), "4.7uF", "0402", vreg_avdd, gnd)
    u["VREG_LX"] += vreg_lx
    core_l = part(
        "Device", "L", ref("L"), "hexy:L_Abracon_AOTA-B201610",
        "AOTA-B201610S3R3-101-T", "Abracon", "C42411119", "3.3uH",
    )
    # Not stocked at JLC: bought from Digi-Key and hand-placed. The schematic
    # and board mark L3 DNP / excluded from BOM and position files, so the
    # JLC BOM and CPL skip it; its pads stay on the board.
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
    u["USB_DP"] += (dp_mcu := Net("USB_MCU_P"))
    u["USB_DM"] += (dm_mcu := Net("USB_MCU_N"))
    res(ref("R"), "27", "0603", dp_mcu, usb_dp)  # 27 Ohm per Raspberry Pi (not 22)
    res(ref("R"), "27", "0603", dm_mcu, usb_dm)

    # BOOTSEL on QSPI_SS through 1 kOhm (per the RPi design). There is no
    # RESET button: RUN has the chip's internal pull-up (RP2350 datasheet; the
    # hardware guide's external parts on RUN are optional) and a test pad, TP3,
    # beside the SWD pads, so a debugger can still reset the chip.
    qspi_ss, boot_r = Net("QSPI_SS"), Net("BOOTSEL_R")
    u["~{QSPI_SS}"] += qspi_ss
    u["QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3", "QSPI_SCLK"] += NC
    res(ref("R"), "1k", "0402", qspi_ss, boot_r)
    run = Net("RUN")
    u["RUN"] += run
    ref("R")  # R47 burned (the RESET button's 1 kOhm)
    # BOOT: side-push tactile switch on the top edge, pressed through a pinhole
    # in the case with the end of a 2.5 mm hex key.
    sw = part(
        "Switch", "SW_Push", ref("SW"), BOOT_SW["fp"], BOOT_SW["mpn"], BOOT_SW["mfr"], BOOT_SW["lcsc"], "BOOT",
    )
    sw[1] += boot_r
    sw[2] += gnd
    ref("SW")  # SW3 burned (RESET removed)

    # SWD test pads for factory programming and debugging, plus RUN and GND
    # (TP3/TP4), all on the bottom side so a debugger can clip on with the pack
    # still fitted.
    for name in ("SWCLK", "SWDIO"):
        net = Net(name)
        u[name] += net
        tp = part(
            "Connector", "TestPoint", ref("TP"), "TestPoint:TestPoint_Pad_D1.0mm",
            "", "", "", name,
        )
        tp[1] += net
    for tp_ref, name, net in (("TP3", "RUN", run), ("TP4", "GND", gnd)):
        tp = part("Connector", "TestPoint", tp_ref, "TestPoint:TestPoint_Pad_D1.0mm", "", "", "", name)
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
    usba_dp, usba_dm, usba_vbus = Net("USBA_P"), Net("USBA_N"), Net("USBA_VBUS")
    res(ref("R"), "22", "0402", dp_gpio, usba_dp)
    res(ref("R"), "22", "0402", dm_gpio, usba_dm)

    esd = part(
        "hexyhustle", "SRV05-4", ref("U"), "Package_TO_SOT_SMD:SOT-23-6",
        "SRV05-4", "hongjiacheng", "C7420376", "SRV05-4",
    )
    esd["IO1", "IO4"] += usba_dp
    esd["IO2", "IO3"] += usba_dm
    esd["VP"] += vcc  # 4.96 V, at the 5 V working voltage (VBR 6 V min)
    esd["VN"] += gnd

    switch = part(
        "hexyhustle", "SY6280AAC", ref("U"), "Package_TO_SOT_SMD:SOT-23-5",
        "SY6280AAC", "Silergy Corp", "C55136", "SY6280AAC",
    )
    switch["IN"] += vcc
    switch["EN"] += vbus_en  # active high, must not float
    switch["OUT"] += usba_vbus
    switch["GND"] += gnd
    iset = Net("USBA_ISET")
    switch["ISET"] += iset
    res(ref("R"), "100k", "0402", vbus_en, gnd)  # off while the MCU boots
    # Ilim = 6800 / Rset = 0.68 A nominal (about 0.51-0.85 A, scaling the
    # datasheet's +/-25% at 6.8k); the USB-A dongle draws well under 0.5 A.
    res("R79", "10k", "0402", iset, gnd)  # added part: fresh ref
    cap(ref("C"), "1uF", "0402", vcc, gnd)
    cap(ref("C"), "10uF", "0805", usba_vbus, gnd)  # same basic line as the 10 uF bulk caps
    cap(ref("C"), "100nF", "0402", usba_vbus, gnd)

    j = part(
        "Connector", "USB_A", ref("J"), "hexy:USB_A_ShouHan_AF90_WJDG",
        "AF 90 WJDG", "SHOU HAN", "C456018", "USB-A host",
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
    cap(vint_cap, "2.2uF", "0603", vint, gnd)
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
    """Six 3-pin IO ports on one 3 x 6 right-angle header (J5) at the board's left end.

    Pins point out through the left wall. Per port: GND on the row nearest the
    wall (the lowest mating pin), 5V in the middle, SIG on the inner row (the
    top pin), so a plug put in upside down only swaps SIG and GND. One 6-unit
    symbol (hexyhustle:IO_3x6_RA), unit k = port k: SIG pin 3k, 5V 3k-1,
    GND 3k-2. Refs stay stable: J6-J10 are burned.

    330 Ohm series resistors protect the GPIOs from shorts and hot-plugging.
    IO1-IO4 are on 5 V tolerant GPIOs; IO5/IO6 are on GPIO26/27 (ADC), which
    are not, so IO5/IO6 must stay at 3.3 V logic.
    """
    j = None
    for n, io in enumerate(ios, start=1):
        pin_net = Net(f"IO{n}")
        res(ref("R"), "330", "0402", io, pin_net)
        if j is None:
            j = part(
                "hexyhustle", "IO_3x6_RA", ref("J"), "hexy:PinHeader_3x06_P2.54mm_Horizontal_WingTAT",
                "2011-3X06G00RB", "WingTAT", "C51953246", "IO 3x6 RA",
            )
        else:
            ref("J")  # J6-J10 burned: one header now
        j[3 * n] += pin_net
        j[3 * n - 1] += vcc
        j[3 * n - 2] += gnd


@subcircuit
def led_stick(din, vcc, gnd):
    """Connector for an off-board WS2812B stick (DIYmall 8 x 5050), on the case's top edge.

    WS2812B wants VIH >= 0.7 * VDD = 3.5 V at 5 V, so a 74AHCT1G125 (TTL
    inputs, VIH 2.0 V, 5 V supply) lifts the RP2354's 3.3 V PIO output to
    5 V. 330 Ohm in series at the cable damps ringing and limits current into
    the first LED's input. The stick runs from VCC (the 5 V buck): 8 LEDs at
    full white draw up to about 0.5 A of the rail's roughly 2.3 A, so
    firmware should cap brightness.
    Refs are explicit: the sequential counters would reuse R78/R79.
    """
    buf = part(
        "74xGxx", "74AHCT1G125", "U14", "Package_TO_SOT_SMD:SOT-23-5",
        "SN74AHCT1G125DBVR", "UMW", "C20617903", "74AHCT1G125",
    )
    din_5v, din_j = Net("LED_DIN_5V"), Net("LED_DIN_J")
    buf[1] += gnd  # /OE: always driving
    buf[2] += din  # A, from GPIO18
    buf[3] += gnd
    buf[4] += din_5v  # Y
    buf[5] += vcc
    cap("C69", "100nF", "0402", vcc, gnd)  # U14 supply
    res("R80", "330", "0402", din_5v, din_j)
    j = part(
        "Connector_Generic", "Conn_01x03", "J12",
        "Connector_JST:JST_PH_B3B-PH-K_1x03_P2.00mm_Vertical",
        "B3B-PH-K-S(LF)(SN)", "JST", "C131339", "LED stick",
    )
    j[1] += vcc  # 5V
    j[2] += din_j  # DIN
    j[3] += gnd
    cap("C70", "10uF", "0805", vcc, gnd)  # bulk at the connector


@subcircuit
def battery_sense(vsys, sense, gnd):
    """VSYS / 4.7 into an ADC pin: 12.6 V reads as about 2.68 V."""
    # On VSYS, after the power switch, so the divider drains nothing when the
    # switch is off. With the switch off, read the pack from the BQ25798 ADC.
    res(ref("R"), "100k", "0402", vsys, sense)
    res(ref("R"), "27k", "0402", sense, gnd)
    cap(ref("C"), "100nF", "0402", sense, gnd)


@subcircuit
def pack_protection(pack, bat_n, gnd):
    """BQ7791501 standalone 3S primary protector with low-side CHG/DSG FETs.

    The pack (Ovonic 80C 3S 450 mAh) has no protection board, so the board protects it. Wired
    as the datasheet's 3-series configuration (Figure 9-11) and design example:
    CCFG, CTRC, CTRD and CBI to VSS (3 cells, no stack, balancing on), PRES
    pulled high (HIBERNATE off), CBO and LPWR open.

    BQ7791501 thresholds: OV 4.25 V, UV 2.8 V, OCD1 35 mV, OCD2 60 mV, SCD
    120 mV, OCC 20 mV; OTD 70 C / OTC 50 C / UTD -20 C / UTC 0 C. With the
    2.5 mOhm shunt (two 5 mOhm in parallel): OCD1 14 A, OCD2 24 A, SCD 48 A,
    charge OC 8 A. ROCD 100 kOhm (1 %) selects the EEPROM OCD delays (180 ms).

    Ground: VSS and the cell taps are the pack's own negative (bat_n). Board
    GND is PACK-, after the back-to-back FETs (cell- -> shunt -> DSG FET ->
    CHG FET -> GND). Balancing runs through the balance lead (RIN 100 Ohm,
    about 20 mA).
    """
    bal = part(
        "Connector_Generic", "Conn_01x04", ref("J"),
        "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical",
        "B4B-XH-A(LF)(SN)", "JST", "C144395", "Balance",
    )
    cell = [Net(f"CELL{k}") for k in range(4)]  # balance taps: 0 = cell 1 -, 3 = cell 3 +
    for k in range(4):
        bal[k + 1] += cell[k]
    u = part(
        "hexyhustle", "BQ77915", ref("U"), "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
        "BQ7791501PWR", "Texas Instruments", "C2876947", "BQ7791501",
    )
    vdd = Net("PROT_VDD")
    vdd.drive = POWER  # fed from PACK+ through the RVDD filter
    u["VDD"] += vdd
    u["VSS"] += bat_n
    res(ref("R"), "1k", "0402", pack, vdd)
    cap(ref("C"), "1uF", "0402", vdd, bat_n)
    avdd = Net("PROT_AVDD")
    u["AVDD"] += avdd
    cap(ref("C"), "1uF", "0402", avdd, bat_n)
    # Cell inputs: VC3-VC5 together on the top cell (3-series), RIN/CIN filters.
    vc = [Net(f"PROT_VC{k}") for k in range(4)]
    u["VC0"] += vc[0]
    u["VC1"] += vc[1]
    u["VC2"] += vc[2]
    u["VC3", "VC4", "VC5"] += vc[3]
    for k in range(4):
        res(ref("R"), "100", "0402", cell[k], vc[k])
    for k in range(3):
        cap(ref("C"), "1uF", "0402", vc[k + 1], vc[k])
    cap(ref("C"), "1uF", "0402", vc[0], bat_n)
    # Current sense: 2 x 5 mOhm 2512 in parallel, Kelvin-filtered into SRP/SRN.
    sns = Net("PROT_SNS")  # shunt, FET side
    for _ in range(2):
        part("Device", "R", ref("R"), "Resistor_SMD:R_2512_6332Metric",
             "LRBM25GFER005", "NCT", "C5121087", "5m")[1, 2] += bat_n, sns  # 3 W, 1 %
    srp, srn = Net("PROT_SRP"), Net("PROT_SRN")
    u["SRP"] += srp
    u["SRN"] += srn
    res(ref("R"), "100", "0402", bat_n, srp)
    res(ref("R"), "100", "0402", sns, srn)
    cap(ref("C"), "100nF", "0402", srp, srn)
    # Back-to-back N-FETs: DSG (source on the shunt side), then CHG (source on PACK-).
    mid = Net("PROT_FET_D")
    dsg_g, chg_g = Net("PROT_DSG_G"), Net("PROT_CHG_G")
    for g, src, pin, rg in ((dsg_g, sns, "DSG", "4.7k"), (chg_g, gnd, "CHG", "1k")):
        q = part(
            "Transistor_FET", "BSC026N08NS5", ref("Q"), "Package_TO_SOT_SMD:TDSON-8-1",
            "80N03F", "HL", "C7471104", "80N03F",  # PDFN5x6: 1-3 S, 4 G, 5-8 D (datasheet pin table)
        )
        q["G"] += g
        q["S"] += src
        q["D"] += mid
        drv = Net(f"PROT_{pin}")
        u[pin] += drv
        res(ref("R"), rg, "0402", drv, g)
        res(ref("R"), "1M", "0402", g, src)
    res(ref("R"), "470k", "0402", u["LD"], gnd)  # load-removal detect on PACK-
    for name in ("CTRC", "CTRD", "CCFG", "CBI"):
        u[name] += bat_n
    res(ref("R"), "10k", "0402", vdd, u["PRES"])  # HIBERNATE off
    res(ref("R"), "100k", "0402", u["OCDP"], bat_n)  # OCD delays from EEPROM (180 ms)
    u["CBO", "LPWR"] += NC
    # Temperature: 10 kOhm pull-up from VTB, 0603 NTC by the FETs (board/FET heat).
    ts = Net("PROT_TS")
    u["TS"] += ts
    res(ref("R"), "10k", "0402", u["VTB"], ts)
    part("Device", "Thermistor_NTC", ref("TH"), "Resistor_SMD:R_0603_1608Metric",
         "NCP18XH103F03RB", "Murata", "C13564", "10k B3434")[1, 2] += ts, bat_n
    # Assembly fiducials (top side).
    for _ in range(3):
        part("Mechanical", "Fiducial", ref("FID"), "Fiducial:Fiducial_1mm_Mask2mm", "", "")


# Top level -------------------------------------------------------------------

vbus = Net("VBUS")  # USB-C, 5 V or 9 V (PD)
vbat = Net("VBAT")  # pack, after the fuse
vsys = Net("VSYS")  # pack, after the power switch: motors and buck
vcc = Net("VCC")  # 5 V from the buck
v3v3 = Net("+3V3")
regn = Net("REGN")  # charger's internal 5 V, present while USB is powered
gnd = Net("GND")  # board ground = PACK-, after the protection FETs
bat_n = Net("BAT_N")  # the pack's negative, before the protection FETs
for rail in (vbus, vbat, vsys, vcc, v3v3, regn, gnd, bat_n):
    rail.drive = POWER

# GPIO map (RP2354A, GPIO0-29), chosen in the PCB layout so each signal leaves
# U10 on the side facing its destination (pin-swap pass redone again on
# 2026-10-17, after the IO ports moved to the left end; IO1-IO4 reordered for the
# recessed header so U10's pin order matches S1-S6). Each motor's two inputs are one PWM slice's
# A/B pair (n even, n + 1), and the six motors use six different slices. "A/B
# swapped" means the motor's IN1 is on the odd GPIO (PWM channel B); the
# firmware maps direction per motor.
#
#   GPIO0-1   M3 (U2 AIN1/AIN2)                GPIO14-15 M4 (U2 BIN1/BIN2)
#   GPIO2     USB-A D+ (PIO-USB)               GPIO16  IO1
#   GPIO3     USB-A D- (PIO-USB, D+ + 1)       GPIO17  I2C0 SCL (charger)
#   GPIO4-5   M1 (U1 AIN1/AIN2)                GPIO18  LED stick data (PIO WS2812)
#   GPIO6-7   M2 (U1 BIN2/BIN1, A/B swapped)   GPIO19  driver nFAULT (wired-OR)
#   GPIO8     I2C0 SDA (charger)               GPIO20  spare
#   GPIO9     charger /INT                     GPIO21  IO2
#   GPIO10-11 M5 (U3 AIN1/AIN2)                GPIO22  IO3
#   GPIO12-13 M6 (U3 BIN2/BIN1, A/B swapped)   GPIO23  driver nSLEEP (all three)
#   GPIO24    IO4                              GPIO25  USB-A VBUS enable
#   GPIO26-27 IO5, IO6 (ADC0-1, 3.3 V only)    GPIO28  battery sense (ADC2)
#   GPIO29    spare (ADC3)
#
# PWM slices: M3 0, M1 2, M2 3, M5 5, M6 6, M4 7. IO1-IO4 are 5 V tolerant
# (GPIO0-25); servos on the IO ports run from PIO.
MOTOR_GPIO = {  # motor -> (IN1 GPIO, IN2 GPIO); the net is GPIO<n>_<motor><A|B>
    "M1": (4, 5), "M2": (7, 6), "M3": (0, 1),
    "M4": (14, 15), "M5": (10, 11), "M6": (13, 12),
}
GPIO_NETS = {
    2: "USBA_GPIO_P", 3: "USBA_GPIO_N", 8: "I2C_SDA", 9: "CHG_INT", 16: "IO1_GPIO",
    17: "I2C_SCL", 18: "LED_DIN", 19: "DRV_FAULT", 21: "IO2_GPIO",
    22: "IO3_GPIO", 23: "DRV_SLEEP", 24: "IO4_GPIO", 25: "USBA_VBUS_EN",
    26: "IO5_GPIO", 27: "IO6_GPIO", 28: "BAT_SENSE",
}
GP = {name: n for n, name in GPIO_NETS.items()}  # signal name -> GPIO number
gpio = {n: Net(f"GPIO{n}_{m}{ab}") for m, pins in MOTOR_GPIO.items() for n, ab in zip(pins, "AB")}
gpio.update({n: Net(name) for n, name in GPIO_NETS.items()})
for name in ("CHG_INT", "DRV_FAULT"):  # open-drain outputs into GPIO inputs, with pull-ups
    gpio[GP[name]].do_erc = False
motor_in = {m: (gpio[a], gpio[b]) for m, (a, b) in MOTOR_GPIO.items()}
sig = lambda name: gpio[GP[name]]

usb_dp, usb_dm = Net("USB_P"), Net("USB_N")  # P/N names: KiCad diff-pair router

usb_c_port(vbus, usb_dp, usb_dm, v3v3, gnd)
charger_3s(vbus, vbat, regn, sig("I2C_SCL"), sig("I2C_SDA"), sig("CHG_INT"), v3v3, gnd)
battery_and_switch(vbat, vsys, bat_n, gnd)
buck_5v(vsys, vcc, gnd)
rail_3v3(vbus, vcc, v3v3, gnd)
mcu(v3v3, gnd, usb_dp, usb_dm, gpio)
usb_a_host(sig("USBA_GPIO_P"), sig("USBA_GPIO_N"), sig("USBA_VBUS_EN"), vcc, gnd)
ref("R"); ref("LED")  # R51 and LED2 burned: the GPIO status LED was removed (the LED stick shows status)
battery_sense(vsys, sig("BAT_SENSE"), gnd)
res(ref("R"), "10k", "0402", v3v3, sig("DRV_FAULT"))  # nFAULT pull-up

for drv_ref, motors, caps in (
    ("U1", ("M1", "M2"), ("C2", "C3", "C4")),
    ("U2", ("M3", "M4"), ("C9", "C6", "C7")),
    ("U3", ("M5", "M6"), ("C13", "C10", "C11")),
):
    motor_driver(drv_ref, sig("DRV_SLEEP"), sig("DRV_FAULT"), *motor_in[motors[0]], *motor_in[motors[1]],
                 vsys, gnd, motors=motors, caps=caps)

io_ports([sig(f"IO{k}_GPIO") for k in range(1, 7)], vcc, gnd)
pack_protection(Net.get("PACK+"), bat_n, gnd)  # last, so earlier references stay put
led_stick(sig("LED_DIN"), vcc, gnd)  # added after rev 2 layout: explicit refs U14, J12, R80, C69, C70


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
