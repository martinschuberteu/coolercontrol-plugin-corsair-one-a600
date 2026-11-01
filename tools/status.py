# SPDX-License-Identifier: GPL-3.0-or-later
"""Decode 0d27 status replies (21 01 ...) and host temperature pushes (20 03 ...) over time.

Usage: status.py FILE [EVERY_N]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usbpcap  # noqa: E402

NAMES = ["GPU1", "GPU2", "GPU3", "CPU1", "CPU2", "ch6"]


def main():
    path = sys.argv[1]
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    pk = list(usbpcap.packets(path))
    m = usbpcap.device_map(pk) or {(4, 3): (0x1B1C, 0x0D27)}
    n = 0
    print("time     " + " ".join(f"{x:>14}" for x in NAMES) + "   pumpA pumpB  tail")
    for p in pk:
        if m.get((p.bus, p.dev)) != (0x1B1C, 0x0D27) or p.transfer != 1:
            continue
        d = p.data
        if p.is_in and p.is_completion and d[:2] == b"\x21\x01":
            n += 1
            if n % every:
                continue
            cols = []
            for i in range(6):
                temp, _, tgt, act = struct.unpack_from(">BBHH", d, 4 + 6 * i)
                cols.append(f"{temp:2d}C {tgt:4d}/{act:4d}")
            pa, pb = struct.unpack_from(">HH", d, 40)
            tail = d[56:62].hex(" ")
            print(f"{p.t:7.2f}  " + " ".join(f"{c:>14}" for c in cols) + f"   {pa:5d} {pb:5d}  {tail}")
        elif not p.is_in and not p.is_completion and d[:2] == b"\x20\x13":
            print(f"{p.t:7.2f}  >>> set mode {d[2] if len(d) > 2 else 0}")
        elif not p.is_in and not p.is_completion and d[:2] == b"\x20\x09":
            print(f"{p.t:7.2f}  >>> commit {d[2:7].hex(' ')}")


if __name__ == "__main__":
    main()
