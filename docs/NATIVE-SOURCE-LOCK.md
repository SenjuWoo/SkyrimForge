# Native source lock

Forge native project generation is pinned to the maintained [alandtse/CommonLibSSE-NG](https://github.com/alandtse/CommonLibSSE-NG) `ng` lineage (v14.1.0, commit `896f6d0`), its dependency manifest and the vcpkg registry baseline in `references/NATIVE-SOURCE-LOCK.json`. The same commit is pinned in `references/SDK-LOCK.json`; a test fails if the two disagree.

A generated project is not a finished DLL mod. Publication requires:

1. A hash-pinned build toolchain.
2. A successful clean build into Forge staging.
3. PE x64 DLL inspection.
4. Runtime launch on every declared Skyrim/SKSE target.
5. SKSE log and crash-log review.
6. Coexistence testing with relevant native hooks.
7. Nexus rights, source, licence, and third-party-notice review.

Forge refuses to infer compatibility from compilation alone.

## SDK vault (maintained CommonLibSSE-NG)

`references/SDK-LOCK.json` pins the SDK sources an AI needs to write or rework a native plugin, each by full commit SHA: the maintained [alandtse/CommonLibSSE-NG](https://github.com/alandtse/CommonLibSSE-NG) `ng` lineage (v14.1.0, SE+AE+VR), vcpkg, and optional reference lineages (libxse/commonlibsse, powerof3/CommonLibSSE `dev`, the libxse NG template). `forge sdk-status` reports each as `absent`, `current`, `modified`, `mismatch`, `incomplete` or `unknown`; `forge sdk-install [ids] [--all] --approve` fetches missing ones into `<tool vault parent>/sdk-vault`, verifies the fetched HEAD equals the pin, and refuses to overwrite a directory that is not the clean pinned commit. `--bootstrap` additionally runs vcpkg's own bootstrap script once. Installation is CLI-only by design: the MCP surface reports SDK state through `forge_toolchain_status` but cannot download. Public releases carry no SDK source.

`native-scaffold` generates a CMake project that consumes the vault copy with `add_subdirectory(${COMMONLIBSSE_NG_ROOT})` (tests off, `add_commonlibsse_plugin` included explicitly because a source build does not define it) and a vcpkg manifest listing the dependencies locked here. `native-build` passes `-DCOMMONLIBSSE_NG_ROOT` only when the vault checkout is the clean pinned commit, imports the Visual C++ x64 environment so Ninja finds `cl.exe` outside a Developer shell, and allows at least 3600 seconds because a cold library build takes about sixteen minutes. The superseded colorglass/CharmedBaryon lineage is no longer generated; `native-audit` warns (does not fail) on a project that still resolves it, so old plugins can still be audited and reworked.

**Build proof (2026-10-27, Windows 11, MSVC 19.51.36260.0, CMake 4.5.0-rc1, Ninja, vcpkg 2026.10.16):** a Forge-scaffolded probe plugin configured and compiled 525/525 steps with zero compiler errors against the pinned vault checkout, installed the 11 locked dependencies under `x64-windows-static-md` from the baseline registry, and produced `SKSE/Plugins/ForgeProbePlugin.dll` (551,936 bytes) that exports `SKSEPlugin_Load`, `SKSEPlugin_Query` and `SKSEPlugin_Version`, imports only Windows and CRT DLLs, and passes `native-binary-audit` as an x64 PE32+ DLL. The build was run by hand with the arguments `native-build` assembles, because Forge's `allow_external_processes` switch was off; `native-build` itself, including its imported Visual C++ environment, has not been run end to end. No DLL was loaded in Skyrim.
