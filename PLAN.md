# Current plan (2026-11-15)

Released: 6.13.1. Earlier per-release plans are in Git history; `STATE.md` holds the verified outcome of each release.

## Done in 6.13.0: parity with Fallout 4 Forge 0.1.1

Reference implementation read in place (not modified): Fallout 4 Forge `src/f4forge`, `workers/F4Forge.Records`, `tools.lock.json`.
Every item is adapted to Forge's shape: path in, JSON out, workspace-only writes behind `approved`, external processes behind
`allow_external_processes`. Tests use synthetic bytes; game files are read only by the gate run.

| # | Item | Decision | Command(s) |
|---|---|---|---|
| 1 | Records worker (Mutagen.Bethesda.Skyrim 0.54.4, the version houseCARL 2.1.1 ships) | adopt | `worker-build`, `worker-status`, `records-find/show/override/new/conflicts/overlap/validate/index` |
| 2 | Spriggit YAML round trip (Spriggit.Yaml.Skyrim, pinned CLI 0.41.0) | adopt | `spriggit-export`, `spriggit-build`, `spriggit-roundtrip` |
| 3 | PEX reader (Skyrim PEX is big-endian) + one diagnostics format for the official compiler and Caprica 0.3.0 (`-g skyrim` verified in its help) | adopt | `pex-info`, `papyrus-check` |
| 4 | NIF header/texture references + headless PyNifly round trip | adopt | `nif-info`, `nif-refs`, `nif-blender` |
| 5 | Voice: LIP generation and one-command WAV -> XWM + LIP -> FUZ (xwmaencode and LipGenerator ship with the CK) | adopt (FUZ pack already present) | `audio-encode`, `audio-lip`, `voice-generate` |
| 6 | Deploy/undeploy with a receipt, dry run unless `--approve` | adopt; CLI only | `deploy`, `undeploy` |
| 7 | Creation Kit switches read from CreationKit.exe | adopt; CLI only | `ck-info`, `ck-run` |
| 8 | Evidence tiers static / compiled / packaged / runtime | adopt | `check` |
| 9 | Deterministic package | **drop**: `release-build` uses fixed timestamps and sorted entries, `tests/test_core.py` builds twice and compares; the product ZIP is built from tracked files | - |
| 10 | Facts with tier/source/recheck command, `plan <goal>` | adopt | `facts`, `plan` |
| 11 | Nexus GraphQL v2 lookups (no key) | adopt | `nexus-mod`, `nexus-find` |
| 12 | Tool lock with asset SHA-256, receipt-owned tools root, SAFE-TOOLS verdicts, no-download second sync | adopt | `tools-sync`, `tools-lock-status` |
| 13 | Native BSA v104/v105 reader/writer with LZ4 frames | adopt | `bsa-info`, `bsa-extract`, `bsa-pack` |
| 14 | CLI contract: JSON usage errors, exit 0/1/2/3, parser-generated command list, invocation log, hygiene test | adopt | all |
| 15 | BodySlide presets/groups and INI validators; BOS quirks downgraded to warnings | adopt (BOS lint already present) | `data-validate` |

## Open

0. Put the 6.13 read-only commands (records, PEX, NIF, BSA, facts, plan, check) on the MCP surface once their CLI contract has settled.
1. Runtime proof for the commands that only have static or sandboxed evidence: a real SKSE load for `skse-inspect-pe` and `skse-audit-imports`, an MO2 and a Vortex installation for `fomod-test-install`, and one dialogue line in game for the `audio-*` commands.
2. Pin delayed expansion off in the scheduled maintenance task's `cmd.exe` action. It changes the canonical task arguments, so it needs a takeover path for tasks registered by earlier versions.

## Standing

- After each bundle update, run the ecosystem check (`.github/workflows/ecosystem.yml`, weekly and on demand) and `forge doctor` against the installed copy; a `DRIFT` row names the contract that changed.
- Never move a pin because a newer tag exists; `scripts/check_freshness.py --online` names the gate for each one.
