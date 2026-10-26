# Validation - 6.2.0 source

Authority: the existing source owner, branch `codex/standalone-toolchain-6-2`; parent `efe9de1bb33babbfc3042899cd15b43a0f2bd07c` (public 6.1.1). Live tools, application/provider configuration, game Data, staging and saves remain untouched.

Observed source checks:

- `python -m unittest discover -s tests -p test_standalone_toolchain.py -v`: 19 real/offline runtime, updater and Reverse reuse fixtures PASS. They verify SHA rejection, version/Git preservation, owner-swap failure, post-swap setup rollback, private collision refusal, workspace junction preservation without copying source-only `.git`/`.venv` exclusions, edited-owner-file refusal, same-version mismatch refusal, nonzero setup-exit rollback and a held concurrent-update lock and game-target refusal before even creating its sibling lock. Private file identity is retained through successful update and rollback.
- Full repository validator Python suite: 199 tests PASS, with two documented platform skips. This includes 12 real Windows skill ownership/migration fixtures and four real child-process output acceptance fixtures.
- Pinned Go 1.23.2 test/vet/race and deterministic two-build comparison PASS; Windows native version/self-test and mirrored package-copy integrity PASS. Windows helper SHA-256 `83b33b9fd198f8dd9873b8247c42839bb5f8d26eb3ac1efe0e0add76ffedcb43`; Linux helper SHA-256 `bacb9b8085d3347a81be4f620317929c0b0cd917599692d78da990cda2a7ad36`.
- Deterministic wheel/source distribution, JSON/schema/source hygiene and dual-era MCP checks PASS. The initial full run rejected an intentional old-version fixture literal in the version sweep; fixture formatting was corrected using the existing test convention. `VALIDATION.json` records the final full result.
- The shipped Windows PowerShell parser is also exercised directly; static screening alone is not its runtime proof.

Final source command: `.venv/Scripts/python.exe scripts/validate_repository.py --scope full --write-reports`, with `SKYRIM_FORGE_GO` set to the existing pinned compiler. Final full command returned exit 0 with 199 tests (two platform skips), all selected checks PASS and no errors. Afterwards, only two stale houseCARL documentation routes were corrected to Forge's actual `Install-HouseCarl.ps1`; source/file/version checks and manifest/SBOM regeneration cover that documentation-only change without repeating unchanged code tests. No third-party executables were executed or publicly bundled.

Scope gate: source-only PASS. Plugin/Papyrus/framework/FOMOD content changes: N/A. Runtime evidence: tool-validated. SSEEdit/CK: not launched. Final public archive and exact-SHA CI/alert checks, Git publication and live installation are the parent's next phase; no final archive/hash is claimed here. GUI/game/save/animation/navmesh testing was not performed.

PR #16 CI portability correction: the initial Windows matrix exposed a lexical comparison against a resolved temporary-directory alias and Python 3.11 lacking `Path.is_junction()`. The fixture now asserts actual same-file identity and Windows reparse metadata plus the resolved target. Product code is unchanged; focused offline tests and regenerated file/version/manifest checks cover this correction locally, with the full remote matrix required on the new pushed SHA.
