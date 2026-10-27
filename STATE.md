# Skyrim Forge 6.2.0 verified release handoff

- Goal: standalone Skyrim tools and skills with shared-runtime/tool reuse, preserving private work, source edits and project pins.
- Owner: this Git checkout; its historical folder name is not the product version. Active/public version: 6.2.0. Release source/tag: aefa1a2d222801a4953e6fe39b65983750dc7997. Previous public rollback baseline: 6.1.1; Git tags and retained deployment backups preserve it.
- Published: https://github.com/SenjuWoo/SkyrimForge/releases/tag/v6.2.0 . PRs #16/#17 and exact merged-SHA CI/security passed. Release workflow 40421709024 succeeded on attempt two after a transient HTTP-500 draft failure; the tag was unchanged. All eight public assets were downloaded and checked against GitHub digests and SHA256SUMS.
- Public ZIP: 5,137,601 bytes; SHA256 2c66c6bdf79473a68e95b749e12489e0fa14db876cc583184e77b20370d1b175.
- Done: distinct skyrim-tooling-stack namespace with digest-proven legacy migration; shared Python resolution; protected standalone source updates/locking/rollback/private-tree moves; owner-bound Reverse texconv/7-Zip reuse; CLI output acceptance; supplied CLibDT GUI discovery and exact CommonLib build-route documentation. Reference binaries/libraries were not executed or copied into releases.
- Verification: full local validator and exact source/main/release CI passed, including Python/native/Go/race/reproducibility/packaging/MCP/version checks. Current checkout's report refresh is documentation-only; product code is unchanged from the verified release.
- Source implementation/publication remaining: none. Cross-product machine deployment and provider proof belong to the Starter Bundle's STATE.md; do not infer installed version or runtime success from this source file.
- Companion ownership: Starter Bundle owns general AI/build tools, including Xmake; Reverse THIS! owns analysis payloads. Each product runs independently and only its owner writes its receipts.
- Build/test: .venv/Scripts/python.exe scripts/validate_repository.py --scope full --write-reports ; pinned native compiler is Go 1.23.2.
- Run: START-HERE.bat . Source update: Update-Forge.ps1 ; the bundle uses -Root <installed-root> -SourceDir <verified-source> -SkipSetup.
- Logs: %LOCALAPPDATA%/Skyrim-Forge/logs; SKYRIM_FORGE_DEBUG=1 enables detail. Owner update failures and backup paths are recorded in owner-update.log.
- Runtime limit: tool-validated; GUI/game/editor behavior is not certified. Use the installed owner doctor and task-specific samples before claiming runtime readiness.
