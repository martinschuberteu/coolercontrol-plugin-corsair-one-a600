# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal pcapng + USBPcap (linktype 249) reader. No dependencies."""
import struct

TRANSFER = {0: "iso", 1: "int", 2: "ctrl", 3: "bulk"}


class Packet:
    __slots__ = ("t", "irp", "status", "function", "info", "bus", "dev", "ep",
                 "transfer", "stage", "data")

    @property
    def is_in(self):
        return bool(self.ep & 0x80)

    @property
    def is_completion(self):
        # info bit 0: 1 = PDO->FDO (completion / data coming back from device)
        return bool(self.info & 1)


def read_pcapng(path):
    """Yield (timestamp_seconds, linktype, raw_bytes) for each packet."""
    with open(path, "rb") as f:
        buf = f.read()
    off = 0
    endian = "<"
    ifaces = []  # list of (linktype, ts_divisor)
    while off + 12 <= len(buf):
        btype = struct.unpack_from(endian + "I", buf, off)[0]
        if btype == 0x0A0D0D0A:
            bom = buf[off + 8:off + 12]
            endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            ifaces = []
        blen = struct.unpack_from(endian + "I", buf, off + 4)[0]
        if blen < 12 or off + blen > len(buf):
            break
        body = buf[off + 8:off + blen - 4]
        if btype == 1:  # Interface Description Block
            linktype = struct.unpack_from(endian + "H", body, 0)[0]
            div = 1_000_000
            o = 8
            while o + 4 <= len(body):
                code, ln = struct.unpack_from(endian + "HH", body, o)
                if code == 0:
                    break
                if code == 9 and ln >= 1:  # if_tsresol
                    v = body[o + 4]
                    div = (2 ** (v & 0x7F)) if v & 0x80 else 10 ** v
                o += 4 + ((ln + 3) & ~3)
            ifaces.append((linktype, div))
        elif btype == 6:  # Enhanced Packet Block
            iface, th, tl, caplen, _ = struct.unpack_from(endian + "IIIII", body, 0)
            data = body[20:20 + caplen]
            linktype, div = ifaces[iface] if iface < len(ifaces) else (None, 1_000_000)
            yield ((th << 32) | tl) / div, linktype, data
        off += blen


def parse_usbpcap(raw):
    p = Packet()
    (hlen, p.irp, p.status, p.function, p.info, p.bus, p.dev, p.ep,
     p.transfer, dlen) = struct.unpack_from("<HQIHBHHBBI", raw, 0)
    p.stage = raw[27] if p.transfer == 2 and hlen >= 28 else None
    p.data = raw[hlen:hlen + dlen]
    return p


def packets(path):
    t0 = None
    for t, lt, raw in read_pcapng(path):
        if lt != 249 or len(raw) < 27:
            continue
        p = parse_usbpcap(raw)
        if t0 is None:
            t0 = t
        p.t = t - t0
        yield p


def device_map(pkts):
    """Map (bus, dev) -> (vid, pid) from device descriptors seen in control transfers."""
    m = {}
    for p in pkts:
        d = p.data
        if p.transfer == 2 and p.is_completion and len(d) >= 18 and d[0] == 18 and d[1] == 1:
            vid, pid = struct.unpack_from("<HH", d, 8)
            m[(p.bus, p.dev)] = (vid, pid)
    return m
