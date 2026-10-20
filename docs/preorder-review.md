# goosebrain rev 2 brain: pre-order electrical review

Date: 2026-10-20. Scope: `kicad/thegoose.kicad_sch` / `kicad/thegoose.kicad_pcb` as of commit `c7baa78`, plus `build/fab/jlc_bom.csv` and `jlc_cpl.csv`. This was a read-only review: no project files were changed.

**Method.**
- The netlist was exported fresh with `kicad-cli sch export netlist` and dumped pin by pin.
- Pad positions, zones and tracks were read from the PCB with KiCad's pcbnew Python.
- Each part was checked against its datasheet:
  - TI SLVSFU6 (DRV8251A)
  - Diodes DS41979 rev 5-2 (AP64500)
  - the RP2350 datasheet and "Hardware design with RP2350"
  - Torex XC6206
  - Hongjiacheng SRV05-4 rev 2.1
  - the ShouHan TYPE-C16PIN, AF 90 WJDG and SK12D07VG4 drawings
  - Abracon AOTA-B201610S3R3-101-T rev A
  - Alps SKRTLAE010
  - UMW AO4407A
  - Littelfuse SMF series
- The LCSC PDFs are the ones linked from each part's LCSC page.

**Bottom line:** there is no netlist-level pin error that would need a respin. Every custom symbol and footprint I could check against a drawing matches. The real risk is **the RP2354's core regulator layout**, which breaks several of Raspberry Pi's explicit layout requirements (finding 1). After that come two things that only JLC's placement preview, or the parts themselves, can settle (findings 2 and 3).

---

## Findings, most severe first

### 1. HIGH: the RP2354 core SMPS layout ignores RPi's required arrangement (C_IN, C_OUT, FB, layer-2 cut-out)

RP2350 datasheet §6.3.8.1, "Layout recommendations" (pp. 411–412, Figures 26 and 27), and §6.3.8.2:
- "Don't place any of C_IN/L_X/C_OUT on the opposite side of the PCB."
- C_IN is ≥ 4.7 µF and goes right at VREG_VIN, with its own GND path to the QFN pad.
- "The VREG_FB pin should be fed from the output of C_OUT."
- "For a multi-layer board … cut away any copper immediately underneath L_X/VREG_LX node."

"Hardware design with RP2350" §2.1 adds that the regulator "needs to be treated in exactly the right way to keep it producing the correct output voltage under a range of load current conditions", and that other layouts are at your own risk.

What the board has:

| Item | RPi requirement | This board |
|---|---|---|
| C_IN (4.7 µF at VREG_VIN pin 49) | Same side as L3, between VREG_VIN and VREG_PGND | **There is no 4.7 µF near pin 49.** Pin 49 (124.55, 112.20) drops straight through a via at (124.55, 113.25) into the In3 +3V3 area. The only 4.7 µF on +3V3, **C50**, is on **B.Cu at (118.85, 117.75)**: the opposite side of the chip, about 8 mm away, on the back. The nearest local cap is C45 (100 nF, back, at the IOVDD 44/45 corner). |
| C_OUT (4.7 µF on +1V1) | Same side as L3, tight loop L3 → C_OUT → VREG_PGND | **C52 is on B.Cu at (130.35, 113.09).** It is reached through a via-in-pad at L3 pad 1 (130.35, 112.61). Its GND return reaches VREG_PGND (pin 47) through the planes. |
| VREG_FB (pin 50) | Tapped at C_OUT | Pin 50 joins the DVDD network on F.Cu/In2 (via 123.57, 113.25 → In2 → via 125.40, 114.90). It reaches C52/L3 only through about 6 mm of 0.2 mm B.Cu track (126.42, 115.83 → 131.03, 114.12 → C52). So FB senses at the DVDD pins, after that resistance and inductance. |
| Under L3 / VREG_LX | Copper cut away on layer 2 | A fill check at L3's centre (129.35, 111.44) and along the LX trace (126.5, 111.44) finds solid **In1 GND, In2 GND, In3 +3V3, In4 GND and B.Cu GND**. There is no cut-out. |
| VREG_AVDD RC | 33 Ω + 4.7 µF | R42 33 Ω, C51 4.7 µF: OK (both on the back, short) |

**Effect:** the regulator may well start (the default is 1.1 V at a few tens of mA), but RPi's own testing found that a layout like this lets the output voltage drift or misbehave at higher load currents and load transients. On the bench that looks like random crashes under load or at higher clocks, or USB dropouts. It is the most likely bring-up problem on this board, and you can't bodge it on a populated QFN.

**Fix before ordering:**
- Copy Figure 26 onto F.Cu: L3, then a 4.7 µF C_OUT and a 4.7 µF C_IN (0402), all on the front, as in the Pico 2 regulator layout. C_IN goes between VREG_VIN (pin 49) and VREG_PGND (pin 47), C_OUT between L3 pad 1 and VREG_PGND, with two GND vias next to them.
- Feed VREG_FB from C_OUT's pad.
- Keep the second 4.7 µF on +1V1 near DVDD pin 23. RPi recommends one there; C52 can move there.
- Add a keep-out on In1 (and preferably In2–In3) under L3 and the LX trace.
- It is tight: L3's pads sit 0.8 mm above the pin-46–54 row, and the USB fan-out rule area covers (120.1, 105.3)–(125.7, 112.7). Use RPi's KiCad minimal-design files as the template.

### 2. HIGH, verify before paying: bottom-side rotation of U6/U11 (SOT-23-6) and polarity of D2/D3

`jlc_cpl.csv` agrees with `tools/fab.py`'s rule (bottom = 180 − KiCad + offset):

| Ref | KiCad rot (B.Cu) | Offset | CPL | Pin 1 / cathode, KiCad top view (y down) |
|---|---|---|---|---|
| U6 SRV05-4 | 0 | −90 | 90 ✓ | pad 1 (USB_P) at (122.41, 111.65): west row, south end |
| U11 SRV05-4 | −90 | −90 | 180 ✓ | pad 1 (USBA_P) at (141.60, 106.51): north row, west end |
| U9 XC6206 | 0 | 180 | 0 ✓ | pad 1 (GND) at (137.71, 130.13): west, south. The single pad 3 (VIN) faces east |
| U8 HT7550-1 | 0 | 0 + 180 (C16106) | 0 ✓ | pad 1 (GND) at (132.40, 127.68): south end of the pin row |
| D2 B5819W | 90 | 0 | 90 ✓ | cathode pad 1 (Net-(D2-K)) at (142.55, 127.83): south |
| D3 B5819W | 90 | 0 | 90 ✓ | cathode pad 1 (Net-(D2-K)) at (117.00, 121.20): south |

The numbers are consistent. What matters is the convention itself:
- **U8 needed a part-specific +180°** after the 2026-10-20 preview. That is consistent with a quirk in C16106's model, but it is also exactly what a 180° error in the bottom convention would look like.
- A wrong convention would rotate every bottom part by 180°. For the parts with a −90° offset (U6, U11), a sign error in how the offset is applied on the bottom also gives 180°.
- If U6 or U11 lands 180° rotated:
  - SRV05-4 pin 2 (GND) goes onto the VP pad (+3V3 or VCC), and pin 5 goes onto GND.
  - The internal VCC–GND clamp diode is then forward-biased **across +3V3 (U6) or VCC (U11)**: the board won't come up, or the buck sits in current limit.
- If D2/D3 are reversed, there is no +3V3 from either source.

The previous preview apparently showed only U8 wrong, which points to the convention being right. Still, before paying:
- In JLC's preview, confirm U6/U11's pin-1 dot against the table above (in a bottom view east and west swap).
- Confirm D2/D3's cathode bands face south (toward the bottom edge, y = 132).
- If U6/U11 come out 180° off, the CPL values become U6 = 270 and U11 = 0.

### 3. MEDIUM, verify before soldering: USB-A J4 pin-1 orientation can't be confirmed from ShouHan's drawing

`hexy:USB_A_ShouHan_AF90_WJDG` matches the AF 90 WJDG drawing (C456018 spec, page 1):
- 4 × Ø0.9 holes at 2.5/2.0/2.5 mm: pads at 0, 2.5, 4.5 and 7.0 with 0.92 mm drills
- shell tabs 13.1 mm apart (pads at −3.07 / +10.07) with Ø2.1 holes (2.3 × 2.6 mm slots)

But the drawing doesn't number the contacts. The pad layout (pad 1 at x = 0, mouth toward +y) is identical to KiCad's stock `USB_A_Molex_67643_Horizontal`. That suggests it's right, but it doesn't prove it.
- **If it is mirrored, VBUS (F2 output) lands on the GND contact**: F2 trips and the dongle is reverse-powered.
- It's hand-soldered, so before fitting J4, check continuity on a loose part (the outer contact next to the square pad should be the one opposite GND) or against LCSC's EasyEDA footprint for C456018.

### 4. MEDIUM: L3 must be hand-placed on a twice-reflowed board, next to the QFN

- L3 is DNP and excluded from the BOM and CPL (`exclude_from_bom` = True in the netlist). **With L3 missing, +1V1 is dead and the MCU won't run.** Every board needs it before first power, as the README says.
- **Polarity: the design is correct.** RP2350 datasheet Figures 26 and 28 put the dot (current-exit end) on V_OUT. L3 pad 1 is on +1V1, the footprint's silk dot is beside pad 1, and on the board pad 1 is the east pad (x 130.35, rot 180).
- Abracon's own sheet (rev A, p. 4, "Marking") draws the current entering at the dot, the opposite way round. **Follow RPi's figure, not Abracon's**: it matches the Pico 2.
- The land pattern matches Abracon's recommendation (1.00 × 1.60 mm pads with a 1.00 mm gap).
- If you redo the regulator layout (finding 1), it's worth asking JLC to consign and place L3, so the part's alignment and the loop stay as designed.

### 5. MEDIUM, firmware: with USB-only power, the USB-A host lines back-power VCC through U11

- U11's VP is on VCC. On USB alone (pack off), VCC is 0 V.
- If Pico-PIO-USB drives GPIO24/25 high, the current flows through R48/R49 (22 Ω) and U11's upper steering diodes into VCC. VCC carries F2 → the dongle, J5's servos, J12's LED stick, the buck output and U14.
- That over-sources the GPIOs and half-powers the dongle at about 2.5 V.

There's no copper fix needed. In firmware, start the USB host only when BAT_SENSE shows VSYS present.

The other half of item 4 checks out: **USB-only power can't backfeed VSYS**.
- VBUS reaches only U8 and C37.
- D2 blocks U8's output from VCC, and D3 blocks VCC from that path.
- The buck has no reverse path.
- Q1 is off with the switch off: R40 holds VGS at 0, and C72 holds it at plug-in.

### 6. LOW: AP64500 compensation and inductor differ from the datasheet's 5 V design

DS41979 Table 1 (5.0 V, 500 kHz) gives:
- R1 115.8k / R2 22.1k
- **L 3.6 µH**, C_OUT 3 × 22 µF
- **R5 15.8k, C5 2.7 nF, C6 39 pF (optional)**

This board has R26 39k / R27 7.5k (V_FB 0.8 V → 4.96 V ✓), **L1 2.2 µH**, **R28 15k / C16 4.7 nF** and no C6.
- R25 200k gives 500 kHz (450–550 kHz) ✓.
- EN tied to VSYS is allowed (EN abs max 42 V; "connect to VIN") ✓.
- BST: C14 100 nF ✓.

Ripple at 12.6 V in: ΔI = 5 V × (1 − 5/12.6) / (2.2 µH × 500 kHz) ≈ **2.7 A p-p**, against 1.7 A with 3.6 µH.
- At a 5 A load the peak is 6.4 A, close to the 6.8 A minimum HS current limit (§Electrical Characteristics). In practice that leaves about 4.5 A of usable output.
- The zero moves from 3.7 kHz to 2.3 kHz: slower but probably stable.

At bring-up, check the load-step response on VCC. If it rings, change C16 to 2.7 nF and add a 39 pF C6. Both are 0402 and can be changed after the boards arrive.

### 7. LOW: C74 is rated 16 V but sits on VSYS

C74 is a CL05B104KO5NNNC: the "O" code means 16 V. It sits on VSYS at U4's VIN.
- VSYS is 12.6 V at a full 3S pack.
- D4 (SMF14A) clamps at 23.2 V at 8.6 A (Littelfuse table: VBR 15.6–17.2 V, VRWM 14 V).
- So transients can go past 16 V on a part that would short VSYS if it cracked.

Swap it for a 50 V 0402 100 nF (for example CL05B104KB54PNC). Every other VSYS cap is 25 V or 50 V ✓.

### 8. LOW: Q1 inrush and turn-off

- **Turn-on:** the gate current through R41 (4.7k) at the Miller plateau is about 2 mA, and C71 (10 nF) gives dV/dt ≈ 0.2 V/µs, under the DRV8251A's 2 V/µs VM ramp limit ✓. With about 32–80 µF of VSYS ceramics, the inrush is **about 6–16 A for about 60 µs**. That is far below the AO4407A's 56 A pulsed rating and well inside the pack protector's delays.
- **Turn-off:** (switch opened) R40 47k × (C72 + C71) ≈ 5 ms, so Q1 goes through its linear region for milliseconds if the motors are drawing current.
- **Gate drive:** VGS is −5.09 V at 5.6 V in and −11.45 V at 12.6 V. Against the UMW AO4407A datasheet (±25 V; R_DS(on) < 14.7 mΩ at −4.5 V) that's fine ✓.
- Worth a scope check: switch off with a stalled motor.

### 9. LOW, firmware: DRV8251A sleep and current-limit details

All against SLVSFU6:
- **Pinout:** Table 6-1 gives 1 IPROPI, 2 IN2, 3 IN1, 4 VREF, 5 VM, 6 OUT1, 7 GND, 8 OUT2, PAD GND, which matches `hexyhustle:DRV8251ADDA` pin for pin, with EP = pad 9 on GND ✓.
- **Sleep:** with IN1 = IN2 = 0 for t_SLEEP 0.8–1.5 ms the driver sleeps, and t_WAKE is 250 µs (§7.5, §8.5.2). Coast-mode PWM with off periods over about 0.8 ms will add 250 µs wake delays. Use drive/brake (slow-decay) PWM or a PWM frequency above a few kHz. Both inputs low at reset (GPIO pull-downs plus the internal 100 kΩ R_PD) keeps the motors off at boot ✓.
- **Current limit:** VREF is 2.53 V, inside the 0–3.6 V operating range ✓. V_IPROPI at trip is 2.53 V, at or under 3.0 V ✓, so I_TRIP = 2.53 / (1.2k × 1575 µA/A) = 1.34 A ✓. A_ERR (±5 %) is specified only at VM ≥ 6.5 V, so the limit isn't guaranteed on a nearly empty 2S pack.
- **Shared VREF:** one VREF divider (Thevenin about 7.7 kΩ) feeds six VREF pins, and the IPROPI clamp is referenced to VREF. During the stall test (README bring-up step 4), measure MOT_VREF while several motors are in current limit, to confirm it doesn't move.
- **VM caps:** 10 µF/25 V + 100 nF/50 V per driver meets the "0.1 µF bypass + bulk" requirement (Table 6-1). TI's example uses 47 µF bulk; the six drivers share about 80 µF of ceramics plus the pack.

### 10. LOW: R109/R114 (15 kΩ) and erratum RP2350-E9

E9 (the pad latching at about 2.2 V with only weak pull-downs; it needs ≤ 8.2 kΩ) affects **only the A2 stepping** (datasheet Appendix D.5.1). The 15 kΩ host pull-downs on USBA_P/N are fine on A3/A4. If JLC's RP2354A stock (C41378174) turns out to be A2, a USB-A disconnect may not be detected.

### 11. LOW, usability: entering BOOTSEL needs a full power-down

There is no RUN button (TP3 only; RUN has an internal pull-up, per the datasheet pin table, so it's OK left on the pad). With the pack switched on, +3V3 stays up through D3, so unplugging USB-C doesn't reset the chip. To get into BOOTSEL: switch off, hold BOOT, then plug in USB-C. Or short TP3 to TP4 while holding BOOT. Firmware can also reboot into BOOTSEL through picotool.

### 12. LOW: J4 VBUS has only 10 µF (C59) after the PTC

USB 2.0 asks a host port for ≥ 120 µF. A dongle hot-plug will dip J4's VBUS, but VCC itself sits behind F2's resistance and the buck's 66 µF. Fine for a 2.4 GHz dongle.

### 13. INFO: SW2's land pattern is smaller than Alps recommends

`SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010_JLC`:
- **Matches Alps:** the numbering (1 = terminals ① and ③, 2 = terminal ②, matching Alps' circuit diagram) and the 2 × Ø0.9 boss holes 4.25 mm apart.
- **Smaller than Alps' land dimensions (p. 3):** signal pads are 0.55/0.60 mm wide where Alps calls for 0.75/0.6, and the mounting pads are 1.0 × 0.8 mm where Alps calls for about 1.3 × 1.2.

It's hand-placed and solders fine. Alps also marks a no-copper area under the switch centre; check that no track runs between pads 1 and 2 there.

---

## Checked and correct

**Symbols (`kicad/hexyhustle.kicad_sym`), pin by pin against the datasheet**

| Symbol | Netlist pins | Datasheet | Result |
|---|---|---|---|
| DRV8251ADDA (U1–U3, U15–U17) | 1 IPROPI, 2 IN2, 3 IN1, 4 VREF, 5 VM, 6 OUT1, 7 GND, 8 OUT2, 9 GND (EP) | SLVSFU6 Table 6-1 | ✓ |
| XC6206P332MR (U9) | 1 GND, 2 VOUT, 3 VIN | Torex pin assignment, SOT-23: 1 VSS, 2 VOUT, 3 VIN | ✓. VIN ≤ 5 V against 6 V operating / 7 V abs max |
| AP64500-13 (U4) | 1 BST, 2 VIN, 3 EN, 4 RT/CLK, 5 FB, 6 COMP, 7 GND, 8 SW, 9 EP | DS41979 pin descriptions | ✓. EP on GND |
| SRV05-4 (U6, U11) | 1/6 one line, 3/4 the other, 5 VP, 2 GND | Hongjiacheng rev 2.1 function diagram: I/O 1, 3, 4, 6; 5 VCC; 2 GND | ✓. The "USBLC6 pinout" wiring works because the four SRV05-4 channels are independent and each line uses two of them |
| IO_3x6_RA, motor | Consistent with the footprints (GND/5V/SIG per column) | — | ✓ |

**Stock symbols**
- U8 HT75xx-1-SOT89: 1 GND, 2 VIN, 3 VOUT, Holtek's SOT-89 order. Holtek's datasheet wasn't retrieved, but LCSC lists 30 V and 150 mA.
- U14 74AHCT1G125: 1 OE̅ (GND), 2 A, 3 GND, 4 Y, 5 VCC.
- Q1: 1–3 S, 4 G, 5–8 D, the same as the AO4407A.
- Y1 Crystal_GND24: pins 1/3 crystal, 2/4 GND.

**Footprints**
- **J1 `USB_C_Receptacle_ShouHan_TYPE-C16PIN`** against the ShouHan TYPE-C 16PIN drawing (C393939):
  - spans 6.40 (A1/B12 and B1/A12 at ±3.20), 4.80 (VBUS ±2.40), 3.50, 2.50, 1.50 and 0.50 ✓
  - pad widths 0.60 and 0.30 ✓
  - Ø0.65 pegs 5.78 apart ✓
  - shell slots 8.64 apart with 0.6 × 1.7 and 0.6 × 1.4 drills on 2.1 and 1.8 pads ✓
  - the pin order (B8, A5, B7, A6, A7, B6, A8, B5) matches the drawing's table ✓
- **L1 `L_Coilcraft_XAL5030`:** identical to KiCad's stock `L_Coilcraft_XAL5030-XXX` (1.18 × 4.70 mm at ±1.655) ✓.
- **L3 `L_Abracon_AOTA-B201610`:** matches Abracon's recommended land, with the dot on pad 1 ✓.
- **SW1 `SK12D07VG4`:** 2.0 mm pitch with the centre pin 2 as common, which matches the SW_SPDT symbol. The gate goes to the common, R41 to one throw, and pin 3 is open ✓.
- **J4:** see finding 3.
- **SW2:** see finding 13.

**RP2354A against RPi's minimal design**
- Pins: the KiCad pin numbers match the datasheet pin table (RUN 26, XIN 21, XOUT 22, VREG_AVDD 46, PGND 47, LX 48, VIN 49, FB 50, USB_DM 51, DP 52, USB_OTP_VDD 53, QSPI_IOVDD 54, ADC_AVDD 44, DVDD 6/23/39).
- Supply pins: every IOVDD, QSPI_IOVDD, USB_OTP_VDD and ADC_AVDD pin is on +3V3, and DVDD is on +1V1 ✓.
- Decoupling: 8 × 100 nF around U10 (C41–C45, C47–C49) and 3 × 100 nF on DVDD ✓. The one 4.7 µF on +3V3 is in the wrong place (finding 1). C46 sits by U9, not U10.
- Crystal: ABM8-272-T3 with 2 × 15 pF C0G and R43 1 kΩ in series on XOUT, as RPi specifies ✓.
- USB: R44/R45 27 Ω (USB_DM "27 Ω" in the pin table) ✓.
- BOOTSEL: QSPI_SS → R46 1 kΩ → SW2 → GND, with no flash pull-up ("If using RP2354, remove R10") ✓. QSPI_SD0–3 and SCLK are left unconnected (internal flash) ✓.
- RUN has an internal pull-up and goes to TP3 ✓. SWD goes to TP1/TP2 (internal pull-ups) ✓.

**Power path**
- D4 polarity: the netlist puts pad 1 (the cathode band in KiCad's D_SMF) on VSYS ✓, and the board places pad 1 west, toward J3, as the README says. The symbol is the bidirectional `Device:D_TVS` for a unidirectional part, so ERC can't catch it being reversed. It's hand-placed, so follow the README note.
- U8/U9 inputs: U8 sees only VBUS (5 V against 30 V). U9 sees at most 5 V − V_F.
- USB-only headroom: 4.75 V − HT7550 dropout − B5819W V_F (about 0.35 V) − XC6206 dropout still leaves several hundred mV above 3.3 V. Measure U9's VIN on a weak PC port at bring-up.
- Buck feedback, RT and EN: see finding 6.
- D2/D3 OR-ing: correct direction (cathodes on Net-(D2-K) → U9 VIN).

**Motor drivers:** see finding 9. The IPROPI/VREF network, VM decoupling and both-inputs-low sleep are as the datasheet describes.

**USB**
- USB-C: CC1 → R99 and CC2 → R100, 5.1 kΩ each ✓.
- D+ pins A6/B6 and D− pins A7/B7 are tied together ✓. SBU is open.
- USB-A host: R109/R114 15 kΩ pull-downs on the connector side of the 22 Ω resistors ✓. F2 (0.5 A hold, 16 V) is on VCC → J4 VBUS ✓.

## Not covered

- I didn't rerun DRC or ERC; the README reports both clean.
- I didn't verify the Holtek HT7550-1 dropout at 50 mA or its SOT-89 order against Holtek's PDF (LCSC returned no datasheet).
- The pack boards are out of scope.

## Verdict

**Most likely to fail at bring-up**, in order:
1. **The +1V1 core regulator** (finding 1). Expect a board that boots but resets or misbehaves under CPU or USB load, or reads an off-nominal +1V1 under load.
2. **A dead or shorted 3V3 if U6/U11 or D2/D3 are rotated on the bottom** (finding 2). This is cheap to rule out in JLC's preview.
3. **USB-A wiring, if J4's footprint is mirrored** (finding 3). Check it before soldering.

**Fix before ordering:**
- Rework U10's regulator corner to RPi's Figure 26: C_IN and C_OUT on F.Cu next to L3 and VREG_PGND, VREG_FB tapped at C_OUT, a second 4.7 µF at DVDD pin 23, and an inner-layer cut-out under L3 and LX. Then rerun DRC and the fab package.
- Swap C74 to a 50 V part.
- In JLC's preview, confirm U6, U11, U9 and U8 pin 1 and the D2/D3 cathodes against the table in finding 2.

Everything else is firmware (findings 5, 9, 11) or tuning after the boards arrive (finding 6).
