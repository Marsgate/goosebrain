# goosebrain rev 2 parts

Parts for the RP2354 + USB host + internal 3S battery revision. **MPN is the primary ID**, and LCSC is optional, for JLC assembly. Stock was checked on 2026-10-15 through JLCPCB's parts API; the cost-down swaps of 2026-10-16 (build/cost-down-2026-10-16.md, rows 1-21) were checked that day. "DK" means Digi-Key and Mouser carry the manufacturer's line; it was not checked live unless marked ✓.

**Assembly** column: **M** = machine (PCBA), **H** = hand-solder (through-hole), **D** = Digi-Key part, hand-placed (DNP for PCBA: out of the JLC BOM and CPL, pads still on the board).

## Design decisions behind the parts

- **MCU: RP2354A**, the RP2350A with 2 MB of flash stacked in the package. JLC has it in stock, so no external flash chip is needed. The pinout is identical to the RP2350A, so the RP2350A plus a W25Q16JV can replace it if needed.
- **Charger: BQ25798.** It's the active sibling of the BQ25792 (TI's BQ25792 pages now return 404). Pinout and PROG table are identical, and KiCad 10 ships its symbol (`Battery_Management:BQ25798`).
- **Motors and the 5 V buck run straight from the pack**, through the fuse and power switch, not from the charger's SYS output. The charger's internal battery switch is rated 6 A continuous and only 10 A for at most 1 s (BQ25798 datasheet, Recommended Operating Conditions), which motor stalls would exceed. SYS gets its capacitors and no load.
- **Charge current is safe with zero firmware.** The power-on default charge current is 1 A, and no pin can change it, so the **ILIM_HIZ divider caps input current** instead. 100 kΩ from REGN with 33 kΩ to GND puts 1.24 V on the pin, which sets about a 0.30 A input limit. That works out to:
  - about 2.4 W from a 9 V PD source, or roughly 220 mA into the pack (about 0.22C for the 1000 mAh pack);
  - about 120 mA from plain 5 V USB.

  Firmware can raise the limit over I2C through the board support library. The pack's BMS is the backstop if it's set wrong.
- **PD request: 9 V**, which nearly every USB-PD charger offers (12 V is optional in the spec). It also keeps the USB-only 5 V regulator cool.
- **3S profile:** PROG = 13.6 kΩ as 2 × 6.8 kΩ in series (R31 + R78; TI's 13.7 kΩ setting, 750 kHz, 2.2 µH inductor, 3S → 12.6 V charge voltage; TI allows ±2 %, and the 1 % pair is 13.46-13.74 kΩ). Read REG0x0A CELL on the first board. TS divider: 5.23 kΩ (REGN–TS) and 30.1 kΩ (TS–GND) for a 103AT NTC, with JEITA enabled by default. These stay on E96: the E24 pair 5.1 k / 27 k would move the cold cutoff to about −1.5 °C, below the 0 °C charging limit. /CE is tied to GND. Charger D+/D− are left open; the ILIM pin overrides detection.
- **Charge LED** on the charger's STAT pin (pulled up to REGN), so charging shows with no firmware.
- **MCU power from USB alone:** HT7550 (30 V in) on VBUS → Schottky → OR'd with the buck's 5 V → XC6206P332MR (200 mA, 6 V max, no enable).
- **5 V buck values** (AP64500 datasheet equations, comments in `buck_5v()`): divider 39 k / 7.5 k gives 4.960 V, the same as rev 1's 115 k / 22.1 k. Compensation 15 k + 4.7 nF puts crossover at 14-22 kHz for 30-45 µF effective output capacitance, about 5° more phase margin than rev 1, with a slower settling tail. Scope one VCC load step on the first board.
- **ESD:** SRV05-4 arrays on the USBLC6-2SC6 pinout (two channels per line: 1/6 D+, 3/4 D−, 5 VP, 2 VN). VP is a 5 V working-voltage clamp, so tie it to 3V3 (USB-C) or 5 V (USB-A), never to PD VBUS. On USB-A it sits at 4.96 V, at the working voltage, so leakage may run above the 5 µA spec. The SMBJ20A TVS clamps PD VBUS.
- **LED stick (J12):** an off-board DIYmall 8 × WS2812B 5050 stick (5V/GND/DIN, about 51 × 10 mm) on the case's top edge near the USB ports, on a short cable to a JST-PH 3-pin header. WS2812B needs VIH ≥ 0.7 × VDD (3.5 V at 5 V), so GPIO21 (PIO) drives it through a 74AHCT1G125 (TTL inputs, 5 V supply) and 330 Ω. It runs from VCC, the 5 V buck: up to about 0.5 A at full white against roughly 2.3 A for the whole rail, so **firmware should cap brightness**. A 10 µF bulk cap sits at the connector.
- **Not using:**
  - JST-PH/XH for battery power, which are rated only 2–3 A. The pack plugs into an XT60 instead;
  - reverse-polarity protection, because the XT60 is keyed (the pigtail is soldered once, red to "+").
- **Pack: Gens Ace Soaring 3S1P 1000 mAh 30C** (listed as 71.5 × 35 × 17 mm or 71.5 × 30 × 20 mm, ±5 mm; the layout allows **74 × 36 × 20 mm** until a real pack is measured). It has an XT60 male main lead, a JST-XH 4-pin balance lead and no protection board or NTC, so the board protects it:
  - **BQ7791501** standalone primary protector (OV 4.25 V, UV 2.8 V; OTD 70 °C, OTC 50 °C, UTD −20 °C, UTC 0 °C) with low-side back-to-back N-FETs. Path: cell − → shunt → DSG FET → CHG FET → board GND (PACK−).
  - **Shunt: 2 × 5 mΩ 2512 in parallel (2.5 mΩ)**, which sets OCD1 14 A, OCD2 24 A, SCD 48 A and charge OC 8 A. The 15 A fuse stays as the backstop.
  - The balance lead feeds the cell inputs (100 Ω / 1 µF filters) and passive balancing.
  - An on-board 0603 NTC by the FETs serves the protector. A 10 kΩ B3435 bead on wire pads (J2), taped to the pack, serves the charger's TS.
- **Pack connector: an XT60 female pigtail** (14 AWG, about 6–8 cm, off-board) soldered to two wire pads (J3) at the top of the left-end strip. It mates with the pack's XT60 plug off the board, and the mated pair (about 31 × 15.5 × 8.1 mm plus wire bends) stands on its 15.5 mm side in a channel under the strip, left of J11 (B.Fab: board x 0.6–8.9, y 1–46.6). Two board-mounted options were dropped:
  - a **vertical XT60**: its mated stack is about 26–30 mm below the board, over the 22 mm envelope (2 mm gap + 20 mm pack);
  - a **right-angle XT60PW-F**: its plug has to slide straight on along about 20 mm of the strip, and J11 and the M5/M6 pin tails sit in that path.
- **Board: 91 × 47 mm** (74 mm pack envelope + a 17 mm connector strip at the left end), in a **96 × 52 mm box** (outline + 5 mm). If the measured pack is 71.5 mm long, the board can drop to about 89 × 47. The pack sits 2 mm behind the board, x 17–91, y 5.5–41.5 board mm (centred across the height), with its lead end facing the strip.

## Parts

| Role | MPN | Mfr | Package | LCSC | JLC stock / class | Asm | Notes |
|---|---|---|---|---|---|---|---|
| MCU | RP2354A | Raspberry Pi | QFN-60 7x7 | C41378174 | 11,350 / ext | M | DK: SC1511-A4. KiCad `MCU_RaspberryPi:RP2354A` |
| Core SMPS inductor (L3) | AOTA-B201610S3R3-101-T | Abracon | 0806 | (C42411119) | **4** / ext (2026-10-16) | **D** | Specified by RPi; polarity-marked (dot = pin 1 = +1V1). **Buy from Digi-Key and hand-place**: DNP, excluded from BOM and position files in the schematic and board, so the JLC BOM/CPL skip it |
| Crystal 12 MHz | ABM8-272-T3 | Abracon | 3225 | C20625731 | 6,171 / ext | M | 2× 15 pF C0G, 1 kΩ on XOUT |
| 3.3 V LDO | XC6206P332MR-G | Torex | SOT-23-3 | C5446 | 432,828 / basic | M | 200 mA, 6 V max in, 250 mV dropout at 100 mA, no EN. Local symbol `hexyhustle:XC6206P332MR`. Was AP2112K (C51118) |
| USB-only 5 V reg | HT7550-1 | Holtek | SOT-89-3 | C16106 | 208,365 / pref | M | 30 V in, 150 mA; load ≈ 50 mA |
| OR diodes ×2 | B5819W | MDD | SOD-123 | C64885 | 817,211 / pref | M | |
| Charger | BQ25798RQMR | TI | VQFN-29 4x4 | C2876593 | 3,289 / ext | M | Fallback BQ25792RQMR C2862876 (8,312) |
| Charger inductor | FNR4030S2R2MT | Changjiang | 4x4 | C167869 | 55,644 / ext | M | 2.2 µH, Isat 4.9 A, Irms 2.95 A, DCR 39 mΩ max; `Inductor_SMD:L_Changjiang_FNR4030S`. Was MWSA0402S (C408335, delisted) |
| PD sink | CH224A | WCH | ESSOP-10 | C42459160 | 15,449 / ext | M | CH224K is EOL. 9 V via CFG1 resistor; check value against the CH224A datasheet. Not at DK |
| VBUS TVS | SMBJ20A | hongjiacheng | SMB | C19077575 | 19,908 / pref | M | Unidirectional. Was MDD C364296. DK: Littelfuse SMBJ20A |
| USB ESD ×2 (U6, U11) | SRV05-4 | hongjiacheng | SOT-23-6 | C7420376 | 48,574 / pref | M | One per port, same footprint as the USBLC6-2SC6 it replaces (C7519). Pinout per the industry SRV05-4 (onsemi); **check the hongjiacheng PDF by eye** before ordering. Local symbol `hexyhustle:SRV05-4` |
| USB-C receptacle | TYPE-C16PIN | SHOU HAN | SMD + THT shell | C393939 | 349,824 / ext | M | `hexy:USB_C_Receptacle_ShouHan_TYPE-C16PIN` (the GCT USB4105 pattern, outer GND pads trimmed 0.1 mm for peg clearance). Same pegs, tabs and mouth as the HRO TYPE-C-31-M-12 (C165948), which stays the fallback |
| USB-A receptacle | AF 90 WJDG | SHOU HAN | THT RA | C456018 | 105,145 / ext | H | `hexy:USB_A_ShouHan_AF90_WJDG`: the maker drawing (shell tabs 2.4 mm forward, Ø2.1) and EasyEDA (2.71, Ø2.3) disagree, so the shell holes are 2.3 × 2.6 slots that take either. Mouth 12.8-13.0 mm from the contact row, so 0.05-0.26 mm behind the board edge. Was Amphenol 87520-0010BLF (C599115) |
| USB-A power switch | SY6280AAC | Silergy | SOT-23-5 | C55136 | 106,445 / ext | M | Ilim = 6800 / Rset: R79 10 kΩ gives 0.68 A nominal (about 0.51-0.85 A, extrapolating the ±25 % spec at 6.8 k). Active-high EN (must not float; R50 holds it low). No fault flag. Local symbol `hexyhustle:SY6280AAC`. Was TPS2051C (C129581) |
| Battery fuse | 0453015.MR | Littelfuse | 2410 | C178997 | 3,510 / ext | M | 15 A **very fast-acting** (the old "slow-blow" label was wrong). Alt 0451015.MRL (C44480). The cheaper JDT JFC2410-2150TS (C136393) was **rejected**: it is time-lag, about 7-15× slower at 30-50 A, with 2.4× the melting I²t |
| Power switch FET | AO4407A | UMW | SOP-8 | C2841482 | 96,825 / ext | M | −30 V, 9.5 mΩ. Alt AONR21357 (C431196) |
| Power slide switch | SK12D07VG4 | SHOU HAN | THT RA SPDT | C393937 | 101,545 / ext | H | Switches the FET gate only; rated 50 V (the SMD MSK12C02 was rated 12 V and sees 12.6 V). `hexy:SW_SPDT_ShouHan_SK12D07VG4`, body face on the top edge. **The 2 × 2 lever reaches 4.0 mm past the board edge (datasheet; EasyEDA draws about 2.65), more than the 2.5 mm board-to-wall gap: the box wall needs a slot for it** |
| Pack connector (J3) | none on the board: two 14 AWG wire pads (Connector_Wire SolderWire-2sqmm, 2.5 mm drill, 7.8 mm pitch) | | THT pads | | | H | Solder an XT60 **female** pigtail (Amass XT60-F with 14 AWG silicone wire, bought separately) from the top: red to "+" (pin 2, PACK+), black to "-" (pin 1, the pack's −, BAT_N, before the FETs). Check that the pack's plug is the male (pin) type before ordering |
| Balance connector (J11) | B4B-XH-A(LF)(SN) | JST | THT vertical | C144395 | not rechecked | H | Bottom side in the strip beside M5/M6, mates the pack's 4-pin balance lead |
| Pack protector (U13) | BQ7791501PWR | TI | TSSOP-24 | C2876947 | not rechecked | M | 3S hookup: VC3–VC5 tied, CCFG/CTRC/CTRD/CBI to VSS, PRES 10 kΩ to VDD, CBO/LPWR open, ROCD 100 kΩ (EEPROM delays) |
| Protection FETs ×2 (Q2 DSG, Q3 CHG) | 80N03F | HL | PDFN 5x6 (TDSON-8) | C7471104 | 5,010 / ext | M | 30 V N-channel, back to back, drains joined. Pins 1-3 S, 4 G, 5-8 D, same as the TDSON-8 footprint; Ciss 1.4 nF, Qg 32 nC, VGS ±20 V, matching the old part. Was RC80N03D5 (C5443943, delisted). Alt PTN10HN03 (C49384072) |
| Current shunt ×2 (R66, R67) | LRBM25GFER005 | NCT | 2512 | C5121087 | 29,810 / ext | M | 5 mΩ each, in parallel. Was RALEC C154688 |
| Protector NTC (TH1) | NCP18XH103F03RB | Murata | 0603 | C13564 | 168,924 / ext | M | 10 kΩ B25/85 3434, by the FETs: OTC 50 °C / OTD 70 °C stay within 0.5 °C. Was TDK C22432708 (4 in stock) |
| Charger NTC (J2) | none: 10 kΩ B3435 bead on wire pads (Connector_Wire 0.1 mm²) | | THT pads | | | H | Taped to the pack; the Gens Ace has no NTC |
| Fiducials ×3 | — | — | 1 mm, 2 mm mask | — | — | — | Top side |
| 5 V buck | AP64500SP-13 | Diodes | SO-8EP | C2070920 | **19** / ext (2026-10-16) | M | Unchanged from rev 1. **Low JLC stock: consign from DK/Mouser** |
| Buck inductor | CR4030-3R6M | Ceaiya | 4x4 | C7588667 | 664 / ext | M | Unchanged value. Alt 3.3 µH Sunlord SWPA4030S3R3MT (C15269, 29k) |
| Motor drivers ×3 | DRV8848PWPR | TI | HTSSOP-16 | C131079 | (rev 1) | M | Unchanged; sense pins to GND |
| Motor connectors ×6 | S2B-XH-A(LF)(SN) | JST | THT RA | C157931 | 82,074 / ext | H | Unchanged |
| IO headers ×6 (1x3) | 2.54-1*3P | BOOMELE(Boom Precision Elec) | THT vertical | C49257 | 196,940 / ext | H | One per port, side by side at 2.54 mm as one 3 × 6 block under a recessed slot in the face (nothing sticks out). Replaces the right-angle hanxia C32713262; same netlist. Stock checked on LCSC 2026-10-16 |
| BOOT / RESET buttons | TS-1088-AR02016 | XUNPU | SMD 4x3 | C720477 | 642,299 / **basic** | M | 1 kΩ in series on each |
| LED stick buffer (U14) | SN74AHCT1G125DBVR | UMW | SOT-23-5 | C20617903 | 28,924 / ext | M | 3.3 V → 5 V for the WS2812B data line; /OE to GND. $0.053 at JLC vs TI C7484 at $0.100 (51,402), the fallback |
| LED stick connector (J12) | B3B-PH-K-S(LF)(SN) | JST | THT vertical, 2 mm | C131339 | 169,640 / ext | H | Pin 1 5 V, 2 DIN, 3 GND. Top edge beside the USB-C/USB-A group |
| Status LED (GPIO) | KT-0603R | KENTO | 0603 red | C2286 | 7.8 M / **basic** | M | |
| Charge LED (STAT) | KT-0805G | KENTO | 0805 green | C2297 | basic | M | Was KT-0603G (C12624, extended) |
| Passives | UNI-ROYAL 0402WGF…/0603WAF…, Samsung CL05/CL10/CL21/CL31, FH 0402/0603 | — | 0402/0603/0805/1206 | See `PASSIVES` in `circuit/goosebrain.py` | Mostly basic or preferred, all in stock | M | Cost-down (2026-10-16): buck 39k/7.5k/15k/4.7nF, buck outputs C5/C8/C12 22 µF **1206/10 V** CL31A226KPHNNNE (C5672; 5 V DC-bias capacitance not published, check ripple on the first board), C59 10 µF 0805, R44/R45 27 Ω 0603, C18/C19 47 nF 0603, VINT caps C2/C9/C13 2.2 µF 0603, C17/C37 1 µF 0603/50 V CL10A105KB8NNNC (C15849) |

## Stock and supply risks

1. **RP2354 core inductor L3 (4 at JLC on 2026-10-16, down from 9).** Raspberry Pi specifies this exact part. It is now a Digi-Key part, hand-placed after assembly (DNP for PCBA; the pads stay on the board). Don't substitute an unmarked inductor.
2. **AP64500 buck (19 at JLC on 2026-10-16, down from 38).** Kept. JLC covers up to 19 boards; **above 19 boards it must come from Digi-Key** (consign it, or hand-place it like L3). Check stock again before ordering.
3. **Single-source Chinese parts** (CH224A, SHOU HAN USB-C/USB-A/switch, hongjiacheng SRV05-4/SMBJ20A, HL 80N03F): order through LCSC. Each has an alternative listed above except the CH224A. For it, the fallback is 5 V-only charging: 5.1 kΩ Rd on CC1/CC2 and no PD.
4. **Unconfirmed stepping.** Confirm that the RP2354A is A4-stepping at the distributor. As far as found, RP2354 parts launched with the A4 stepping.
5. **Cleared on 2026-10-16:** TH1 (now Murata C13564), the protection FETs (now HL 80N03F) and the charger inductor (now FNR4030S2R2MT). BQ7791501PWR is at about 303.
