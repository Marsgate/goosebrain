# goosebrain rev 2 parts: brain + smart pack

Parts for the two boards: the **brain** (`kicad/`, RP2354 + motors + USB host) and the **smart pack** (`kicad-pack/`, charger + protector on the cells). **MPN is the primary ID**, and LCSC is for JLC assembly. Stock was checked on 2026-10-15 to 2026-10-19 through JLCPCB's parts API; every part new on 2026-10-19 (the brain/pack split) was checked live that day. "DK" means Digi-Key and Mouser carry the manufacturer's line; it was not checked live unless marked ✓.

**Asm** column: **JLC** = machine-placed by JLC (basic or preferred parts, and parts hard to solder with an iron). **Hand** = SMD part marked DNP in the schematic and hand-placed (out of the JLC BOM and CPL, pads stay on the board). **THT** = through-hole, hand-soldered. The rule for both boards: a part stays at JLC if it's basic or preferred, or hard to solder by hand; otherwise it's DNP and hand-placed.

## The split (2026-10-19)

Charging moved off the robot into a **smart pack**: the Ovonic 3S 450 mAh cells plus a small board with the BQ25798 charger (standalone, fixed settings), the BQ7791501 protector, the 15 A fuse and its own USB-C charging port. It plugs into the brain over an XT30 lead.

- **Why:** a wrong setting on an external RC charger caused a battery fire, so the settings must be impossible to get wrong. The pack has no MCU and no I2C host, so nothing can change them. Packs can be swapped, and spares can be sold.
- **No PD:** at 1C the pack can't use more than about 5 W, so PD saves no charge time.
- **No Bluetooth** on either board: SIG fees.
- **Brain MCU stays the chip-down RP2354A.** Rechecked: an RP2040 plus flash costs about the same and loses 5 V-tolerant IO and a PIO block; a WCH CH32V saves about $0.50 a board but needs a firmware rewrite.
- **The brain's PCB goes from 6 layers to 4** (JLC04161H-7628) and will be routed by hand.

## Datasheet checks (2026-10-19)

All passed; no architecture change was needed. The full numbers are on the schematic notes.

1. **BQ25798 ILIM_HIZ** (SLUSDV2C §7.3.4.3): V = 1 V + 0.8 Ω × ILIM, read once at power-on; it clamps IINDPM from detection and from I2C. REGN is 4.6/4.8/5.0 V at 5 V VBUS. **R32 39k / R33 24k** (both JLC preferred; 100k/62k would need an extended 62k) put 1.83 V on the pin: **1.04 A** typ, 0.94–1.13 A over REGN. IINDPM accuracy at 1 A is 0.88–1.00 A (typ 0.94 A). Charge current at 90 % efficiency from 5 V: **0.44 A at 3.5 V/cell (≤1C), 0.38 A at 4.1 V/cell**, about 0.42/0.36 A with typical accuracy. ICHG stays at its 1 A default with no host, so this divider is the only rate limit.
2. **BQ25798 BC1.2 limits** (Table 7-4): SDP 0.5 A, CDP 1.5 A, DCP 3.25 A, HVDCP 1.5 A, unknown adapter 3 A, non-standard dividers 1–2.4 A. The ILIM pin clamps all of them to 1.04 A; an SDP (PC port) and the 1 A non-standard divider charge slower. The datasheet doesn't say what a Type-C source with open D+/D− detects as: bench-test it.
3. **BQ25798 with no host:** SCL/SDA get 10 kΩ to the logic rail (pin table), here REGN (R97/R98). /INT is open-drain and left open; /QON has an internal pull-up and is left open; /CE must not float and goes to PACK−. Power-on defaults (Table 7-9, register map): 3S from PROG (12.6 V), ICHG 1 A, IPRECHG 120 mA, ITERM 200 mA, EN_TERM 1, 12 h fast-charge timer, JEITA, ADC_EN 0, HVDCP_EN 0, EN_9V/EN_12V 0, EN_EXTILIM 1, AUTO_INDET_EN 1, EN_ICO 0. So VBUS stays at 5 V and no high-voltage request is ever made. Battery-only quiescent current IQ_BAT_ON is 17 µA typ, 24 µA max (ADC off).
4. **TS / NTC:** thresholds T1 73.3 % (0 °C), T2 68.4 % (10 °C), T3 44.8 % (45 °C), T5 34.2 % (60 °C) of REGN, specified with a 103AT and 5.24k/30.31k. With the existing 5.23k/30.1k and TH2 = Murata NCP18XH103F03RB (B25/50 3380, B25/85 3434), the cold cutoff lands at −0.2 to +1.0 °C and the hot cutoff at 59.9–60.6 °C. Both within 1 °C, so the divider is unchanged. JEITA defaults: 0–10 °C charges at 20 % of ICHG; 45–60 °C drops VREG by 0.4 V.
5. **BQ7791501 load removal and R94** (BQ77915 datasheet §9.3.2.10, LD specs): OCD1/OCD2/SCD recover on load removal only. With a fault active, LD has 200 kΩ (typ) to VSS; it must fall below VLDT 1.25 V min. With R94 100 kΩ from PACK− to BAT_N, the charger's 17 µA (24 µA max) sees R94 ‖ (R74 470k + 200k) = 87 kΩ: PACK− ≈ 1.5 V (2.1 V max), LD ≈ 0.44 V (0.62 V max). Any load under about 48 µA reads as removed. **Pass.** With the FETs on, R94 sees about 0 V, so it adds no standby drain. UV recovers on load removal plus hysteresis; OCC on load detection (needs more than about 48 µA of load).
6. **DRV8251A current limit** (SLVSFU6, 2026-10-19; replaced the DRV8871, whose 6.5 V VM minimum a 2S pack goes below): I_TRIP × A_IPROPI = V_VREF / R_IPROPI, A_IPROPI 1575 µA/A, ±5 % (A_ERR, specified at VM ≥ 6.5 V and V_IPROPI ≤ 3.0 V). VREF is 0–3.6 V. **One shared divider from +3V3 (R107 10k / R108 33k, so 2.53 V) and 1.2 kΩ per driver → 1.34 A.** (1.18 kΩ would give 1.36 A, but JLC has only 2,341 of it as an extended part; 1.2 kΩ is preferred, with 164k in stock.) At the limit it brakes on both low-side FETs for 25 µs (t_OFF). VM 4.5–48 V, 50 V abs max; UVLO 4.05–4.35 V falling, 4.15–4.45 V rising. Inputs VIH 1.5 V, 100 kΩ pull-downs; sleeps after 0.8–1.5 ms with both inputs low. R_DS(on) 225 + 225 mΩ. Same DDA HSOP-8 package, so the footprint stays. Pinout 1 IPROPI, 2 IN2, 3 IN1, 4 VREF, 5 VM, 6 OUT1, 7 GND, 8 OUT2, pad GND: pins 1, 4 and 7 differ from the DRV8871 (GND, ILIM, PGND). Local symbol `hexyhustle:DRV8251ADDA`, drawn with IPROPI where the DRV8871's ILIM was, so R101–R106 keep their wiring.
7. **Pack FETs (Q2/Q3):** Infineon IRF8736TRPBF, SO-8: 30 V, ±20 V gate, 3.9 mΩ typ / 4.8 mΩ max at 10 V, Qg 17 nC typ (4.5 V), RθJA 50 °C/W. At 10 A: 0.48 W max per FET, about 24 °C rise. Pins 1–3 S, 4 G, 5–8 D, the same as KiCad's `Transistor_FET:IRF8721PBF-1` symbol and the SOIC-8 footprint.
8. **Pack thresholds with the 2 mΩ shunt:** OCD1 17.5 A (14 A at the −20 % tolerance), OCD2 30 A, SCD 60 A, OCC 10 A. Six stalled motors (about 8 A) plus the buck stay under 14 A.
9. **USB pair impedance on JLC04161H-7628** (7628 prepreg 0.2104 mm, εr 4.4): 0.22 mm / 0.15 mm gap ≈ 90 Ω. See the README for how it was worked out; confirm it in JLC's calculator.

## Brain parts

| Role | MPN | Mfr | Package | LCSC | JLC stock / class | Asm | Notes |
|---|---|---|---|---|---|---|---|
| MCU (U10) | RP2354A | Raspberry Pi | QFN-60 7x7 | C41378174 | 11,350 / ext | JLC | DK: SC1511-A4. Hard to solder |
| Core SMPS inductor (L3) | AOTA-B201610S3R3-101-T | Abracon | 0806 | (C42411119) | 1 at JLC, 0 at LCSC | Hand | Specified by RPi; polarity-marked (dot = pin 1 = +1V1). Buy from Digi-Key. DNP and excluded from BOM/position files |
| Crystal 12 MHz (Y1) | ABM8-272-T3 | Abracon | 3225 | C20625731 | 6,171 / ext | JLC | 2× 15 pF C0G, 1 kΩ on XOUT |
| 3.3 V LDO (U9) | XC6206P332MR-G | Torex | SOT-23-3 | C5446 | basic | JLC | 200 mA, 6 V max in. Local symbol `hexyhustle:XC6206P332MR` |
| USB-only 5 V reg (U8) | HT7550-1 | Holtek | SOT-89-3 | C16106 | pref | JLC | 30 V in, 150 mA; load ≈ 50 mA |
| OR diodes (D2, D3) | B5819W | MDD | SOD-123 | C64885 | pref | JLC | |
| USB ESD (U6, U11) | SRV05-4 | hongjiacheng | SOT-23-6 | C7420376 | pref | JLC | USBLC6-2SC6 pinout: I/O 1, 3, 4, 6; VP 5; GND 2. VP to 3V3 (USB-C) or 5 V (USB-A) |
| USB-C receptacle (J1) | TYPE-C16PIN | SHOU HAN | SMD + THT shell | C393939 | 321,036 / ext | JLC | **Programming only.** Fine-pitch, so JLC places it |
| USB-C Rd (R99, R100) | 0402WGF5101TCE | UNI-ROYAL | 0402 | C25905 | basic | JLC | 5.1 kΩ on CC1/CC2 (the CH224A used to provide Rd) |
| USB-A receptacle (J4) | AF 90 WJDG | SHOU HAN | THT RA | C456018 | ext | THT | `hexy:USB_A_ShouHan_AF90_WJDG` |
| USB-A PTC (F2) | JK-nSMD050-16 | Jinrui | 1206, 0.85 mm | C2680506 | 21,796 / ext, $0.025 | Hand | 0.5 A hold, 1 A trip, 16 V; VCC to USB-A VBUS, with C59 10 µF. Replaces the SY6280 |
| Pack connector (J3) | XT30PW-M30.G.Y | Changzhou Amass Elec | THT horizontal (right-angle) | C431092 | 62,641 / ext, $0.39 | THT | Male, on the bottom edge with its mouth out through the wall. Takes the pack's XT30U-F lead. **Pin 1 GND (PACK−), pin 2 PACK+.** KiCad's `Connector_AMASS:AMASS_XT30PW-M_1x02_P2.50mm_Horizontal`, whose hole pattern matches the Amass drawing: Ø1.9 mm pins 5.00 mm apart, Ø1.0 mm pegs 11.00 mm apart and 10.00 mm behind them, mating face 3.05 mm past the pegs. The footprint's silk marks pad 1 "−"; the drawing is too small to read the molded mark, so check it on the first part. Replaced the vertical XT30UPB-M (C428721), which stood about 17 mm tall with its plug in and set the box height |
| Power switch FET (Q1) | AO4407A | UMW | SOP-8 | C2841482 | ext | JLC | −30 V, 9.5 mΩ. Gate divider R40 47k, R41 4.7k (VGS −5.1 V at a 5.6 V empty 2S pack, −11.5 V at a full 3S pack); soft start C71 10 nF (CL05B103KB5NNNC, C15195 basic; doubled with R41 halved, to keep about 70 µs), C72 100 nF |
| Power slide switch (SW1) | SK12D07VG4 | SHOU HAN | THT RA SPDT | C393937 | ext | THT | Gate only. Lever reaches 4.0 mm past the board edge: the wall needs a slot |
| VSYS TVS (D4) | SMF14A | Littelfuse | SOD-123FL | C207256 | 3,726 / ext | Hand | Clamps VSYS (about 19 V at 3 A, under the DRV8251A's 50 V abs max). Cathode (pad 1) on VSYS |
| 5 V buck (U4) | AP64500SP-13 | Diodes | SO-8EP | C2070920 | 3,973 / ext | JLC | Divider 39k/7.5k = 4.96 V |
| Buck inductor (L1) | XAL5030-222MEC | Coilcraft | 5.28 × 5.48 × 3.1 mm | C920280 | 1,268 / ext, $6.72 | Hand | 2.2 µH, Isat 9.2 A (30 % drop), Irms 7.2 A, 13.2 mΩ typ. `hexy:L_Coilcraft_XAL5030`, in its old pocket. See "L1" below |
| Buck VIN caps (C73, C74) | CL21A106KAYNNNE / CL05B104KO5NNNC | Samsung | 0805 / 0402 | C15850 / C1525 | basic | JLC | 10 µF + 100 nF. On the board since 2026-10-19 (they were schematic-only), just below C15, about 3 mm from U4's VIN pins |
| Motor drivers (U1, U15, U2, U16, U3, U17) | DRV8251ADDAR | TI | HSOP-8 PowerPAD | C5218844 | ext (stock and price to recheck on order day) | JLC | One per motor: M1 U1, M2 U15, M3 U2, M4 U16, M5 U3, M6 U17. 4.5–48 V, so it runs from a 2S or a 3S pack. Exposed pad to GND. `Package_SO:Texas_HTSOP-8-1EP_3.9x4.9mm…_ThermalVias`, the same as the DRV8871 it replaced. **Stocked at LCSC as C5218844 (2026-10-19):** the genuine TI part, so JLC places it as an ordinary extended part; no Global Sourcing or consigning needed. Sources disagreed on stock and price (about 16.5k at about $0.29 each for 60, against an older listing of about 9.3k at $0.73 each), so check LCSC on order day. Don't substitute C3681116: that is the DRV8251DDAR, without the A, a different part |
| Motor IPROPI (R101–R106) | 0402WGF1201TCE | UNI-ROYAL | 0402 | C25862 | 164,223 / pref | JLC | 1.2 kΩ: 1.34 A per motor with VREF 2.53 V. R101 U1, R102 U15, R103 U2, R104 U16, R105 U3, R106 U17 |
| Motor VREF divider (R107, R108, C81) | 0402WGF1002TCE / 0402WGF3302TCE / CL05B104KO5NNNC | UNI-ROYAL / Samsung | 0402 | C25744 / C25779 / C1525 | basic | JLC | +3V3 → 10k → MOT_VREF → 33k → GND, 100 nF on MOT_VREF. One divider feeds all six VREF pins. On the board in the column between J3 and the buck |
| Motor VM caps | CL21A106KAYNNNE + CC0805KRX7R9BB104 | Samsung / YAGEO | 0805 | C15850 / C49678 | basic | JLC | 10 µF/25 V + 100 nF/50 V per driver: C3/C4 U1, C6/C7 U2, C10/C11 U3, C75/C76 U15, C77/C78 U16, C79/C80 U17 |
| Motor connectors (M1–M6) | S2B-XH-A(LF)(SN) | JST | THT RA | C157931 | ext | THT | M2, M4, M6 wired reversed (OUT1 to pin 2) |
| IO header S1–S6 (J5) | 2011-3X06G00RB | WingTAT | THT RA 3 × 6 | C51953246 | 144 / ext | THT | Low stock: fallback is the 3 × 40 strip (C51953256) cut to 3 × 6 |
| BOOT button (SW2) | SKRTLAE010 | Alps | SMD side push | C110293 | ext | Hand | Easy to solder; 1 kΩ (R46) to QSPI_SS |
| LED stick buffer (U14) | SN74AHCT1G125DBVR | UMW | SOT-23-5 | C20617903 | ext | Hand | 3.3 V → 5 V for the WS2812B data line. R80 and C70 removed: it drives J12 pin 2 directly |
| LED stick connector (J12) | B3B-PH-K-S(LF)(SN) | JST | THT vertical | C131339 | ext | THT | Pin 1 5 V, 2 DIN, 3 GND |
| Test pads TP1–TP4 | — | — | 1 mm round, bottom | — | — | — | SWCLK, SWDIO, RUN, GND |
| Fiducials FID1–3 | — | — | 1 mm, 2 mm mask | — | — | — | |
| Passives | UNI-ROYAL 0402WGF…/0603WAF…, Samsung CL05/CL10/CL21/CL31, FH | — | 0402–1206 | See `PASSIVES` in `circuit/goosebrain.py` | basic or preferred | JLC | Buck outputs C5/C8/C12 22 µF 1206/10 V (1.6 mm tall, partly under the pack; foam takes it) |

### L1

**L1 must not saturate below the AP64500's current limit** (6.8 A min, 8 A typ, 9.2 A max): an overload or a short on the 5 V rail (the IO ports take servos through the case wall) should end in the buck's own limit and hiccup, not in a collapsed inductor.

- **XAL5030-222MEC (kept):** Isat 9.2 A at a 30 % drop, the same as U4's 9.2 A maximum limit. It sits in its original pocket between J4, U4, C5/C12 and the pack's edge, with no other part moved.
- **Sunlord MWSA0603S, checked and rejected on 2026-10-19.** The 2.2 µH part has Isat 10 A and Irms 9.5 A (3.3 µH: 9.5 A / 8.5 A; JLC/LCSC parametrics; Sunlord's PDF could not be opened to confirm the drop criterion), so it would qualify electrically, at $0.11. But its courtyard is 9.0 × 7.2 mm and the pocket is 6.6 mm tall between J4's courtyard (an edge connector) and the pack's edge (y = 121.95 mm), and the part is 3 mm tall, so it can't go under the pack. The only other spot, left of J4 after moving U8/C38, puts L1 about 9 mm from U4's SW pin and opens up the switch loop. To use it, J4 or the pack bay would have to move.
- **MWSA0503S-2R2MT** (5.4 × 5.2 mm, $0.15, fits the pocket) was tried first but rejected: its 7 A Isat is under U4's typical 8 A limit.

## Pack parts

| Role | MPN | Mfr | Package | LCSC | JLC stock / class | Asm | Notes |
|---|---|---|---|---|---|---|---|
| USB-C receptacle (J1) | TYPE-C16PIN | SHOU HAN | SMD + THT shell | C393939 | 321,036 / ext | JLC | Charging only. VBUS to the charger, D+/D− to the BQ25798, SBU open |
| CC Rd (R95, R96) | 0402WGF5101TCE | UNI-ROYAL | 0402 | C25905 | basic | JLC | Plain 5 V sink |
| VBUS TVS (D1) | SMBJ20A | hongjiacheng | SMB | C19077575 | 19,729 / pref | JLC | The pack is the thing users plug into random chargers |
| Charger (U7) | BQ25798RQMR | TI | VQFN-29 4x4 | C2876593 | 3,079 / ext | JLC | Standalone. Fallback BQ25792RQMR C2862876 |
| Charger inductor (L2) | FNR4030S2R2MT | Changjiang | 4 × 4 mm | C167869 | 55,599 / ext | Hand | 2.2 µH |
| PROG (R31, R78) | 0402WGF6801TCE | UNI-ROYAL | 0402 | C25917 | pref | JLC | 2 × 6.8 kΩ = 13.6 kΩ: 3S, 750 kHz |
| ILIM_HIZ (R32, R33) | 0402WGF3902TCE / 0402WGF2402TCE | UNI-ROYAL | 0402 | C25783 / C25769 | pref / pref | JLC | 39 kΩ from REGN, 24 kΩ to PACK−: 1.04 A in |
| TS divider (R34, R35) | 0402WGF5231TCE / 0402WGF3012TCE | UNI-ROYAL | 0402 | C25907 / C29402 | basic | JLC | 5.23 kΩ / 30.1 kΩ |
| Cell NTC (TH2) | NCP18XH103F03RB | Murata | 0603 | C13564 | 407,883 / ext | Hand | 10 kΩ, B25/85 3434. On the board's underside, pressed against the cells. Replaces R81 |
| I2C pull-ups (R97, R98) | 0402WGF1002TCE | UNI-ROYAL | 0402 | C25744 | basic | JLC | 10 kΩ SCL/SDA to REGN |
| Charge LED (LED1, R36) | KT-0805G | Hubei KENTO | 0805 top view | C2297 | 2.6 M / basic | JLC | Green, from REGN through R36 2.2 kΩ to STAT. The housing shows it |
| Charger caps | Samsung CL21/CL05/CL10, FH 0402/0603 | — | — | as on the brain before | basic | JLC | VBUS C20–C22, PMID C23–C26, BTST C18/C19, SYS C27–C32, BAT C33/C34, REGN C35, SDRV C36; R30 100 Ω to BATP |
| Protector (U13) | BQ7791501PWR | TI | TSSOP-24 | C2876947 | 309 / ext | JLC | **Low stock: 309 packs.** Same-threshold alternative BQ7791501PWT (C3682023, small reel) |
| Protector FETs (Q2 DSG, Q3 CHG) | IRF8736TRPBF | Infineon | SO-8 | C51630 | 33,259 / ext, $0.44 | Hand | See check 7. Replaces the 80N03F PDFN |
| Shunt (R66) | RLP25FEER002 | TA-I Tech | 2512 | C160590 | 49,780 / ext, $0.06 | Hand | 2 mΩ 1 % 2 W ±50 ppm. One part replaces R66 ‖ R67. Check the maker's land pattern before layout |
| Protector NTC (TH1) | NCP18XH103F03RB | Murata | 0603 | C13564 | 407,883 / ext | Hand | By the FETs |
| Load-removal pull-down (R94) | 0402WGF1003TCE | UNI-ROYAL | 0402 | C25741 | basic | JLC | 100 kΩ PACK− to BAT_N. See check 5 |
| Protector passives | UNI-ROYAL 0402, Samsung CL05 | — | 0402 | — | basic | JLC | Cell filters R62–R65 100 Ω / C64–C67 1 µF, R61 1k + C62, C63, R75 10k (PRES), R76 100k (ROCD), R77 10k (VTB), R74 470k (LD), R68/R69 100 Ω + C68, gate R70 4.7k / R71 1M / R72 1k / R73 1M |
| Fuse (F1) | 0453015.MR | Littelfuse | 2410 | C178997 | 3,510 / ext | Hand | 15 A very fast-acting, CELL+ to PACK+ ahead of J2. Moved from the brain |
| Cell connector (J3) | XT30UPB-M | Changzhou Amass Elec | THT vertical | C428721 | 68,839 / ext | THT | The cells' own XT30U-F plugs in, so the cell leads are never cut. Pin 1 BAT_N, pin 2 CELL+ |
| Balance connector (J11) | B4B-XH-A(LF)(SN) | JST | THT vertical | C144395 | 455,390 / ext | THT | Pin 1 cell 1−, pin 4 cell 3+ |
| Output lead (J2) | XT30U-F on a 16 AWG lead | Changzhou Amass Elec | `hexy:XT30_SolderPads_1x02_P5.00mm` | C99102 (plug) | 41,268 / ext | THT | Pad 1 PACK−, pad 2 PACK+. Mates the brain's J3. The footprint's silk was fixed to match (it said "+BATT" on pad 1) |
| Fiducials FID1–3 | — | — | 1 mm, 2 mm mask | — | — | — | JLC assembles the pack |

## 2S pack parts (kicad-pack-2s, 2026-10-19)

A copy of the 3S pack for 2-cell packs (8.4 V full, 5.6 V at the 2.8 V/cell cutoff, the HY2120-LB's cutoff). The charger block, USB-C, F1, J2, J3, Q2/Q3 and their gate resistors R71–R73 are the 3S pack's. The cells (part number, capacity) aren't chosen yet: the charge rate below assumes 450 mAh.

**Changed:**

| Role | MPN | Mfr | Package | LCSC | Asm | Notes |
|---|---|---|---|---|---|---|
| PROG (R31, R78) | 0402WGF8201TCE / 0402WGF0000TCE | UNI-ROYAL | 0402 | C25924 / C17168 | JLC | 8.2 kΩ + 0 Ω: 2S, 750 kHz (BQ25798 Table 7-1). 2S defaults: VREG 8.4 V, ICHG 1 A, VSYSMIN 7 V |
| ILIM_HIZ low side (R33) | 0402WGF1802TCE | UNI-ROYAL | 0402 | C25762 | JLC | 18 kΩ (R32 stays 39k): V = 4.8 × 18/57 = 1.52 V → 0.65 A in → about 0.42 A into a 2S pack at 3.5 V/cell |
| Protector (U13) | HY2120-LB | HYCON | SOT-23-6 | C168778 | 6,631 / ext | JLC | 2-cell (DS-HY2120-V15). OV 4.25 V (release 4.05 V), UV 2.80 V (release 3.00 V), discharge OC 200 mV (10 ms), short 1.0 V (0.6–1.4 V, 250 µs), charge OC −210 mV, power-down on. Senses current as the drop across Q2 + Q3 (pin CS), not a shunt: about 18–20 A at 10 mΩ. Pin-for-pin the same as the ABLIC S-8252, which was the first pick but isn't stocked at JLC. Over-current releases when CS falls back under 200 mV with the load gone; R94 holds CS at about 80 mV against the charger's 17 µA |
| U13 VDD filter (R61, C62) | 0402WGF4700TCE / CL05B104KO5NNNC | UNI-ROYAL / Samsung | 0402 | C25117 / C1525 | JLC | 470 Ω from CELL+ to VDD, 100 nF VDD to VSS (HY2120 §10: 100–470 Ω, 0.01–1 µF) |
| U13 VC filter (R63, C64) | 0402WGF4700TCE / CL05B104KO5NNNC | UNI-ROYAL / Samsung | 0402 | C25117 / C1525 | JLC | 470 Ω from CELL1 (the mid tap) to VC, 100 nF VC to VSS |
| U13 CS resistor (R74) | 0402WGF2001TCE | UNI-ROYAL | 0402 | C4109 | JLC | 2 kΩ from CS to PACK− (datasheet R3, 1–4 kΩ; reverse-charger protection) |
| Trip-recovery resistor (R94) | 0402WGF4701TCE | UNI-ROYAL | 0402 | C25900 | JLC | 4.7 kΩ PACK− to BAT_N. Discharge over-current releases when CS falls back below 200 mV. With R94, the charger's 17 µA standby draw holds CS at only 17 µA × 4.7k ≈ 80 mV; without it, the pack's PB+/PB− impedance (about 490 kΩ from the charger) sits right at the HY2120's 450 kΩ release threshold. Any load above about 190 kΩ counts as removed; the brain with its switch off qualifies |
| DSG gate resistor (R70) | 0402WGF1001TCE | UNI-ROYAL | 0402 | C11702 | JLC | 1 kΩ (was 4.7k). DO/CO drive the gates directly, so this keeps the short-circuit turn-off fast |
| Balance connector (J11) | B3B-XH-A(LF)(SN) | JST | THT vertical | C144394 | THT | Pin 1 cell 1−, pin 2 mid, pin 3 cell 2+. A 3S plug (4-pin) doesn't fit, and the 3S pack's 4-pin header doesn't take a 2S plug |

**Added (cell balancing, charge only):**

| Role | MPN | Mfr | Package | LCSC | Asm | Notes |
|---|---|---|---|---|---|---|
| Balancers (U21 cell 1, U22 cell 2) | HY2213-BB3A | HYCON | SOT-23-6 | C113632 | JLC | Bleeds a cell above 4.200 V (release 4.190 V), N-FET drive, 250 ms delay, 2.5 µA. Pins 2 VDD, 3 VSS, 6 OUT, 1/4/5 NC |
| Balancer supply (R110, R111 / C83, C84) | 0402WGF1000TCE / CL05B104KO5NNNC | UNI-ROYAL / Samsung | 0402 | C25076 / C1525 | JLC | 100 Ω + 100 nF per HY2213 (datasheet §9) |
| Balance FETs (Q4, Q5) | AO3400A | Alpha & Omega | SOT-23-3 | C20917 | JLC | Gate from OUT, source on the cell's negative tap |
| Bleed resistors (R112, R113) | 25121WJ0470T4E | UNI-ROYAL | 2512 | C15261 | JLC | 47 Ω, 1 W: about 89 mA and 0.38 W at 4.2 V. The bleed current comes through the balance lead |

**Removed from the copy:** BQ7791501 (U13) and its parts R62, R64–R66, R68, R69, R75–R77, C63, C65–C68, TH1. With no shunt, Q2's source is BAT_N. The HY2120 has no temperature input, so the pack loses the protector's discharge over-temperature cutoff (TH1 next to the FETs). TH2 on the charger still stops charging outside 0–60 °C.

## Removed

- **From the brain:** CH224A PD sink (U5) with R29 and C17; BQ25798 charger (U7) and its block (L2, R30–R36, R78, R81, C18–C36, LED1); I2C/INT pull-ups R37–R39; BQ7791501 protector (U13), Q2/Q3, R61–R77, C62–C68, TH1, J11; F1; D1 SMBJ20A; SY6280 USB-A switch (U12) with R50, R79, C58, C60; the 3× DRV8848 (U1–U3) with their VINT caps C2/C9/C13, VREF dividers R84/R85, R88/R89, R92/R93, sense resistors R82/R83, R86/R87, R90/R91 and the nFAULT pull-up R54; **R67** (second shunt); **R80** (330 Ω to the LED stick) and **C70** (10 µF at J12).
- **Parts gone from the BOM:** CH224A (C42459160), SY6280AAC (C55136), DRV8848PWPR (C131079), RL1206FR-7W0R15L sense resistors (C859925), 80N03F (C7471104), LRBM25GFER005 (C5121087), 27-21SYGC side-view LED (C74270).

## Compliance

- **The pack is a separately sold product.** It needs its own FCC/CE declaration; the EMC test can share one lab campaign with the brain.
- **UN38.3** is needed for the pack assembly (cells + board). Ovonic publishes no test summary: ask Ovonic for theirs, and ask the lab whether it covers the assembled pack or whether the pack needs its own test. A draft request is in goosebrain's `build/ovonic-un38.3-request.md`.

## Stock and supply risks

1. **L3 (1 at JLC, 0 at LCSC).** Raspberry Pi approves only this Abracon part. Buy from Digi-Key and hand-place it.
2. **U13 BQ7791501PWR (309 at JLC):** covers 309 packs.
3. **J5 IO header (144 at JLC):** above 144 boards use the cut 3 × 40 strip.
4. **L1 XAL5030-222MEC (1,268 at JLC, $6.72)** covers about 1,268 boards; Digi-Key/Mouser stock Coilcraft too. **U7 BQ25798 (3,079)** is fine for now. Recheck both before a large order.
5. **Single-source Chinese parts** (SHOU HAN USB-C/USB-A/switch, hongjiacheng SRV05-4/SMBJ20A, Jinrui PTC): each has common equivalents in the same package.

## Layout and mechanical notes for later

- The pack board sits on the cell pack, with TH2 on its underside against the cells. The housing shows LED1 and the USB-C opening.
- The pack rides outside the brain's box and plugs into the horizontal J3 through the bottom wall, so the brain has no pack bay. Box = outline + 5 mm: about 78.4 × 48 × 16 mm. The board has no mounting holes: the case holds it, with a rib behind J3 to take the plug force.
- The brain is on 4 layers now (JLC04161H-7628). The 6-layer stack was chosen because 4 layers couldn't route around the RP2354A when the board also carried the charger and protector; with those gone, 4 layers is worth trying first.
- `tools/fab.py` builds all three boards (`--board brain|pack|pack2s`). Its `Texas_HTSOP-8` rotation for the motor drivers still needs confirming in JLC's placement preview.
- **2S pack board:** the 10 new footprints (U21, U22, Q4, Q5, R110–R113, C83, C84) are staged in a row at y 170 below the cluster. U13 is now SOT-23-6 and J11 a B3B-XH-A, both swapped in place. Like the 3S pack, it has no outline yet.
