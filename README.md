# thegoose
The schematic uses six interchangeable `IO_PORT_1` through `IO_PORT_6` 3-pin headers. Pin order is 1 = IO, 2 = VCC, 3 = GND. Verify this order against the assembled harness before powering a sensor or servo.

Power-review checklist:

- The VCC rail currently has local 100 nF decoupling and bulk capacitors shown in the schematic; its allowable load must be checked against the regulator/module data sheet and the worst-case current of all six attached devices.
- The six ports are intentionally generic, so no total current rating can be confirmed until the actual sensor/servo part numbers and duty cycle are recorded.
- Replace the remaining generic motor values (`~`) with the selected motor part numbers and confirm their footprints before fabrication.
- Document the soldered battery-wire polarity at the battery connector. Add fuse/reverse-polarity/overvoltage protection to the schematic if the physical battery assembly does not already provide it.
