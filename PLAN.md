# Current plan (2026-11-03)

0. [complete] Forge 6.9.0 — whole-pack audit: single-walk tool discovery, three catalog tools, observed tool inventory, houseCARL 2.1.1 Mutagen schema and .NET 10 setup, GPL notice for houseCARL-derived skills, SkyrimForge name disambiguation.
1. [complete] Forge 6.10.0 — maintenance and moved-root detection (`forge maintain`, `forge_maintain`), README reset and the local cleanup (148 stale skill backups, 8 kept). Released from `1d01c41`; live install 6.10.0 is 579/579 with doctor PASS.
2. [complete] Forge 6.8.1 — free procedural textures plus the free-tool map. `texture-generate` writes deterministic BC1/BC3/A8R8G8B8 DDS with mip chains, six kinds and normal maps; `texture-inspect` reads any DDS; agents are routed to the typed tool. Released from `785cf51`; the live install is 6.8.1, 569/569 byte-identical, doctor PASS.
2. [complete] The contract check runs weekly (`.github/workflows/ecosystem.yml`) and on demand: bundle `skyrim-forge` catalog entry, release assets, Reverse THIS! receipts. Forge never copies either project's version.
3. [next] After each bundle auto-update, run the ecosystem check plus `forge doctor` against the live install; a `DRIFT` row names the exact contract that changed.
4. [open] Runtime proof for the new commands: a real SKSE load for `skse-inspect-pe`/`skse-audit-imports`, an MO2 and a Vortex installation for `fomod-test-install`, and one dialogue line for `audio-*`. The current evidence is static and sandboxed.

Earlier per-release plans remain in Git history; STATE.md holds the verified outcome of each release.
