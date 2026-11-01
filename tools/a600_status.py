#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read live status from the Corsair ONE a600 cooling controller (1b1c:0d27).

Sends only the two read commands Corsair Dashboard polls with (status and mode);
nothing that changes settings. Safe to run while the plugin is running: every
hidraw reader gets its own copy of the replies.

Usage: a600_status.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "coolercontrol-plugin", "corsair-a600"))
import a600hw  # noqa: E402

LABELS = {"gpu1": "GPU 1", "gpu2": "GPU 2", "gpu3": "GPU 3", "cpu1": "CPU 1", "cpu2": "CPU 2"}


def main():
    cooling = a600hw.Cooling()
    try:
        cooling.open()
        reply = cooling._transfer(b"\x01")
        mode = cooling.mode()
    except OSError as e:
        sys.exit(f"Cannot read the cooling controller: {e}")
    finally:
        cooling.close()

    fans, pumps = a600hw.decode_status(reply)
    print(f"Device: {cooling.path}")
    print(f"Mode:   {a600hw.MODE_NAMES.get(mode, f'unknown ({mode})')}")
    print()
    print(f"{'Fan':<10}{'Temp seen':>10}{'Target':>9}{'Actual':>9}")
    for i, (cid, (target, actual)) in enumerate(fans.items()):
        temp = struct.unpack_from(">B", reply, 4 + 6 * i)[0]
        print(f"{LABELS[cid]:<10}{temp:>8} °C{target:>9}{actual:>9}")
    print()
    print(f"Pumps:  {pumps[0]} rpm, {pumps[1]} rpm")


if __name__ == "__main__":
    main()
