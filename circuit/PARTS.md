# goosebrain rev 2 parts

Parts for the RP2354 + USB host + internal 3S battery revision. **MPN is the primary ID**, and LCSC is optional, for JLC assembly. Stock was checked on 2026-10-15 through JLCPCB's parts API. "DK" means Digi-Key and Mouser carry the manufacturer's line; it was not checked live unless marked ✓.

**Assembly** column: **M** = machine (PCBA), **H** = hand-solder (through-hole).

## Design decisions behind the parts

- **MCU: RP2354A**, the RP2350A with 2 MB of flash stacked in the package. JLC has it in stock, so no external flash chip is needed. The pinout is identical to the RP2350A, so the RP2350A plus a W25Q16JV can replace it if needed.
- **Charger: BQ25798.** It's the active sibling of the BQ25792 (TI's BQ25792 pages now return 404). Pinout and PROG table are identical, and KiCad 10 ships its symbol (`Battery_Management:BQ25798`).
- **Motors and the 5 V buck run straight from the pack**, through the fuse and power switch, not from the charger's SYS output. The charger's internal battery switch is rated 6 A continuous and only 10 A for at most 1 s (BQ25798 datasheet, Recommended Operating Conditions), which motor stalls would exceed. SYS gets its capacitors and no load.
- **Charge current is safe with zero firmware.** The power-on default charge current is 1 A, and no pin can change it, so the **ILIM_HIZ divider caps input current** instead. 100 kΩ from REGN with 33 kΩ to GND puts 1.24 V on the pin, which sets about a 0.30 A input limit. That works out to:
  - about 2.4 W from a 9 V PD source, or roughly 220 mA into the pack (about 0.45C for 500 mAh);
  - about 120 mA from plain 5 V USB.

  Firmware can raise the limit over I2C through the board support library. The pack's BMS is the backstop if it's set wrong.
- **PD request: 9 V**, which nearly every USB-PD charger offers (12 V is optional in the spec). It also keeps the USB-only 5 V regulator cool.
- **3S profile:** PROG = 13.7 kΩ (750 kHz, 2.2 µH inductor, 3S → 12.6 V charge voltage). TS divider: 5.23 kΩ (REGN–TS) and 30.1 kΩ (TS–GND) for a 103AT NTC, with JEITA enabled by default. /CE is tied to GND. Charger D+/D− are left open; the ILIM pin overrides detection.
- **Charge LED** on the charger's STAT pin (pulled up to REGN), so charging shows with no firmware.
- **MCU power from USB alone:** HT7550 (30 V in) on VBUS → Schottky → OR'd with the buck's 5 V → AP2112K-3.3.
- **ESD:** the USBLC6-2SC6's VBUS pin is rated 6 V, so tie it to 3V3 (USB-C) or 5 V (USB-A), never to PD VBUS. The SMBJ20A TVS clamps PD VBUS.
- **Not using:**
  - WS2812-type RGB LEDs, which need a supply of 3.5 V or more and a level shifter from 3.3 V GPIO;
  - JST-PH/XH for battery power, which are rated only 2–3 A, so XT30 instead;
  - reverse-polarity protection, because the XT30 is keyed and the internal pack is fitted at build.

## Parts

| Role | MPN | Mfr | Package | LCSC | JLC stock / class | Asm | Notes |
|---|---|---|---|---|---|---|---|
| MCU | RP2354A | Raspberry Pi | QFN-60 7x7 | C41378174 | 11,350 / ext | M | DK: SC1511-A4. KiCad `MCU_RaspberryPi:RP2354A` |
| Core SMPS inductor | AOTA-B201610S3R3-101-T | Abracon | 0806 | C42411119 | **9** / ext | M | Specified by RPi; polarity-marked. **Low JLC stock: consign from DK/Mouser** |
| Crystal 12 MHz | ABM8-272-T3 | Abracon | 3225 | C20625731 | 6,171 / ext | M | 2× 15 pF C0G, 1 kΩ on XOUT |
| 3.3 V LDO | AP2112K-3.3TRG1 | Diodes | SOT-23-5 | C51118 | 11,473 / ext | M | 600 mA, 6 V max in |
| USB-only 5 V reg | HT7550-1 | Holtek | SOT-89-3 | C16106 | 208,365 / pref | M | 30 V in, 150 mA; load ≈ 50 mA |
| OR diodes ×2 | B5819W | MDD | SOD-123 | C64885 | 817,211 / pref | M | |
| Charger | BQ25798RQMR | TI | VQFN-29 4x4 | C2876593 | 3,289 / ext | M | Fallback BQ25792RQMR C2862876 (8,312) |
| Charger inductor | MWSA0402S-2R2MT | Sunlord | 4.4x4.2 | C408335 | 13,612 / ext | M | 2.2 µH, 4.5 A Isat |
| PD sink | CH224A | WCH | ESSOP-10 | C42459160 | 15,449 / ext | M | CH224K is EOL. 9 V via CFG1 resistor; check value against the CH224A datasheet. Not at DK |
| VBUS TVS | SMBJ20A | MDD | SMB | C364296 | 161,936 / ext | M | DK: Littelfuse SMBJ20A |
| USB ESD ×2 | USBLC6-2SC6 | ST | SOT-23-6 | C7519 | 47,922 / ext | M | One per port |
| USB-C receptacle | TYPE-C-31-M-12 | HRO | SMD + THT shell | C165948 | 379,840 / ext | M | Not at DK; alt GCT USB4105-GF-A-120 (C5184243) |
| USB-A receptacle | 87520-0010BLF | Amphenol | THT RA | C599115 | 18,504 / ext | H | Needs a custom footprint (`hexy:USB_A_Amphenol_87520-0010BLF`). Alt SHOU HAN AF 90 WJDG (C456018) |
| USB-A power switch | TPS2051CDBVR | TI | SOT-23-5 | C129581 | 18,917 / ext | M | Fixed 0.5 A limit, active-high EN, KiCad symbol `TPS2051CDBV`. Alt SY6280AAC (C55136) |
| Battery fuse | 0453015.MR | Littelfuse | 2410 | C178997 | 3,510 / ext | M | 15 A slow-blow. Alt 0451015.MRL (C44480) |
| Power switch FET | AO4407A | UMW | SOP-8 | C2841482 | 96,825 / ext | M | −30 V, 9.5 mΩ. Alt AONR21357 (C431196) |
| Power slide switch | MSK12C02 | SHOU HAN | SMD SPDT | C431540 | 179,607 / ext | M | Switches the FET gate only. Alt THT RA SK12D07VG4 (C393937) |
| Battery main | XT30PW-M | Amass | THT RA | C431092 | 65,359 / ext | H | Not at DK (TME) |
| Battery NTC | S2B-PH-K-S | JST | THT RA | C173752 | 147,054 / ext | H | |
| 5 V buck | AP64500SP-13 | Diodes | SO-8EP | C2070920 | **38** / ext | M | Unchanged from rev 1. **Low JLC stock: consign from DK/Mouser** |
| Buck inductor | CR4030-3R6M | Ceaiya | 4x4 | C7588667 | 664 / ext | M | Unchanged value. Alt 3.3 µH Sunlord SWPA4030S3R3MT (C15269, 29k) |
| Motor drivers ×3 | DRV8848PWPR | TI | HTSSOP-16 | C131079 | (rev 1) | M | Unchanged; sense pins to GND |
| Motor connectors ×6 | S2B-XH-A(LF)(SN) | JST | THT RA | C157931 | 82,074 / ext | H | Unchanged |
| IO headers ×6 (1x3) | HX PZ2.54-1x3P WZ | hanxia | THT RA | C32713262 | 35,327 / ext | H | One per port. Straight alt: BOOMELE 2.54-1*3PPin (C49257, 252k); same netlist |
| BOOT / RESET buttons | TS-1088-AR02016 | XUNPU | SMD 4x3 | C720477 | 642,299 / **basic** | M | 1 kΩ in series on each |
| Status LED (GPIO) | KT-0603R | KENTO | 0603 red | C2286 | 7.8 M / **basic** | M | |
| Charge LED (STAT) | KT-0603G | KENTO | 0603 green | C12624 | 521,230 / ext | M | |
| Passives | UNI-ROYAL 0402WGF…, Samsung CL05/CL10/CL21, FH 0402 | — | 0402/0603/0805 | See `PASSIVES` in `circuit/goosebrain.py` | Mostly basic, all in stock | M | The rev 1 buck resistors and C16 moved to 0402 parts; the 22.1 kΩ, 15.8 kΩ and 2.7 nF were at 0–24 stock. The 22 µF outputs are now 0805/25 V (DC-bias fix) |

## Stock and supply risks

1. **RP2354 core inductor (9 at JLC).** Raspberry Pi specifies this exact part. Order it from Digi-Key or Mouser and consign it, or wait for JLC to restock. Don't substitute an unmarked inductor.
2. **AP64500 buck (38 at JLC).** Consign from Digi-Key or Mouser, or check stock again before ordering.
3. **Single-source Chinese parts** (CH224A, HRO USB-C, XT30, SHOU HAN switch): order through LCSC. Each has an alternative listed above except the CH224A. For it, the fallback is 5 V-only charging: 5.1 kΩ Rd on CC1/CC2 and no PD.
4. **Unconfirmed stepping.** Confirm that the RP2354A is A4-stepping at the distributor. As far as found, RP2354 parts launched with the A4 stepping.
