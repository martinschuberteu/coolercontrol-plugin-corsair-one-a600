#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install the Corsair ONE a600 CoolerControl plugin. Run with: sudo bash deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }
pacman -Q python-grpcio python-protobuf >/dev/null || { echo "Install python-grpcio and python-protobuf first" >&2; exit 1; }

PLUGIN_ID=corsair-a600
PLUGIN_DIR=/var/lib/coolercontrol/plugins/$PLUGIN_ID
PLUGIN_USER=cc-plugin-user   # the user CoolerControl runs unprivileged plugins as

# Device access: a group that owns the cooling controller's hidraw node.
install -Dm644 deploy/corsair-a600.sysusers   /etc/sysusers.d/corsair-a600.conf
install -Dm644 deploy/70-corsair-a600.rules /etc/udev/rules.d/70-corsair-a600.rules
systemd-sysusers /etc/sysusers.d/corsair-a600.conf
udevadm control --reload
udevadm trigger --subsystem-match=hidraw --action=change

# The plugin user (created the same way CoolerControl does it) joins that group.
id "$PLUGIN_USER" >/dev/null 2>&1 || useradd --system --comment "CoolerControl unprivileged plugin user" \
    --shell /usr/sbin/nologin "$PLUGIN_USER"
usermod -aG corsair-a600 "$PLUGIN_USER"

# Plugin files. An existing config.json (your saved settings) is kept.
keep_config=""
[[ -f $PLUGIN_DIR/config.json ]] && keep_config=$(cat "$PLUGIN_DIR/config.json")
rm -rf "$PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"
cp -r coolercontrol-plugin/corsair-a600/. "$PLUGIN_DIR/"
find "$PLUGIN_DIR" -name __pycache__ -prune -exec rm -rf {} +
[[ -n $keep_config ]] && printf '%s\n' "$keep_config" > "$PLUGIN_DIR/config.json"
chown -R root:root "$PLUGIN_DIR"
chmod 0644 "$PLUGIN_DIR/manifest.toml"

# CoolerControl picks up new plugins on start and creates cc-plugin-$PLUGIN_ID.service.
systemctl restart coolercontrold.service

for _ in $(seq 1 20); do
    systemctl is-active --quiet "cc-plugin-$PLUGIN_ID.service" && break
    sleep 1
done
systemctl --no-pager --lines=8 status "cc-plugin-$PLUGIN_ID.service"
