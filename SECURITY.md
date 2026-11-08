# Security policy

## Supported versions

Only the [latest release](https://github.com/martinschuberteu/coolercontrol-plugin-corsair-one-a600/releases/latest) gets fixes.

## Reporting a vulnerability

Report it privately through [GitHub's vulnerability reporting](https://github.com/martinschuberteu/coolercontrol-plugin-corsair-one-a600/security/advisories/new), not in a public issue. Include what is affected, how to reproduce it and what an attacker could do.

This is a hobby project maintained in spare time: expect a reply within about two weeks. Once a fix is released, the report is published as a security advisory, with credit if you want it.

## Scope

Things worth reporting include:

- `deploy/install.sh` and `deploy/uninstall.sh`, which run as root,
- the udev rule and `corsair-a600` group giving access to more than the a600 controllers,
- the plugin (running as CoolerControl's unprivileged `cc-plugin-user`) accepting input from CoolerControl or its settings page that leads to unintended device commands, such as fan speeds below safe limits or writes outside the commands documented in `protocol-notes.md`.

Bugs in CoolerControl itself should go to the [CoolerControl project](https://gitlab.com/coolercontrol/coolercontrol).
