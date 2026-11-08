# Contributing

Bug reports and pull requests are welcome. Ask questions and suggest ideas with the *Question or idea* issue form; report security problems through [private reporting](SECURITY.md).

## Safety first

This plugin controls the cooling of a running PC.

- Only send commands that Corsair Dashboard was seen sending (see [protocol-notes.md](protocol-notes.md) and [docs/capturing.md](docs/capturing.md)). New commands need a capture that shows them.
- Keep the fail-safe: when a temperature can't be read or the plugin stops, the controller must get a high temperature so the fans speed up.
- Custom curves and the flash commit are deliberately not implemented; don't add them without understanding the behaviour described in the protocol notes.
- Test changes on the hardware while watching temperatures (`python3 tools/a600_status.py`).

## Before a pull request

```bash
python3 -m unittest discover -s tests
coolercontrol-plugin/generate.sh      # only if proto/ changed; commit the regenerated gen/
```

CI runs the tests, checks that `gen/` matches `proto/` and checks the shell scripts. Note in the pull request which hardware and CoolerControl version you tested with.
