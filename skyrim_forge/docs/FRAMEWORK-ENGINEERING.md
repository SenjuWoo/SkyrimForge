# Distribution and patcher framework engineering

Forge uses versioned profiles rather than one timeless parser:

- SPID 7.3
- KID 4.0.6
- BOS 3.4.1
- SkyPatcher 6.4.2 core INI shape and placement
- FLM 1.8.1 core INI shape

`framework-build` renders only modeled syntax and lints the generated file. Existing syntax outside the modeled profile must be reported as unverified or warning-level, not silently rewritten. A clean static result does not prove that FormIDs resolve or that runtime distribution occurred. Check the corresponding SKSE log.

## Runtime correlation

`forge framework-correlate-logs <mod-root> <log-dir>` matches every static finding against the SKSE logs in that directory (`po3_SpellPerkItemDistributor.log`, `po3_KeywordItemDistributor.log`, `SkyPatcher.log`, custom plugin logs). Each finding gets one status:

- `RUNTIME_ERROR` — a log line names this file and this row as an error.
- `RUNTIME_VERIFIED_PASS` — a log line names this file and this row, or names the file with a positive distribution count and no row error. A warning is marked `promoted`.
- `RUNTIME_ERROR_FILE` — the file is named in an error with no row number.
- `UNVERIFIED` — no log mentions the file.

A static error is never cleared by a runtime pass; the evidence is recorded and left for review. The matcher reads text, so it does not parse framework internals and cannot prove the log came from this exact deployed file unless you record its hash (`logs_scanned` includes one).
