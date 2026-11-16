# Capability matrix

Forge distinguishes evidence levels so an AI cannot turn a configured adapter into a false claim of implementation.

| Capability | Level | Status | Boundary |
|---|---|---|---|
| Verified local toolchain | Direct/Profiled | Implemented | Recursive directory/ZIP discovery, private vault import, SHA-256 pins, exact capability match; no public binary bundling |
| BSArch BSA/BA2 | Direct | Implemented | Official BSArch contract for inspect/unpack/SSE pack; configured executable required |
| Champollion/Synthesis CLI/DeadMesh CLI | Adapter | Implemented | Exact executable identity and hash pin required; GUI substitutes rejected |
| Plugin header/query | Direct | Implemented | Forge parser evidence, not xEdit/runtime |
| Load order, record winners, SEQ | Direct | Implemented | Plugin bytes without a field schema; houseCARL remains primary, parity map in `HOUSECARL-PARITY.md` |
| Typed KYWD/GLOB/FLST/OTFT output | Direct | Implemented | No arbitrary record writing |
| SPID/KID/BOS/SkyPatcher/FLM lint/build | Profiled | Implemented | Modeled source-locked subsets; unknown syntax is unverified, not rewritten |
| Papyrus analysis | Profiled | Implemented | Performance findings are review heuristics |
| Architecture recommendation | Direct | Implemented | Keyword/constraint routing; installed frameworks and runtime compatibility remain unverified |
| Skyrim source/API registry | Direct | Implemented | Curated URLs and local probes; DETECTED is not a version or signature proof |
| Mod quality gate | Direct | Implemented | Selects applicable dimensions and refuses PASS without hash-verified tool receipts; no single score |
| Performance comparison | Direct | Implemented | Explicit metric and process; frame-time arithmetic over matching captures; no capture, visual or FPS guarantee |
| Papyrus compile | Adapter | Implemented | Pinned official compiler; fresh PEX is not runtime proof |
| CommonLibSSE-NG scaffold | Profiled | Implemented | Source-locked project generation |
| SKSE PE inspection | Direct | Implemented | Exports, `SKSEPlugin_Version`, imports, timestamp-normalised reproducibility; not a load or hook proof |
| Maintenance | Direct | Implemented | Forge-owned spill/sandbox/skill-backup cleanup, moved-root detection, self-test; never touches mods or tools |
| Procedural textures | Direct | Implemented | DDS BC1/BC3/A8R8G8B8 with mip chains, six procedural kinds, tangent-space normals, PNG preview; placeholders, not art direction |
| Audio containers | Direct | Implemented | FUZ/XWM/WAV/LIP inspect, split, pack, voice layout |
| Voice generation | Adapter | Implemented | WAV -> XWM (xwmaencode) + LIP (LipGenerator) -> FUZ with the Creation Kit's own tools; playback and timing not tested |
| Native BSA archives | Direct | Implemented | BSA 104/105 read, extract, pack with LZ4/zlib; re-serializes installed archives byte-identical; no game load test |
| PEX reader and Papyrus diagnostics | Direct | Implemented | One 1-based diagnostics format for the official compiler and Caprica; bytecode not disassembled |
| NIF meshes | Direct | Implemented | Header, blocks, texture-set references; headless PyNifly import/export; effect-shader textures not listed |
| Records worker (Mutagen) | Adapter | Implemented | Forge-built .NET worker: find, show, override, new QUST with script, conflicts, overlap, EditorID index, validate; workspace plugin writes only |
| Spriggit YAML | Adapter | Implemented | Pinned Spriggit 0.41.0; record-equal round trip, not byte-equal |
| Deploy / undeploy | Direct | Implemented | CLI only; receipt-owned writes into Data or a mod folder with --approve; exact undo |
| Creation Kit jobs | Adapter | Implemented | CLI only; switches read from CreationKit.exe; dry run until --approve; receipt of files written |
| Evidence tiers (`check`) | Direct | Implemented | static / compiled / packaged reported; runtime always NOT RUN |
| Facts, routes, Nexus lookup | Direct | Implemented | Tiered facts with recheck commands; verified Nexus IDs; public GraphQL, read-only |
| Tool lock | Direct | Implemented | SHA-256-pinned release assets, receipt-owned tools root, identical existing copies reused |
| Framework runtime correlation | Direct | Implemented | Log text matched to file and row; static errors are never cleared |
| Native build | Adapter | Implemented | Pinned local build tools; workspace staging only |
| FOMOD XML | Profiled | Implemented | Declarative ModuleConfig only; arbitrary C# blocked |
| xEdit/MO2 | Adapter | Implemented | Installed pinned tools required |
| CK/Wrye/LOOT/assets/animations/LOD | Worker contract | Adapter only | Compatible pinned worker required |
| Nexus publication | Human gate | Implemented | Machine evidence plus uploader attestation; not legal authentication |
| Skyrim runtime/visual/save/gameplay | Human gate | Required | Must be tested in the game |
| Generic navmesh/worldspace/landscape binary editing | Unsupported | Blocked | Specialist editor and human verification required |
