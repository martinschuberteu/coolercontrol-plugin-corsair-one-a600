# Corsair ONE a600 cooling controller USB protocol

Decoded from Corsair Dashboard captures (Windows, USBPcap, 2026-11-01). The controller is plain HID: write an output report to the interrupt OUT endpoint, read the reply on the interrupt IN endpoint. On Linux it is reachable through `/dev/hidraw*` without a kernel driver.

## Cooling controller `1b1c:0d27` ("Corsair one i500 cooling system")

Single interface. Output report ID `0x20` (64 data bytes), input report ID `0x21` (63 data bytes). Every reply echoes the command byte, followed by a constant block `28 00 3b 00 09 51` plus a 7-character ASCII string (likely firmware/hardware identifiers; the string may be unit-specific, so it is not reproduced here).

Multi-byte values in status replies are **big-endian**; RPM values inside curve uploads are **little-endian**.

### Channels

| Index | Dashboard name | Notes |
|---|---|---|
| 0 | GPU 1 | GPU radiator |
| 1 | GPU 2 | GPU radiator |
| 2 | GPU 3 | GPU radiator |
| 3 | CPU 1 | CPU radiator |
| 4 | CPU 2 | CPU radiator |
| 5 | (unused) | always 0 rpm; Dashboard mirrors CPU settings into it |

Maximum fan speed is 2100 rpm (Dashboard's "100 %").

### Commands

| Command | Host sends | Reply | Meaning |
|---|---|---|---|
| Status | `20 01` | see below | Dashboard polls once per second |
| Push temperatures | `20 03 g g g c c c` | ack | GPU °C for channels 0–2, CPU °C for channels 3–5. Dashboard sends this about once per second. **The controller runs its fan curves on these host-supplied temperatures.** |
| Set mode | `20 13 <m>` | ack | `00` Quiet, `01` Balanced, `02` Custom (Dashboard sends `20 13` with no byte for Quiet) |
| Read mode | `20 15` | `21 15 00 <m>` | current mode |
| Upload curve | `20 05 <ch> 02 <7 temps A> <7 × u16le rpm> <14 × 01> <7 temps B> <14 × 01>` | ack | one packet per channel 0–5; Dashboard sends all six, then commits |
| Commit | `20 09 df 5a a5 fa 55` | ack | sent after the six curve packets, before `20 13 02`; probably writes the curves to flash, so don't send it often |

### Status reply `21 01 00 00 …`

Starting at byte 4: six 6-byte channel records `<temp °C> 00 <target rpm u16be> <actual rpm u16be>`, then `<pump A rpm u16be> <pump B rpm u16be>` (≈2970 and ≈3000, pumps are not controllable from Dashboard), then the constant block, then `00 03 00 06 02 xx` (last byte varies slowly, meaning unknown).

Example (Balanced, idle): GPU 1 `23 00 0546 0559` = 35 °C, target 1350, actual 1369 rpm.

### Observed behaviour

- **Quiet** at idle: GPU 800/800/700, CPU 1100/1000 rpm targets. **Balanced** at idle: GPU 1350/1000/1000, CPU 1600/1500 (at 62–70 °C CPU).
- **Custom** mode behaved unexpectedly: with Dashboard's curves uploaded, fans reported target **0 rpm** whenever the pushed temperature was below the first entry of *temps B* (GPU below 50 °C, CPU below 65 °C) and **2100 rpm** at or above it, regardless of the RPM values set in Dashboard. Not understood yet; custom curves are not safe to use until it is.
- Dashboard sends nothing special on exit. The controller keeps the last mode and the last pushed temperatures.

## Reproducing

How the recordings were made: [docs/capturing.md](docs/capturing.md). Raw captures are not published (they contain unrelated USB devices and serial numbers).

Parsers in `tools/`: `usbpcap.py` (pcapng + USBPcap reader), `dump.py` (hex dump), `status.py` (decoded fan status over time).
