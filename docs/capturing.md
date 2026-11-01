# Recording the Corsair Dashboard protocol

How the USB traffic in [protocol-notes.md](../protocol-notes.md) was recorded, for anyone who wants to extend it (for example to understand Custom mode). Needs Windows with Corsair Dashboard on the same machine (dual boot works).

## Setup

1. Install [Wireshark](https://www.wireshark.org/download.html) with the **USBPcap** option ticked, then restart Windows.
2. Start Wireshark as administrator. Each `USBPcapN` interface is one USB controller. Click the gear next to each until you find the one listing the Corsair cooling controller (`VID_1B1C&PID_0D27`).
3. In that dialog untick *Capture from all devices connected* and tick only the cooling controller, so keyboards and Bluetooth stay out of the recording. If USBPcap ignores the selection, filter later by device address and do not share the raw files.
4. **Decline any firmware update** Dashboard offers; it could change the protocol.
5. Quit Dashboard completely (tray icon, remaining processes, and any Corsair service in `services.msc`) so the first recording includes its start-up.

## Recordings

One file per row. Pause 15–20 s between changes so each change stands out, and write down what you changed and what Dashboard showed (screenshots help).

| File | Actions |
|---|---|
| `01-startup.pcapng` | start recording, then start Dashboard; touch nothing for 60 s |
| `02-idle.pcapng` | Dashboard open, 60 s, screenshots of fan speeds at start and end |
| `03-modes.pcapng` | Quiet, Balanced, Custom |
| `04-fan-<name>.pcapng` | one fan's curve at a few distinct speeds (one file per fan) |
| `05-exit.pcapng` | exit Dashboard while recording |

## Analysing

```bash
python3 tools/dump.py 03-modes.pcapng --no-ctrl --strip-trailing-zeros
python3 tools/status.py 04-fan-cpu1.pcapng 3
```

`dump.py` prints the cooling controller's traffic; `status.py` decodes the cooling controller's status replies over time.
