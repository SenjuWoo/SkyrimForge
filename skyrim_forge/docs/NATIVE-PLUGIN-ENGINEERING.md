# Native SKSE plugin engineering

Forge generates a source-locked CommonLibSSE-NG project and requires one explicit compatibility strategy:

- Address Library
- signature scanning
- an explicit runtime-version list

The generated CMake project refuses to deploy unless `FORGE_OUTPUT_ROOT` points to a staging directory. It does not write to live Skyrim `Data`.

`native-audit` checks the CommonLib target, lifecycle entry point, runtime strategy and staging rule. `native-binary-audit` checks x86-64 PE32+ DLL structure. `native-build` requires hash-pinned CMake and vcpkg executables and builds inside the Forge workspace.

The scaffold consumes the maintained CommonLibSSE-NG checkout pinned in the SDK vault (`forge sdk-status`), not a vcpkg port; see [native source lock](NATIVE-SOURCE-LOCK.md) for the exact commit, locked dependencies and current build-proof status.

A successful compilation and PE audit are not proof that a hook is correct, that offsets are current, or that the DLL coexists with another SKSE plugin. Those require a matching runtime, logs, crash testing and gameplay evidence.

## SKSE PE workbench

`native-binary-audit` reads PE structure and imports. Three narrower commands read the SKSE contract directly, without loading the DLL:

```text
forge skse-inspect-pe <plugin.dll>
forge skse-audit-imports <plugin.dll>
forge skse-verify-reproducible <built.dll> <reference.dll>
```

`skse-inspect-pe` verifies the PE32+ x64 header, lists exports, and decodes `SKSEPlugin_Version` at the offsets CommonLibSSE-NG asserts (`0x350` bytes: data version, plugin version, name, author, support email, independence flags, compatible versions, minimum XSE version). Version words decode with `REL::Version::pack` (major<<24 | minor<<16 | patch<<4 | build). A missing export table or a non-x64 image fails the command.

`skse-audit-imports` lists every imported DLL and function and groups network, process-execution and DirectStorage imports, which is the machine-checkable half of the Nexus binary-behaviour step. It proves the import table only; dynamic resolution through `GetProcAddress` is invisible to it.

`skse-verify-reproducible` compares two DLLs byte-for-byte, then again with the linker-owned fields zeroed (COFF `TimeDateStamp`, PE `CheckSum`, debug-directory timestamps). `identical_after_timestamp_normalisation` is the claim a reproducible build can actually make without MSVC `/Brepro`; it does not prove either file matches the published source.
