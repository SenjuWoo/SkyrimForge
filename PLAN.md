# Current plan (2026-10-31)

1. [complete] Forge 6.7.1 — weekly ecosystem contract check plus the 6.7.0 subsystems (audio, SKSE PE, runtime correlation, FOMOD sandbox install, MCP annotations/bounded output/compact surface, venv durability). Released from `d04432e`; the live install is 6.7.1 and `forge doctor` passes there with a stable venv base.
2. [complete] The contract check runs weekly (`.github/workflows/ecosystem.yml`) and on demand: bundle `skyrim-forge` catalog entry, release assets, Reverse THIS! receipts. Forge never copies either project's version.
3. [next] After each bundle auto-update, run the ecosystem check plus `forge doctor` against the live install; a `DRIFT` row names the exact contract that changed.
4. [open] Runtime proof for the new commands: a real SKSE load for `skse-inspect-pe`/`skse-audit-imports`, an MO2 and a Vortex installation for `fomod-test-install`, and one dialogue line for `audio-*`. The current evidence is static and sandboxed.

Earlier per-release plans remain in Git history; STATE.md holds the verified outcome of each release.
