# Current plan (2026-11-12)

Released: 6.12.6. Earlier per-release plans are in Git history; `STATE.md` holds the verified outcome of each release.

## Open

1. Runtime proof for the commands that only have static or sandboxed evidence: a real SKSE load for `skse-inspect-pe` and `skse-audit-imports`, an MO2 and a Vortex installation for `fomod-test-install`, and one dialogue line in game for the `audio-*` commands.
2. Pin delayed expansion off in the scheduled maintenance task's `cmd.exe` action. It changes the canonical task arguments, so it needs a takeover path for tasks registered by earlier versions.

## Standing

- After each bundle update, run the ecosystem check (`.github/workflows/ecosystem.yml`, weekly and on demand) and `forge doctor` against the installed copy; a `DRIFT` row names the contract that changed.
- Never move a pin because a newer tag exists; `scripts/check_freshness.py --online` names the gate for each one.
