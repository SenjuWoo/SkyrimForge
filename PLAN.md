# Current plan (2026-10-31)

1. [complete] Forge 6.7.3 — install audit plus bounded backup retention. The live install was proven byte-identical to each release (567/567), and `Update-Forge.ps1` now prunes Forge-owned backups to the newest two and ages failed stages out after seven days (`pruned=<n>` in the owner-update log). Released from `1e1f89c`; the live install is 6.7.3 with doctor PASS.
2. [complete] The contract check runs weekly (`.github/workflows/ecosystem.yml`) and on demand: bundle `skyrim-forge` catalog entry, release assets, Reverse THIS! receipts. Forge never copies either project's version.
3. [next] After each bundle auto-update, run the ecosystem check plus `forge doctor` against the live install; a `DRIFT` row names the exact contract that changed.
4. [open] Runtime proof for the new commands: a real SKSE load for `skse-inspect-pe`/`skse-audit-imports`, an MO2 and a Vortex installation for `fomod-test-install`, and one dialogue line for `audio-*`. The current evidence is static and sandboxed.

Earlier per-release plans remain in Git history; STATE.md holds the verified outcome of each release.
