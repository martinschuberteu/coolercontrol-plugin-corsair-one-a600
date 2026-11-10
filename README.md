# Corsair ONE a600 for CoolerControl

A [CoolerControl](https://gitlab.com/coolercontrol/coolercontrol) device plugin for the **Corsair ONE a600** on Linux: fan and pump monitoring, and a working fan curve without Corsair software.

> Not affiliated with or endorsed by Corsair. The USB protocol was reverse-engineered from Corsair Dashboard for interoperability. Use at your own risk.

## Why it's needed

The a600's cooling controller (USB ID `1b1c:0d27`) drives the five radiator fans (GPU 1–3, CPU 1–2) and reports both pump speeds. No other Linux tool supports it (liquidctl and OpenLinkHub don't know its ID).

The cooling controller runs Corsair's own **Quiet** and **Balanced** fan curves, but only on CPU and GPU temperatures that the computer sends it. Under Windows, Corsair Dashboard sends them every second. Under Linux nothing does, so the fans stay at whatever speed they had when Windows last ran, however hot the system gets. This plugin sends them.

## What you get

- **a600 Cooling** device: live rpm for the five fans (also as % of their 2100 rpm maximum) and both pumps (as % of their nominal 3000 rpm), plus the temperatures being sent to the controller.
- **Plugin page** in CoolerControl: fan mode (Balanced or Quiet). Follows the CoolerControl theme.
- Fail-safe: if a temperature can't be read, or the plugin is stopped normally, 85 °C is sent so the fans run fast rather than idle. If the plugin is killed or crashes, the controller keeps the last temperature it received until systemd restarts the plugin.

### Limitations

- **Fans can't be set to a fixed speed or a CoolerControl curve.** The controller has no fixed-speed command, only its built-in curves. Its *Custom* mode accepts uploaded curves, but in recordings it stopped fans entirely below a threshold regardless of the curve, so it is not used. See [protocol-notes.md](protocol-notes.md).
- Temperatures come from AMD `k10temp` (CPU) and the NVIDIA driver (GPU), which is what the a600 ships with. Other CPU or GPU makers would need small changes.
- Tested with CoolerControl 5.1.1 on CachyOS (Arch-based). The installer uses `pacman` to check dependencies.

## Install

Requirements: CoolerControl 5.1+, `python-grpcio`, `python-protobuf`.

Install the latest [release](https://github.com/martinschuberteu/coolercontrol-plugin-corsair-one-a600/releases/latest) (replace `v0.3.1` with its tag):

```bash
sudo pacman -S --needed python-grpcio python-protobuf
git clone --branch v0.3.1 https://github.com/martinschuberteu/coolercontrol-plugin-corsair-one-a600.git
cd coolercontrol-plugin-corsair-one-a600
sudo bash deploy/install.sh
```

`main` is the development version and may be ahead of the latest release.

The installer:

1. adds a `corsair-a600` group and a udev rule giving that group (and the logged-in desktop user) access to the cooling controller,
2. adds CoolerControl's unprivileged `cc-plugin-user` to the group (the plugin does **not** run as root),
3. copies the plugin to `/var/lib/coolercontrol/plugins/corsair-a600`, keeping your saved settings,
4. restarts CoolerControl, which starts the plugin as `cc-plugin-corsair-a600.service`.

To update, check out the new release tag and run the installer again (your settings are kept):

```bash
git fetch --tags
git checkout v0.3.1   # the new tag
sudo bash deploy/install.sh
```

To be told about new versions, use *Watch → Custom → Releases* on GitHub.

Logs: `journalctl -u cc-plugin-corsair-a600 -f`. Remove everything with `sudo bash deploy/uninstall.sh`.

If you set temporary permissions on `/dev/hidraw*` with `setfacl` before installing, reboot once (or run `sudo setfacl -b` on those nodes), otherwise the old ACL can override the group access.

### Motherboard fan header

The motherboard's CPU_FAN header carries one pump's speed signal (about 3000 rpm), not a fan. The kernel's built-in `nct6683` driver reads it on the a600's MSI board, so no extra driver is needed for that reading.

## Development

| Path | Contents |
|---|---|
| `coolercontrol-plugin/corsair-a600/` | the plugin as installed: `corsair_a600_plugin.py` (gRPC service, temperature feed), `a600hw.py` (USB protocol), `manifest.toml`, `config.json`, `ui/` (settings page), `gen/` (generated gRPC code) |
| `coolercontrol-plugin/proto/` | CoolerControl's device-service protobuf definitions (5.1.1) |
| `coolercontrol-plugin/generate.sh` | regenerates `gen/` from `proto/` (needs `python-grpcio-tools`) |
| `coolercontrol-plugin/test_client.py` | queries a running plugin the way CoolerControl does |
| `tests/` | protocol unit tests built from recorded Corsair Dashboard packets |
| `tools/` | `a600_status.py` (read live fan status), parsers for USBPcap recordings |
| `docs/capturing.md` | how the protocol was recorded |
| `protocol-notes.md` | the reverse-engineered protocol |

```bash
python3 -m unittest discover -s tests
python3 tools/a600_status.py          # live status, read-only
```

Run the plugin by hand (stop CoolerControl's copy first, or both will feed the controller):

```bash
python3 coolercontrol-plugin/corsair-a600/corsair_a600_plugin.py
python3 coolercontrol-plugin/test_client.py status
```

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The files in `coolercontrol-plugin/proto/` are from CoolerControl (GPL-3.0-or-later, © Guy Boldon, Eren Simsek and contributors), and the code in `gen/` is generated from them.
