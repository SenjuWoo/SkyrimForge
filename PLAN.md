# Current plan (2026-10-31)

1. [complete] Forge 6.7.0 — audio containers, SKSE PE workbench, runtime log correlation, FOMOD sandbox install, MCP annotations/bounded output/compact surface, venv durability. Released from `7d8b2c6`; the bundle's auto-update moved the live install to 6.7.0 and `forge doctor` passes there with a stable venv base.
2. [complete] Weekly ecosystem contract check — `scripts/check_ecosystem.py` and `.github/workflows/ecosystem.yml` verify the bundle's `skyrim-forge` catalog entry, this repository's release assets, and Reverse THIS!'s `kit.json`/`installed.json` shape. Forge never copies either project's version.
3. [next] After each bundle auto-update, run the ecosystem check plus `forge doctor` against the live install; a `DRIFT` row names the exact contract that changed.
4. [open] Runtime proof for the new commands: a real SKSE load for `skse-inspect-pe`/`skse-audit-imports`, an MO2 and a Vortex installation for `fomod-test-install`, and one dialogue line for `audio-*`. The current evidence is static and sandboxed.

Earlier per-release plans remain in Git history; STATE.md holds the verified outcome of each release.
