# SPDX-License-Identifier: GPL-3.0-or-later
"""Print cooling controller (1b1c:0d27) USB traffic from a USBPcap pcapng, one line per transfer.

Usage: dump.py FILE [--no-ctrl] [--strip-trailing-zeros]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usbpcap  # noqa: E402

COOLING = (0x1B1C, 0x0D27)
FALLBACK = {(4, 3): COOLING}


def main():
    args = sys.argv[1:]
    path = args.pop(0)
    no_ctrl = "--no-ctrl" in args
    strip = "--strip-trailing-zeros" in args
    pk = list(usbpcap.packets(path))
    m = usbpcap.device_map(pk) or FALLBACK
    for p in pk:
        if m.get((p.bus, p.dev)) != COOLING:
            continue
        pid = COOLING[1]
        if p.transfer == 2:
            if no_ctrl:
                continue
            # setup stage carries the 8-byte setup packet in the request
            if not p.is_completion and p.stage == 0 and len(p.data) >= 8:
                d = p.data
                print(f"{p.t:9.3f} {pid:04x} SETUP bm={d[0]:02x} req={d[1]:02x} val={d[3]:02x}{d[2]:02x} idx={d[5]:02x}{d[4]:02x} len={d[7] << 8 | d[6]}"
                      + (f" data={d[8:].hex(' ')}" if len(d) > 8 else ""))
            elif p.is_completion and p.data:
                print(f"{p.t:9.3f} {pid:04x} CTRL< {p.data.hex(' ')}")
            continue
        if not p.data:
            continue
        # OUT data travels in the request, IN data in the completion
        if p.is_in != p.is_completion:
            continue
        d = p.data.rstrip(b"\0") if strip else p.data
        arrow = "<" if p.is_in else ">"
        print(f"{p.t:9.3f} {pid:04x} {arrow} ep{p.ep & 0x7f} ({len(p.data)}) {d.hex(' ')}")


if __name__ == "__main__":
    main()
