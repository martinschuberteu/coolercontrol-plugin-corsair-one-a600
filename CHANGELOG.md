# Changelog

## 0.3.1 – unreleased

- Fixed: an unexpected error (for example a malformed controller reply) could end the temperature feed silently, leaving the fans at their last speed while the plugin still reported healthy. Every error is now logged and retried, and the plugin exits for a systemd restart if the feed ever stops.
- A sensor that keeps failing is logged once, not every second, and its recovery is logged.
- The NVIDIA sensor is retried every 30 s if it isn't available at start.
- On stop, the fail-safe temperature is sent first, before the rest of the shutdown.
- udev rule and group cover only the cooling controller.
- Tests for the feed loop.

## 0.3.0 – 2026-11-08

- First public release.
- Fans only: the plugin now handles just the cooling controller.

Earlier versions were never released publicly.

## 0.2.0 – 2026-11-01

- Follow CoolerControl's log level (`CC_LOG`).
- Create the plugin socket owner-only, so other local users cannot drive the hardware through its unauthenticated gRPC API.
- Homepage link in the manifest (shown on CoolerControl's plugin page).
- Protocol encoding/decoding split into pure functions, with unit tests built from packets recorded from Corsair Dashboard.
- `deploy/uninstall.sh`, GPL-3.0-or-later licence, CI.

## 0.1.1

- Pumps report their speed as a percentage of their nominal 3000 rpm, so CoolerControl graphs them.
- Settings page follows the CoolerControl theme.
- Log why the cooling controller cannot be opened.

## 0.1.0

- First version: temperature feed for Corsair's Quiet/Balanced curves, fan and pump monitoring, settings page.
