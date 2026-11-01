# SPDX-License-Identifier: GPL-3.0-or-later
"""Protocol tests using packets recorded from Corsair Dashboard (see protocol-notes.md)."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "coolercontrol-plugin", "corsair-a600")
sys.path[:0] = [PLUGIN_DIR, os.path.join(PLUGIN_DIR, "gen")]

import a600hw  # noqa: E402


def hexbytes(text, length=None):
    data = bytes.fromhex(text)
    return data + bytes(length - len(data)) if length else data


# Status reply captured at Dashboard start-up (Balanced mode, idle).
STATUS_REPLY = hexbytes(
    "21 01 00 00 23 00 05 46 05 59 23 00 03 e8 03 fb 23 00 03 e8 03 f9 38 00 05 46 05 59"
    " 38 00 04 b0 04 c3 38 00 00 00 00 00 0b 9a 0b b8 28 00 3b 00 09 51", 64)


class CoolingProtocol(unittest.TestCase):
    def test_decode_status_matches_dashboard(self):
        fans, pumps = a600hw.decode_status(STATUS_REPLY)
        # Dashboard showed GPU fans 1369/1019/1018 and CPU fans 1369/1221 rpm at the same time.
        self.assertEqual(fans["gpu1"], (1350, 1369))
        self.assertEqual(fans["gpu2"], (1000, 1019))
        self.assertEqual(fans["gpu3"], (1000, 1017))
        self.assertEqual(fans["cpu1"], (1350, 1369))
        self.assertEqual(fans["cpu2"], (1200, 1219))
        self.assertEqual(pumps, (2970, 3000))

    def test_decode_status_rejects_other_replies(self):
        with self.assertRaises(ValueError):
            a600hw.decode_status(hexbytes("21 03 00 00", 64))
        with self.assertRaises(ValueError):
            a600hw.decode_status(STATUS_REPLY[:20])

    def test_temps_payload_matches_dashboard(self):
        # Dashboard: GPU 35 °C, CPU 56 °C -> 20 03 23 23 23 38 38 38 (report ID added on write).
        self.assertEqual(a600hw.temps_payload(35, 56), hexbytes("03 23 23 23 38 38 38"))

    def test_temps_payload_range(self):
        with self.assertRaises(ValueError):
            a600hw.temps_payload(-1, 50)
        with self.assertRaises(ValueError):
            a600hw.temps_payload(50, 256)

    def test_only_quiet_and_balanced_are_settable(self):
        self.assertEqual(set(a600hw.MODES.values()), {0, 1})


class PluginMetadata(unittest.TestCase):
    def test_versions_match(self):
        with open(os.path.join(PLUGIN_DIR, "manifest.toml")) as f:
            manifest_version = re.search(r'^version = "([^"]+)"', f.read(), re.M).group(1)
        with open(os.path.join(PLUGIN_DIR, "corsair_a600_plugin.py")) as f:
            plugin_version = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M).group(1)
        self.assertEqual(manifest_version, plugin_version)


if __name__ == "__main__":
    unittest.main()
