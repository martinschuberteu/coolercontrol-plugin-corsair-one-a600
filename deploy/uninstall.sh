#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Remove the Corsair ONE a600 CoolerControl plugin. Run with: sudo bash deploy/uninstall.sh
#
# Leaves CoolerControl's own cc-plugin-user in place (other plugins may use it).
# The fans keep the last temperatures the plugin sent until something else (or a
# reboot into Corsair Dashboard) feeds the controller again.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }

PLUGIN_ID=corsair-a600

rm -rf "/var/lib/coolercontrol/plugins/$PLUGIN_ID"
# CoolerControl removes cc-plugin-$PLUGIN_ID.service itself once the plugin folder is gone.
systemctl restart coolercontrold.service

gpasswd -d cc-plugin-user corsair-a600 2>/dev/null || true
rm -f /etc/udev/rules.d/70-corsair-a600.rules /etc/sysusers.d/corsair-a600.conf
udevadm control --reload
udevadm trigger --subsystem-match=hidraw --action=change
groupdel corsair-a600 2>/dev/null || true
rm -f "/tmp/$PLUGIN_ID.sock"

echo "Corsair ONE a600 plugin removed."
